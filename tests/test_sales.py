import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.sales.models import Payment, Sale, SaleItem, SaleReturnRecord
from app.modules.sales.router import (
    _date_range_bounds,
    _period_dates,
    amend_sale,
    change_sale_item,
    create_sale,
    list_sales,
    return_sale_item,
    sales_summary,
)
from app.modules.sales.schemas import (
    PaymentCreate,
    SaleAmend,
    SaleChange,
    SaleCreate,
    SaleItemCreate,
    SaleReturn,
)


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


class AmendSession:
    def __init__(self, sale: Sale, products: list[Product]) -> None:
        self.sale = sale
        self.products = products
        self.added: list[object] = []

    async def scalar(self, _statement):
        return self.sale

    async def scalars(self, _statement):
        return Result(rows=self.products)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None


class AmendSaleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.admin = Staff(
            id=1,
            username="admin",
            full_name="Admin",
            password_hash="unused",
            role="admin",
            is_active=True,
        )
        self.small = Product(
            id=1,
            sku="VOD-250",
            name="Vodka 250ml",
            unit_price=Decimal("200.00"),
            stock_quantity=Decimal("4"),
            low_stock_threshold=Decimal("1"),
            is_active=True,
        )
        self.large = Product(
            id=2,
            sku="VOD-750",
            name="Vodka 750ml",
            unit_price=Decimal("500.00"),
            stock_quantity=Decimal("3"),
            low_stock_threshold=Decimal("1"),
            is_active=True,
        )
        self.sale = Sale(
            id=9,
            currency="KES",
            subtotal=Decimal("200.00"),
            total=Decimal("200.00"),
            created_at=datetime(2026, 11, 23, 9, tzinfo=timezone.utc),
        )
        self.sale.items = [
            SaleItem(
                id=1,
                sale_id=9,
                product_id=1,
                product_name="Vodka 250ml",
                sku="VOD-250",
                quantity=Decimal("1.000"),
                unit_price=Decimal("200.00"),
                line_total=Decimal("200.00"),
            )
        ]
        self.sale.payments = [
            Payment(
                id=3,
                sale_id=9,
                method="cash",
                amount=Decimal("200.00"),
                cash_received=Decimal("200.00"),
                change_given=Decimal("0.00"),
            )
        ]

    async def test_swap_to_larger_bottle_restocks_original_and_records_top_up(self) -> None:
        session = AmendSession(self.sale, [self.small, self.large])

        sale = await amend_sale(
            9,
            SaleAmend(
                items=[SaleItemCreate(product_id=2, quantity=Decimal("1"))],
                settlement_method="cash",
                cash_received=Decimal("400.00"),
            ),
            session,
            self.admin,
        )

        self.assertEqual(sale.total, Decimal("500.00"))
        self.assertEqual(self.small.stock_quantity, Decimal("5"))
        self.assertEqual(self.large.stock_quantity, Decimal("2"))
        self.assertEqual(sale.items[0].product_name, "Vodka 750ml")
        self.assertEqual(sale.items[0].unit_price, Decimal("500.00"))
        self.assertEqual(len(sale.payments), 2)
        top_up = sale.payments[-1]
        self.assertEqual(top_up.amount, Decimal("300.00"))
        self.assertEqual(top_up.cash_received, Decimal("400.00"))
        self.assertEqual(top_up.change_given, Decimal("100.00"))
        movements = [item for item in session.added if isinstance(item, StockMovement)]
        self.assertEqual(
            sorted((item.product_id, item.quantity_delta) for item in movements),
            [(1, Decimal("1.000")), (2, Decimal("-1"))],
        )

    async def test_extra_quantity_keeps_the_price_charged_on_the_original_sale(self) -> None:
        self.small.unit_price = Decimal("999.00")
        session = AmendSession(self.sale, [self.small, self.large])

        sale = await amend_sale(
            9,
            SaleAmend(
                items=[SaleItemCreate(product_id=1, quantity=Decimal("2"))],
                settlement_method="mpesa",
                mpesa_reference="TOPUP1",
            ),
            session,
            self.admin,
        )

        self.assertEqual(sale.total, Decimal("400.00"))
        self.assertEqual(sale.items[0].unit_price, Decimal("200.00"))
        self.assertEqual(self.small.stock_quantity, Decimal("3"))
        self.assertEqual(sale.payments[-1].method, "mpesa")
        self.assertEqual(sale.payments[-1].amount, Decimal("200.00"))
        self.assertEqual(sale.payments[-1].mpesa_reference, "TOPUP1")

    async def test_swap_rejects_insufficient_stock_without_changing_the_sale(self) -> None:
        self.large.stock_quantity = Decimal("0")
        session = AmendSession(self.sale, [self.small, self.large])

        with self.assertRaises(HTTPException) as raised:
            await amend_sale(
                9,
                SaleAmend(
                    items=[SaleItemCreate(product_id=2, quantity=Decimal("1"))],
                    settlement_method="cash",
                ),
                session,
                self.admin,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.sale.total, Decimal("200.00"))
        self.assertEqual(self.small.stock_quantity, Decimal("4"))
        self.assertEqual(self.large.stock_quantity, Decimal("0"))
        self.assertEqual(len(self.sale.payments), 1)
        self.assertEqual(session.added, [])

    async def test_cheaper_swap_refunds_the_selected_method(self) -> None:
        cheaper = Product(
            id=4,
            sku="VOD-MINI",
            name="Vodka miniature",
            unit_price=Decimal("50.00"),
            stock_quantity=Decimal("6"),
            low_stock_threshold=Decimal("1"),
            is_active=True,
        )
        session = AmendSession(self.sale, [self.small, cheaper])

        sale = await amend_sale(
            9,
            SaleAmend(
                items=[SaleItemCreate(product_id=4, quantity=Decimal("1"))],
                settlement_method="cash",
            ),
            session,
            self.admin,
        )

        self.assertEqual(sale.total, Decimal("50.00"))
        self.assertEqual(sale.payments[0].amount, Decimal("50.00"))
        self.assertEqual(sale.payments[0].cash_received, Decimal("50.00"))
        self.assertEqual(self.small.stock_quantity, Decimal("5"))
        self.assertEqual(cheaper.stock_quantity, Decimal("5"))

    async def test_price_increase_requires_a_settlement_method(self) -> None:
        session = AmendSession(self.sale, [self.small, self.large])

        with self.assertRaises(HTTPException) as raised:
            await amend_sale(
                9,
                SaleAmend(items=[SaleItemCreate(product_id=2, quantity=Decimal("1"))]),
                session,
                self.admin,
            )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(self.sale.total, Decimal("200.00"))
        self.assertEqual(self.large.stock_quantity, Decimal("3"))

    async def test_return_puts_the_sold_bottle_back_in_stock(self) -> None:
        session = AmendSession(self.sale, [self.small, self.large])

        sale = await return_sale_item(
            9,
            SaleReturn(sale_item_id=1, quantity=Decimal("1"), settlement_method="cash"),
            session,
            self.admin,
        )

        self.assertEqual(self.small.stock_quantity, Decimal("5"))
        self.assertEqual(sale.items, [])
        self.assertEqual(sale.total, Decimal("0.00"))
        self.assertEqual(sale.payments, [])
        movement = next(item for item in session.added if isinstance(item, StockMovement))
        self.assertEqual(movement.quantity_delta, Decimal("1"))
        self.assertEqual(movement.reason, "Sale 9 return")
        record = next(item for item in session.added if isinstance(item, SaleReturnRecord))
        self.assertEqual(record.sale_id, 9)
        self.assertEqual(record.product_name, "Vodka 250ml")
        self.assertEqual(record.amount, Decimal("200.00"))
        self.assertEqual(record.method, "cash")
        self.assertEqual(record.kind, "return")

    async def test_change_restocks_the_returned_bottle_and_removes_the_replacement(self) -> None:
        session = AmendSession(self.sale, [self.small, self.large])

        sale = await change_sale_item(
            9,
            SaleChange(
                sale_item_id=1,
                quantity=Decimal("1"),
                replacement_product_id=2,
                replacement_quantity=Decimal("1"),
                settlement_method="cash",
                cash_received=Decimal("300.00"),
            ),
            session,
            self.admin,
        )

        self.assertEqual(self.small.stock_quantity, Decimal("5"))
        self.assertEqual(self.large.stock_quantity, Decimal("2"))
        self.assertEqual(len(sale.items), 1)
        self.assertEqual(sale.items[0].product_id, 2)
        self.assertEqual(sale.total, Decimal("500.00"))
        self.assertEqual(sale.payments[-1].amount, Decimal("300.00"))
        movements = {
            item.product_id: item.quantity_delta
            for item in session.added
            if isinstance(item, StockMovement)
        }
        self.assertEqual(movements[1], Decimal("1"))
        self.assertEqual(movements[2], Decimal("-1"))
        record = next(item for item in session.added if isinstance(item, SaleReturnRecord))
        self.assertEqual(record.kind, "change")
        self.assertEqual(record.product_name, "Vodka 250ml")
        self.assertEqual(record.replacement_product_name, "Vodka 750ml")
        self.assertEqual(record.amount, Decimal("300.00"))

    async def test_change_rejects_insufficient_replacement_stock_without_restocking(self) -> None:
        self.large.stock_quantity = Decimal("0")
        session = AmendSession(self.sale, [self.small, self.large])

        with self.assertRaises(HTTPException) as raised:
            await change_sale_item(
                9,
                SaleChange(
                    sale_item_id=1,
                    quantity=Decimal("1"),
                    replacement_product_id=2,
                    replacement_quantity=Decimal("1"),
                    settlement_method="cash",
                ),
                session,
                self.admin,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.small.stock_quantity, Decimal("4"))
        self.assertEqual(self.sale.total, Decimal("200.00"))
        self.assertEqual(len(self.sale.payments), 1)
