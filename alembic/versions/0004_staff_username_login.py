"""Use usernames for staff login.

Revision ID: 0004_staff_username_login
Revises: 0003_owner_role_to_admin
Create Date: 2026-11-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_staff_username_login"
down_revision: Union[str, None] = "0003_owner_role_to_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_staff_email", table_name="staff")
    op.alter_column(
        "staff",
        "email",
        new_column_name="username",
        existing_type=sa.String(length=254),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "staff",
        "username",
        new_column_name="email",
        existing_type=sa.String(length=254),
        existing_nullable=False,
    )
    op.create_index("ix_staff_email", "staff", ["email"])
