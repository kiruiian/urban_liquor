"""Rename owner staff role to admin.

Revision ID: 0003_owner_role_to_admin
Revises: 0002_staff_authentication
Create Date: 2026-11-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_owner_role_to_admin"
down_revision: Union[str, None] = "0002_staff_authentication"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_staff_role_valid", "staff", type_="check")
    op.execute(sa.text("UPDATE staff SET role = 'admin' WHERE role = 'owner'"))
    op.create_check_constraint(
        "ck_staff_role_valid", "staff", "role IN ('admin', 'cashier')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_staff_role_valid", "staff", type_="check")
    op.execute(sa.text("UPDATE staff SET role = 'owner' WHERE role = 'admin'"))
    op.create_check_constraint(
        "ck_staff_role_valid", "staff", "role IN ('owner', 'cashier')"
    )
