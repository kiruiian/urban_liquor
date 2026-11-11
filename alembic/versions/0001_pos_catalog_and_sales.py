"""Create product, inventory, and sales tables.

Revision ID: 0001_pos_catalog_and_sales
Revises:
Create Date: 2026-11-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_pos_catalog_and_sales"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("stock_quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("low_stock_threshold", sa.Numeric(12, 3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("unit_price >= 0", name="ck_products_unit_price_nonnegative"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_products_stock_nonnegative"),
        sa.CheckConstraint(
            "low_stock_threshold >= 0", name="ck_products_threshold_nonnegative"
        ),
        sa.UniqueConstraint("sku"),
        sa.UniqueConstraint("barcode"),
    )
    op.create_index("ix_products_sku", "products", ["sku"])
    op.create_index("ix_products_barcode", "products", ["barcode"])
    op.create_index("ix_products_name", "products", ["name"])

    op.create_table(
        "sales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("subtotal >= 0", name="ck_sales_subtotal_nonnegative"),
        sa.CheckConstraint("total >= 0", name="ck_sales_total_nonnegative"),
    )
    op.create_index("ix_sales_created_at", "sales", ["created_at"])

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(12, 3), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("reference_type", sa.String(length=32), nullable=False),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("quantity_delta != 0", name="ck_stock_movements_nonzero"),
    )
    op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"])

    op.create_table(
        "sale_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_sale_items_price_nonnegative"),
        sa.CheckConstraint("line_total >= 0", name="ck_sale_items_total_nonnegative"),
    )
    op.create_index("ix_sale_items_sale_id", "sale_items", ["sale_id"])
    op.create_index("ix_sale_items_product_id", "sale_items", ["product_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("cash_received", sa.Numeric(12, 2), nullable=False),
        sa.Column("change_given", sa.Numeric(12, 2), nullable=False),
        sa.Column("mpesa_reference", sa.String(length=64), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "method != 'cash' OR cash_received >= amount",
            name="ck_payments_cash_received_gte_amount",
        ),
        sa.CheckConstraint("method IN ('cash', 'mpesa')", name="ck_payments_method_valid"),
    )
    op.create_index("ix_payments_sale_id", "payments", ["sale_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_sale_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_sale_items_product_id", table_name="sale_items")
    op.drop_index("ix_sale_items_sale_id", table_name="sale_items")
    op.drop_table("sale_items")
    op.drop_index("ix_stock_movements_product_id", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("ix_sales_created_at", table_name="sales")
    op.drop_table("sales")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_index("ix_products_barcode", table_name="products")
    op.drop_index("ix_products_sku", table_name="products")
    op.drop_table("products")
