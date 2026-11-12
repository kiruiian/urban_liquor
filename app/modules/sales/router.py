from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_staff
from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.sales.models import Payment, Sale, SaleItem
from app.modules.sales.schemas import (
    DailySalesSummary,
    SaleCreate,
    SaleRead,
    SalesSummary,
)

router = APIRouter()
CENT = Decimal("0.01")
STORE_TIMEZONE = ZoneInfo("Africa/Nairobi")


def _day_bounds(sale_date: date) -> tuple[datetime, datetime]:
    return _date_range_bounds(sale_date, sale_date)


def _date_range_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(start_date, time.min, tzinfo=STORE_TIMEZONE)
    local_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=STORE_TIMEZONE)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


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
        ).where(Sale.created_at >= start, Sale.created_at < end)
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

    statement = select(Sale).options(selectinload(Sale.items), selectinload(Sale.payments))
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
