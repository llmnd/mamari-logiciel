"""Store public contact inquiries and newsletter consent.

Revision ID: 0023_public_site_inquiries
Revises: 0022_stock_thresholds_audit_approvals
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_public_site_inquiries"
down_revision: str | None = "0022_stock_thresholds_audit_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = sa.Uuid(as_uuid=True).with_variant(postgresql.UUID(as_uuid=True), "postgresql")
    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("organization_id", uuid_type, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("unsubscribe_token", uuid_type, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_newsletter_subscribers_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "email", name="uq_newsletter_org_email"),
        sa.UniqueConstraint("unsubscribe_token", name="uq_newsletter_unsubscribe_token"),
    )
    op.create_index(
        "ix_newsletter_org_active_created",
        "newsletter_subscribers",
        ["organization_id", "is_active", "created_at"],
    )
    op.create_table(
        "contact_inquiries",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("organization_id", uuid_type, nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('new', 'read', 'replied')",
            name="ck_contact_inquiries_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_contact_inquiries_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contact_inquiries_org_status_created",
        "contact_inquiries",
        ["organization_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_contact_inquiries_org_status_created",
        table_name="contact_inquiries",
    )
    op.drop_table("contact_inquiries")
    op.drop_index(
        "ix_newsletter_org_active_created",
        table_name="newsletter_subscribers",
    )
    op.drop_table("newsletter_subscribers")
