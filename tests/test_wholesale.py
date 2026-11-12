import unittest
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.wholesale.models import (
    WholesaleCustomer,
    WholesalePayment,
    WholesaleSale,
    WholesaleSaleItem,
)
from app.modules.wholesale.router import add_wholesale_payment, create_wholesale_sale
from app.modules.wholesale.schemas import (
    WholesaleCustomerCreate,
    WholesalePaymentCreate,
    WholesaleSaleCreate,
    WholesaleSaleItemCreate,
    WholesaleSaleRead,
)


class Result:
    def __init__(self, rows=None) -> None:
        self.rows = rows or []

    def all(self):
        return self.rows


class WholesaleSession:
    def __init__(
        self,
        customer: WholesaleCustomer,
        products: list[Product],
        sale: WholesaleSale | None = None,
    ) -> None:
        self.customer = customer
        self.products = products
        self.sale = sale
        self.added: list[object] = []

    async def get(self, model, _key):
        if model is WholesaleCustomer:
            return self.customer
        return None

    async def scalar(self, _statement):
        if self.sale is not None:
            return self.sale
        return next((item for item in self.added if isinstance(item, WholesaleSale)), None)

    async def scalars(self, _statement):
        return Result(self.products)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        for item in self.added:
            if isinstance(item, WholesaleSale) and item.id is None:
                item.id = 23


class WholesaleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.cashier = Staff(
            id=2,
            username="cashier",
            full_name="Cashier",
            password_hash="unused",
            role="cashier",
            is_active=True,
        )
        self.customer = WholesaleCustomer(
            id=9, name="Town Spirits", is_active=True
        )
        self.product = Product(
            id=4,
            sku="UL-4",
            name="House Red",
            unit_price=Decimal("1250.00"),
            stock_quantity=Decimal("20"),
            low_stock_threshold=Decimal("5"),
            is_active=True,
        )

    def sale_payload(self, payments=None) -> WholesaleSaleCreate:
        return WholesaleSaleCreate(
            customer_id=9,
            delivery_reference="DEL-100",
            items=[
                WholesaleSaleItemCreate(
                    product_id=4,
                    quantity=Decimal("4"),
                    unit_price=Decimal("900.00"),
                )
            ],
            payments=payments or [],
        )

    async def test_delivery_uses_agreed_price_reduces_stock_and_records_audit(self) -> None:
        payload = self.sale_payload(
            [
                WholesalePaymentCreate(
                    method="cash",
                    amount=Decimal("1000.00"),
                    cash_received=Decimal("1200.00"),
                )
            ]
        )
        session = WholesaleSession(self.customer, [self.product])

        sale = await create_wholesale_sale(payload, session, self.cashier)

        self.assertEqual(sale.total, Decimal("3600.00"))
        self.assertEqual(self.product.stock_quantity, Decimal("16"))
        self.assertEqual(sale.customer_name, "Town Spirits")
        self.assertEqual(sale.created_by_name, "Cashier")
        self.assertEqual(sale.payments[0].change_given, Decimal("200.00"))
        movement = next(item for item in session.added if isinstance(item, StockMovement))
        self.assertEqual(movement.quantity_delta, Decimal("-4"))
        self.assertEqual(movement.reference_type, "wholesale_sale")

    async def test_partial_payment_leaves_balance_and_later_payment_clears_it(self) -> None:
        item = WholesaleSaleItem(
            id=1,
            product_id=4,
            product_name="House Red",
            sku="UL-4",
            quantity=Decimal("4"),
            unit_price=Decimal("900.00"),
            line_total=Decimal("3600.00"),
        )
        sale = WholesaleSale(
            id=23,
            customer_id=9,
            customer_name="Town Spirits",
            created_by_id=2,
            created_by_name="Cashier",
            currency="KES",
            total=Decimal("3600.00"),
            created_at=datetime(2026, 11, 12, 9, tzinfo=timezone.utc),
        )
        sale.items = [item]
        sale.payments = [
            WholesalePayment(
                id=1,
                method="cash",
                amount=Decimal("1000.00"),
                cash_received=Decimal("1000.00"),
                change_given=Decimal("0.00"),
            )
        ]
        response = WholesaleSaleRead.model_validate(sale)
        self.assertEqual(response.balance_due, Decimal("2600.00"))
        self.assertEqual(response.payment_status, "partial")

        session = WholesaleSession(self.customer, [self.product], sale=sale)
        updated = await add_wholesale_payment(
            23,
            WholesalePaymentCreate(
                method="mpesa",
                amount=Decimal("2600.00"),
                mpesa_reference="PAY123",
            ),
            session,
            self.cashier,
        )

        self.assertEqual(sum((payment.amount for payment in updated.payments)), Decimal("3600.00"))

    async def test_payment_cannot_exceed_outstanding_balance(self) -> None:
        sale = WholesaleSale(
            id=23,
            customer_id=9,
            customer_name="Town Spirits",
            created_by_id=2,
            created_by_name="Cashier",
            currency="KES",
            total=Decimal("3600.00"),
        )
        sale.items = []
        sale.payments = [
            WholesalePayment(
                id=1,
                method="cash",
                amount=Decimal("1000.00"),
                cash_received=Decimal("1000.00"),
                change_given=Decimal("0.00"),
            )
        ]

        with self.assertRaises(HTTPException) as raised:
            await add_wholesale_payment(
                23,
                WholesalePaymentCreate(method="cash", amount=Decimal("2600.01")),
                WholesaleSession(self.customer, [self.product], sale=sale),
                self.cashier,
            )

        self.assertEqual(raised.exception.status_code, 422)

    async def test_delivery_rejects_insufficient_stock_without_mutating(self) -> None:
        payload = self.sale_payload()
        payload.items[0].quantity = Decimal("21")

        with self.assertRaises(HTTPException) as raised:
            await create_wholesale_sale(
                payload, WholesaleSession(self.customer, [self.product]), self.cashier
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.product.stock_quantity, Decimal("20"))

    async def test_delivery_payments_cannot_exceed_total(self) -> None:
        payload = self.sale_payload(
            [WholesalePaymentCreate(method="cash", amount=Decimal("3600.01"))]
        )
        session = WholesaleSession(self.customer, [self.product])

        with self.assertRaises(HTTPException) as raised:
            await create_wholesale_sale(payload, session, self.cashier)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(self.product.stock_quantity, Decimal("20"))
        self.assertEqual(session.added, [])

    def test_customer_name_is_trimmed_and_cannot_be_blank(self) -> None:
        customer = WholesaleCustomerCreate(name="  Town Spirits  ")
        self.assertEqual(customer.name, "Town Spirits")
        with self.assertRaises(ValidationError):
            WholesaleCustomerCreate(name="   ")

    def test_delivery_rejects_repeated_payment_methods(self) -> None:
        with self.assertRaises(ValidationError):
            self.sale_payload(
                [
                    WholesalePaymentCreate(method="cash", amount=Decimal("100.00")),
                    WholesalePaymentCreate(method="cash", amount=Decimal("200.00")),
                ]
            )

