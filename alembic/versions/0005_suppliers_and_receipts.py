"""Add suppliers and supplier stock receipts.

Revision ID: 0005_suppliers_and_receipts
Revises: 0004_staff_username_login
Create Date: 2026-11-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_suppliers_and_receipts"
down_revision: Union[str, None] = "0004_staff_username_login"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("contact_name", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])

    op.create_table(
        "supplier_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("supplier_name", sa.String(length=160), nullable=False),
        sa.Column("supplier_reference", sa.String(length=80), nullable=True),
        sa.Column("received_by_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("received_by_name", sa.String(length=120), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "supplier_id",
            "supplier_reference",
            name="uq_supplier_receipts_supplier_reference",
        ),
    )
    op.create_index("ix_supplier_receipts_supplier_id", "supplier_receipts", ["supplier_id"])
    op.create_index("ix_supplier_receipts_received_at", "supplier_receipts", ["received_at"])

    op.create_table(
        "supplier_receipt_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "receipt_id",
            sa.Integer(),
            sa.ForeignKey("supplier_receipts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("quantity_received", sa.Numeric(12, 3), nullable=False),
        sa.CheckConstraint(
            "quantity_received > 0",
            name="ck_supplier_receipt_items_quantity_positive",
        ),
    )
    op.create_index(
        "ix_supplier_receipt_items_receipt_id", "supplier_receipt_items", ["receipt_id"]
    )
    op.create_index(
        "ix_supplier_receipt_items_product_id", "supplier_receipt_items", ["product_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_supplier_receipt_items_product_id", table_name="supplier_receipt_items")
    op.drop_index("ix_supplier_receipt_items_receipt_id", table_name="supplier_receipt_items")
    op.drop_table("supplier_receipt_items")
    op.drop_index("ix_supplier_receipts_received_at", table_name="supplier_receipts")
    op.drop_index("ix_supplier_receipts_supplier_id", table_name="supplier_receipts")
    op.drop_table("supplier_receipts")
    op.drop_index("ix_suppliers_name", table_name="suppliers")
    op.drop_table("suppliers")
