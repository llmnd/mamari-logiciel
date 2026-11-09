import asyncio
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mamari_api.core.config import get_settings
from mamari_api.modules.agriculture.models import (
    Campaign,
    CampaignStatus,
    Crop,
    Farm,
    FinanceTransaction,
    FinanceType,
    Harvest,
    Parcel,
)
from mamari_api.modules.agriculture.schemas import (
    CampaignPageResponse,
    CampaignResponse,
    CampaignSaleRequest,
    CampaignSimulationResponse,
    CreateCampaignRequest,
    CreateCropRequest,
    CreateFinanceTransactionRequest,
    CreateHarvestRequest,
    CreateParcelRequest,
    CropResponse,
    FarmPageResponse,
    FarmResponse,
    FinanceSummaryResponse,
    FinanceTransactionPageResponse,
    FinanceTransactionResponse,
    HarvestPageResponse,
    HarvestResponse,
    MonthlyFinanceResponse,
    ParcelPageResponse,
    ParcelResponse,
    UpdateParcelRequest,
)
from mamari_api.modules.audit.service import record_audit_event
from mamari_api.modules.identity.dependencies import (
    CurrentMembership,
    SessionDep,
    get_current_membership,
    require_roles,
)
from mamari_api.modules.sales.models import Customer
from mamari_api.modules.stocks.service import (
    get_or_create_production_item,
    record_stock_movement,
)

router = APIRouter(prefix="/agriculture")
CurrentOrganizationDep = Annotated[CurrentMembership, Depends(get_current_membership)]
CanManageAgricultureDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager")),
]
CanOperateAgricultureDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager", "operator")),
]
CanViewAgricultureFinanceDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager")),
]
MONTH_LABELS = (
    "Jan",
    "Fév",
    "Mar",
    "Avr",
    "Mai",
    "Jun",
    "Jul",
    "Aoû",
    "Sep",
    "Oct",
    "Nov",
    "Déc",
)
MAX_PHOTO_BYTES = 5 * 1024 * 1024
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
    return get_settings().upload_directory / str(organization_id) / filename


async def _store_photo(
    organization_id: uuid.UUID,
    photo_data: tuple[bytes, str],
) -> tuple[str, Path]:
    content, extension = photo_data
    filename = f"{uuid.uuid4().hex}{extension}"
    path = _photo_path(organization_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, content)
    return filename, path


def _is_duplicate_name_error(
    error: IntegrityError,
    constraint_name: str,
    sqlite_message: str,
) -> bool:
    actual_constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    return actual_constraint == constraint_name or str(error.orig) == sqlite_message


async def _read_photo(photo: UploadFile) -> tuple[bytes, str]:
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
    return content, photo_type[0]


async def _farm_response(session: AsyncSession, farm: Farm) -> FarmResponse:
    totals = await session.execute(
        select(
            func.count(Parcel.id),
            func.coalesce(func.sum(Parcel.area_hectares), 0),
        ).where(
            Parcel.organization_id == farm.organization_id,
            Parcel.farm_id == farm.id,
            Parcel.is_active.is_(True),
        )
    )
    parcel_count, area = totals.one()
    return FarmResponse(
        id=farm.id,
        name=farm.name,
        location=farm.location,
        is_active=farm.is_active,
        photo_url=f"/agriculture/farms/{farm.id}/photo" if farm.photo_filename else None,
        parcel_count=parcel_count,
        area_hectares=area,
        created_at=farm.created_at,
    )


async def _parcel_response(session: AsyncSession, parcel: Parcel) -> ParcelResponse:
    farm = await session.scalar(
        select(Farm).where(
            Farm.id == parcel.farm_id,
            Farm.organization_id == parcel.organization_id,
        )
    )
    if farm is None:
        raise HTTPException(status_code=404, detail="Ferme de la parcelle introuvable.")
    return ParcelResponse(
        id=parcel.id,
        farm_id=parcel.farm_id,
        farm_name=farm.name,
        name=parcel.name,
        crop=parcel.crop,
        crop_id=parcel.crop_id,
        area_hectares=parcel.area_hectares,
        is_active=parcel.is_active,
        photo_url=f"/agriculture/parcels/{parcel.id}/photo" if parcel.photo_filename else None,
        created_at=parcel.created_at,
    )


def _expected_values(campaign: Campaign) -> tuple[Decimal, int, int, int]:
    production = campaign.area_hectares * campaign.expected_yield_kg_per_hectare
    revenue = int(
        (production * campaign.expected_price_fcfa_per_kg).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    costs = campaign.estimated_input_cost_fcfa + campaign.estimated_other_cost_fcfa
    return production, revenue, costs, revenue - costs


async def _campaign_responses(
    session: AsyncSession,
    rows: list[tuple[Campaign, Parcel, Farm, Crop]],
    organization_id: uuid.UUID,
    *,
    include_financials: bool = True,
) -> list[CampaignResponse]:
    campaign_ids = [row[0].id for row in rows]
    if not campaign_ids:
        return []

    harvest_rows = await session.execute(
        select(Harvest.campaign_id, func.coalesce(func.sum(Harvest.quantity_kg), 0))
        .where(
            Harvest.organization_id == organization_id,
            Harvest.campaign_id.in_(campaign_ids),
        )
        .group_by(Harvest.campaign_id)
    )
    harvest_totals = {campaign_id: quantity for campaign_id, quantity in harvest_rows}
    sold_rows = await session.execute(
        select(
            FinanceTransaction.campaign_id,
            func.coalesce(func.sum(FinanceTransaction.quantity), 0),
        )
        .where(
            FinanceTransaction.organization_id == organization_id,
            FinanceTransaction.campaign_id.in_(campaign_ids),
            FinanceTransaction.category == "commercialization",
        )
        .group_by(FinanceTransaction.campaign_id)
    )
    sold_totals = {campaign_id: quantity for campaign_id, quantity in sold_rows}
    finance_totals: dict[uuid.UUID, tuple[int, int]] = {}
    if include_financials:
        finance_rows = await session.execute(
            select(
                FinanceTransaction.campaign_id,
                func.coalesce(
                    func.sum(
                        case(
                            (
                                FinanceTransaction.transaction_type == FinanceType.INCOME.value,
                                FinanceTransaction.amount_fcfa,
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
                                FinanceTransaction.transaction_type == FinanceType.EXPENSE.value,
                                FinanceTransaction.amount_fcfa,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .where(
                FinanceTransaction.organization_id == organization_id,
                FinanceTransaction.campaign_id.in_(campaign_ids),
            )
            .group_by(FinanceTransaction.campaign_id)
        )
        finance_totals = {
            campaign_id: (int(income), int(expense))
            for campaign_id, income, expense in finance_rows
        }

    responses: list[CampaignResponse] = []
    for campaign, parcel, farm, crop in rows:
        expected_production, expected_revenue, estimated_costs, estimated_margin = _expected_values(
            campaign
        )
        actual_income, actual_expenses = finance_totals.get(campaign.id, (0, 0))
        responses.append(
            CampaignResponse(
                id=campaign.id,
                parcel_id=parcel.id,
                parcel_name=parcel.name,
                farm_id=farm.id,
                farm_name=farm.name,
                crop_id=crop.id,
                crop=crop.name,
                name=campaign.name,
                season=campaign.season,
                status=campaign.status,
                start_date=campaign.start_date,
                expected_harvest_date=campaign.expected_harvest_date,
                area_hectares=campaign.area_hectares,
                expected_yield_kg_per_hectare=campaign.expected_yield_kg_per_hectare,
                expected_price_fcfa_per_kg=(
                    campaign.expected_price_fcfa_per_kg if include_financials else None
                ),
                estimated_input_cost_fcfa=(
                    campaign.estimated_input_cost_fcfa if include_financials else None
                ),
                estimated_other_cost_fcfa=(
                    campaign.estimated_other_cost_fcfa if include_financials else None
                ),
                simulated_at=campaign.simulated_at,
                started_at=campaign.started_at,
                closed_at=campaign.closed_at,
                archived_at=campaign.archived_at,
                expected_production_kg=expected_production,
                expected_revenue_fcfa=expected_revenue if include_financials else None,
                estimated_total_cost_fcfa=estimated_costs if include_financials else None,
                estimated_margin_fcfa=estimated_margin if include_financials else None,
                actual_production_kg=harvest_totals.get(campaign.id, Decimal(0)),
                actual_sold_kg=sold_totals.get(campaign.id, Decimal(0)),
                actual_revenue_fcfa=actual_income if include_financials else None,
                actual_expenses_fcfa=actual_expenses if include_financials else None,
                created_at=campaign.created_at,
            )
        )
    return responses


async def _get_campaign_rows(
    session: AsyncSession,
    organization_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> tuple[Campaign, Parcel, Farm, Crop] | None:
    result = await session.execute(
        select(Campaign, Parcel, Farm, Crop)
        .join(
            Parcel,
            (Parcel.organization_id == Campaign.organization_id)
            & (Parcel.id == Campaign.parcel_id),
        )
        .join(Farm, (Farm.organization_id == Parcel.organization_id) & (Farm.id == Parcel.farm_id))
        .join(
            Crop, (Crop.organization_id == Campaign.organization_id) & (Crop.id == Campaign.crop_id)
        )
        .where(Campaign.organization_id == organization_id, Campaign.id == campaign_id)
    )
    return result.one_or_none()


async def _finance_response(
    session: AsyncSession,
    transaction: FinanceTransaction,
) -> FinanceTransactionResponse:
    farm = await session.get(Farm, transaction.farm_id)
    campaign_name = None
    if transaction.campaign_id is not None:
        campaign_name = await session.scalar(
            select(Campaign.name).where(
                Campaign.id == transaction.campaign_id,
                Campaign.organization_id == transaction.organization_id,
            )
        )
    return FinanceTransactionResponse(
        id=transaction.id,
        customer_id=transaction.customer_id,
        farm_id=transaction.farm_id,
        farm_name=farm.name if farm else "",
        campaign_id=transaction.campaign_id,
        campaign_name=campaign_name,
        transaction_type=transaction.transaction_type,
        category=transaction.category,
        label=transaction.label,
        amount_fcfa=transaction.amount_fcfa,
        transaction_date=transaction.transaction_date,
        quantity=transaction.quantity,
        unit=transaction.unit,
        customer_name=transaction.customer_name,
        notes=transaction.notes,
        created_at=transaction.created_at,
    )


@router.get("/farms", response_model=FarmPageResponse, summary="Lister les fermes")
async def list_farms(
    session: SessionDep,
    context: CurrentOrganizationDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    active: bool | None = True,
) -> FarmPageResponse:
    filters = [Farm.organization_id == context.organization.id]
    if active is not None:
        filters.append(Farm.is_active.is_(active))
    if search and search.strip():
        filters.append(Farm.name.ilike(f"%{search.strip()}%"))
    total = await session.scalar(select(func.count()).select_from(Farm).where(*filters))
    rows = await session.execute(
        select(
            Farm,
            func.count(Parcel.id),
            func.coalesce(func.sum(Parcel.area_hectares), 0),
        )
        .outerjoin(
            Parcel,
            (Parcel.organization_id == Farm.organization_id)
            & (Parcel.farm_id == Farm.id)
            & Parcel.is_active.is_(True),
        )
        .where(*filters)
        .group_by(Farm.id)
        .order_by(Farm.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return FarmPageResponse(
        items=[
            FarmResponse(
                id=farm.id,
                name=farm.name,
                location=farm.location,
                is_active=farm.is_active,
                photo_url=f"/agriculture/farms/{farm.id}/photo" if farm.photo_filename else None,
                parcel_count=parcel_count,
                area_hectares=area,
                created_at=farm.created_at,
            )
            for farm, parcel_count, area in rows.all()
        ],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/farms",
    response_model=FarmResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une ferme avec sa photo",
)
async def create_farm(
    session: SessionDep,
    context: CanOperateAgricultureDep,
    name: Annotated[str, Form(min_length=2, max_length=120)],
    location: Annotated[str | None, Form(max_length=180)] = None,
    photo: Annotated[UploadFile | None, File()] = None,
) -> FarmResponse:
    farm_name = name.strip()
    if len(farm_name) < 2:
        raise HTTPException(status_code=422, detail="Le nom de la ferme est trop court.")
    photo_data = await _read_photo(photo) if photo is not None else None
    farm = Farm(
        id=uuid.uuid4(),
        organization_id=context.organization.id,
        created_by_id=context.user.id,
        name=farm_name,
        location=location.strip() if location and location.strip() else None,
    )
    photo_path = None
    if photo_data is not None:
        farm.photo_filename, photo_path = await _store_photo(context.organization.id, photo_data)
    session.add(farm)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        if photo_path is not None:
            photo_path.unlink(missing_ok=True)
        if not _is_duplicate_name_error(
            error,
            "uq_agriculture_farms_org_name",
            "UNIQUE constraint failed: agriculture_farms.organization_id, agriculture_farms.name",
        ):
            raise
        raise HTTPException(
            status_code=409,
            detail="Une ferme porte déjà ce nom dans l'organisation.",
        ) from error
    except SQLAlchemyError:
        await session.rollback()
        if photo_path is not None:
            photo_path.unlink(missing_ok=True)
        raise
    return await _farm_response(session, farm)


@router.get("/farms/{farm_id}/photo", response_class=FileResponse, include_in_schema=False)
async def read_farm_photo(
    farm_id: uuid.UUID,
    session: SessionDep,
    context: CurrentOrganizationDep,
) -> FileResponse:
    farm = await session.scalar(
        select(Farm).where(
            Farm.id == farm_id,
            Farm.organization_id == context.organization.id,
        )
    )
    if farm is None or farm.photo_filename is None:
        raise HTTPException(status_code=404, detail="Photo de la ferme introuvable.")
    path = _photo_path(context.organization.id, farm.photo_filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier photo introuvable sur le serveur.")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@router.patch("/farms/{farm_id}", response_model=FarmResponse, summary="Modifier une ferme")
async def update_farm(
    farm_id: uuid.UUID,
    session: SessionDep,
    context: CanOperateAgricultureDep,
    name: Annotated[str, Form(min_length=2, max_length=120)],
    location: Annotated[str | None, Form(max_length=180)] = None,
    photo: Annotated[UploadFile | None, File()] = None,
    remove_photo: Annotated[bool, Form()] = False,
) -> FarmResponse:
    farm = await session.scalar(
        select(Farm).where(
            Farm.id == farm_id,
            Farm.organization_id == context.organization.id,
        )
    )
    if farm is None:
        raise HTTPException(status_code=404, detail="Ferme introuvable.")
    farm_name = name.strip()
    if len(farm_name) < 2:
        raise HTTPException(status_code=422, detail="Le nom de la ferme est trop court.")
    if photo is not None and remove_photo:
        raise HTTPException(
            status_code=422,
            detail="Choisissez une nouvelle photo ou la suppression, pas les deux.",
        )

    photo_data = await _read_photo(photo) if photo is not None else None
    previous_filename = farm.photo_filename
    new_photo_path = None
    if photo_data is not None:
        farm.photo_filename, new_photo_path = await _store_photo(
            context.organization.id,
            photo_data,
        )
    elif remove_photo:
        farm.photo_filename = None
    farm.name = farm_name
    farm.location = location.strip() if location and location.strip() else None
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        if new_photo_path is not None:
            new_photo_path.unlink(missing_ok=True)
        if not _is_duplicate_name_error(
            error,
            "uq_agriculture_farms_org_name",
            "UNIQUE constraint failed: agriculture_farms.organization_id, agriculture_farms.name",
        ):
            raise
        raise HTTPException(
            status_code=409,
            detail="Une ferme porte déjà ce nom dans l'organisation.",
        ) from error
    except SQLAlchemyError:
        await session.rollback()
        if new_photo_path is not None:
            new_photo_path.unlink(missing_ok=True)
        raise

    if previous_filename and farm.photo_filename != previous_filename:
        _photo_path(context.organization.id, previous_filename).unlink(missing_ok=True)
    return await _farm_response(session, farm)


@router.patch("/farms/{farm_id}/archive", response_model=FarmResponse)
async def archive_farm(
    farm_id: uuid.UUID,
    session: SessionDep,
    context: CanManageAgricultureDep,
) -> FarmResponse:
    farm = await session.scalar(
        select(Farm).where(
            Farm.id == farm_id,
            Farm.organization_id == context.organization.id,
        )
    )
    if farm is None:
        raise HTTPException(status_code=404, detail="Ferme introuvable.")
    active_campaign = await session.scalar(
        select(Campaign.id)
        .join(Parcel, Campaign.parcel_id == Parcel.id)
        .where(
            Parcel.farm_id == farm.id,
            Campaign.organization_id == farm.organization_id,
            Campaign.status == CampaignStatus.ACTIVE.value,
        )
        .limit(1)
    )
    if active_campaign is not None:
        raise HTTPException(
            status_code=409,
            detail="Clôturez les campagnes actives avant d'archiver cette ferme.",
        )
    farm.is_active = False
    await session.commit()
    return await _farm_response(session, farm)


@router.patch("/farms/{farm_id}/restore", response_model=FarmResponse)
async def restore_farm(
    farm_id: uuid.UUID,
    session: SessionDep,
    context: CanManageAgricultureDep,
) -> FarmResponse:
    farm = await session.scalar(
        select(Farm).where(Farm.id == farm_id, Farm.organization_id == context.organization.id)
    )
    if farm is None:
        raise HTTPException(status_code=404, detail="Ferme introuvable.")
    farm.is_active = True
    await session.commit()
    return await _farm_response(session, farm)


@router.get("/crops", response_model=list[CropResponse], summary="Catalogue des cultures")
async def list_crops(
    session: SessionDep,
    context: CurrentOrganizationDep,
) -> list[CropResponse]:
    result = await session.scalars(
        select(Crop)
        .where(Crop.organization_id == context.organization.id, Crop.is_active.is_(True))
        .order_by(Crop.name)
    )
    return [CropResponse(id=crop.id, name=crop.name, is_active=crop.is_active) for crop in result]


@router.post(
    "/crops",
    response_model=CropResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ajouter une culture au catalogue",
)
async def create_crop(
    data: CreateCropRequest,
    session: SessionDep,
    context: CanManageAgricultureDep,
) -> CropResponse:
    crop = Crop(
        id=uuid.uuid4(),
        organization_id=context.organization.id,
        name=data.name,
    )
    session.add(crop)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Cette culture existe déjà dans le catalogue.",
        ) from error
    return CropResponse(id=crop.id, name=crop.name, is_active=crop.is_active)


@router.get("/parcels", response_model=ParcelPageResponse, summary="Lister les parcelles")
async def list_parcels(
    session: SessionDep,
    context: CurrentOrganizationDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    farm_id: uuid.UUID | None = None,
    active: bool | None = True,
) -> ParcelPageResponse:
    filters = [Parcel.organization_id == context.organization.id]
    if active is not None:
        filters.append(Parcel.is_active.is_(active))
    if farm_id is not None:
        filters.append(Parcel.farm_id == farm_id)
    if search is not None and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(or_(Parcel.name.ilike(pattern), Parcel.crop.ilike(pattern)))
    total = await session.scalar(select(func.count()).select_from(Parcel).where(*filters))
    rows = await session.execute(
        select(Parcel, Farm)
        .join(
            Farm,
            (Farm.organization_id == Parcel.organization_id) & (Farm.id == Parcel.farm_id),
        )
        .where(*filters)
        .order_by(Parcel.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ParcelPageResponse(
        items=[
            ParcelResponse(
                id=parcel.id,
                farm_id=parcel.farm_id,
                farm_name=farm.name,
                name=parcel.name,
                crop=parcel.crop,
                crop_id=parcel.crop_id,
                area_hectares=parcel.area_hectares,
                is_active=parcel.is_active,
                photo_url=(
                    f"/agriculture/parcels/{parcel.id}/photo" if parcel.photo_filename else None
                ),
                created_at=parcel.created_at,
            )
            for parcel, farm in rows.all()
        ],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/parcels",
    response_model=ParcelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une parcelle dans une ferme",
)
async def create_parcel(
    data: CreateParcelRequest,
    session: SessionDep,
    context: CanOperateAgricultureDep,
) -> ParcelResponse:
    farm = await session.scalar(
        select(Farm).where(
            Farm.id == data.farm_id,
            Farm.organization_id == context.organization.id,
            Farm.is_active.is_(True),
        )
    )
    crop = await session.scalar(
        select(Crop).where(
            Crop.id == data.crop_id,
            Crop.organization_id == context.organization.id,
            Crop.is_active.is_(True),
        )
    )
    if farm is None:
        raise HTTPException(status_code=404, detail="Ferme introuvable ou archivée.")
    if crop is None:
        raise HTTPException(status_code=404, detail="Culture introuvable ou inactive.")
    parcel = Parcel(
        id=uuid.uuid4(),
        organization_id=context.organization.id,
        farm_id=farm.id,
        crop_id=crop.id,
        created_by_id=context.user.id,
        name=data.name,
        crop=crop.name,
        area_hectares=data.area_hectares,
    )
    session.add(parcel)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        if not _is_duplicate_name_error(
            error,
            "uq_agriculture_parcels_org_name",
            (
                "UNIQUE constraint failed: agriculture_parcels.organization_id, "
                "agriculture_parcels.name"
            ),
        ):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une parcelle porte déjà ce nom dans l'organisation.",
        ) from error
    await session.refresh(parcel)
    return await _parcel_response(session, parcel)


@router.patch(
    "/parcels/{parcel_id}",
    response_model=ParcelResponse,
    summary="Modifier une parcelle",
)
async def update_parcel(
    parcel_id: uuid.UUID,
    data: UpdateParcelRequest,
    session: SessionDep,
    context: CanOperateAgricultureDep,
) -> ParcelResponse:
    parcel = await session.scalar(
        select(Parcel).where(
            Parcel.id == parcel_id,
            Parcel.organization_id == context.organization.id,
        )
    )
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcelle introuvable.")
    largest_campaign_area = await session.scalar(
        select(func.max(Campaign.area_hectares)).where(
            Campaign.organization_id == context.organization.id,
            Campaign.parcel_id == parcel.id,
        )
    )
    if largest_campaign_area is not None and data.area_hectares < largest_campaign_area:
        raise HTTPException(
            status_code=409,
            detail="La superficie ne peut pas être inférieure à celle d'une campagne existante.",
        )
    parcel.name = data.name
    parcel.area_hectares = data.area_hectares
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        if not _is_duplicate_name_error(
            error,
            "uq_agriculture_parcels_org_name",
            (
                "UNIQUE constraint failed: agriculture_parcels.organization_id, "
                "agriculture_parcels.name"
            ),
        ):
            raise
        raise HTTPException(
            status_code=409,
            detail="Une parcelle porte déjà ce nom dans l'organisation.",
        ) from error
    return await _parcel_response(session, parcel)


@router.post("/parcels/{parcel_id}/photo", response_model=ParcelResponse)
async def update_parcel_photo(
    parcel_id: uuid.UUID,
    session: SessionDep,
    context: CanOperateAgricultureDep,
    photo: Annotated[UploadFile, File()],
) -> ParcelResponse:
    parcel = await session.scalar(
        select(Parcel).where(
            Parcel.id == parcel_id,
            Parcel.organization_id == context.organization.id,
        )
    )
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcelle introuvable.")
    photo_data = await _read_photo(photo)
    previous_filename = parcel.photo_filename
    parcel.photo_filename, new_photo_path = await _store_photo(
        context.organization.id,
        photo_data,
    )
    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        new_photo_path.unlink(missing_ok=True)
        raise
    if previous_filename:
        _photo_path(context.organization.id, previous_filename).unlink(missing_ok=True)
    return await _parcel_response(session, parcel)


@router.delete("/parcels/{parcel_id}/photo", response_model=ParcelResponse)
async def remove_parcel_photo(
    parcel_id: uuid.UUID,
    session: SessionDep,
    context: CanOperateAgricultureDep,
) -> ParcelResponse:
    parcel = await session.scalar(
        select(Parcel).where(
            Parcel.id == parcel_id,
            Parcel.organization_id == context.organization.id,
        )
    )
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcelle introuvable.")
    previous_filename = parcel.photo_filename
    parcel.photo_filename = None
    await session.commit()
    if previous_filename:
        _photo_path(context.organization.id, previous_filename).unlink(missing_ok=True)
    return await _parcel_response(session, parcel)


@router.get("/parcels/{parcel_id}/photo", response_class=FileResponse, include_in_schema=False)
async def read_parcel_photo(
    parcel_id: uuid.UUID,
    session: SessionDep,
    context: CurrentOrganizationDep,
) -> FileResponse:
    parcel = await session.scalar(
        select(Parcel).where(
            Parcel.id == parcel_id,
            Parcel.organization_id == context.organization.id,
        )
    )
    if parcel is None or parcel.photo_filename is None:
        raise HTTPException(status_code=404, detail="Photo de la parcelle introuvable.")
    path = _photo_path(context.organization.id, parcel.photo_filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier photo introuvable sur le serveur.")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@router.patch("/parcels/{parcel_id}/archive", response_model=ParcelResponse)
async def archive_parcel(
    parcel_id: uuid.UUID,
    session: SessionDep,
    context: CanManageAgricultureDep,
) -> ParcelResponse:
    parcel = await session.scalar(
        select(Parcel).where(
            Parcel.id == parcel_id,
            Parcel.organization_id == context.organization.id,
        )
    )
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcelle introuvable.")
    active_campaign = await session.scalar(
        select(Campaign.id)
        .where(
            Campaign.organization_id == context.organization.id,
            Campaign.parcel_id == parcel.id,
            Campaign.status == CampaignStatus.ACTIVE.value,
        )
        .limit(1)
    )
    if active_campaign is not None:
        raise HTTPException(
            status_code=409,
            detail="Clôturez les campagnes actives avant d'archiver cette parcelle.",
        )
    parcel.is_active = False
    await session.commit()
    return await _parcel_response(session, parcel)


@router.patch("/parcels/{parcel_id}/restore", response_model=ParcelResponse)
async def restore_parcel(
    parcel_id: uuid.UUID,
    session: SessionDep,
    context: CanManageAgricultureDep,
) -> ParcelResponse:
    parcel = await session.scalar(
        select(Parcel).where(
            Parcel.id == parcel_id,
            Parcel.organization_id == context.organization.id,
        )
    )
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcelle introuvable.")
    farm = await session.scalar(
        select(Farm).where(
            Farm.id == parcel.farm_id,
            Farm.organization_id == context.organization.id,
            Farm.is_active.is_(True),
        )
    )
    if farm is None:
        raise HTTPException(
            status_code=409,
            detail="Restaurez d'abord la ferme de cette parcelle.",
        )
    parcel.is_active = True
    await session.commit()
    return await _parcel_response(session, parcel)


@router.get("/campaigns", response_model=CampaignPageResponse, summary="Lister les campagnes")
async def list_campaigns(
    session: SessionDep,
    context: CurrentOrganizationDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    archived: bool | None = None,
    farm_id: uuid.UUID | None = None,
) -> CampaignPageResponse:
    filters = [Campaign.organization_id == context.organization.id]
    if status_filter is not None:
        filters.append(Campaign.status == status_filter)
    elif archived is not None:
        filters.append(
            Campaign.status == CampaignStatus.ARCHIVED.value
            if archived
            else Campaign.status != CampaignStatus.ARCHIVED.value
        )
    if farm_id is not None:
        filters.append(Parcel.farm_id == farm_id)
    count_query = (
        select(func.count())
        .select_from(Campaign)
        .join(
            Parcel,
            (Parcel.organization_id == Campaign.organization_id)
            & (Parcel.id == Campaign.parcel_id),
        )
        .where(*filters)
    )
    total = await session.scalar(count_query)
    rows = await session.execute(
        select(Campaign, Parcel, Farm, Crop)
        .join(
            Parcel,
            (Parcel.organization_id == Campaign.organization_id)
            & (Parcel.id == Campaign.parcel_id),
        )
        .join(Farm, (Farm.organization_id == Parcel.organization_id) & (Farm.id == Parcel.farm_id))
        .join(
            Crop, (Crop.organization_id == Campaign.organization_id) & (Crop.id == Campaign.crop_id)
        )
        .where(*filters)
        .order_by(Campaign.start_date.desc(), Campaign.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = await _campaign_responses(
        session,
        list(rows.all()),
        context.organization.id,
        include_financials=context.membership.role in {"owner", "admin", "manager"},
    )
    return CampaignPageResponse(items=items, total=total or 0, page=page, page_size=page_size)


@router.post(
    "/campaigns",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Planifier une campagne",
)
async def create_campaign(
    data: CreateCampaignRequest,
    session: SessionDep,
    context: CanOperateAgricultureDep,
) -> CampaignResponse:
    if context.membership.role == "operator" and (
        data.expected_price_fcfa_per_kg > 0
        or data.estimated_input_cost_fcfa > 0
        or data.estimated_other_cost_fcfa > 0
    ):
        raise HTTPException(
            status_code=403,
            detail="Seul un responsable peut définir les hypothèses financières d’une campagne.",
        )
    parcel = await session.scalar(
        select(Parcel)
        .join(
            Farm,
            (Farm.organization_id == Parcel.organization_id) & (Farm.id == Parcel.farm_id),
        )
        .where(
            Parcel.id == data.parcel_id,
            Parcel.organization_id == context.organization.id,
            Parcel.is_active.is_(True),
            Farm.is_active.is_(True),
        )
    )
    crop = await session.scalar(
        select(Crop).where(
            Crop.id == data.crop_id,
            Crop.organization_id == context.organization.id,
            Crop.is_active.is_(True),
        )
    )
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcelle introuvable ou inactive.")
    if crop is None:
        raise HTTPException(status_code=404, detail="Culture introuvable ou inactive.")
    if crop.id != parcel.crop_id:
        raise HTTPException(
            status_code=422,
            detail="La culture de la campagne doit correspondre à celle de la parcelle.",
        )
    area = data.area_hectares or parcel.area_hectares
    if area > parcel.area_hectares:
        raise HTTPException(
            status_code=422,
            detail="La superficie de campagne ne peut pas dépasser celle de la parcelle.",
        )
    campaign = Campaign(
        id=uuid.uuid4(),
        organization_id=context.organization.id,
        parcel_id=parcel.id,
        crop_id=crop.id,
        created_by_id=context.user.id,
        name=data.name,
        season=data.season,
        start_date=data.start_date,
        expected_harvest_date=data.expected_harvest_date,
        area_hectares=area,
        expected_yield_kg_per_hectare=data.expected_yield_kg_per_hectare,
        expected_price_fcfa_per_kg=data.expected_price_fcfa_per_kg,
        estimated_input_cost_fcfa=data.estimated_input_cost_fcfa,
        estimated_other_cost_fcfa=data.estimated_other_cost_fcfa,
    )
    session.add(campaign)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="La campagne n'a pas pu être créée.") from error
    row = await _get_campaign_rows(session, context.organization.id, campaign.id)
    assert row is not None
    return (
        await _campaign_responses(
            session,
            [row],
            context.organization.id,
            include_financials=context.membership.role in {"owner", "admin", "manager"},
        )
    )[0]


@router.post(
    "/campaigns/{campaign_id}/simulate",
    response_model=CampaignSimulationResponse,
    summary="Simuler une campagne selon ses hypothèses",
)
async def simulate_campaign(
    campaign_id: uuid.UUID,
    session: SessionDep,
    context: CanManageAgricultureDep,
) -> CampaignSimulationResponse:
    row = await _get_campaign_rows(session, context.organization.id, campaign_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Campagne introuvable.")
    campaign = row[0]
    if campaign.status not in (CampaignStatus.PLANNED.value, CampaignStatus.SIMULATED.value):
        raise HTTPException(
            status_code=409, detail="Seule une campagne planifiée peut être simulée."
        )
    campaign.status = CampaignStatus.SIMULATED.value
    campaign.simulated_at = datetime.now(UTC)
    await session.commit()
    campaign_response = (
        await _campaign_responses(
            session,
            [row],
            context.organization.id,
            include_financials=True,
        )
    )[0]
    assert campaign_response.estimated_margin_fcfa is not None
    assert campaign_response.expected_revenue_fcfa is not None
    assert campaign_response.estimated_total_cost_fcfa is not None
    margin_rate = (
        Decimal(campaign_response.estimated_margin_fcfa)
        / Decimal(campaign_response.expected_revenue_fcfa)
        * Decimal(100)
        if campaign_response.expected_revenue_fcfa
        else Decimal(0)
    )
    return CampaignSimulationResponse(
        campaign=campaign_response,
        assumptions={
            "area_hectares": campaign.area_hectares,
            "yield_kg_per_hectare": campaign.expected_yield_kg_per_hectare,
            "price_fcfa_per_kg": campaign.expected_price_fcfa_per_kg,
            "input_cost_fcfa": campaign.estimated_input_cost_fcfa,
            "other_cost_fcfa": campaign.estimated_other_cost_fcfa,
        },
        expected_production_kg=campaign_response.expected_production_kg,
        expected_revenue_fcfa=campaign_response.expected_revenue_fcfa,
        estimated_total_cost_fcfa=campaign_response.estimated_total_cost_fcfa,
        estimated_margin_fcfa=campaign_response.estimated_margin_fcfa,
        margin_rate_percent=margin_rate.quantize(Decimal("0.01")),
    )


@router.patch("/campaigns/{campaign_id}/start", response_model=CampaignResponse)
async def start_campaign(
    campaign_id: uuid.UUID,
    session: SessionDep,
    context: CanOperateAgricultureDep,
) -> CampaignResponse:
    row = await _get_campaign_rows(session, context.organization.id, campaign_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Campagne introuvable.")
    campaign = row[0]
    if campaign.status not in (CampaignStatus.PLANNED.value, CampaignStatus.SIMULATED.value):
        raise HTTPException(status_code=409, detail="Cette campagne ne peut pas être lancée.")
    campaign.status = CampaignStatus.ACTIVE.value
    campaign.started_at = datetime.now(UTC)
    await session.commit()
    return (
        await _campaign_responses(
            session,
            [row],
            context.organization.id,
            include_financials=context.membership.role in {"owner", "admin", "manager"},
        )
    )[0]


@router.patch("/campaigns/{campaign_id}/close", response_model=CampaignResponse)
async def close_campaign(
    campaign_id: uuid.UUID,
    session: SessionDep,
    context: CanOperateAgricultureDep,
) -> CampaignResponse:
    row = await _get_campaign_rows(session, context.organization.id, campaign_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Campagne introuvable.")
    campaign = row[0]
    if campaign.status != CampaignStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Seule une campagne active peut être clôturée.")
    campaign.status = CampaignStatus.CLOSED.value
    campaign.closed_at = datetime.now(UTC)
    await session.commit()
    return (
        await _campaign_responses(
            session,
            [row],
            context.organization.id,
            include_financials=context.membership.role in {"owner", "admin", "manager"},
        )
    )[0]


@router.patch("/campaigns/{campaign_id}/archive", response_model=CampaignResponse)
async def archive_campaign(
    campaign_id: uuid.UUID,
    session: SessionDep,
    context: CanManageAgricultureDep,
) -> CampaignResponse:
    row = await _get_campaign_rows(session, context.organization.id, campaign_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Campagne introuvable.")
    campaign = row[0]
    if campaign.status == CampaignStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Clôturez la campagne avant de l'archiver.")
    if campaign.status == CampaignStatus.CLOSED.value:
        harvested, sold = await _campaign_harvest_balance(
            session, context.organization.id, campaign
        )
        if sold < harvested:
            raise HTTPException(
                status_code=409,
                detail="Commercialisez toute la récolte enregistrée avant d'archiver la campagne.",
            )
    campaign.status = CampaignStatus.ARCHIVED.value
    campaign.archived_at = datetime.now(UTC)
    await session.commit()
    return (
        await _campaign_responses(
            session,
            [row],
            context.organization.id,
            include_financials=context.membership.role in {"owner", "admin", "manager"},
        )
    )[0]


async def _campaign_harvest_balance(
    session: AsyncSession,
    organization_id: uuid.UUID,
    campaign: Campaign,
) -> tuple[Decimal, Decimal]:
    harvested = await session.scalar(
        select(func.coalesce(func.sum(Harvest.quantity_kg), 0)).where(
            Harvest.organization_id == organization_id,
            Harvest.campaign_id == campaign.id,
        )
    )
    sold = await session.scalar(
        select(func.coalesce(func.sum(FinanceTransaction.quantity), 0)).where(
            FinanceTransaction.organization_id == organization_id,
            FinanceTransaction.campaign_id == campaign.id,
            FinanceTransaction.category == "commercialization",
        )
    )
    return Decimal(harvested or 0), Decimal(sold or 0)


@router.post(
    "/campaigns/{campaign_id}/sales",
    response_model=FinanceTransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Commercialiser la récolte d'une campagne",
)
async def sell_campaign_harvest(
    campaign_id: uuid.UUID,
    data: CampaignSaleRequest,
    session: SessionDep,
    context: CanOperateAgricultureDep,
) -> FinanceTransactionResponse:
    customer = None
    if data.customer_id is not None:
        customer = await session.scalar(
            select(Customer).where(
                Customer.id == data.customer_id,
                Customer.organization_id == context.organization.id,
            )
        )
        if customer is None:
            raise HTTPException(status_code=404, detail="Client introuvable.")
    customer_name = customer.name if customer else data.customer_name
    if customer_name is None:
        raise HTTPException(status_code=422, detail="Sélectionnez un client.")
    row = await _get_campaign_rows(session, context.organization.id, campaign_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Campagne introuvable.")
    campaign, parcel, farm, crop = row
    if campaign.status != CampaignStatus.CLOSED.value:
        raise HTTPException(
            status_code=409, detail="Clôturez la campagne avant sa commercialisation."
        )
    harvested, sold = await _campaign_harvest_balance(session, context.organization.id, campaign)
    if data.quantity_kg + sold > harvested:
        raise HTTPException(
            status_code=422, detail="La quantité vendue dépasse la récolte enregistrée."
        )
    amount = int(
        (data.quantity_kg * data.unit_price_fcfa_per_kg).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    if amount < 1:
        raise HTTPException(
            status_code=422,
            detail="Le montant total de la vente doit atteindre au moins 1 FCFA.",
        )
    transaction = FinanceTransaction(
        id=uuid.uuid4(),
        organization_id=context.organization.id,
        farm_id=farm.id,
        campaign_id=campaign.id,
        created_by_id=context.user.id,
        transaction_type=FinanceType.INCOME.value,
        category="commercialization",
        label=f"Vente {crop.name} · {customer_name}",
        amount_fcfa=amount,
        transaction_date=data.transaction_date,
        quantity=data.quantity_kg,
        unit="kg",
        customer_name=customer_name,
        customer_id=customer.id if customer else None,
        notes=data.notes,
    )
    session.add(transaction)
    await session.commit()
    return await _finance_response(session, transaction)


@router.post(
    "/harvests",
    response_model=HarvestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer une récolte",
)
async def create_harvest(
    data: CreateHarvestRequest,
    session: SessionDep,
    context: CanOperateAgricultureDep,
) -> HarvestResponse:
    parcel = await session.scalar(
        select(Parcel).where(
            Parcel.id == data.parcel_id,
            Parcel.organization_id == context.organization.id,
            Parcel.is_active.is_(True),
        )
    )
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcelle introuvable ou inactive.")
    campaign_name = None
    if data.campaign_id is not None:
        campaign = await session.scalar(
            select(Campaign).where(
                Campaign.id == data.campaign_id,
                Campaign.organization_id == context.organization.id,
                Campaign.parcel_id == parcel.id,
                Campaign.status == CampaignStatus.ACTIVE.value,
            )
        )
        if campaign is None:
            raise HTTPException(
                status_code=404,
                detail="Campagne active introuvable pour cette parcelle.",
            )
        campaign_name = campaign.name
    harvest = Harvest(
        id=uuid.uuid4(),
        organization_id=context.organization.id,
        parcel_id=parcel.id,
        campaign_id=data.campaign_id,
        created_by_id=context.user.id,
        harvest_date=data.harvest_date,
        quantity_kg=data.quantity_kg,
        notes=data.notes,
    )
    session.add(harvest)
    stock_item = await get_or_create_production_item(
        session,
        organization_id=context.organization.id,
        source="agriculture",
        name=parcel.crop,
        unit="kg",
        location=parcel.name,
    )
    await record_stock_movement(
        session,
        organization_id=context.organization.id,
        stock_item=stock_item,
        movement_type="production",
        direction="in",
        quantity=data.quantity_kg,
        movement_date=data.harvest_date,
        created_by_id=context.user.id,
        note=data.notes or f"Récolte enregistrée sur la parcelle {parcel.name}.",
        reference_type="agriculture_harvest",
        reference_id=harvest.id,
    )
    await record_audit_event(
        session,
        organization_id=context.organization.id,
        actor_id=context.user.id,
        module="agriculture",
        action="harvest_recorded",
        entity_type="harvest",
        entity_id=harvest.id,
        summary=f"Récolte de {data.quantity_kg} kg enregistrée sur {parcel.name}.",
    )
    await session.commit()
    await session.refresh(harvest)
    return HarvestResponse(
        id=harvest.id,
        parcel_id=parcel.id,
        parcel_name=parcel.name,
        crop=parcel.crop,
        campaign_id=harvest.campaign_id,
        campaign_name=campaign_name,
        harvest_date=harvest.harvest_date,
        quantity_kg=harvest.quantity_kg,
        notes=harvest.notes,
        created_at=harvest.created_at,
    )


@router.get("/harvests", response_model=HarvestPageResponse, summary="Consulter les récoltes")
async def list_harvests(
    session: SessionDep,
    context: CurrentOrganizationDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    campaign_id: uuid.UUID | None = None,
    farm_id: uuid.UUID | None = None,
) -> HarvestPageResponse:
    filters = [
        Harvest.organization_id == context.organization.id,
        Parcel.organization_id == context.organization.id,
    ]
    if search is not None and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(or_(Parcel.name.ilike(pattern), Parcel.crop.ilike(pattern)))
    if campaign_id is not None:
        filters.append(Harvest.campaign_id == campaign_id)
    if farm_id is not None:
        filters.append(Parcel.farm_id == farm_id)
    total = await session.scalar(
        select(func.count())
        .select_from(Harvest)
        .join(
            Parcel,
            (Harvest.parcel_id == Parcel.id) & (Harvest.organization_id == Parcel.organization_id),
        )
        .where(*filters)
    )
    result = await session.execute(
        select(Harvest, Parcel, Campaign)
        .join(
            Parcel,
            (Harvest.parcel_id == Parcel.id) & (Harvest.organization_id == Parcel.organization_id),
        )
        .outerjoin(
            Campaign,
            (Campaign.id == Harvest.campaign_id)
            & (Campaign.organization_id == Harvest.organization_id),
        )
        .where(*filters)
        .order_by(Harvest.harvest_date.desc(), Harvest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return HarvestPageResponse(
        items=[
            HarvestResponse(
                id=harvest.id,
                parcel_id=parcel.id,
                parcel_name=parcel.name,
                crop=parcel.crop,
                campaign_id=harvest.campaign_id,
                campaign_name=campaign.name if campaign else None,
                harvest_date=harvest.harvest_date,
                quantity_kg=harvest.quantity_kg,
                notes=harvest.notes,
                created_at=harvest.created_at,
            )
            for harvest, parcel, campaign in result.all()
        ],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/finance/transactions",
    response_model=FinanceTransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer une recette ou une dépense",
)
async def create_finance_transaction(
    data: CreateFinanceTransactionRequest,
    session: SessionDep,
    context: CanManageAgricultureDep,
) -> FinanceTransactionResponse:
    if data.category == "commercialization":
        raise HTTPException(
            status_code=422,
            detail="Utilisez l'action de commercialisation d'une campagne clôturée.",
        )
    farm = await session.scalar(
        select(Farm).where(
            Farm.id == data.farm_id,
            Farm.organization_id == context.organization.id,
        )
    )
    if farm is None:
        raise HTTPException(status_code=404, detail="Ferme introuvable.")
    if data.campaign_id is not None:
        campaign = await session.scalar(
            select(Campaign)
            .join(
                Parcel,
                (Parcel.id == Campaign.parcel_id)
                & (Parcel.organization_id == Campaign.organization_id),
            )
            .where(
                Campaign.id == data.campaign_id,
                Campaign.organization_id == context.organization.id,
                Parcel.farm_id == farm.id,
                Campaign.status != CampaignStatus.ARCHIVED.value,
            )
        )
        if campaign is None:
            raise HTTPException(
                status_code=404,
                detail="Campagne introuvable dans cette ferme ou archivée.",
            )
    transaction = FinanceTransaction(
        id=uuid.uuid4(),
        organization_id=context.organization.id,
        farm_id=farm.id,
        campaign_id=data.campaign_id,
        created_by_id=context.user.id,
        transaction_type=data.transaction_type,
        category=data.category,
        label=data.label,
        amount_fcfa=data.amount_fcfa,
        transaction_date=data.transaction_date,
        quantity=data.quantity,
        unit=data.unit,
        customer_name=data.customer_name,
        notes=data.notes,
    )
    session.add(transaction)
    await session.commit()
    return await _finance_response(session, transaction)


@router.get(
    "/finance/transactions",
    response_model=FinanceTransactionPageResponse,
    summary="Lister les mouvements financiers",
)
async def list_finance_transactions(
    session: SessionDep,
    context: CanViewAgricultureFinanceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    year: Annotated[int, Query(ge=2000, le=2100)] = date.today().year,
    transaction_type: Annotated[str | None, Query(alias="type")] = None,
    farm_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
) -> FinanceTransactionPageResponse:
    filters = [
        FinanceTransaction.organization_id == context.organization.id,
        FinanceTransaction.transaction_date >= date(year, 1, 1),
        FinanceTransaction.transaction_date < date(year + 1, 1, 1),
    ]
    if transaction_type is not None:
        if transaction_type not in (FinanceType.INCOME.value, FinanceType.EXPENSE.value):
            raise HTTPException(status_code=422, detail="Type financier invalide.")
        filters.append(FinanceTransaction.transaction_type == transaction_type)
    if farm_id is not None:
        filters.append(FinanceTransaction.farm_id == farm_id)
    if campaign_id is not None:
        filters.append(FinanceTransaction.campaign_id == campaign_id)
    total = await session.scalar(
        select(func.count()).select_from(FinanceTransaction).where(*filters)
    )
    rows = await session.scalars(
        select(FinanceTransaction)
        .where(*filters)
        .order_by(FinanceTransaction.transaction_date.desc(), FinanceTransaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [await _finance_response(session, transaction) for transaction in rows]
    return FinanceTransactionPageResponse(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/finance/summary", response_model=FinanceSummaryResponse)
async def read_finance_summary(
    session: SessionDep,
    context: CanViewAgricultureFinanceDep,
    year: Annotated[int, Query(ge=2000, le=2100)] = date.today().year,
    farm_id: uuid.UUID | None = None,
) -> FinanceSummaryResponse:
    filters = [
        FinanceTransaction.organization_id == context.organization.id,
        FinanceTransaction.transaction_date >= date(year, 1, 1),
        FinanceTransaction.transaction_date < date(year + 1, 1, 1),
    ]
    if farm_id is not None:
        filters.append(FinanceTransaction.farm_id == farm_id)
    summary = await session.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            FinanceTransaction.transaction_type == FinanceType.INCOME.value,
                            FinanceTransaction.amount_fcfa,
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
                            FinanceTransaction.transaction_type == FinanceType.EXPENSE.value,
                            FinanceTransaction.amount_fcfa,
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
                            FinanceTransaction.category == "input",
                            FinanceTransaction.amount_fcfa,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(*filters)
    )
    income, expenses, input_expenses = summary.one()
    month_rows = await session.execute(
        select(
            func.extract("month", FinanceTransaction.transaction_date),
            func.sum(
                case(
                    (
                        FinanceTransaction.transaction_type == FinanceType.INCOME.value,
                        FinanceTransaction.amount_fcfa,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        FinanceTransaction.transaction_type == FinanceType.EXPENSE.value,
                        FinanceTransaction.amount_fcfa,
                    ),
                    else_=0,
                )
            ),
        )
        .where(*filters)
        .group_by(func.extract("month", FinanceTransaction.transaction_date))
    )
    incomes = [0] * 12
    expenses_by_month = [0] * 12
    for month_number, monthly_income, monthly_expenses in month_rows:
        month_index = int(month_number) - 1
        incomes[month_index] = int(monthly_income or 0)
        expenses_by_month[month_index] = int(monthly_expenses or 0)

    def monthly_response(amounts: list[int]) -> list[MonthlyFinanceResponse]:
        return [
            MonthlyFinanceResponse(
                month=month,
                month_number=index + 1,
                amount_fcfa=amount,
            )
            for index, (month, amount) in enumerate(zip(MONTH_LABELS, amounts, strict=True))
        ]

    return FinanceSummaryResponse(
        year=year,
        income_fcfa=int(income),
        expenses_fcfa=int(expenses),
        balance_fcfa=int(income) - int(expenses),
        input_expenses_fcfa=int(input_expenses),
        monthly_income=monthly_response(incomes),
        monthly_expenses=monthly_response(expenses_by_month),
    )
