from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_staff, require_admin
from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.wholesale.models import (
    WholesaleCustomer,
    WholesalePayment,
    WholesaleSale,
    WholesaleSaleItem,
)
from app.modules.wholesale.schemas import (
    WholesaleCustomerCreate,
    WholesaleCustomerRead,
    WholesaleCustomerUpdate,
    WholesalePaymentCreate,
    WholesaleSaleCreate,
    WholesaleSaleRead,
)

router = APIRouter()
CENT = Decimal("0.01")


@router.get("/customers", response_model=list[WholesaleCustomerRead])
async def list_customers(
    active_only: bool = True,
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> list[WholesaleCustomer]:
    statement = select(WholesaleCustomer)
    if active_only:
        statement = statement.where(WholesaleCustomer.is_active.is_(True))
    result = await session.scalars(
        statement.order_by(WholesaleCustomer.name, WholesaleCustomer.id)
    )
    return list(result.all())


@router.post(
    "/customers",
    response_model=WholesaleCustomerRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer(
    payload: WholesaleCustomerCreate,
    session: AsyncSession = Depends(get_db),
    _admin: Staff = Depends(require_admin),
) -> WholesaleCustomer:
    customer = WholesaleCustomer(**payload.model_dump())
    session.add(customer)
    await session.flush()
    return customer


@router.patch("/customers/{customer_id}", response_model=WholesaleCustomerRead)
async def update_customer(
    customer_id: int,
    payload: WholesaleCustomerUpdate,
    session: AsyncSession = Depends(get_db),
    _admin: Staff = Depends(require_admin),
) -> WholesaleCustomer:
    customer = await session.get(WholesaleCustomer, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    changes = payload.model_dump(exclude_unset=True)
    if any(value is None for field, value in changes.items() if field in {"name", "is_active"}):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Shop name and active status cannot be null",
        )
    for field, value in changes.items():
        setattr(customer, field, value)
    return customer


@router.get("/sales", response_model=list[WholesaleSaleRead])
async def list_wholesale_sales(
    customer_id: int | None = Query(default=None, gt=0),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> list[WholesaleSale]:
    statement = select(WholesaleSale).options(
        selectinload(WholesaleSale.items),
        selectinload(WholesaleSale.payments),
    )
    if customer_id is not None:
        statement = statement.where(WholesaleSale.customer_id == customer_id)
    result = await session.scalars(
        statement.order_by(WholesaleSale.created_at.desc(), WholesaleSale.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())


@router.post(
    "/sales",
    response_model=WholesaleSaleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_wholesale_sale(
    payload: WholesaleSaleCreate,
    session: AsyncSession = Depends(get_db),
    staff: Staff = Depends(get_current_staff),
) -> WholesaleSale:
    customer = await session.get(WholesaleCustomer, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot record a delivery for an inactive shop",
        )

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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more products were not found",
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

    line_data: list[tuple[Product, Decimal, Decimal, Decimal]] = []
    total = Decimal("0.00")
    for item in payload.items:
        line_total = (item.unit_price * item.quantity).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        line_data.append((products[item.product_id], item.quantity, item.unit_price, line_total))
        total += line_total

    payment_total = sum(
        (payment.amount for payment in payload.payments), Decimal("0.00")
    )
    if payment_total > total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payments cannot exceed the delivery total",
        )
    for payment in payload.payments:
        if payment.method == "cash" and payment.cash_received is not None:
            if payment.cash_received < payment.amount:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Cash received must be at least the cash payment amount",
                )

    sale = WholesaleSale(
        customer_id=customer.id,
        customer_name=customer.name,
        delivery_reference=payload.delivery_reference,
        created_by_id=staff.id,
        created_by_name=staff.full_name,
        currency=get_settings().currency,
        total=total,
        items=[],
        payments=[],
    )
    for product, quantity, unit_price, line_total in line_data:
        product.stock_quantity -= quantity
        sale.items.append(
            WholesaleSaleItem(
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
        )
    session.add(sale)
    await session.flush()

    for product, quantity, _unit_price, _line_total in line_data:
        session.add(
            StockMovement(
                product_id=product.id,
                quantity_delta=-quantity,
                reason=f"Wholesale delivery {sale.id}",
                reference_type="wholesale_sale",
                reference_id=sale.id,
            )
        )
    for payment in payload.payments:
        sale.payments.append(
            WholesalePayment(
                method=payment.method,
                amount=payment.amount,
                cash_received=(
                    payment.cash_received
                    if payment.method == "cash" and payment.cash_received is not None
                    else payment.amount
                    if payment.method == "cash"
                    else Decimal("0.00")
                ),
                change_given=(
                    payment.cash_received - payment.amount
                    if payment.method == "cash" and payment.cash_received is not None
                    else Decimal("0.00")
                ),
                mpesa_reference=payment.mpesa_reference,
            )
        )

    await session.flush()
    return sale


@router.post(
    "/sales/{sale_id}/payments",
    response_model=WholesaleSaleRead,
)
async def add_wholesale_payment(
    sale_id: int,
    payload: WholesalePaymentCreate,
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> WholesaleSale:
    sale = await session.scalar(
        select(WholesaleSale)
        .where(WholesaleSale.id == sale_id)
        .options(
            selectinload(WholesaleSale.items),
            selectinload(WholesaleSale.payments),
        )
        .with_for_update()
    )
    if sale is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wholesale delivery not found"
        )

    amount_paid = sum((payment.amount for payment in sale.payments), Decimal("0.00"))
    balance_due = sale.total - amount_paid
    if payload.amount > balance_due:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Payment exceeds the outstanding balance of {balance_due}",
        )
    if payload.method == "cash" and payload.cash_received is not None:
        if payload.cash_received < payload.amount:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cash received must be at least the payment amount",
            )

    sale.payments.append(
        WholesalePayment(
            method=payload.method,
            amount=payload.amount,
            cash_received=(
                payload.cash_received
                if payload.method == "cash" and payload.cash_received is not None
                else payload.amount
                if payload.method == "cash"
                else Decimal("0.00")
            ),
            change_given=(
                payload.cash_received - payload.amount
                if payload.method == "cash" and payload.cash_received is not None
                else Decimal("0.00")
            ),
            mpesa_reference=payload.mpesa_reference,
        )
    )
    await session.flush()
    return sale
