import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from mamari_api.modules.agriculture.models import FinanceTransaction, Harvest, Parcel
from mamari_api.modules.dashboard.schemas import (
    DashboardOverviewResponse,
    LivestockQuantitySummary,
    MonthlyProductionResponse,
    MonthlySalesResponse,
    OperationsReportResponse,
    RecentHarvestResponse,
    ReportPeriodSummary,
    StockMovementUnitSummary,
)
from mamari_api.modules.identity.dependencies import (
    CurrentMembership,
    SessionDep,
    get_current_membership,
)
from mamari_api.modules.livestock.models import LivestockFinanceTransaction, LivestockRecord
from mamari_api.modules.operations.models import OperationTask
from mamari_api.modules.sales.models import OrderStatus, SalesOrder
from mamari_api.modules.stocks.models import StockItem, StockMovement

router = APIRouter(prefix="/dashboard")
CurrentOrganizationDep = Annotated[
    CurrentMembership,
    Depends(get_current_membership),
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
REVENUE_STATUSES = (
    OrderStatus.CONFIRMED.value,
    OrderStatus.PREPARING.value,
    OrderStatus.DELIVERED.value,
)


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="Indicateurs réels du tableau de bord",
)
async def read_dashboard_overview(
    session: SessionDep,
    context: CurrentOrganizationDep,
    year: Annotated[int, Query(ge=2000, le=2100)] = date.today().year,
) -> DashboardOverviewResponse:
    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)
    organization_id = context.organization.id
    today = date.today()
    financial_access = context.membership.role in {"owner", "admin", "manager"}
    order_filters = (
        SalesOrder.organization_id == organization_id,
        SalesOrder.order_date >= year_start,
        SalesOrder.order_date < year_end,
    )
    harvest_filters = (
        Harvest.organization_id == organization_id,
        Harvest.harvest_date >= year_start,
        Harvest.harvest_date < year_end,
    )

    revenue_by_month = [0] * 12
    if financial_access:
        sales_months = await session.execute(
            select(
                func.extract("month", SalesOrder.order_date),
                func.sum(SalesOrder.amount_fcfa),
            )
            .where(
                *order_filters,
                SalesOrder.status.in_(REVENUE_STATUSES),
            )
            .group_by(func.extract("month", SalesOrder.order_date))
        )
        for month_number, amount in sales_months:
            revenue_by_month[int(month_number) - 1] = int(amount or 0)

    active_order = SalesOrder.status != OrderStatus.CANCELLED.value
    revenue_order = SalesOrder.status.in_(REVENUE_STATUSES)
    sales_stats = (
        await session.execute(
            select(
                func.count(case((active_order, 1), else_=None)),
                func.count(
                    case(
                        (
                            SalesOrder.status.in_(
                                (
                                    OrderStatus.PENDING.value,
                                    OrderStatus.CONFIRMED.value,
                                    OrderStatus.PREPARING.value,
                                )
                            ),
                            1,
                        ),
                        else_=None,
                    )
                ),
                func.count(
                    func.distinct(
                        case(
                            (active_order, func.lower(SalesOrder.customer_name)),
                            else_=None,
                        )
                    )
                ),
                (
                    func.avg(case((revenue_order, SalesOrder.amount_fcfa), else_=None))
                    if financial_access
                    else null()
                ),
            ).where(*order_filters)
        )
    ).one()
    recent_orders = await session.scalars(
        select(SalesOrder)
        .where(*order_filters)
        .order_by(SalesOrder.order_date.desc(), SalesOrder.created_at.desc())
        .limit(5)
    )

    production_by_month = [0.0] * 12
    harvest_months = await session.execute(
        select(
            func.extract("month", Harvest.harvest_date),
            func.sum(Harvest.quantity_kg),
        )
        .where(*harvest_filters)
        .group_by(func.extract("month", Harvest.harvest_date))
    )
    for month_number, quantity in harvest_months:
        production_by_month[int(month_number) - 1] = float(quantity or 0)

    production_stats = (
        await session.execute(
            select(
                func.coalesce(func.sum(Harvest.quantity_kg), 0),
                func.count(Harvest.id),
            ).where(*harvest_filters)
        )
    ).one()
    parcel_count = await session.scalar(
        select(func.count())
        .select_from(Parcel)
        .where(
            Parcel.organization_id == organization_id,
            Parcel.is_active.is_(True),
        )
    )
    task_filters = [
        OperationTask.organization_id == organization_id,
        OperationTask.status.in_(("todo", "in_progress")),
    ]
    if context.membership.role == "operator":
        task_filters.append(OperationTask.assigned_user_id == context.user.id)
    task_counts = (
        await session.execute(
            select(
                func.count(OperationTask.id),
                func.count(
                    case(
                        (
                            OperationTask.due_date < today,
                            OperationTask.id,
                        )
                    )
                ),
            ).where(*task_filters)
        )
    ).one()
    overdue_care_count = await session.scalar(
        select(func.count(LivestockRecord.id)).where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.record_type == "health",
            LivestockRecord.next_due_date < today,
            LivestockRecord.is_resolved.is_(False),
        )
    )
    stock_balance = func.coalesce(
        func.sum(
            case(
                (StockMovement.direction == "in", StockMovement.quantity),
                else_=-StockMovement.quantity,
            )
        ),
        0,
    )
    stock_balances = (
        select(StockItem.id)
        .outerjoin(
            StockMovement,
            (StockMovement.stock_item_id == StockItem.id)
            & (StockMovement.organization_id == StockItem.organization_id),
        )
        .where(StockItem.organization_id == organization_id)
        .group_by(StockItem.id)
        .having(
            StockItem.minimum_quantity.is_not(None),
            stock_balance <= StockItem.minimum_quantity,
        )
        .subquery()
    )
    restock_item_count = await session.scalar(select(func.count()).select_from(stock_balances))
    recent_harvests = await session.execute(
        select(Harvest, Parcel)
        .join(
            Parcel,
            (Parcel.id == Harvest.parcel_id) & (Parcel.organization_id == Harvest.organization_id),
        )
        .where(*harvest_filters)
        .order_by(Harvest.harvest_date.desc(), Harvest.created_at.desc())
        .limit(5)
    )

    return DashboardOverviewResponse(
        year=year,
        financial_access=financial_access,
        revenue_fcfa=sum(revenue_by_month) if financial_access else None,
        order_count=sales_stats[0],
        pending_order_count=sales_stats[1],
        customer_count=sales_stats[2],
        average_order_fcfa=round(float(sales_stats[3] or 0)) if financial_access else None,
        open_task_count=task_counts[0],
        overdue_task_count=task_counts[1],
        overdue_care_count=overdue_care_count or 0,
        restock_item_count=restock_item_count or 0,
        production_kg=float(production_stats[0] or 0),
        harvest_count=production_stats[1],
        parcel_count=parcel_count or 0,
        monthly_revenue=(
            [
                MonthlySalesResponse(
                    month=label,
                    month_number=index + 1,
                    amount_fcfa=amount,
                )
                for index, (label, amount) in enumerate(
                    zip(MONTH_LABELS, revenue_by_month, strict=True)
                )
            ]
            if financial_access
            else None
        ),
        monthly_production_kg=[
            MonthlyProductionResponse(
                month=label,
                month_number=index + 1,
                quantity_kg=quantity,
            )
            for index, (label, quantity) in enumerate(
                zip(MONTH_LABELS, production_by_month, strict=True)
            )
        ],
        recent_orders=list(recent_orders.all()),
        recent_harvests=[
            RecentHarvestResponse(
                id=harvest.id,
                parcel_name=parcel.name,
                crop=parcel.crop,
                harvest_date=harvest.harvest_date,
                quantity_kg=float(harvest.quantity_kg),
            )
            for harvest, parcel in recent_harvests.all()
        ],
    )


async def _report_period_summary(
    session: AsyncSession,
    organization_id: uuid.UUID,
    start_date: date,
    end_date: date,
    financial_access: bool,
) -> ReportPeriodSummary:
    revenue_statuses = (
        OrderStatus.CONFIRMED.value,
        OrderStatus.PREPARING.value,
        OrderStatus.DELIVERED.value,
    )
    order_count, revenue = (
        await session.execute(
            select(
                func.count(SalesOrder.id),
                func.coalesce(
                    func.sum(
                        case(
                            (SalesOrder.status.in_(revenue_statuses), SalesOrder.amount_fcfa),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(
                SalesOrder.organization_id == organization_id,
                SalesOrder.order_date >= start_date,
                SalesOrder.order_date <= end_date,
                SalesOrder.status != OrderStatus.CANCELLED.value,
            )
        )
    ).one()
    movement_count = (
        await session.execute(
            select(func.count(StockMovement.id)).where(
                StockMovement.organization_id == organization_id,
                StockMovement.movement_date >= start_date,
                StockMovement.movement_date <= end_date,
            )
        )
    ).scalar_one()
    movement_units = await session.execute(
        select(
            StockItem.unit,
            StockMovement.direction,
            func.sum(StockMovement.quantity),
        )
        .join(
            StockItem,
            (StockItem.id == StockMovement.stock_item_id)
            & (StockItem.organization_id == StockMovement.organization_id),
        )
        .where(
            StockMovement.organization_id == organization_id,
            StockMovement.movement_date >= start_date,
            StockMovement.movement_date <= end_date,
        )
        .group_by(StockItem.unit, StockMovement.direction)
    )
    stock_quantities: dict[str, dict[str, float]] = {}
    for unit, direction, quantity in movement_units:
        stock_quantities.setdefault(unit, {"in": 0.0, "out": 0.0})[direction] = float(quantity or 0)
    harvest_count, harvest_quantity = (
        await session.execute(
            select(func.count(Harvest.id), func.coalesce(func.sum(Harvest.quantity_kg), 0)).where(
                Harvest.organization_id == organization_id,
                Harvest.harvest_date >= start_date,
                Harvest.harvest_date <= end_date,
            )
        )
    ).one()
    livestock_record_count = (
        await session.execute(
            select(func.count(LivestockRecord.id)).where(
                LivestockRecord.organization_id == organization_id,
                LivestockRecord.event_date >= start_date,
                LivestockRecord.event_date <= end_date,
            )
        )
    ).scalar_one()
    livestock_unit_rows = await session.execute(
        select(LivestockRecord.unit, func.sum(LivestockRecord.quantity))
        .where(
            LivestockRecord.organization_id == organization_id,
            LivestockRecord.event_date >= start_date,
            LivestockRecord.event_date <= end_date,
            LivestockRecord.quantity.is_not(None),
        )
        .group_by(LivestockRecord.unit)
        .order_by(LivestockRecord.unit)
    )
    agriculture_income = agriculture_expense = None
    livestock_income = livestock_expense = None
    if financial_access:
        agriculture_income, agriculture_expense = (
            await session.execute(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    FinanceTransaction.transaction_type == "income",
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
                                    FinanceTransaction.transaction_type == "expense",
                                    FinanceTransaction.amount_fcfa,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).where(
                    FinanceTransaction.organization_id == organization_id,
                    FinanceTransaction.source == "agriculture",
                    FinanceTransaction.transaction_date >= start_date,
                    FinanceTransaction.transaction_date <= end_date,
                )
            )
        ).one()
        livestock_income, livestock_expense = (
            await session.execute(
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
                ).where(
                    LivestockFinanceTransaction.organization_id == organization_id,
                    LivestockFinanceTransaction.transaction_date >= start_date,
                    LivestockFinanceTransaction.transaction_date <= end_date,
                )
            )
        ).one()
    return ReportPeriodSummary(
        start_date=start_date,
        end_date=end_date,
        order_count=order_count,
        revenue_fcfa=int(revenue) if financial_access else None,
        stock_movement_count=movement_count,
        stock_quantities=[
            StockMovementUnitSummary(
                unit=unit,
                quantity_in=quantities["in"],
                quantity_out=quantities["out"],
            )
            for unit, quantities in sorted(stock_quantities.items())
        ],
        harvest_count=harvest_count,
        harvest_quantity_kg=float(harvest_quantity),
        agriculture_income_fcfa=(
            int(agriculture_income) if agriculture_income is not None else None
        ),
        agriculture_expense_fcfa=(
            int(agriculture_expense) if agriculture_expense is not None else None
        ),
        livestock_record_count=livestock_record_count,
        livestock_quantities=[
            LivestockQuantitySummary(unit=unit, quantity=float(quantity or 0))
            for unit, quantity in livestock_unit_rows
        ],
        livestock_income_fcfa=int(livestock_income) if livestock_income is not None else None,
        livestock_expense_fcfa=int(livestock_expense) if livestock_expense is not None else None,
    )


@router.get(
    "/reports/summary",
    response_model=OperationsReportResponse,
    summary="Comparer les rapports opérationnels sur deux périodes équivalentes",
)
async def read_operations_report(
    session: SessionDep,
    context: CurrentOrganizationDep,
    start_date: Annotated[date, Query()],
    end_date: Annotated[date, Query()],
) -> OperationsReportResponse:
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="La date de début doit précéder ou égaler la date de fin.",
        )
    period_days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    financial_access = context.membership.role in {"owner", "admin", "manager"}
    return OperationsReportResponse(
        financial_access=financial_access,
        current=await _report_period_summary(
            session,
            context.organization.id,
            start_date,
            end_date,
            financial_access,
        ),
        previous=await _report_period_summary(
            session,
            context.organization.id,
            previous_start,
            previous_end,
            financial_access,
        ),
    )
