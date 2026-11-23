"""Show bottle changes beside returns, and fill history already recorded in stock.

Revision ID: 0008_return_and_change_history
Revises: 0007_sale_returns
Create Date: 2026-11-23
"""

from collections import defaultdict
from decimal import Decimal
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_return_and_change_history"
down_revision: Union[str, None] = "0007_sale_returns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sale_returns",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="return"),
    )
    op.add_column(
        "sale_returns", sa.Column("replacement_product_name", sa.String(length=160), nullable=True)
    )
    op.add_column(
        "sale_returns", sa.Column("replacement_quantity", sa.Numeric(12, 3), nullable=True)
    )
    op.alter_column("sale_returns", "method", existing_type=sa.String(length=16), nullable=True)
    op.drop_constraint("ck_sale_returns_amount_nonnegative", "sale_returns", type_="check")
    op.create_check_constraint(
        "ck_sale_returns_kind_valid", "sale_returns", "kind IN ('return', 'change')"
    )

    bind = op.get_bind()
    products = {
        row.id: row
        for row in bind.execute(sa.text("SELECT id, name, sku, unit_price FROM products"))
    }
    movements = bind.execute(
        sa.text(
            """
            SELECT product_id, quantity_delta, reason, created_at, reference_id
            FROM stock_movements
            WHERE reference_type = 'sale'
              AND (reason LIKE '% return' OR reason LIKE '% change')
            ORDER BY created_at, id
            """
        )
    ).all()
    grouped: dict[tuple[int, object], list] = defaultdict(list)
    for movement in movements:
        grouped[(movement.reference_id, movement.created_at)].append(movement)

    for (sale_id, created_at), group in grouped.items():
        returned = [row for row in group if row.reason.endswith("return") and row.quantity_delta > 0]
        changed = [row for row in group if row.reason.endswith("change") and row.quantity_delta < 0]
        method = bind.execute(
            sa.text(
                "SELECT method FROM payments WHERE sale_id = :sale_id ORDER BY id DESC LIMIT 1"
            ),
            {"sale_id": sale_id},
        ).scalar()
        if changed and returned:
            source = returned[0]
            target = changed[0]
            source_product = products[source.product_id]
            target_product = products[target.product_id]
            credit = (source_product.unit_price * source.quantity_delta).quantize(Decimal("0.01"))
            charge = (target_product.unit_price * (-target.quantity_delta)).quantize(Decimal("0.01"))
            bind.execute(
                sa.text(
                    """
                    INSERT INTO sale_returns (
                        sale_id, product_id, product_name, sku, quantity, unit_price, amount,
                        method, created_at, kind, replacement_product_name, replacement_quantity
                    ) VALUES (
                        :sale_id, :product_id, :product_name, :sku, :quantity, :unit_price, :amount,
                        :method, :created_at, 'change', :replacement_product_name, :replacement_quantity
                    )
                    """
                ),
                {
                    "sale_id": sale_id,
                    "product_id": source.product_id,
                    "product_name": source_product.name,
                    "sku": source_product.sku,
                    "quantity": source.quantity_delta,
                    "unit_price": source_product.unit_price,
                    "amount": charge - credit,
                    "method": method,
                    "created_at": created_at,
                    "replacement_product_name": target_product.name,
                    "replacement_quantity": -target.quantity_delta,
                },
            )
            continue
        for source in returned:
            source_product = products[source.product_id]
            amount = (source_product.unit_price * source.quantity_delta).quantize(Decimal("0.01"))
            bind.execute(
                sa.text(
                    """
                    INSERT INTO sale_returns (
                        sale_id, product_id, product_name, sku, quantity, unit_price, amount,
                        method, created_at, kind, replacement_product_name, replacement_quantity
                    ) VALUES (
                        :sale_id, :product_id, :product_name, :sku, :quantity, :unit_price, :amount,
                        :method, :created_at, 'return', NULL, NULL
                    )
                    """
                ),
                {
                    "sale_id": sale_id,
                    "product_id": source.product_id,
                    "product_name": source_product.name,
                    "sku": source_product.sku,
                    "quantity": source.quantity_delta,
                    "unit_price": source_product.unit_price,
                    "amount": amount,
                    "method": method,
                    "created_at": created_at,
                },
            )


def downgrade() -> None:
    op.drop_constraint("ck_sale_returns_kind_valid", "sale_returns", type_="check")
    op.drop_column("sale_returns", "replacement_quantity")
    op.drop_column("sale_returns", "replacement_product_name")
    op.drop_column("sale_returns", "kind")
    op.create_check_constraint(
        "ck_sale_returns_amount_nonnegative", "sale_returns", "amount >= 0"
    )
    op.alter_column("sale_returns", "method", existing_type=sa.String(length=16), nullable=False)
