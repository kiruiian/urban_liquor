"""Add an optional buying price for products added from now on.

Revision ID: 0009_product_buying_price
Revises: 0008_return_and_change_history
Create Date: 2026-11-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_product_buying_price"
down_revision: Union[str, None] = "0008_return_and_change_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("cost_price", sa.Numeric(12, 2), nullable=True))
    op.create_check_constraint(
        "ck_products_cost_price_nonnegative",
        "products",
        "cost_price IS NULL OR cost_price >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_cost_price_nonnegative", "products", type_="check")
    op.drop_column("products", "cost_price")
