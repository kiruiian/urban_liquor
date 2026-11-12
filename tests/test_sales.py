import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.sales.models import Payment, Sale, SaleItem
from app.modules.sales.router import (
    _date_range_bounds,
    _period_dates,
    create_sale,
    list_sales,
    sales_summary,
)
from app.modules.sales.schemas import PaymentCreate, SaleCreate, SaleItemCreate


class Result:
    def __init__(self, row=None, rows=None) -> None:
        self.row = row
        self.rows = rows or []

    def one(self):
        return self.row

    def all(self):
        return self.rows


class SalesSession:
    def __init__(self, products: list[Product]) -> None:
        self.products = products
        self.added: list[object] = []
        self.flush_count = 0

    async def scalars(self, _statement):
        return Result(rows=self.products)

    async def scalar(self, _statement):
        return next((item for item in self.added if isinstance(item, Sale)), None)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_count += 1
        for item in self.added:
            if isinstance(item, Sale) and item.id is None:
                item.id = 42


class SalesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.cashier = Staff(
            id=2,
            username="cashier",
            full_name="Cashier",
            password_hash="unused",
            role="cashier",
            is_active=True,
        )
        self.product = Product(
            id=4,
            sku="UL-4",
            name="House Red",
            unit_price=Decimal("12.50"),
            stock_quantity=Decimal("10"),
            low_stock_threshold=Decimal("2"),
            is_active=True,
        )

    async def test_split_sale_uses_server_price_and_updates_stock_and_movements(self) -> None:
        payload = SaleCreate(
            items=[SaleItemCreate(product_id=4, quantity=Decimal("2"))],
            payments=[
                PaymentCreate(
                    method="cash",
                    amount=Decimal("12.50"),
                    cash_received=Decimal("15.00"),
                ),
                PaymentCreate(
                    method="mpesa",
                    amount=Decimal("12.50"),
                    mpesa_reference="ABC123",
                ),
            ],
        )
        session = SalesSession([self.product])

        sale = await create_sale(payload, session, self.cashier)

        self.assertEqual(sale.total, Decimal("25.00"))
        self.assertEqual(self.product.stock_quantity, Decimal("8"))
        item = next(value for value in session.added if isinstance(value, SaleItem))
        self.assertEqual(item.unit_price, Decimal("12.50"))
        movement = next(value for value in session.added if isinstance(value, StockMovement))
        self.assertEqual(movement.quantity_delta, Decimal("-2"))
        payments = [value for value in session.added if isinstance(value, Payment)]
        cash_payment = next(value for value in payments if value.method == "cash")
        self.assertEqual(cash_payment.change_given, Decimal("2.50"))

    async def test_sale_rejects_insufficient_stock_without_mutating_stock(self) -> None:
        payload = SaleCreate(
            items=[SaleItemCreate(product_id=4, quantity=Decimal("11"))],
            payments=[PaymentCreate(method="cash", amount=Decimal("137.50"))],
        )
        session = SalesSession([self.product])

        with self.assertRaises(HTTPException) as raised:
            await create_sale(payload, session, self.cashier)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.product.stock_quantity, Decimal("10"))
        self.assertEqual(session.added, [])

    async def test_sale_rejects_payment_total_that_does_not_match_sale(self) -> None:
        payload = SaleCreate(
            items=[SaleItemCreate(product_id=4, quantity=Decimal("2"))],
            payments=[PaymentCreate(method="cash", amount=Decimal("24.99"))],
        )
        session = SalesSession([self.product])

        with self.assertRaises(HTTPException) as raised:
            await create_sale(payload, session, self.cashier)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(self.product.stock_quantity, Decimal("10"))
        self.assertEqual(session.added, [])

    async def test_weekly_and_monthly_ranges_use_store_calendar(self) -> None:
        anchor = date(2026, 11, 12)
        self.assertEqual(
            _period_dates(anchor, "weekly"),
            (date(2026, 11, 9), date(2026, 11, 15)),
        )
        self.assertEqual(
            _period_dates(anchor, "monthly"),
            (date(2026, 11, 1), date(2026, 11, 30)),
        )
        self.assertEqual(
            _period_dates(date(2024, 2, 12), "monthly"),
            (date(2024, 2, 1), date(2024, 2, 29)),
        )
        start, end = _date_range_bounds(date(2026, 11, 9), date(2026, 11, 15))
        self.assertEqual(start.isoformat(), "2026-11-08T21:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-11-15T21:00:00+00:00")

    async def test_cashier_can_load_cumulative_sales_summary(self) -> None:
        class SummaryResult:
            def __init__(self, row=None, rows=None) -> None:
                self.row = row
                self.rows = rows or []

            def one(self):
                return self.row

            def all(self):
                return self.rows

        class Session:
            calls = 0

            async def execute(self, _statement):
                self.calls += 1
                if self.calls == 1:
                    return SummaryResult(row=(5, Decimal("1450.00")))
                return SummaryResult(
                    rows=[
                        ("cash", Decimal("900.00")),
                        ("mpesa", Decimal("550.00")),
                    ]
                )

        summary = await sales_summary(
            date(2026, 11, 12),
            "weekly",
            Session(),
            self.cashier,
        )

        self.assertEqual(summary.sale_count, 5)
        self.assertEqual(summary.total, Decimal("1450.00"))
        self.assertEqual(summary.cash_total, Decimal("900.00"))
        self.assertEqual(summary.mpesa_total, Decimal("550.00"))

    async def test_cashier_can_view_transaction_details(self) -> None:
        sale = Sale(
            id=42,
            currency="KES",
            subtotal=Decimal("25.00"),
            total=Decimal("25.00"),
            created_at=datetime(2026, 11, 12, 9, tzinfo=timezone.utc),
        )
        sale.items = [
            SaleItem(
                id=1,
                product_id=4,
                product_name="House Red",
                sku="UL-4",
                quantity=Decimal("2"),
                unit_price=Decimal("12.50"),
                line_total=Decimal("25.00"),
            )
        ]
        sale.payments = [
            Payment(
                id=1,
                method="cash",
                amount=Decimal("25.00"),
                cash_received=Decimal("30.00"),
                change_given=Decimal("5.00"),
            )
        ]

        class Session:
            async def scalars(self, _statement):
                return Result(rows=[sale])

        sales = await list_sales(
            offset=0,
            limit=50,
            sale_date=date(2026, 11, 12),
            from_date=None,
            to_date=None,
            session=Session(),
            _staff=self.cashier,
        )

        self.assertEqual(sales[0].items[0].product_name, "House Red")
        self.assertEqual(sales[0].payments[0].amount, Decimal("25.00"))
