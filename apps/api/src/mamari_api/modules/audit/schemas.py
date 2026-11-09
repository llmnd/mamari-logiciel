import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

ApprovalAction = Literal["stock_adjustment", "order_cancellation"]


class CreateApprovalRequest(BaseModel):
    action: ApprovalAction
    resource_id: uuid.UUID
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1000)]
    quantity: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)] | None = None
    direction: Literal["in", "out"] | None = None
    movement_date: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def validate_action_payload(self) -> "CreateApprovalRequest":
        if self.action == "stock_adjustment" and (self.quantity is None or self.direction is None):
            raise ValueError("Un ajustement nécessite une quantité et un sens.")
        if self.action == "order_cancellation" and (
            self.quantity is not None or self.direction is not None
        ):
            raise ValueError("Une annulation ne peut pas contenir un ajustement de stock.")
        return self


class ReviewApprovalRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    review_note: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None
    ) = None


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    action: ApprovalAction
    resource_id: uuid.UUID
    payload: dict[str, object]
    reason: str
    status: Literal["pending", "approved", "rejected"]
    requester_id: uuid.UUID | None
    requester_name: str | None
    reviewer_id: uuid.UUID | None
    reviewer_name: str | None
    review_note: str | None
    created_at: datetime
    reviewed_at: datetime | None


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    module: str
    action: str
    entity_type: str
    entity_id: str | None
    summary: str
    actor_name: str | None
    created_at: datetime


class AuditEventPageResponse(BaseModel):
    items: list[AuditEventResponse]
    total: int
    page: int
    page_size: int
