"""Store delivery location and estimated fees.

Revision ID: 0024_store_delivery_estimates
Revises: 0023_public_site_inquiries
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_store_delivery_estimates"
down_revision: str | None = "0023_public_site_inquiries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sales_orders",
        sa.Column("delivery_latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "sales_orders",
        sa.Column("delivery_longitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "sales_orders",
        sa.Column("delivery_distance_km", sa.Float(), nullable=True),
    )
    op.add_column(
        "sales_orders",
        sa.Column("delivery_fee_fcfa", sa.BigInteger(), nullable=True, server_default="0"),
    )
    op.add_column(
        "sales_orders",
        sa.Column(
            "delivery_quote_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("sales_orders", "delivery_fee_fcfa", server_default=None)
    op.alter_column("sales_orders", "delivery_quote_required", server_default=None)


def downgrade() -> None:
    op.drop_column("sales_orders", "delivery_quote_required")
    op.drop_column("sales_orders", "delivery_fee_fcfa")
    op.drop_column("sales_orders", "delivery_distance_km")
    op.drop_column("sales_orders", "delivery_longitude")
    op.drop_column("sales_orders", "delivery_latitude")
