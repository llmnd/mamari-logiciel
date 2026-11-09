import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from mamari_api.core.base import Base


class StockItem(Base):
    __tablename__ = "stock_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_stock_items_org_id"),
        CheckConstraint(
            "source IN ('agriculture', 'elevage', 'other')",
            name="ck_stock_items_source",
        ),
        Index("ix_stock_items_org_source", "organization_id", "source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False, default="Magasin")
    minimum_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "stock_item_id"],
            ["stock_items.organization_id", "stock_items.id"],
            name="fk_stock_movements_org_item",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id",
            "reference_type",
            "reference_id",
            name="uq_stock_movements_org_reference",
        ),
        CheckConstraint(
            "movement_type IN ('opening', 'production', 'sale', 'cancellation', "
            "'addition', 'loss', 'consumption', 'adjustment', 'transfer_in', 'transfer_out')",
            name="ck_stock_movements_type",
        ),
        CheckConstraint("direction IN ('in', 'out')", name="ck_stock_movements_direction"),
        CheckConstraint("quantity > 0", name="ck_stock_movements_quantity_positive"),
        Index(
            "ix_stock_movements_org_item_date",
            "organization_id",
            "stock_item_id",
            "movement_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    stock_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    movement_type: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    movement_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
