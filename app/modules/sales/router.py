from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_staff, require_admin
from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.sales.models import Payment, Sale, SaleItem, SaleReturnRecord
from app.modules.sales.schemas import (
    DailySalesSummary,
    ProfitAndLoss,
    SaleAmend,
    SaleChange,
    SaleCreate,
    SaleRead,
    SaleReturn,
    SaleReturnRead,
    SalesSummary,
)
from app.modules.wholesale.models import WholesaleSale, WholesaleSaleItem

router = APIRouter()
CENT = Decimal("0.01")
STORE_TIMEZONE = ZoneInfo("Africa/Nairobi")


def _day_bounds(sale_date: date) -> tuple[datetime, datetime]:
    return _date_range_bounds(sale_date, sale_date)


def _date_range_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(start_date, time.min, tzinfo=STORE_TIMEZONE)
    local_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=STORE_TIMEZONE)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _profit_statement(
    retail_sales: Decimal,
    wholesale_sales: Decimal,
    cost: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return retail_sales, wholesale_sales, cost, retail_sales + wholesale_sales - cost


def _period_dates(anchor_date: date, period: str) -> tuple[date, date]:
    if period == "daily":
        return anchor_date, anchor_date
    if period == "weekly":
        start_date = anchor_date - timedelta(days=anchor_date.weekday())
        return start_date, start_date + timedelta(days=6)
    start_date = anchor_date.replace(day=1)
    if start_date.month == 12:
        next_month = start_date.replace(year=start_date.year + 1, month=1)
    else:
        next_month = start_date.replace(month=start_date.month + 1)
    return start_date, next_month - timedelta(days=1)


async def _summary_values(
    session: AsyncSession, start: datetime, end: datetime
) -> tuple[int, Decimal, Decimal, Decimal]:
    totals = await session.execute(
        select(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total), Decimal("0.00")),
        ).where(Sale.created_at >= start, Sale.created_at < end, Sale.items.any())
    )
    sale_count, total = totals.one()
    payment_totals = await session.execute(
        select(Payment.method, func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
        .join(Sale, Sale.id == Payment.sale_id)
        .where(Sale.created_at >= start, Sale.created_at < end)
        .group_by(Payment.method)
    )
    payments_by_method = dict(payment_totals.all())
    return (
        sale_count,
        total,
        payments_by_method.get("cash", Decimal("0.00")),
        payments_by_method.get("mpesa", Decimal("0.00")),
    )


@router.post("", response_model=SaleRead, status_code=status.HTTP_201_CREATED)
async def create_sale(
    payload: SaleCreate,
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> Sale:
    product_ids = sorted(item.product_id for item in payload.items)
    products_result = await session.scalars(
        select(Product)
        .where(Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
    )
    products = {product.id: product for product in products_result.all()}
    if len(products) != len(product_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="One or more products were not found"
        )

    for item in payload.items:
        product = products[item.product_id]
        if not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product {product.sku} is inactive",
            )
        if product.stock_quantity < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient stock for product {product.sku}",
            )

    line_data: list[tuple[Product, Decimal, Decimal]] = []
    total = Decimal("0.00")
    for item in payload.items:
        product = products[item.product_id]
        line_total = (product.unit_price * item.quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        line_data.append((product, item.quantity, line_total))
        total += line_total

    payment_total = sum((payment.amount for payment in payload.payments), Decimal("0.00"))
    if payment_total != total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payment allocations must equal the sale total",
        )

    for payment in payload.payments:
        if payment.method == "cash" and payment.cash_received is not None:
            if payment.cash_received < payment.amount:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Cash received must be at least the cash payment amount",
                )

    sale = Sale(currency=get_settings().currency, subtotal=total, total=total)
    session.add(sale)
    await session.flush()

    for product, quantity, line_total in line_data:
        product.stock_quantity -= quantity
        session.add(
            SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=quantity,
                unit_price=product.unit_price,
                line_total=line_total,
            )
        )
        session.add(
            StockMovement(
                product_id=product.id,
                quantity_delta=-quantity,
                reason=f"Sale {sale.id}",
                reference_type="sale",
                reference_id=sale.id,
            )
        )

    for payment in payload.payments:
        session.add(
            Payment(
                sale_id=sale.id,
                method=payment.method,
                amount=payment.amount,
                cash_received=(
                    payment.cash_received
                    if payment.method == "cash" and payment.cash_received is not None
                    else payment.amount
                    if payment.method == "cash"
                    else Decimal("0")
                ),
                change_given=(
                    payment.cash_received - payment.amount
                    if payment.method == "cash" and payment.cash_received is not None
                    else Decimal("0")
                ),
                mpesa_reference=payment.mpesa_reference,
            )
        )

    await session.flush()
    result = await session.scalar(
        select(Sale)
        .where(Sale.id == sale.id)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
    )
    if result is None:
        raise RuntimeError("Newly created sale could not be reloaded")
    return result


@router.get("", response_model=list[SaleRead])
async def list_sales(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    sale_date: date | None = Query(default=None, alias="date"),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> list[Sale]:
    if sale_date is not None and (from_date is not None or to_date is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use either date or from_date/to_date, not both",
        )
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from_date cannot be after to_date",
        )

    statement = (
        select(Sale)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
        .where(Sale.items.any())
    )
    if sale_date is not None:
        start, end = _day_bounds(sale_date)
        statement = statement.where(Sale.created_at >= start, Sale.created_at < end)
    else:
        if from_date is not None:
            start, _ = _day_bounds(from_date)
            statement = statement.where(Sale.created_at >= start)
        if to_date is not None:
            _, end = _day_bounds(to_date)
            statement = statement.where(Sale.created_at < end)
    result = await session.scalars(
        statement.order_by(Sale.created_at.desc(), Sale.id.desc()).offset(offset).limit(limit)
    )
    return [sale for sale in result.all() if sale.items]


@router.get("/returns", response_model=list[SaleReturnRead])
async def list_returns(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> list[SaleReturnRecord]:
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from_date cannot be after to_date",
        )
    statement = select(SaleReturnRecord)
    if from_date is not None:
        start, _ = _day_bounds(from_date)
        statement = statement.where(SaleReturnRecord.created_at >= start)
    if to_date is not None:
        _, end = _day_bounds(to_date)
        statement = statement.where(SaleReturnRecord.created_at < end)
    result = await session.scalars(
        statement.order_by(SaleReturnRecord.created_at.desc(), SaleReturnRecord.id.desc()).limit(limit)
    )
    return list(result.all())


@router.get("/summary/daily", response_model=DailySalesSummary)
async def daily_sales_summary(
    sale_date: date = Query(alias="date"),
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> DailySalesSummary:
    start, end = _day_bounds(sale_date)
    sale_count, total, cash_total, mpesa_total = await _summary_values(session, start, end)
    return DailySalesSummary(
        date=sale_date,
        sale_count=sale_count,
        total=total,
        cash_total=cash_total,
        mpesa_total=mpesa_total,
    )


async def _sum_column(session: AsyncSession, statement) -> Decimal:
    value = await session.scalar(statement)
    return value if value is not None else Decimal("0.00")


@router.get("/profit", response_model=ProfitAndLoss)
async def profit_and_loss(
    report_date: date = Query(alias="date"),
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> ProfitAndLoss:
    start_date, end_date = _period_dates(report_date, period)
    start, end = _date_range_bounds(start_date, end_date)
    retail_sales = await _sum_column(
        session,
        select(func.coalesce(func.sum(Sale.total), Decimal("0.00"))).where(
            Sale.created_at >= start, Sale.created_at < end
        ),
    )
    wholesale_sales = await _sum_column(
        session,
        select(func.coalesce(func.sum(WholesaleSale.total), Decimal("0.00"))).where(
            WholesaleSale.created_at >= start, WholesaleSale.created_at < end
        ),
    )
    retail_cost = await _sum_column(
        session,
        select(func.coalesce(func.sum(SaleItem.quantity * Product.cost_price), Decimal("0.00")))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(
            Sale.created_at >= start,
            Sale.created_at < end,
            Product.cost_price.is_not(None),
        ),
    )
    wholesale_cost = await _sum_column(
        session,
        select(
            func.coalesce(func.sum(WholesaleSaleItem.quantity * Product.cost_price), Decimal("0.00"))
        )
        .join(WholesaleSale, WholesaleSale.id == WholesaleSaleItem.sale_id)
        .join(Product, Product.id == WholesaleSaleItem.product_id)
        .where(
            WholesaleSale.created_at >= start,
            WholesaleSale.created_at < end,
            Product.cost_price.is_not(None),
        ),
    )
    uncosted_retail = await _sum_column(
        session,
        select(func.coalesce(func.sum(SaleItem.line_total), Decimal("0.00")))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(Sale.created_at >= start, Sale.created_at < end, Product.cost_price.is_(None)),
    )
    uncosted_wholesale = await _sum_column(
        session,
        select(func.coalesce(func.sum(WholesaleSaleItem.line_total), Decimal("0.00")))
        .join(WholesaleSale, WholesaleSale.id == WholesaleSaleItem.sale_id)
        .join(Product, Product.id == WholesaleSaleItem.product_id)
        .where(
            WholesaleSale.created_at >= start,
            WholesaleSale.created_at < end,
            Product.cost_price.is_(None),
        ),
    )
    retail_sales, wholesale_sales, cost, net = _profit_statement(
        retail_sales, wholesale_sales, retail_cost + wholesale_cost
    )
    return ProfitAndLoss(
        period=period,
        start_date=start_date,
        end_date=end_date,
        retail_sales=retail_sales,
        wholesale_sales=wholesale_sales,
        cost=cost,
        uncosted_sales=uncosted_retail + uncosted_wholesale,
        net=net,
    )


@router.get("/summary", response_model=SalesSummary)
async def sales_summary(
    report_date: date = Query(alias="date"),
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> SalesSummary:
    start_date, end_date = _period_dates(report_date, period)
    start, end = _date_range_bounds(start_date, end_date)
    sale_count, total, cash_total, mpesa_total = await _summary_values(session, start, end)
    return SalesSummary(
        date=report_date,
        period=period,
        start_date=start_date,
        end_date=end_date,
        sale_count=sale_count,
        total=total,
        cash_total=cash_total,
        mpesa_total=mpesa_total,
    )


@router.patch("/{sale_id}", response_model=SaleRead)
async def amend_sale(
    sale_id: int,
    payload: SaleAmend,
    session: AsyncSession = Depends(get_db),
    _admin: Staff = Depends(require_admin),
) -> Sale:
    sale = await session.scalar(
        select(Sale)
        .where(Sale.id == sale_id)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
        .with_for_update()
    )
    if sale is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")

    existing_items = list(sale.items)
    previous_quantities = {item.product_id: item.quantity for item in existing_items}
    original_prices = {item.product_id: item.unit_price for item in existing_items}
    original_labels = {item.product_id: (item.product_name, item.sku) for item in existing_items}
    requested_quantities = {item.product_id: item.quantity for item in payload.items}
    product_ids = sorted(set(previous_quantities) | set(requested_quantities))
    products_result = await session.scalars(
        select(Product)
        .where(Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
    )
    products = {product.id: product for product in products_result.all()}
    if any(product_id not in products for product_id in product_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="One or more products were not found"
        )

    for item in payload.items:
        product = products[item.product_id]
        previous = previous_quantities.get(item.product_id, Decimal("0"))
        if item.quantity > previous and not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product {product.sku} is inactive",
            )

    stock_deltas: list[tuple[Product, Decimal]] = []
    for product_id in product_ids:
        product = products[product_id]
        delta = requested_quantities.get(product_id, Decimal("0")) - previous_quantities.get(
            product_id, Decimal("0")
        )
        if delta > 0 and product.stock_quantity < delta:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient stock for product {product.sku}",
            )
        if delta != 0:
            stock_deltas.append((product, delta))

    replacement_lines: list[SaleItem] = []
    total = Decimal("0.00")
    for item in payload.items:
        product = products[item.product_id]
        if item.product_id in original_prices:
            unit_price = original_prices[item.product_id]
            product_name, sku = original_labels[item.product_id]
        else:
            unit_price = product.unit_price
            product_name, sku = product.name, product.sku
        line_total = (unit_price * item.quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        total += line_total
        replacement_lines.append(
            SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product_name,
                sku=sku,
                quantity=item.quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    difference = total - sale.total
    if difference == 0:
        if payload.settlement_method is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No payment is due for this change",
            )
    elif payload.settlement_method is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Record how the price difference was settled",
        )
    elif difference < 0 and (
        payload.cash_received is not None or payload.mpesa_reference is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A refund only needs the payment method",
        )

    refundable: list[Payment] = []
    top_up_cash_received = Decimal("0.00")
    top_up_change = Decimal("0.00")
    if difference < 0:
        refund = -difference
        refundable = [
            payment
            for payment in sale.payments
            if payment.method == payload.settlement_method
        ]
        if sum((payment.amount for payment in refundable), Decimal("0.00")) < refund:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That payment method does not cover the refund",
            )
    elif difference > 0 and payload.settlement_method == "cash":
        top_up_cash_received = (
            payload.cash_received if payload.cash_received is not None else difference
        )
        if top_up_cash_received < difference:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cash received must be at least the additional cash amount",
            )
        top_up_change = top_up_cash_received - difference

    for product, delta in stock_deltas:
        product.stock_quantity -= delta
        session.add(
            StockMovement(
                product_id=product.id,
                quantity_delta=-delta,
                reason=f"Sale {sale.id} amended",
                reference_type="sale",
                reference_id=sale.id,
            )
        )

    sale.items.clear()
    sale.items.extend(replacement_lines)
    sale.subtotal = total
    sale.total = total

    if difference > 0:
        amount = difference
        if payload.settlement_method == "cash":
            cash_received = top_up_cash_received
            change_given = top_up_change
        else:
            cash_received = Decimal("0.00")
            change_given = Decimal("0.00")
        sale.payments.append(
            Payment(
                sale_id=sale.id,
                method=payload.settlement_method,
                amount=amount,
                cash_received=cash_received,
                change_given=change_given,
                mpesa_reference=(
                    payload.mpesa_reference if payload.settlement_method == "mpesa" else None
                ),
            )
        )
    elif difference < 0:
        refund = -difference
        for payment in sorted(refundable, key=lambda payment: payment.id or 0, reverse=True):
            if refund <= 0:
                break
            if payment.amount <= refund:
                refund -= payment.amount
                sale.payments.remove(payment)
            else:
                payment.amount -= refund
                refund = Decimal("0.00")
                if payment.method == "cash":
                    payment.cash_received = payment.amount
                    payment.change_given = Decimal("0.00")

    await session.flush()
    return sale


def _credit_for_quantity(item: SaleItem, quantity: Decimal) -> Decimal:
    if quantity > item.quantity:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Quantity is higher than the quantity sold",
        )
    if quantity == item.quantity:
        return item.line_total
    return (item.unit_price * quantity).quantize(CENT, rounding=ROUND_HALF_UP)


def _reduce_or_remove_line(sale: Sale, item: SaleItem, quantity: Decimal, credit: Decimal) -> None:
    if quantity == item.quantity:
        sale.items.remove(item)
        return
    item.quantity -= quantity
    item.line_total -= credit


async def _products_for_update(
    session: AsyncSession, product_ids: list[int]
) -> dict[int, Product]:
    products_result = await session.scalars(
        select(Product)
        .where(Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
    )
    products = {product.id: product for product in products_result.all()}
    if any(product_id not in products for product_id in product_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="One or more products were not found"
        )
    return products


def _move_stock(
    session: AsyncSession,
    sale_id: int,
    product: Product,
    quantity_delta: Decimal,
    reason: str,
) -> None:
    if quantity_delta == 0:
        return
    if quantity_delta < 0 and product.stock_quantity < -quantity_delta:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Insufficient stock for product {product.sku}",
        )
    product.stock_quantity += quantity_delta
    session.add(
        StockMovement(
            product_id=product.id,
            quantity_delta=quantity_delta,
            reason=reason,
            reference_type="sale",
            reference_id=sale_id,
        )
    )


def _apply_payment_difference(
    sale: Sale,
    difference: Decimal,
    method: str | None,
    cash_received: Decimal | None,
    mpesa_reference: str | None,
) -> None:
    if difference == 0:
        if method is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No payment is due for this change",
            )
        return
    if method is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Record how the price difference was settled",
        )
    if difference < 0 and (cash_received is not None or mpesa_reference is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A refund only needs the payment method",
        )
    if difference < 0:
        refund = -difference
        refundable = [payment for payment in sale.payments if payment.method == method]
        if sum((payment.amount for payment in refundable), Decimal("0.00")) < refund:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That payment method does not cover the refund",
            )
        for payment in sorted(refundable, key=lambda payment: payment.id or 0, reverse=True):
            if refund <= 0:
                break
            if payment.amount <= refund:
                refund -= payment.amount
                sale.payments.remove(payment)
            else:
                payment.amount -= refund
                refund = Decimal("0.00")
                if payment.method == "cash":
                    payment.cash_received = payment.amount
                    payment.change_given = Decimal("0.00")
        return

    if method == "cash":
        received = cash_received if cash_received is not None else difference
        if received < difference:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cash received must be at least the additional cash amount",
            )
        change_given = received - difference
    else:
        received = Decimal("0.00")
        change_given = Decimal("0.00")
    sale.payments.append(
        Payment(
            sale_id=sale.id,
            method=method,
            amount=difference,
            cash_received=received,
            change_given=change_given,
            mpesa_reference=mpesa_reference if method == "mpesa" else None,
        )
    )


async def _sale_for_update(session: AsyncSession, sale_id: int) -> Sale:
    sale = await session.scalar(
        select(Sale)
        .where(Sale.id == sale_id)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
        .with_for_update()
    )
    if sale is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")
    return sale


@router.post("/{sale_id}/return", response_model=SaleRead)
async def return_sale_item(
    sale_id: int,
    payload: SaleReturn,
    session: AsyncSession = Depends(get_db),
    _admin: Staff = Depends(require_admin),
) -> Sale:
    sale = await _sale_for_update(session, sale_id)
    item = next((line for line in sale.items if line.id == payload.sale_item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale item not found")
    credit = _credit_for_quantity(item, payload.quantity)
    session.add(
        SaleReturnRecord(
            sale_id=sale.id,
            product_id=item.product_id,
            product_name=item.product_name,
            sku=item.sku,
            quantity=payload.quantity,
            unit_price=item.unit_price,
            amount=credit,
            method=payload.settlement_method,
            kind="return",
            created_at=datetime.now(timezone.utc),
        )
    )
    products = await _products_for_update(session, [item.product_id])
    _apply_payment_difference(sale, -credit, payload.settlement_method, None, None)
    _move_stock(
        session,
        sale.id,
        products[item.product_id],
        payload.quantity,
        f"Sale {sale.id} return",
    )
    _reduce_or_remove_line(sale, item, payload.quantity, credit)
    sale.subtotal -= credit
    sale.total -= credit
    await session.flush()
    return sale


@router.post("/{sale_id}/change", response_model=SaleRead)
async def change_sale_item(
    sale_id: int,
    payload: SaleChange,
    session: AsyncSession = Depends(get_db),
    _admin: Staff = Depends(require_admin),
) -> Sale:
    sale = await _sale_for_update(session, sale_id)
    item = next((line for line in sale.items if line.id == payload.sale_item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale item not found")
    if payload.replacement_product_id == item.product_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose a different product to change this item",
        )
    credit = _credit_for_quantity(item, payload.quantity)
    products = await _products_for_update(
        session, [item.product_id, payload.replacement_product_id]
    )
    replacement = products[payload.replacement_product_id]
    existing_replacement = next(
        (line for line in sale.items if line.product_id == replacement.id), None
    )
    if existing_replacement is None and not replacement.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Product {replacement.sku} is inactive",
        )
    if replacement.stock_quantity < payload.replacement_quantity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Insufficient stock for product {replacement.sku}",
        )
    unit_price = existing_replacement.unit_price if existing_replacement else replacement.unit_price
    charge = (unit_price * payload.replacement_quantity).quantize(CENT, rounding=ROUND_HALF_UP)
    session.add(
        SaleReturnRecord(
            sale_id=sale.id,
            product_id=item.product_id,
            product_name=item.product_name,
            sku=item.sku,
            quantity=payload.quantity,
            unit_price=item.unit_price,
            amount=charge - credit,
            method=payload.settlement_method,
            kind="change",
            replacement_product_name=(
                existing_replacement.product_name if existing_replacement else replacement.name
            ),
            replacement_quantity=payload.replacement_quantity,
            created_at=datetime.now(timezone.utc),
        )
    )
    _apply_payment_difference(
        sale,
        charge - credit,
        payload.settlement_method,
        payload.cash_received,
        payload.mpesa_reference,
    )
    _move_stock(
        session,
        sale.id,
        products[item.product_id],
        payload.quantity,
        f"Sale {sale.id} return",
    )
    _move_stock(
        session,
        sale.id,
        replacement,
        -payload.replacement_quantity,
        f"Sale {sale.id} change",
    )
    _reduce_or_remove_line(sale, item, payload.quantity, credit)
    if existing_replacement is None:
        sale.items.append(
            SaleItem(
                sale_id=sale.id,
                product_id=replacement.id,
                product_name=replacement.name,
                sku=replacement.sku,
                quantity=payload.replacement_quantity,
                unit_price=unit_price,
                line_total=charge,
            )
        )
    else:
        existing_replacement.quantity += payload.replacement_quantity
        existing_replacement.line_total += charge
    sale.subtotal = sale.subtotal - credit + charge
    sale.total = sale.subtotal
    await session.flush()
    return sale


@router.get("/{sale_id}", response_model=SaleRead)
async def get_sale(
    sale_id: int,
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> Sale:
    sale = await session.scalar(
        select(Sale)
        .where(Sale.id == sale_id)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
    )
    if sale is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")
    return sale
