import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from mamari_api.modules.audit.models import ApprovalRequest, AuditEvent
from mamari_api.modules.audit.schemas import (
    ApprovalResponse,
    AuditEventPageResponse,
    AuditEventResponse,
    CreateApprovalRequest,
    ReviewApprovalRequest,
)
from mamari_api.modules.audit.service import record_audit_event
from mamari_api.modules.identity.dependencies import (
    CurrentMembership,
    SessionDep,
    get_current_membership,
    require_roles,
)
from mamari_api.modules.identity.models import User
from mamari_api.modules.sales.models import (
    OrderStatus,
    Product,
    SalesOrder,
    SalesOrderStatusEvent,
)
from mamari_api.modules.stocks.models import StockItem
from mamari_api.modules.stocks.service import record_stock_movement

router = APIRouter(prefix="/audit")
CurrentOrganizationDep = Annotated[CurrentMembership, Depends(get_current_membership)]
CanApproveDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager")),
]
CanOperateDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager", "operator")),
]
APPROVER_ROLES = {"owner", "admin", "manager"}


async def _approval_response(
    session: AsyncSession,
    approval: ApprovalRequest,
) -> ApprovalResponse:
    requester_name = (
        await session.scalar(select(User.full_name).where(User.id == approval.requester_id))
        if approval.requester_id is not None
        else None
    )
    reviewer_name = (
        await session.scalar(select(User.full_name).where(User.id == approval.reviewer_id))
        if approval.reviewer_id is not None
        else None
    )
    return ApprovalResponse(
        id=approval.id,
        action=approval.action,
        resource_id=approval.resource_id,
        payload=approval.payload,
        reason=approval.reason,
        status=approval.status,
        requester_id=approval.requester_id,
        requester_name=requester_name,
        reviewer_id=approval.reviewer_id,
        reviewer_name=reviewer_name,
        review_note=approval.review_note,
        created_at=approval.created_at,
        reviewed_at=approval.reviewed_at,
    )


@router.get("/events", response_model=AuditEventPageResponse)
async def list_audit_events(
    session: SessionDep,
    context: CurrentOrganizationDep,
    module: Annotated[str | None, Query(pattern="^(sales|stocks|agriculture|livestock)$")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 30,
) -> AuditEventPageResponse:
    filters = [AuditEvent.organization_id == context.organization.id]
    if module:
        filters.append(AuditEvent.module == module)
    total = await session.scalar(select(func.count()).select_from(AuditEvent).where(*filters))
    actor = aliased(User)
    rows = await session.execute(
        select(AuditEvent, actor.full_name)
        .outerjoin(actor, actor.id == AuditEvent.actor_id)
        .where(*filters)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return AuditEventPageResponse(
        items=[
            AuditEventResponse(
                id=event.id,
                module=event.module,
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                summary=event.summary,
                actor_name=actor_name,
                created_at=event.created_at,
            )
            for event, actor_name in rows
        ],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/requests", response_model=list[ApprovalResponse])
async def list_approval_requests(
    session: SessionDep,
    context: CanOperateDep,
    status: Annotated[str, Query(pattern="^(pending|approved|rejected)$")] = "pending",
) -> list[ApprovalResponse]:
    filters = [
        ApprovalRequest.organization_id == context.organization.id,
        ApprovalRequest.status == status,
    ]
    if context.membership.role not in APPROVER_ROLES:
        filters.append(ApprovalRequest.requester_id == context.user.id)
    requests = await session.scalars(
        select(ApprovalRequest)
        .where(*filters)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(100)
    )
    return [await _approval_response(session, approval) for approval in requests]


@router.post("/requests", response_model=ApprovalResponse, status_code=201)
async def create_approval_request(
    data: CreateApprovalRequest,
    session: SessionDep,
    context: CanOperateDep,
) -> ApprovalResponse:
    if context.membership.role != "operator":
        raise HTTPException(
            status_code=403,
            detail="Seul un opérateur doit soumettre une demande d’approbation.",
        )
    stock_item = None
    order = None
    if data.action == "stock_adjustment":
        stock_item = await session.scalar(
            select(StockItem).where(
                StockItem.id == data.resource_id,
                StockItem.organization_id == context.organization.id,
            )
        )
        resource_exists = stock_item
    else:
        order = await session.scalar(
            select(SalesOrder).where(
                SalesOrder.id == data.resource_id,
                SalesOrder.organization_id == context.organization.id,
                SalesOrder.status == OrderStatus.PENDING.value,
            )
        )
        resource_exists = order
    if resource_exists is None:
        raise HTTPException(status_code=404, detail="Élément concerné introuvable.")
    pending = await session.scalar(
        select(ApprovalRequest.id).where(
            ApprovalRequest.organization_id == context.organization.id,
            ApprovalRequest.action == data.action,
            ApprovalRequest.resource_id == data.resource_id,
            ApprovalRequest.status == "pending",
        )
    )
    if pending is not None:
        raise HTTPException(
            status_code=409,
            detail="Une demande similaire est déjà en attente d’approbation.",
        )
    payload: dict[str, object] = {}
    if data.action == "stock_adjustment":
        if data.quantity is None or data.direction is None or stock_item is None:
            raise HTTPException(
                status_code=422,
                detail="Un ajustement nécessite une quantité et un sens.",
            )
        payload = {
            "quantity": str(data.quantity),
            "direction": data.direction,
            "movement_date": data.movement_date.isoformat(),
            "item_name": stock_item.name,
            "unit": stock_item.unit,
        }
    elif order is not None:
        payload = {
            "order_reference": order.reference,
            "customer_name": order.customer_name,
        }
    approval = ApprovalRequest(
        organization_id=context.organization.id,
        requester_id=context.user.id,
        action=data.action,
        resource_id=data.resource_id,
        payload=payload,
        reason=data.reason,
        status="pending",
    )
    session.add(approval)
    await record_audit_event(
        session,
        organization_id=context.organization.id,
        actor_id=context.user.id,
        module="stocks" if data.action == "stock_adjustment" else "sales",
        action="approval_requested",
        entity_type=data.action,
        entity_id=data.resource_id,
        summary="Demande d’approbation soumise.",
    )
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Une demande similaire est déjà en attente d’approbation.",
        ) from error
    await session.refresh(approval)
    return await _approval_response(session, approval)


@router.patch("/requests/{request_id}", response_model=ApprovalResponse)
async def review_approval_request(
    request_id: uuid.UUID,
    data: ReviewApprovalRequest,
    session: SessionDep,
    context: CanApproveDep,
) -> ApprovalResponse:
    approval = await session.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.id == request_id,
            ApprovalRequest.organization_id == context.organization.id,
        )
        .with_for_update()
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Demande d’approbation introuvable.")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="Cette demande a déjà été traitée.")
    if approval.requester_id == context.user.id:
        raise HTTPException(
            status_code=403,
            detail="Vous ne pouvez pas approuver votre propre demande.",
        )

    if data.decision == "approved" and approval.action == "stock_adjustment":
        item = await session.scalar(
            select(StockItem)
            .where(
                StockItem.id == approval.resource_id,
                StockItem.organization_id == context.organization.id,
            )
            .with_for_update()
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
        await record_stock_movement(
            session,
            organization_id=context.organization.id,
            stock_item=item,
            movement_type="adjustment",
            direction=str(approval.payload["direction"]),
            quantity=Decimal(str(approval.payload["quantity"])),
            movement_date=datetime.fromisoformat(str(approval.payload["movement_date"])).date(),
            created_by_id=context.user.id,
            note=f"Ajustement approuvé : {approval.reason}",
            reference_type="approval_request",
            reference_id=approval.id,
        )
    elif data.decision == "approved":
        order = await session.scalar(
            select(SalesOrder)
            .options(selectinload(SalesOrder.items))
            .where(
                SalesOrder.id == approval.resource_id,
                SalesOrder.organization_id == context.organization.id,
            )
            .with_for_update()
        )
        if order is None:
            raise HTTPException(status_code=404, detail="Commande introuvable.")
        if order.status != OrderStatus.PENDING.value:
            raise HTTPException(
                status_code=409,
                detail="Seule une commande en attente peut être annulée par approbation.",
            )
        product_ids = sorted(
            {item.product_id for item in order.items if item.product_id is not None}
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
        for order_item in order.items:
            if order_item.product_id is None:
                continue
            stock_item = await session.scalar(
                select(StockItem)
                .where(
                    StockItem.organization_id == context.organization.id,
                    StockItem.product_id == order_item.product_id,
                )
                .with_for_update()
            )
            if stock_item is not None:
                await record_stock_movement(
                    session,
                    organization_id=context.organization.id,
                    stock_item=stock_item,
                    movement_type="cancellation",
                    direction="in",
                    quantity=order_item.quantity,
                    movement_date=datetime.now(UTC).date(),
                    created_by_id=context.user.id,
                    note=f"Annulation approuvée de la commande {order.reference}.",
                    reference_type="order_cancelled_item",
                    reference_id=order_item.id,
                )
        order.status = OrderStatus.CANCELLED.value
        order.status_history.append(
            SalesOrderStatusEvent(status=OrderStatus.CANCELLED.value, actor_id=context.user.id)
        )

    approval.status = data.decision
    approval.reviewer_id = context.user.id
    approval.review_note = data.review_note
    approval.reviewed_at = datetime.now(UTC)
    await record_audit_event(
        session,
        organization_id=context.organization.id,
        actor_id=context.user.id,
        module="stocks" if approval.action == "stock_adjustment" else "sales",
        action=f"approval_{data.decision}",
        entity_type=approval.action,
        entity_id=approval.resource_id,
        summary="Demande approuvée." if data.decision == "approved" else "Demande refusée.",
    )
    await session.commit()
    await session.refresh(approval)
    return await _approval_response(session, approval)
