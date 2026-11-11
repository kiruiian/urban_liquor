"""Add staff accounts for authentication.

Revision ID: 0002_staff_authentication
Revises: 0001_pos_catalog_and_sales
Create Date: 2026-11-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_staff_authentication"
down_revision: Union[str, None] = "0001_pos_catalog_and_sales"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('owner', 'cashier')", name="ck_staff_role_valid"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_staff_email", "staff", ["email"])


def downgrade() -> None:
    op.drop_index("ix_staff_email", table_name="staff")
    op.drop_table("staff")
