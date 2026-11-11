from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_staff
from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.sales.models import Payment, Sale, SaleItem
from app.modules.sales.schemas import SaleCreate, SaleRead

router = APIRouter()
CENT = Decimal("0.01")


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
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> list[Sale]:
    result = await session.scalars(
        select(Sale)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
        .order_by(Sale.created_at.desc(), Sale.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())


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
