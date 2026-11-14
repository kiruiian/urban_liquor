import unittest
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException

from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.inventory.router import (
    adjust_stock,
    create_product,
    inventory_insights,
    update_product,
)
from app.modules.inventory.schemas import (
    ProductCreate,
    ProductUpdate,
    StockAdjustmentCreate,
)


class InventorySession:
    def __init__(
        self,
        product: Product | None = None,
        scalar_results: list[object] | None = None,
    ) -> None:
        self.product = product
        self.scalar_results = list(scalar_results or [None])
        self.added: list[object] = []

    async def scalar(self, _statement):
        return self.scalar_results.pop(0)

    async def get(self, _model, _key):
        return self.product

    async def flush(self) -> None:
        for item in self.added:
            if isinstance(item, Product) and item.id is None:
                item.id = 15

    def add(self, item: object) -> None:
        self.added.append(item)

    async def rollback(self) -> None:
        pass


class InventoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.admin = Staff(
            id=1,
            username="storeadmin",
            full_name="Store Admin",
            password_hash="unused",
            role="admin",
            is_active=True,
        )

    async def test_create_product_generates_sku_and_initial_stock_movement(self) -> None:
        session = InventorySession()
        product = await create_product(
            ProductCreate(name="House Red", unit_price=Decimal("1250.00"), initial_stock=Decimal("8")),
            session,
            self.admin,
        )

        self.assertRegex(product.sku, r"^UL-[A-F0-9]{32}$")
        movement = next(item for item in session.added if isinstance(item, StockMovement))
        self.assertEqual(movement.quantity_delta, Decimal("8"))
        self.assertEqual(movement.reference_type, "initial")

    async def test_create_product_rejects_duplicate_barcode(self) -> None:
        session = InventorySession(scalar_results=[3])

        with self.assertRaises(HTTPException) as raised:
            await create_product(
                ProductCreate(
                    name="House Red",
                    barcode="12345",
                    unit_price=Decimal("1250.00"),
                ),
                session,
                self.admin,
            )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_stock_adjustment_changes_stock_and_records_reason(self) -> None:
        product = Product(
            id=15,
            sku="UL-15",
            name="House Red",
            unit_price=Decimal("1250.00"),
            stock_quantity=Decimal("8"),
            low_stock_threshold=Decimal("2"),
        )
        session = InventorySession(product=product, scalar_results=[product])

        updated = await adjust_stock(
            product.id,
            StockAdjustmentCreate(quantity_delta=Decimal("-3"), reason="Damaged bottles"),
            session,
            self.admin,
        )

        self.assertEqual(updated.stock_quantity, Decimal("5"))
        movement = next(item for item in session.added if isinstance(item, StockMovement))
        self.assertEqual(movement.quantity_delta, Decimal("-3"))
        self.assertEqual(movement.reason, "Damaged bottles")

    async def test_stock_cannot_be_reduced_below_zero(self) -> None:
        product = Product(
            id=15,
            sku="UL-15",
            name="House Red",
            unit_price=Decimal("1250.00"),
            stock_quantity=Decimal("2"),
            low_stock_threshold=Decimal("0"),
        )

        with self.assertRaises(HTTPException) as raised:
            await adjust_stock(
                product.id,
                StockAdjustmentCreate(quantity_delta=Decimal("-3"), reason="Stock count"),
                InventorySession(product=product, scalar_results=[product]),
                self.admin,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(product.stock_quantity, Decimal("2"))

    async def test_optional_barcode_and_category_can_be_cleared(self) -> None:
        product = Product(
            id=15,
            sku="UL-15",
            barcode="12345",
            name="House Red",
            category="Wine",
            unit_price=Decimal("1250.00"),
            stock_quantity=Decimal("2"),
            low_stock_threshold=Decimal("0"),
        )

        updated = await update_product(
            product.id,
            ProductUpdate(barcode=None, category=None),
            InventorySession(product=product),
            self.admin,
        )

        self.assertIsNone(updated.barcode)
        self.assertIsNone(updated.category)

    async def test_inventory_insights_include_stock_value_and_fast_movers(self) -> None:
        class InsightsSession:
            async def scalar(self, _statement):
                return Decimal("12500.00")

            async def execute(self, _statement):
                class Result:
                    def all(self):
                        return [
                            SimpleNamespace(
                                id=15,
                                name="House Red",
                                sku="UL-15",
                                unit_price=Decimal("1250.00"),
                                stock_quantity=Decimal("5"),
                                quantity_sold=Decimal("12"),
                            )
                        ]

                return Result()

        insights = await inventory_insights(InsightsSession(), self.admin)

        self.assertEqual(insights.stock_value, Decimal("12500.00"))
        self.assertEqual(insights.currency, "KES")
        self.assertEqual(insights.period_days, 30)
        self.assertEqual(insights.fast_movers[0].name, "House Red")
        self.assertEqual(insights.fast_movers[0].quantity_sold, Decimal("12"))
