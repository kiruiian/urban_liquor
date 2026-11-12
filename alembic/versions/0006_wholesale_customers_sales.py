"""Add wholesale shop deliveries and payments.

Revision ID: 0006_wholesale_customers_sales
Revises: 0005_suppliers_and_receipts
Create Date: 2026-11-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_wholesale_customers_sales"
down_revision: Union[str, None] = "0005_suppliers_and_receipts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wholesale_customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("contact_name", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_wholesale_customers_name", "wholesale_customers", ["name"])

    op.create_table(
        "wholesale_sales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("wholesale_customers.id"),
            nullable=False,
        ),
        sa.Column("customer_name", sa.String(length=160), nullable=False),
        sa.Column("delivery_reference", sa.String(length=80), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("created_by_name", sa.String(length=120), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("total >= 0", name="ck_wholesale_sales_total_nonnegative"),
    )
    op.create_index(
        "ix_wholesale_sales_customer_id", "wholesale_sales", ["customer_id"]
    )
    op.create_index("ix_wholesale_sales_created_at", "wholesale_sales", ["created_at"])

    op.create_table(
        "wholesale_sale_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "sale_id",
            sa.Integer(),
            sa.ForeignKey("wholesale_sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint(
            "quantity > 0", name="ck_wholesale_sale_items_quantity_positive"
        ),
        sa.CheckConstraint(
            "unit_price >= 0", name="ck_wholesale_sale_items_price_nonnegative"
        ),
        sa.CheckConstraint(
            "line_total >= 0", name="ck_wholesale_sale_items_total_nonnegative"
        ),
    )
    op.create_index(
        "ix_wholesale_sale_items_sale_id", "wholesale_sale_items", ["sale_id"]
    )
    op.create_index(
        "ix_wholesale_sale_items_product_id", "wholesale_sale_items", ["product_id"]
    )

    op.create_table(
        "wholesale_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "sale_id",
            sa.Integer(),
            sa.ForeignKey("wholesale_sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("cash_received", sa.Numeric(12, 2), nullable=False),
        sa.Column("change_given", sa.Numeric(12, 2), nullable=False),
        sa.Column("mpesa_reference", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "amount > 0", name="ck_wholesale_payments_amount_positive"
        ),
        sa.CheckConstraint(
            "method != 'cash' OR cash_received >= amount",
            name="ck_wholesale_payments_cash_received_gte_amount",
        ),
        sa.CheckConstraint(
            "method IN ('cash', 'mpesa')",
            name="ck_wholesale_payments_method_valid",
        ),
    )
    op.create_index(
        "ix_wholesale_payments_sale_id", "wholesale_payments", ["sale_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_wholesale_payments_sale_id", table_name="wholesale_payments")
    op.drop_table("wholesale_payments")
    op.drop_index(
        "ix_wholesale_sale_items_product_id", table_name="wholesale_sale_items"
    )
    op.drop_index("ix_wholesale_sale_items_sale_id", table_name="wholesale_sale_items")
    op.drop_table("wholesale_sale_items")
    op.drop_index("ix_wholesale_sales_created_at", table_name="wholesale_sales")
    op.drop_index("ix_wholesale_sales_customer_id", table_name="wholesale_sales")
    op.drop_table("wholesale_sales")
    op.drop_index("ix_wholesale_customers_name", table_name="wholesale_customers")
    op.drop_table("wholesale_customers")
