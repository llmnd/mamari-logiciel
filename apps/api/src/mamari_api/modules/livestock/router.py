import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import case, extract, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mamari_api.core.config import get_settings
from mamari_api.modules.agriculture.models import Farm, FinanceTransaction
from mamari_api.modules.audit.service import record_audit_event
from mamari_api.modules.identity.dependencies import (
    CurrentMembership,
    SessionDep,
    get_current_membership,
    require_roles,
)
from mamari_api.modules.livestock.models import (
    LivestockAnimal,
    LivestockFacility,
    LivestockFinanceTransaction,
    LivestockGroup,
    LivestockRecord,
)
from mamari_api.modules.livestock.schemas import (
    AnimalResponse,
    CreateAnimalRequest,
    CreateFacilityRequest,
    CreateGroupRequest,
    CreateLivestockFinanceTransactionRequest,
    CreateRecordRequest,
    FacilityResponse,
    GroupResponse,
    LivestockFinanceSummaryResponse,
    LivestockFinanceTransactionPageResponse,
    LivestockFinanceTransactionResponse,
    LivestockOverviewResponse,
    MonthlyLivestockFinanceResponse,
    MonthlyProductionTotal,
    RecordResponse,
    UpcomingCareResponse,
)
from mamari_api.modules.stocks.service import (
    get_or_create_production_item,
    record_stock_movement,
)

router = APIRouter(prefix="/livestock")
CurrentOrganizationDep = Annotated[CurrentMembership, Depends(get_current_membership)]
CanManageLivestockDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager")),
]
CanOperateLivestockDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager", "operator")),
]
CanViewLivestockFinanceDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager")),
]

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MONTH_LABELS = (
    "Jan",
    "Fév",
    "Mar",
    "Avr",
    "Mai",
    "Juin",
    "Juil",
    "Août",
    "Sep",
    "Oct",
    "Nov",
    "Déc",
)
PHOTO_TYPES = {
    "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/png": (".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/webp": (
        ".webp",
        lambda data: data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    ),
}


def _photo_path(organization_id: uuid.UUID, filename: str) -> Path:
    if Path(filename).name != filename or Path(filename).suffix not in {".jpg", ".png", ".webp"}:
        raise HTTPException(status_code=404, detail="Photo introuvable.")
    return get_settings().upload_directory / "livestock" / str(organization_id) / filename


async def _store_photo(
    organization_id: uuid.UUID,
    photo: UploadFile,
) -> tuple[str, Path]:
    content = await photo.read(MAX_PHOTO_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Le fichier photo est vide.")
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="La photo ne doit pas dépasser 5 Mo.")
    photo_type = PHOTO_TYPES.get(photo.content_type or "")
    if photo_type is None or not photo_type[1](content):
        raise HTTPException(
            status_code=415,
            detail="Format photo invalide. Utilisez une image JPEG, PNG ou WebP.",
        )
    filename = f"{uuid.uuid4().hex}{photo_type[0]}"
    path = _photo_path(organization_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, content)
    return filename, path


async def _facility_response(
    session: AsyncSession,
    facility: LivestockFacility,
) -> FacilityResponse:
    farm_name = None
    if facility.farm_id is not None:
        farm_name = await session.scalar(
            select(Farm.name).where(
                Farm.id == facility.farm_id,
                Farm.organization_id == facility.organization_id,
            )
        )
    return FacilityResponse(
        id=facility.id,
        name=facility.name,
        facility_type=facility.facility_type,
        farm_id=facility.farm_id,
        farm_name=farm_name,
        location=facility.location,
        photo_url=f"/livestock/facilities/{facility.id}/photo" if facility.photo_filename else None,
        is_active=facility.is_active,
        created_at=facility.created_at,
    )


async def _animal_response(session: AsyncSession, animal: LivestockAnimal) -> AnimalResponse:
    facility_name = None
    group_name = None
    if animal.facility_id is not None:
        facility_name = await session.scalar(
            select(LivestockFacility.name).where(
                LivestockFacility.id == animal.facility_id,
                LivestockFacility.organization_id == animal.organization_id,
            )
        )
    if animal.group_id is not None:
        group_name = await session.scalar(
            select(LivestockGroup.name).where(
                LivestockGroup.id == animal.group_id,
                LivestockGroup.organization_id == animal.organization_id,
            )
        )
    return AnimalResponse(
        id=animal.id,
        name=animal.name,
        tag_number=animal.tag_number,
        species=animal.species,
        breed=animal.breed,
        sex=animal.sex,
        facility_id=animal.facility_id,
        facility_name=facility_name,
        group_id=animal.group_id,
        group_name=group_name,
        birth_date=animal.birth_date,
        entry_date=animal.entry_date,
        photo_url=f"/livestock/animals/{animal.id}/photo" if animal.photo_filename else None,
        notes=animal.notes,
        status=animal.status,
        created_at=animal.created_at,
    )


async def _record_response(
    session: AsyncSession,
    record: LivestockRecord,
    *,
    include_financials: bool = True,
) -> RecordResponse:
    animal_name = None
    group_name = None
    facility_name = None
    finance_transaction_created = include_financials and record.amount_fcfa > 0
    if record.animal_id is not None:
        animal_result = await session.execute(
            select(LivestockAnimal.name, LivestockAnimal.tag_number).where(
                LivestockAnimal.id == record.animal_id,
                LivestockAnimal.organization_id == record.organization_id,
            )
        )
        animal_row = animal_result.one_or_none()
        if animal_row is not None:
            animal_name = animal_row.name or animal_row.tag_number
    if record.group_id is not None:
        group_name = await session.scalar(
            select(LivestockGroup.name).where(
                LivestockGroup.id == record.group_id,
                LivestockGroup.organization_id == record.organization_id,
            )
        )
    if record.facility_id is not None:
        facility_name = await session.scalar(
            select(LivestockFacility.name).where(
                LivestockFacility.id == record.facility_id,
                LivestockFacility.organization_id == record.organization_id,
            )
        )
    return RecordResponse(
        id=record.id,
        record_type=record.record_type,
        category=record.category,
        title=record.title,
        event_date=record.event_date,
        animal_id=record.animal_id,
        animal_name=animal_name,
        group_id=record.group_id,
        group_name=group_name,
        facility_id=record.facility_id,
        facility_name=facility_name,
        quantity=record.quantity,
        unit=record.unit,
        amount_fcfa=record.amount_fcfa if include_financials else None,
        finance_transaction_created=finance_transaction_created,
        next_due_date=record.next_due_date,
        is_resolved=record.is_resolved,
        notes=record.notes,
        created_at=record.created_at,
    )


async def _livestock_finance_response(
    session: AsyncSession,
    transaction: LivestockFinanceTransaction,
) -> LivestockFinanceTransactionResponse:
    animal_name = None
    group_name = None
    facility_name = None
    if transaction.animal_id is not None:
        animal_result = await session.execute(
            select(LivestockAnimal.name, LivestockAnimal.tag_number).where(
                LivestockAnimal.id == transaction.animal_id,
                LivestockAnimal.organization_id == transaction.organization_id,
            )
        )
        animal = animal_result.one_or_none()
        if animal is not None:
            animal_name = animal.name or animal.tag_number
    if transaction.group_id is not None:
        group_name = await session.scalar(
            select(LivestockGroup.name).where(
                LivestockGroup.id == transaction.group_id,
                LivestockGroup.organization_id == transaction.organization_id,
            )
        )
    if transaction.facility_id is not None:
        facility_name = await session.scalar(
            select(LivestockFacility.name).where(
                LivestockFacility.id == transaction.facility_id,
                LivestockFacility.organization_id == transaction.organization_id,
            )
        )
    return LivestockFinanceTransactionResponse(
        id=transaction.id,
        transaction_type=transaction.transaction_type,
        category=transaction.category,
        label=transaction.label,
        amount_fcfa=transaction.amount_fcfa,
        transaction_date=transaction.transaction_date,
        animal_id=transaction.animal_id,
        animal_name=animal_name,
        group_id=transaction.group_id,
        group_name=group_name,
        facility_id=transaction.facility_id,
        facility_name=facility_name,
        quantity=transaction.quantity,
        unit=transaction.unit,
        notes=transaction.notes,
        created_at=transaction.created_at,
    )


@router.get("/overview", response_model=LivestockOverviewResponse)
async def read_livestock_overview(
    session: SessionDep,
    context: CurrentOrganizationDep,
) -> LivestockOverviewResponse:
    organization_id = context.organization.id
    today = date.today()
    week_end = today + timedelta(days=7)
    animal_count = await session.scalar(
        select(func.count())
        .select_from(LivestockAnimal)
        .where(
            LivestockAnimal.organization_id == organization_id,
            LivestockAnimal.status == "active",
        )
    )
    animal_breakdown = await session.execute(
        select(
            func.count(func.distinct(LivestockAnimal.species)),
            func.coalesce(
                func.sum(case((LivestockAnimal.sex == "female", 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((LivestockAnimal.sex == "male", 1), else_=0)),
                0,
            ),
        ).where(
            LivestockAnimal.organization_id == organization_id,
            LivestockAnimal.status == "active",
        )
    )
    species_count, female_animal_count, male_animal_count = animal_breakdown.one()
    group_count = await session.scalar(
        select(func.count())
        .select_from(LivestockGroup)
        .where(
            LivestockGroup.organization_id == organization_id,
            LivestockGroup.is_active.is_(True),
        )
    )
    group_head_count = await session.scalar(
        select(func.coalesce(func.sum(LivestockGroup.head_count), 0)).where(
            LivestockGroup.organization_id == organization_id,
            LivestockGroup.is_active.is_(True),
        )
    )
    facility_count = await session.scalar(
        select(func.count())
        .select_from(LivestockFacility)
        .where(
            LivestockFacility.organization_id == organization_id,
            LivestockFacility.is_active.is_(True),
        )
    )
    health_follow_up_count = await session.scalar(
        select(func.count())
        .select_from(LivestockRecord)
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "health",
            LivestockRecord.is_resolved.is_(False),
            LivestockRecord.next_due_date.is_not(None),
            LivestockRecord.next_due_date <= today,
        )
    )
    health_record_count = await session.scalar(
        select(func.count())
        .select_from(LivestockRecord)
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "health",
        )
    )
    care_due_soon_count = await session.scalar(
        select(func.count())
        .select_from(LivestockRecord)
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "health",
            LivestockRecord.is_resolved.is_(False),
            LivestockRecord.next_due_date > today,
            LivestockRecord.next_due_date <= week_end,
        )
    )
    upcoming_care_count = await session.scalar(
        select(func.count())
        .select_from(LivestockRecord)
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "health",
            LivestockRecord.is_resolved.is_(False),
            LivestockRecord.next_due_date.is_not(None),
            LivestockRecord.next_due_date <= week_end,
        )
    )
    upcoming_records = await session.execute(
        select(LivestockRecord, LivestockAnimal, LivestockGroup)
        .outerjoin(
            LivestockAnimal,
            (LivestockAnimal.organization_id == LivestockRecord.organization_id)
            & (LivestockAnimal.id == LivestockRecord.animal_id),
        )
        .outerjoin(
            LivestockGroup,
            (LivestockGroup.organization_id == LivestockRecord.organization_id)
            & (LivestockGroup.id == LivestockRecord.group_id),
        )
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "health",
            LivestockRecord.is_resolved.is_(False),
            LivestockRecord.next_due_date.is_not(None),
            LivestockRecord.next_due_date <= week_end,
        )
        .order_by(LivestockRecord.next_due_date, LivestockRecord.created_at.desc())
        .limit(8)
    )
    upcoming_rows = upcoming_records.all()
    production_month_start = date(today.year, today.month, 1)
    if today.month == 12:
        production_month_end = date(today.year + 1, 1, 1)
    else:
        production_month_end = date(today.year, today.month + 1, 1)
    production_totals = await session.execute(
        select(
            func.coalesce(func.sum(LivestockRecord.quantity), 0),
            LivestockRecord.unit,
        )
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "production",
            LivestockRecord.event_date >= production_month_start,
            LivestockRecord.event_date < production_month_end,
        )
        .group_by(LivestockRecord.unit)
        .order_by(LivestockRecord.unit)
    )
    production_month_count = await session.scalar(
        select(func.count())
        .select_from(LivestockRecord)
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "production",
            LivestockRecord.event_date >= production_month_start,
            LivestockRecord.event_date < production_month_end,
        )
    )
    reproduction_month_count = await session.scalar(
        select(func.count())
        .select_from(LivestockRecord)
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "reproduction",
            LivestockRecord.event_date >= production_month_start,
            LivestockRecord.event_date < production_month_end,
        )
    )
    reproduction_totals = await session.execute(
        select(
            func.coalesce(func.sum(LivestockRecord.quantity), 0),
            LivestockRecord.unit,
        )
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "reproduction",
            LivestockRecord.event_date >= production_month_start,
            LivestockRecord.event_date < production_month_end,
            LivestockRecord.quantity.is_not(None),
        )
        .group_by(LivestockRecord.unit)
        .order_by(LivestockRecord.unit)
    )
    feed_totals = await session.execute(
        select(
            func.coalesce(func.sum(LivestockRecord.quantity), 0),
            LivestockRecord.unit,
        )
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "feed",
            LivestockRecord.event_date >= production_month_start,
            LivestockRecord.event_date < production_month_end,
        )
        .group_by(LivestockRecord.unit)
        .order_by(LivestockRecord.unit)
    )
    feed_month_count = await session.scalar(
        select(func.count())
        .select_from(LivestockRecord)
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "feed",
            LivestockRecord.event_date >= production_month_start,
            LivestockRecord.event_date < production_month_end,
        )
    )
    feed_month_cost = await session.scalar(
        select(func.coalesce(func.sum(LivestockRecord.amount_fcfa), 0)).where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "feed",
            LivestockRecord.event_date >= production_month_start,
            LivestockRecord.event_date < production_month_end,
        )
    )
    return LivestockOverviewResponse(
        animal_count=animal_count or 0,
        female_animal_count=female_animal_count or 0,
        male_animal_count=male_animal_count or 0,
        species_count=species_count or 0,
        group_count=group_count or 0,
        group_head_count=group_head_count or 0,
        facility_count=facility_count or 0,
        health_record_count=health_record_count or 0,
        health_follow_up_count=health_follow_up_count or 0,
        upcoming_care_count=upcoming_care_count or 0,
        care_due_soon_count=care_due_soon_count or 0,
        production_month_count=production_month_count or 0,
        production_month_totals=[
            MonthlyProductionTotal(quantity=quantity or Decimal("0"), unit=unit)
            for quantity, unit in production_totals.all()
        ],
        reproduction_month_count=reproduction_month_count or 0,
        reproduction_month_totals=[
            MonthlyProductionTotal(quantity=quantity or Decimal("0"), unit=unit)
            for quantity, unit in reproduction_totals.all()
        ],
        feed_month_count=feed_month_count or 0,
        feed_month_totals=[
            MonthlyProductionTotal(quantity=quantity or Decimal("0"), unit=unit)
            for quantity, unit in feed_totals.all()
        ],
        feed_month_cost_fcfa=(
            (feed_month_cost or 0)
            if context.membership.role in {"owner", "admin", "manager"}
            else None
        ),
        upcoming_care=[
            UpcomingCareResponse(
                id=record.id,
                title=record.title,
                due_date=record.next_due_date,
                animal_name=(animal.name or animal.tag_number) if animal is not None else None,
                group_name=group.name if group is not None else None,
                category=record.category,
                overdue=record.next_due_date < today,
            )
            for record, animal, group in upcoming_rows
        ],
    )


@router.get("/facilities", response_model=list[FacilityResponse])
async def list_facilities(
    session: SessionDep,
    context: CurrentOrganizationDep,
) -> list[FacilityResponse]:
    facilities = await session.scalars(
        select(LivestockFacility)
        .where(
            LivestockFacility.organization_id == context.organization.id,
            LivestockFacility.is_active.is_(True),
        )
        .order_by(LivestockFacility.name)
    )
    return [await _facility_response(session, facility) for facility in facilities]


@router.post(
    "/facilities",
    response_model=FacilityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_facility(
    data: CreateFacilityRequest,
    session: SessionDep,
    context: CanOperateLivestockDep,
) -> FacilityResponse:
    if data.farm_id is not None:
        farm_exists = await session.scalar(
            select(Farm.id).where(
                Farm.id == data.farm_id,
                Farm.organization_id == context.organization.id,
                Farm.is_active.is_(True),
            )
        )
        if farm_exists is None:
            raise HTTPException(status_code=404, detail="Ferme introuvable ou archivée.")
    facility = LivestockFacility(
        organization_id=context.organization.id,
        created_by_id=context.user.id,
        **data.model_dump(),
    )
    session.add(facility)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Un bâtiment porte déjà ce nom.") from error
    await session.refresh(facility)
    return await _facility_response(session, facility)


@router.post("/facilities/{facility_id}/photo", response_model=FacilityResponse)
async def upload_facility_photo(
    facility_id: uuid.UUID,
    session: SessionDep,
    context: CanOperateLivestockDep,
    photo: Annotated[UploadFile, File()],
) -> FacilityResponse:
    facility = await session.scalar(
        select(LivestockFacility).where(
            LivestockFacility.id == facility_id,
            LivestockFacility.organization_id == context.organization.id,
        )
    )
    if facility is None:
        raise HTTPException(status_code=404, detail="Bâtiment introuvable.")
    filename, path = await _store_photo(context.organization.id, photo)
    old_filename = facility.photo_filename
    facility.photo_filename = filename
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        path.unlink(missing_ok=True)
        raise
    if old_filename:
        _photo_path(context.organization.id, old_filename).unlink(missing_ok=True)
    await session.refresh(facility)
    return await _facility_response(session, facility)


@router.get("/facilities/{facility_id}/photo")
async def read_facility_photo(
    facility_id: uuid.UUID,
    session: SessionDep,
    context: CurrentOrganizationDep,
):
    filename = await session.scalar(
        select(LivestockFacility.photo_filename).where(
            LivestockFacility.id == facility_id,
            LivestockFacility.organization_id == context.organization.id,
        )
    )
    if filename is None:
        raise HTTPException(status_code=404, detail="Photo introuvable.")
    path = _photo_path(context.organization.id, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Photo introuvable.")
    return FileResponse(path)


@router.get("/groups", response_model=list[GroupResponse])
async def list_groups(
    session: SessionDep,
    context: CurrentOrganizationDep,
) -> list[GroupResponse]:
    rows = await session.execute(
        select(LivestockGroup, LivestockFacility.name)
        .outerjoin(
            LivestockFacility,
            (LivestockFacility.organization_id == LivestockGroup.organization_id)
            & (LivestockFacility.id == LivestockGroup.facility_id),
        )
        .where(
            LivestockGroup.organization_id == context.organization.id,
            LivestockGroup.is_active.is_(True),
        )
        .order_by(LivestockGroup.species, LivestockGroup.name)
    )
    return [
        GroupResponse(
            id=group.id,
            name=group.name,
            species=group.species,
            breed=group.breed,
            facility_id=group.facility_id,
            facility_name=facility_name,
            head_count=group.head_count,
            entry_date=group.entry_date,
            notes=group.notes,
            is_active=group.is_active,
            created_at=group.created_at,
        )
        for group, facility_name in rows.all()
    ]


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    data: CreateGroupRequest,
    session: SessionDep,
    context: CanOperateLivestockDep,
) -> GroupResponse:
    if data.facility_id is not None:
        facility = await session.scalar(
            select(LivestockFacility).where(
                LivestockFacility.id == data.facility_id,
                LivestockFacility.organization_id == context.organization.id,
                LivestockFacility.is_active.is_(True),
            )
        )
        if facility is None:
            raise HTTPException(status_code=404, detail="Bâtiment introuvable ou inactif.")
    group = LivestockGroup(
        organization_id=context.organization.id,
        created_by_id=context.user.id,
        **data.model_dump(),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    facility_name = None
    if group.facility_id:
        facility_name = await session.scalar(
            select(LivestockFacility.name).where(LivestockFacility.id == group.facility_id)
        )
    return GroupResponse(
        id=group.id,
        name=group.name,
        species=group.species,
        breed=group.breed,
        facility_id=group.facility_id,
        facility_name=facility_name,
        head_count=group.head_count,
        entry_date=group.entry_date,
        notes=group.notes,
        is_active=group.is_active,
        created_at=group.created_at,
    )


@router.get("/animals", response_model=list[AnimalResponse])
async def list_animals(
    session: SessionDep,
    context: CurrentOrganizationDep,
    search: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    species: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
    animal_status: Annotated[
        str, Query(alias="status", pattern="^(active|sold|deceased)$")
    ] = "active",
) -> list[AnimalResponse]:
    filters = [
        LivestockAnimal.organization_id == context.organization.id,
        LivestockAnimal.status == animal_status,
    ]
    if species:
        filters.append(LivestockAnimal.species == species)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                LivestockAnimal.name.ilike(pattern),
                LivestockAnimal.tag_number.ilike(pattern),
                LivestockAnimal.species.ilike(pattern),
                LivestockAnimal.breed.ilike(pattern),
            )
        )
    animals = await session.scalars(
        select(LivestockAnimal)
        .where(*filters)
        .order_by(LivestockAnimal.species, LivestockAnimal.name, LivestockAnimal.tag_number)
        .limit(200)
    )
    return [await _animal_response(session, animal) for animal in animals]


@router.post("/animals", response_model=AnimalResponse, status_code=status.HTTP_201_CREATED)
async def create_animal(
    data: CreateAnimalRequest,
    session: SessionDep,
    context: CanOperateLivestockDep,
) -> AnimalResponse:
    if data.facility_id is not None:
        facility_exists = await session.scalar(
            select(LivestockFacility.id).where(
                LivestockFacility.id == data.facility_id,
                LivestockFacility.organization_id == context.organization.id,
                LivestockFacility.is_active.is_(True),
            )
        )
        if facility_exists is None:
            raise HTTPException(status_code=404, detail="Bâtiment introuvable ou inactif.")
    if data.group_id is not None:
        group = await session.scalar(
            select(LivestockGroup).where(
                LivestockGroup.id == data.group_id,
                LivestockGroup.organization_id == context.organization.id,
                LivestockGroup.is_active.is_(True),
            )
        )
        if group is None:
            raise HTTPException(status_code=404, detail="Lot introuvable ou inactif.")
        if group.species.casefold() != data.species.casefold():
            raise HTTPException(
                status_code=422,
                detail="L'espèce doit correspondre à celle du lot.",
            )
    animal = LivestockAnimal(
        organization_id=context.organization.id,
        created_by_id=context.user.id,
        **data.model_dump(),
    )
    session.add(animal)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ce numéro d'identification existe déjà.",
        ) from error
    await session.refresh(animal)
    return await _animal_response(session, animal)


@router.patch("/animals/{animal_id}/status", response_model=AnimalResponse)
async def update_animal_status(
    animal_id: uuid.UUID,
    animal_status: Annotated[str, Query(alias="status", pattern="^(active|sold|deceased)$")],
    session: SessionDep,
    context: CanOperateLivestockDep,
) -> AnimalResponse:
    animal = await session.scalar(
        select(LivestockAnimal).where(
            LivestockAnimal.id == animal_id,
            LivestockAnimal.organization_id == context.organization.id,
        )
    )
    if animal is None:
        raise HTTPException(status_code=404, detail="Animal introuvable.")
    if animal.status != animal_status and animal_status == "deceased":
        session.add(
            LivestockRecord(
                organization_id=context.organization.id,
                animal_id=animal.id,
                facility_id=animal.facility_id,
                created_by_id=context.user.id,
                record_type="reproduction",
                category="mortality",
                title="Décès enregistré",
                event_date=date.today(),
                amount_fcfa=0,
            )
        )
    animal.status = animal_status
    await session.commit()
    await session.refresh(animal)
    return await _animal_response(session, animal)


@router.post("/animals/{animal_id}/photo", response_model=AnimalResponse)
async def upload_animal_photo(
    animal_id: uuid.UUID,
    session: SessionDep,
    context: CanOperateLivestockDep,
    photo: Annotated[UploadFile, File()],
) -> AnimalResponse:
    animal = await session.scalar(
        select(LivestockAnimal).where(
            LivestockAnimal.id == animal_id,
            LivestockAnimal.organization_id == context.organization.id,
        )
    )
    if animal is None:
        raise HTTPException(status_code=404, detail="Animal introuvable.")
    filename, path = await _store_photo(context.organization.id, photo)
    old_filename = animal.photo_filename
    animal.photo_filename = filename
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        path.unlink(missing_ok=True)
        raise
    if old_filename:
        _photo_path(context.organization.id, old_filename).unlink(missing_ok=True)
    await session.refresh(animal)
    return await _animal_response(session, animal)


@router.get("/animals/{animal_id}/photo")
async def read_animal_photo(
    animal_id: uuid.UUID,
    session: SessionDep,
    context: CurrentOrganizationDep,
):
    filename = await session.scalar(
        select(LivestockAnimal.photo_filename).where(
            LivestockAnimal.id == animal_id,
            LivestockAnimal.organization_id == context.organization.id,
        )
    )
    if filename is None:
        raise HTTPException(status_code=404, detail="Photo introuvable.")
    path = _photo_path(context.organization.id, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Photo introuvable.")
    return FileResponse(path)


@router.post(
    "/finance/transactions",
    response_model=LivestockFinanceTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_livestock_finance_transaction(
    data: CreateLivestockFinanceTransactionRequest,
    session: SessionDep,
    context: CanManageLivestockDep,
) -> LivestockFinanceTransactionResponse:
    facility_id = data.facility_id
    if data.animal_id is not None:
        animal = await session.scalar(
            select(LivestockAnimal).where(
                LivestockAnimal.id == data.animal_id,
                LivestockAnimal.organization_id == context.organization.id,
            )
        )
        if animal is None:
            raise HTTPException(status_code=404, detail="Animal introuvable.")
        if facility_id is not None and animal.facility_id != facility_id:
            raise HTTPException(
                status_code=422,
                detail="Le bâtiment ne correspond pas à cet animal.",
            )
        facility_id = animal.facility_id
    elif data.group_id is not None:
        group = await session.scalar(
            select(LivestockGroup).where(
                LivestockGroup.id == data.group_id,
                LivestockGroup.organization_id == context.organization.id,
            )
        )
        if group is None:
            raise HTTPException(status_code=404, detail="Lot introuvable.")
        if facility_id is not None and group.facility_id != facility_id:
            raise HTTPException(status_code=422, detail="Le bâtiment ne correspond pas à ce lot.")
        facility_id = group.facility_id
    elif facility_id is not None:
        facility_exists = await session.scalar(
            select(LivestockFacility.id).where(
                LivestockFacility.id == facility_id,
                LivestockFacility.organization_id == context.organization.id,
            )
        )
        if facility_exists is None:
            raise HTTPException(status_code=404, detail="Bâtiment introuvable.")

    transaction = LivestockFinanceTransaction(
        organization_id=context.organization.id,
        created_by_id=context.user.id,
        facility_id=facility_id,
        **data.model_dump(exclude={"facility_id"}),
    )
    session.add(transaction)
    await session.commit()
    await session.refresh(transaction)
    return await _livestock_finance_response(session, transaction)


@router.get(
    "/finance/transactions",
    response_model=LivestockFinanceTransactionPageResponse,
)
async def list_livestock_finance_transactions(
    session: SessionDep,
    context: CanViewLivestockFinanceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 100,
    year: Annotated[int, Query(ge=2000, le=2100)] = date.today().year,
    transaction_type: Annotated[
        str | None, Query(alias="type", pattern="^(income|expense)$")
    ] = None,
) -> LivestockFinanceTransactionPageResponse:
    filters = [
        LivestockFinanceTransaction.organization_id == context.organization.id,
        LivestockFinanceTransaction.transaction_date >= date(year, 1, 1),
        LivestockFinanceTransaction.transaction_date < date(year + 1, 1, 1),
    ]
    if transaction_type is not None:
        filters.append(LivestockFinanceTransaction.transaction_type == transaction_type)
    total = await session.scalar(
        select(func.count()).select_from(LivestockFinanceTransaction).where(*filters)
    )
    rows = await session.scalars(
        select(LivestockFinanceTransaction)
        .where(*filters)
        .order_by(
            LivestockFinanceTransaction.transaction_date.desc(),
            LivestockFinanceTransaction.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return LivestockFinanceTransactionPageResponse(
        items=[await _livestock_finance_response(session, item) for item in rows],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/finance/summary", response_model=LivestockFinanceSummaryResponse)
async def read_livestock_finance_summary(
    session: SessionDep,
    context: CanViewLivestockFinanceDep,
    year: Annotated[int, Query(ge=2000, le=2100)] = date.today().year,
) -> LivestockFinanceSummaryResponse:
    filters = [
        LivestockFinanceTransaction.organization_id == context.organization.id,
        LivestockFinanceTransaction.transaction_date >= date(year, 1, 1),
        LivestockFinanceTransaction.transaction_date < date(year + 1, 1, 1),
    ]
    totals = await session.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            LivestockFinanceTransaction.transaction_type == "income",
                            LivestockFinanceTransaction.amount_fcfa,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            LivestockFinanceTransaction.transaction_type == "expense",
                            LivestockFinanceTransaction.amount_fcfa,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(*filters)
    )
    income, expenses = totals.one()
    monthly_rows = await session.execute(
        select(
            extract("month", LivestockFinanceTransaction.transaction_date),
            func.sum(
                case(
                    (
                        LivestockFinanceTransaction.transaction_type == "income",
                        LivestockFinanceTransaction.amount_fcfa,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        LivestockFinanceTransaction.transaction_type == "expense",
                        LivestockFinanceTransaction.amount_fcfa,
                    ),
                    else_=0,
                )
            ),
        )
        .where(*filters)
        .group_by(extract("month", LivestockFinanceTransaction.transaction_date))
    )
    incomes = [0] * 12
    expenses_by_month = [0] * 12
    for month_number, monthly_income, monthly_expenses in monthly_rows:
        month_index = int(month_number) - 1
        incomes[month_index] = int(monthly_income or 0)
        expenses_by_month[month_index] = int(monthly_expenses or 0)

    def monthly_response(amounts: list[int]) -> list[MonthlyLivestockFinanceResponse]:
        return [
            MonthlyLivestockFinanceResponse(
                month=month,
                month_number=index + 1,
                amount_fcfa=amount,
            )
            for index, (month, amount) in enumerate(zip(MONTH_LABELS, amounts, strict=True))
        ]

    return LivestockFinanceSummaryResponse(
        year=year,
        income_fcfa=int(income),
        expenses_fcfa=int(expenses),
        balance_fcfa=int(income) - int(expenses),
        monthly_income=monthly_response(incomes),
        monthly_expenses=monthly_response(expenses_by_month),
    )


@router.get("/records", response_model=list[RecordResponse])
async def list_records(
    session: SessionDep,
    context: CurrentOrganizationDep,
    record_type: Annotated[
        str | None,
        Query(alias="type", pattern="^(health|reproduction|production|feed)$"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RecordResponse]:
    filters = [LivestockRecord.organization_id == context.organization.id]
    if record_type:
        filters.append(LivestockRecord.record_type == record_type)
    records = await session.scalars(
        select(LivestockRecord)
        .where(*filters)
        .order_by(LivestockRecord.event_date.desc(), LivestockRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [
        await _record_response(
            session,
            record,
            include_financials=context.membership.role in {"owner", "admin", "manager"},
        )
        for record in records
    ]


@router.patch("/records/{record_id}/resolve", response_model=RecordResponse)
async def resolve_health_record(
    record_id: uuid.UUID,
    session: SessionDep,
    context: CanOperateLivestockDep,
) -> RecordResponse:
    record = await session.scalar(
        select(LivestockRecord).where(
            LivestockRecord.id == record_id,
            LivestockRecord.organization_id == context.organization.id,
            LivestockRecord.record_type == "health",
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Échéance de soin introuvable.")
    record.is_resolved = True
    await session.commit()
    await session.refresh(record)
    return await _record_response(
        session,
        record,
        include_financials=context.membership.role in {"owner", "admin", "manager"},
    )


@router.post("/records", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
async def create_record(
    data: CreateRecordRequest,
    session: SessionDep,
    context: CanOperateLivestockDep,
) -> RecordResponse:
    if context.membership.role == "operator" and data.amount_fcfa > 0:
        raise HTTPException(
            status_code=403,
            detail="Seul un responsable peut enregistrer un montant financier.",
        )
    subject_facility_id = None
    if data.animal_id is not None:
        subject = await session.scalar(
            select(LivestockAnimal).where(
                LivestockAnimal.id == data.animal_id,
                LivestockAnimal.organization_id == context.organization.id,
            )
        )
        if subject is None:
            raise HTTPException(status_code=404, detail="Animal introuvable.")
        subject_facility_id = subject.facility_id
    else:
        subject = await session.scalar(
            select(LivestockGroup).where(
                LivestockGroup.id == data.group_id,
                LivestockGroup.organization_id == context.organization.id,
            )
        )
        if subject is None:
            raise HTTPException(status_code=404, detail="Lot introuvable.")
        subject_facility_id = subject.facility_id

    record = LivestockRecord(
        organization_id=context.organization.id,
        created_by_id=context.user.id,
        facility_id=subject_facility_id,
        **data.model_dump(),
    )
    session.add(record)
    await session.flush()
    if data.record_type == "production" and data.quantity is not None and data.unit is not None:
        facility_name = None
        if subject_facility_id is not None:
            facility_name = await session.scalar(
                select(LivestockFacility.name).where(
                    LivestockFacility.id == subject_facility_id,
                    LivestockFacility.organization_id == context.organization.id,
                )
            )
        production_name = {
            "milk": "Lait",
            "eggs": "Œufs",
            "weight": "Poids / viande",
        }.get(data.category, data.title)
        stock_item = await get_or_create_production_item(
            session,
            organization_id=context.organization.id,
            source="elevage",
            name=production_name,
            unit=data.unit,
            location=facility_name or "Élevage",
        )
        await record_stock_movement(
            session,
            organization_id=context.organization.id,
            stock_item=stock_item,
            movement_type="production",
            direction="in",
            quantity=data.quantity,
            movement_date=data.event_date,
            created_by_id=context.user.id,
            note=data.notes or data.title,
            reference_type="livestock_production",
            reference_id=record.id,
        )
    if data.amount_fcfa > 0:
        session.add(
            LivestockFinanceTransaction(
                organization_id=context.organization.id,
                animal_id=data.animal_id,
                group_id=data.group_id,
                facility_id=subject_facility_id,
                source_record_id=record.id,
                created_by_id=context.user.id,
                transaction_type="income" if data.record_type == "production" else "expense",
                category="input" if data.record_type == "feed" else data.record_type,
                label=data.title,
                amount_fcfa=data.amount_fcfa,
                transaction_date=data.event_date,
                quantity=data.quantity,
                unit=data.unit,
                notes=data.notes,
            )
        )
    if data.amount_fcfa > 0 and subject_facility_id is not None:
        farm_id = await session.scalar(
            select(LivestockFacility.farm_id).where(
                LivestockFacility.id == subject_facility_id,
                LivestockFacility.organization_id == context.organization.id,
            )
        )
        if farm_id is not None:
            session.add(
                FinanceTransaction(
                    organization_id=context.organization.id,
                    farm_id=farm_id,
                    created_by_id=context.user.id,
                    source="livestock",
                    transaction_type="income" if data.record_type == "production" else "expense",
                    category="input" if data.record_type == "feed" else "other",
                    label=data.title,
                    amount_fcfa=data.amount_fcfa,
                    transaction_date=data.event_date,
                    quantity=data.quantity,
                    unit=data.unit,
                    notes=data.notes,
                )
            )
    await record_audit_event(
        session,
        organization_id=context.organization.id,
        actor_id=context.user.id,
        module="livestock",
        action="record_created",
        entity_type="livestock_record",
        entity_id=record.id,
        summary=f"Enregistrement d’élevage ajouté : {record.title}.",
    )
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=422,
            detail="Cet enregistrement n'a pas pu être créé.",
        ) from error
    await session.refresh(record)
    return await _record_response(session, record)
