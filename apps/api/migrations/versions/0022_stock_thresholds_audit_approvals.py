"""Add stock thresholds, audit events and approval requests.

Revision ID: 0022_stock_thresholds_audit_approvals
Revises: 0021_sales_order_status_history
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_stock_thresholds_audit_approvals"
down_revision: str | None = "0021_sales_order_status_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = sa.Uuid(as_uuid=True).with_variant(postgresql.UUID(as_uuid=True), "postgresql")
    op.add_column(
        "stock_items",
        sa.Column("minimum_quantity", sa.Numeric(14, 3), nullable=True),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("organization_id", uuid_type, nullable=False),
        sa.Column("actor_id", uuid_type, nullable=True),
        sa.Column("module", sa.String(length=24), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("summary", sa.String(length=240), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "module IN ('sales', 'stocks', 'agriculture', 'livestock')",
            name="ck_audit_events_module",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="fk_audit_events_actor_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_audit_events_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_org_created",
        "audit_events",
        ["organization_id", "created_at"],
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("organization_id", uuid_type, nullable=False),
        sa.Column("requester_id", uuid_type, nullable=True),
        sa.Column("reviewer_id", uuid_type, nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("resource_id", uuid_type, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action IN ('stock_adjustment', 'order_cancellation')",
            name="ck_approval_requests_action",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_approval_requests_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_approval_requests_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name="fk_approval_requests_requester_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name="fk_approval_requests_reviewer_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_requests_org_status",
        "approval_requests",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "uq_approval_requests_pending_resource",
        "approval_requests",
        ["organization_id", "action", "resource_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_approval_requests_pending_resource",
        table_name="approval_requests",
    )
    op.drop_index("ix_approval_requests_org_status", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index("ix_audit_events_org_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_column("stock_items", "minimum_quantity")
