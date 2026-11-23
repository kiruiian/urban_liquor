"""Record item returns separately from sales.

Revision ID: 0007_sale_returns
Revises: 0006_wholesale_customers_sales
Create Date: 2026-11-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_sale_returns"
down_revision: Union[str, None] = "0006_wholesale_customers_sales"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sale_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("quantity > 0", name="ck_sale_returns_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_sale_returns_price_nonnegative"),
        sa.CheckConstraint("amount >= 0", name="ck_sale_returns_amount_nonnegative"),
        sa.CheckConstraint("method IN ('cash', 'mpesa')", name="ck_sale_returns_method_valid"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    )
    op.create_index("ix_sale_returns_sale_id", "sale_returns", ["sale_id"])
    op.create_index("ix_sale_returns_product_id", "sale_returns", ["product_id"])
    op.create_index("ix_sale_returns_created_at", "sale_returns", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sale_returns_created_at", table_name="sale_returns")
    op.drop_index("ix_sale_returns_product_id", table_name="sale_returns")
    op.drop_index("ix_sale_returns_sale_id", table_name="sale_returns")
    op.drop_table("sale_returns")
