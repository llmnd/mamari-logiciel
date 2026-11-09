import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mamari_api.modules.audit.service import record_audit_event
from mamari_api.modules.identity.dependencies import (
    CurrentMembership,
    SessionDep,
    get_current_membership,
    require_roles,
)
from mamari_api.modules.sales.models import Product
from mamari_api.modules.stocks.models import StockItem, StockMovement
from mamari_api.modules.stocks.schemas import (
    CreateStockItemRequest,
    CreateStockMovementRequest,
    StockItemResponse,
    StockMovementPageResponse,
    TransferStockRequest,
    UpdateStockItemRequest,
)
from mamari_api.modules.stocks.service import (
    get_stock_balance,
    record_stock_movement,
    synchronize_product_stock,
)

router = APIRouter(prefix="/stocks")
CurrentOrganizationDep = Annotated[CurrentMembership, Depends(get_current_membership)]
CanManageStockDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager")),
]
CanOperateStockDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager", "operator")),
]


async def _stock_item_response(session: AsyncSession, item: StockItem) -> StockItemResponse:
    product = None
    if item.product_id is not None:
        product = await session.scalar(
            select(Product).where(
                Product.id == item.product_id,
                Product.organization_id == item.organization_id,
            )
        )
    movement_count = await session.scalar(
        select(func.count())
        .select_from(StockMovement)
        .where(
            StockMovement.organization_id == item.organization_id,
            StockMovement.stock_item_id == item.id,
        )
    )
    return StockItemResponse(
        id=item.id,
        product_id=item.product_id,
        product_name=product.name if product else None,
        source=item.source,
        name=item.name,
        unit=item.unit,
        location=item.location,
        minimum_quantity=item.minimum_quantity,
        balance=await get_stock_balance(session, item.organization_id, item.id),
        movement_count=movement_count or 0,
        created_at=item.created_at,
    )


@router.get("/items", response_model=list[StockItemResponse])
async def list_stock_items(
    session: SessionDep,
    context: CurrentOrganizationDep,
    source: Annotated[str | None, Query(pattern="^(agriculture|elevage|other)$")] = None,
) -> list[StockItemResponse]:
    statement = select(StockItem).where(StockItem.organization_id == context.organization.id)
    if source is not None:
        statement = statement.where(StockItem.source == source)
    items = await session.scalars(
        statement.order_by(StockItem.source, StockItem.name, StockItem.location)
    )
    return [await _stock_item_response(session, item) for item in items]


@router.post(
    "/items",
    response_model=StockItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_stock_item(
    data: CreateStockItemRequest,
    session: SessionDep,
    context: CanManageStockDep,
) -> StockItemResponse:
    item = StockItem(
        organization_id=context.organization.id,
        source=data.source,
        name=data.name,
        unit=data.unit,
        location=data.location,
        minimum_quantity=data.minimum_quantity,
    )
    session.add(item)
    try:
        await session.flush()
        if data.opening_quantity > 0:
            await record_stock_movement(
                session,
                organization_id=context.organization.id,
                stock_item=item,
                movement_type="opening",
                direction="in",
                quantity=data.opening_quantity,
                movement_date=date.today(),
                created_by_id=context.user.id,
                note=data.note or "Inventaire physique initial",
            )
        await record_audit_event(
            session,
            organization_id=context.organization.id,
            actor_id=context.user.id,
            module="stocks",
            action="item_created",
            entity_type="stock_item",
            entity_id=item.id,
            summary=f"Article de stock créé : {item.name}.",
        )
        await session.commit()
        await session.refresh(item)
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Un stock existe déjà pour cette nature, cette unité et ce lieu.",
        ) from error
    return await _stock_item_response(session, item)


@router.patch("/items/{item_id}", response_model=StockItemResponse)
async def update_stock_item(
    item_id: uuid.UUID,
    data: UpdateStockItemRequest,
    session: SessionDep,
    context: CanManageStockDep,
) -> StockItemResponse:
    item = await session.scalar(
        select(StockItem).where(
            StockItem.id == item_id,
            StockItem.organization_id == context.organization.id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Article de stock introuvable.")
    product_ids = sorted(
        {product_id for product_id in (item.product_id, data.product_id) if product_id is not None}
    )
    products = await session.scalars(
        select(Product)
        .where(
            Product.id.in_(product_ids),
            Product.organization_id == context.organization.id,
        )
        .order_by(Product.id)
        .with_for_update()
    )
    products_by_id = {product.id: product for product in products.all()}
    if data.product_id is not None and data.product_id not in products_by_id:
        raise HTTPException(status_code=404, detail="Produit du catalogue introuvable.")
    item = await session.scalar(
        select(StockItem)
        .where(
            StockItem.id == item_id,
            StockItem.organization_id == context.organization.id,
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Article de stock introuvable.")
    if item.product_id not in product_ids and item.product_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Le produit lié a changé. Rechargez la page puis réessayez.",
        )
    if data.product_id is not None:
        product = products_by_id[data.product_id]
        if product.unit != item.unit:
            raise HTTPException(
                status_code=422,
                detail="L’unité du stock doit correspondre à celle du produit lié.",
            )
    previous_product_id = item.product_id
    item.source = data.source
    item.name = data.name
    item.location = data.location
    item.minimum_quantity = data.minimum_quantity
    item.product_id = data.product_id
    try:
        await session.flush()
        if previous_product_id is not None and previous_product_id != data.product_id:
            await synchronize_product_stock(
                session,
                context.organization.id,
                product_id=previous_product_id,
            )
        if data.product_id is not None and previous_product_id != data.product_id:
            await synchronize_product_stock(session, context.organization.id, item)
        await record_audit_event(
            session,
            organization_id=context.organization.id,
            actor_id=context.user.id,
            module="stocks",
            action="item_updated",
            entity_type="stock_item",
            entity_id=item.id,
            summary=f"Article de stock modifié : {item.name}.",
        )
        await session.commit()
        await session.refresh(item)
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Un stock existe déjà pour cette nature, cette unité et ce lieu.",
        ) from error
    return await _stock_item_response(session, item)


@router.post(
    "/items/{item_id}/movements",
    response_model=StockItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_stock_movement(
    item_id: uuid.UUID,
    data: CreateStockMovementRequest,
    session: SessionDep,
    context: CanOperateStockDep,
) -> StockItemResponse:
    if context.membership.role == "operator" and data.movement_type == "adjustment":
        raise HTTPException(
            status_code=403,
            detail="Soumettez une demande d’ajustement pour validation par un responsable.",
        )
    item = await session.scalar(
        select(StockItem).where(
            StockItem.id == item_id,
            StockItem.organization_id == context.organization.id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Article de stock introuvable.")
    if item.product_id is not None:
        await session.scalar(
            select(Product)
            .where(
                Product.id == item.product_id,
                Product.organization_id == context.organization.id,
            )
            .with_for_update()
        )
    item = await session.scalar(
        select(StockItem)
        .where(
            StockItem.id == item_id,
            StockItem.organization_id == context.organization.id,
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Article de stock introuvable.")
    expected_direction = {
        "addition": "in",
        "loss": "out",
        "consumption": "out",
    }.get(data.movement_type)
    direction = data.direction or expected_direction
    if direction is None:
        raise HTTPException(
            status_code=422,
            detail="Précisez si l’ajustement augmente ou diminue le stock.",
        )
    if expected_direction is not None and direction != expected_direction:
        raise HTTPException(status_code=422, detail="Le sens ne correspond pas au mouvement.")
    await record_stock_movement(
        session,
        organization_id=context.organization.id,
        stock_item=item,
        movement_type=data.movement_type,
        direction=direction,
        quantity=data.quantity,
        movement_date=data.movement_date,
        created_by_id=context.user.id,
        note=data.note,
    )
    await record_audit_event(
        session,
        organization_id=context.organization.id,
        actor_id=context.user.id,
        module="stocks",
        action="movement_recorded",
        entity_type="stock_item",
        entity_id=item.id,
        summary=f"Mouvement {data.movement_type} de {data.quantity} {item.unit} : {item.name}.",
    )
    await session.commit()
    await session.refresh(item)
    return await _stock_item_response(session, item)


@router.post(
    "/items/{item_id}/transfers",
    response_model=list[StockItemResponse],
    status_code=status.HTTP_201_CREATED,
)
async def transfer_stock(
    item_id: uuid.UUID,
    data: TransferStockRequest,
    session: SessionDep,
    context: CanManageStockDep,
) -> list[StockItemResponse]:
    items = await session.scalars(
        select(StockItem).where(
            StockItem.organization_id == context.organization.id,
            StockItem.id.in_([item_id, data.destination_item_id]),
        )
    )
    unlocked = {item.id: item for item in items.all()}
    if len(unlocked) != 2:
        raise HTTPException(status_code=404, detail="Stock source ou destination introuvable.")
    product_ids = sorted(
        {item.product_id for item in unlocked.values() if item.product_id is not None}
    )
    if product_ids:
        await session.scalars(
            select(Product)
            .where(
                Product.id.in_(product_ids),
                Product.organization_id == context.organization.id,
            )
            .order_by(Product.id)
            .with_for_update()
        )
    result = await session.scalars(
        select(StockItem)
        .where(
            StockItem.organization_id == context.organization.id,
            StockItem.id.in_([item_id, data.destination_item_id]),
        )
        .order_by(StockItem.id)
        .with_for_update()
    )
    items_by_id = {item.id: item for item in result.all()}
    source = items_by_id.get(item_id)
    destination = items_by_id.get(data.destination_item_id)
    if source is None or destination is None:
        raise HTTPException(status_code=404, detail="Stock source ou destination introuvable.")
    if source.id == destination.id or source.location == destination.location:
        raise HTTPException(status_code=422, detail="Choisissez un autre lieu de destination.")
    if source.name != destination.name or source.unit != destination.unit:
        raise HTTPException(
            status_code=422,
            detail="Un transfert doit concerner la même nature de stock et la même unité.",
        )
    transfer_id = uuid.uuid4()
    try:
        await record_stock_movement(
            session,
            organization_id=context.organization.id,
            stock_item=source,
            movement_type="transfer_out",
            direction="out",
            quantity=data.quantity,
            movement_date=data.movement_date,
            created_by_id=context.user.id,
            note=data.note,
            transfer_id=transfer_id,
        )
        await record_audit_event(
            session,
            organization_id=context.organization.id,
            actor_id=context.user.id,
            module="stocks",
            action="stock_transferred",
            entity_type="stock_item",
            entity_id=source.id,
            summary=(
                f"Transfert de {data.quantity} {source.unit} : "
                f"{source.location} vers {destination.location}."
            ),
        )
        await record_stock_movement(
            session,
            organization_id=context.organization.id,
            stock_item=destination,
            movement_type="transfer_in",
            direction="in",
            quantity=data.quantity,
            movement_date=data.movement_date,
            created_by_id=context.user.id,
            note=data.note,
            transfer_id=transfer_id,
        )
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except SQLAlchemyError:
        await session.rollback()
        raise
    await session.refresh(source)
    await session.refresh(destination)
    return [
        await _stock_item_response(session, source),
        await _stock_item_response(session, destination),
    ]


@router.get("/movements", response_model=StockMovementPageResponse)
async def list_stock_movements(
    session: SessionDep,
    context: CurrentOrganizationDep,
    item_id: uuid.UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> StockMovementPageResponse:
    item_exists = await session.scalar(
        select(StockItem.id).where(
            StockItem.id == item_id,
            StockItem.organization_id == context.organization.id,
        )
    )
    if item_exists is None:
        raise HTTPException(status_code=404, detail="Article de stock introuvable.")
    filters = [
        StockMovement.organization_id == context.organization.id,
        StockMovement.stock_item_id == item_id,
    ]
    total = await session.scalar(select(func.count()).select_from(StockMovement).where(*filters))
    movements = await session.scalars(
        select(StockMovement)
        .where(*filters)
        .order_by(StockMovement.movement_date.desc(), StockMovement.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return StockMovementPageResponse(
        items=list(movements.all()),
        total=total or 0,
        page=page,
        page_size=page_size,
    )
