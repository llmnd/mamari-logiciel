import uuid
from datetime import date

from pydantic import BaseModel

from mamari_api.modules.sales.schemas import SalesOrderResponse


class MonthlySalesResponse(BaseModel):
    month: str
    month_number: int
    amount_fcfa: int


class MonthlyProductionResponse(BaseModel):
    month: str
    month_number: int
    quantity_kg: float


class RecentHarvestResponse(BaseModel):
    id: uuid.UUID
    parcel_name: str
    crop: str
    harvest_date: date
    quantity_kg: float


class DashboardOverviewResponse(BaseModel):
    year: int
    financial_access: bool
    revenue_fcfa: int | None
    order_count: int
    pending_order_count: int
    customer_count: int
    average_order_fcfa: int | None
    open_task_count: int
    overdue_task_count: int
    overdue_care_count: int
    restock_item_count: int
    production_kg: float
    harvest_count: int
    parcel_count: int
    monthly_revenue: list[MonthlySalesResponse] | None
    monthly_production_kg: list[MonthlyProductionResponse]
    recent_orders: list[SalesOrderResponse]
    recent_harvests: list[RecentHarvestResponse]


class ReportPeriodSummary(BaseModel):
    start_date: date
    end_date: date
    order_count: int
    revenue_fcfa: int | None
    stock_movement_count: int
    stock_quantities: list["StockMovementUnitSummary"]
    harvest_count: int
    harvest_quantity_kg: float
    agriculture_income_fcfa: int | None
    agriculture_expense_fcfa: int | None
    livestock_record_count: int
    livestock_quantities: list["LivestockQuantitySummary"]
    livestock_income_fcfa: int | None
    livestock_expense_fcfa: int | None


class StockMovementUnitSummary(BaseModel):
    unit: str
    quantity_in: float
    quantity_out: float


class LivestockQuantitySummary(BaseModel):
    unit: str | None
    quantity: float


class OperationsReportResponse(BaseModel):
    financial_access: bool
    current: ReportPeriodSummary
    previous: ReportPeriodSummary
