import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

StockSource = Literal["agriculture", "elevage", "other"]
MovementType = Literal[
    "opening",
    "production",
    "sale",
    "cancellation",
    "addition",
    "loss",
    "consumption",
    "adjustment",
    "transfer_in",
    "transfer_out",
]
Direction = Literal["in", "out"]


class CreateStockItemRequest(BaseModel):
    source: StockSource = "other"
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]
    unit: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    location: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ] = "Magasin"
    minimum_quantity: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)] | None = None
    opening_quantity: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)] = Decimal(0)
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


class UpdateStockItemRequest(BaseModel):
    source: StockSource
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]
    location: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    minimum_quantity: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)] | None = None
    product_id: uuid.UUID | None = None


class CreateStockMovementRequest(BaseModel):
    movement_type: Literal["addition", "loss", "consumption", "adjustment"]
    direction: Direction | None = None
    quantity: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
    movement_date: date = Field(default_factory=date.today)
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1000)]


class TransferStockRequest(BaseModel):
    destination_item_id: uuid.UUID
    quantity: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
    movement_date: date = Field(default_factory=date.today)
    note: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1000)]
        | None
    ) = None


class StockItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    product_name: str | None
    source: StockSource
    name: str
    unit: str
    location: str
    minimum_quantity: Decimal | None
    balance: Decimal
    movement_count: int
    created_at: datetime


class StockMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stock_item_id: uuid.UUID
    movement_type: MovementType
    direction: Direction
    quantity: Decimal
    movement_date: date
    reference_type: str | None
    reference_id: uuid.UUID | None
    transfer_id: uuid.UUID | None
    note: str | None
    created_at: datetime


class StockMovementPageResponse(BaseModel):
    items: list[StockMovementResponse]
    total: int
    page: int
    page_size: int
