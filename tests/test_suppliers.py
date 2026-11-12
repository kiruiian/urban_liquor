import unittest
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.suppliers.models import Supplier, SupplierReceipt, SupplierReceiptItem
from app.modules.suppliers.router import create_supplier_receipt
from app.modules.suppliers.schemas import (
    SupplierReceiptCreate,
    SupplierReceiptItemCreate,
)


class Result:
    def __init__(self, rows=None) -> None:
        self.rows = rows or []

    def all(self):
        return self.rows


class SupplierSession:
    def __init__(
        self,
        supplier: Supplier,
        products: list[Product],
        duplicate_reference: int | None = None,
    ) -> None:
        self.supplier = supplier
        self.products = products
        self.duplicate_reference = duplicate_reference
        self.added: list[object] = []

    async def get(self, model, _key):
        if model is Supplier:
            return self.supplier
        return None

    async def scalar(self, _statement):
        return self.duplicate_reference

    async def scalars(self, _statement):
        return Result(self.products)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        for item in self.added:
            if isinstance(item, SupplierReceipt) and item.id is None:
                item.id = 31

    async def rollback(self) -> None:
        pass


class SupplierReceiptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.admin = Staff(
            id=1,
            username="storeadmin",
            full_name="Store Admin",
            password_hash="unused",
            role="admin",
            is_active=True,
        )
        self.supplier = Supplier(
            id=3,
            name="Depot Supply",
            is_active=True,
        )
        self.product = Product(
            id=4,
            sku="UL-4",
            name="House Red",
            unit_price=Decimal("1250.00"),
            stock_quantity=Decimal("2"),
            low_stock_threshold=Decimal("5"),
            is_active=True,
        )

    def payload(self) -> SupplierReceiptCreate:
        return SupplierReceiptCreate(
            supplier_id=3,
            supplier_reference="INV-100",
            items=[SupplierReceiptItemCreate(product_id=4, quantity_received=Decimal("6"))],
        )

    async def test_receipt_updates_stock_and_records_auditable_movement(self) -> None:
        session = SupplierSession(self.supplier, [self.product])

        receipt = await create_supplier_receipt(self.payload(), session, self.admin)

        self.assertEqual(self.product.stock_quantity, Decimal("8"))
        self.assertEqual(receipt.supplier_name, "Depot Supply")
        self.assertEqual(receipt.received_by_name, "Store Admin")
        self.assertEqual(receipt.items[0].quantity_received, Decimal("6"))
        movement = next(item for item in session.added if isinstance(item, StockMovement))
        self.assertEqual(movement.quantity_delta, Decimal("6"))
        self.assertEqual(movement.reference_type, "supplier_receipt")
        self.assertEqual(movement.reference_id, receipt.id)

    async def test_duplicate_supplier_reference_is_rejected_without_stock_change(self) -> None:
        session = SupplierSession(self.supplier, [self.product], duplicate_reference=8)

        with self.assertRaises(HTTPException) as raised:
            await create_supplier_receipt(self.payload(), session, self.admin)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.product.stock_quantity, Decimal("2"))
        self.assertEqual(session.added, [])

    async def test_duplicate_product_lines_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SupplierReceiptCreate(
                supplier_id=3,
                items=[
                    SupplierReceiptItemCreate(product_id=4, quantity_received=Decimal("1")),
                    SupplierReceiptItemCreate(product_id=4, quantity_received=Decimal("2")),
                ],
            )

    async def test_inactive_supplier_cannot_receive_stock(self) -> None:
        self.supplier.is_active = False

        with self.assertRaises(HTTPException) as raised:
            await create_supplier_receipt(
                self.payload(),
                SupplierSession(self.supplier, [self.product]),
                self.admin,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.product.stock_quantity, Decimal("2"))
