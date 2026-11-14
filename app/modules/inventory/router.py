from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_staff, require_admin
from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.inventory.schemas import (
    FastMovingProductRead,
    InventoryInsights,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    StockAdjustmentCreate,
)
from app.modules.sales.models import Sale, SaleItem
from app.modules.wholesale.models import WholesaleSale, WholesaleSaleItem

router = APIRouter()
INSIGHTS_PERIOD_DAYS = 30
FAST_MOVER_LIMIT = 10


@router.get("/insights", response_model=InventoryInsights)
async def inventory_insights(
    session: Annotated[AsyncSession, Depends(get_db)],
    _staff: Annotated[Staff, Depends(get_current_staff)],
) -> InventoryInsights:
    cutoff = datetime.now(timezone.utc) - timedelta(days=INSIGHTS_PERIOD_DAYS)
    stock_value = await session.scalar(
        select(func.coalesce(func.sum(Product.unit_price * Product.stock_quantity), 0))
    )

    recent_items = union_all(
        select(SaleItem.product_id, SaleItem.quantity)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(Sale.created_at >= cutoff),
        select(WholesaleSaleItem.product_id, WholesaleSaleItem.quantity)
        .join(WholesaleSale, WholesaleSale.id == WholesaleSaleItem.sale_id)
        .where(WholesaleSale.created_at >= cutoff),
    ).subquery()
    sales_by_product = (
        select(
            recent_items.c.product_id,
            func.sum(recent_items.c.quantity).label("quantity_sold"),
        )
        .group_by(recent_items.c.product_id)
        .subquery()
    )
    result = await session.execute(
        select(
            Product.id,
            Product.name,
            Product.sku,
            Product.unit_price,
            Product.stock_quantity,
            sales_by_product.c.quantity_sold,
        )
        .join(sales_by_product, sales_by_product.c.product_id == Product.id)
        .where(Product.is_active.is_(True))
        .order_by(
            sales_by_product.c.quantity_sold.desc(),
            Product.name,
            Product.id,
        )
        .limit(FAST_MOVER_LIMIT)
    )
    fast_movers = [
        FastMovingProductRead(
            id=row.id,
            name=row.name,
            sku=row.sku,
            unit_price=row.unit_price,
            stock_quantity=row.stock_quantity,
            quantity_sold=row.quantity_sold,
        )
        for row in result.all()
    ]
    return InventoryInsights(
        currency=get_settings().currency,
        stock_value=stock_value or Decimal("0.00"),
        period_days=INSIGHTS_PERIOD_DAYS,
        fast_movers=fast_movers,
    )


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[Staff, Depends(require_admin)],
) -> Product:
    sku = (
        payload.sku.strip()
        if payload.sku and payload.sku.strip()
        else f"UL-{uuid4().hex.upper()}"
    )
    duplicate = await session.scalar(
        select(Product.id).where(
            or_(
                Product.sku == sku,
                Product.barcode == payload.barcode if payload.barcode else False,
            )
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="SKU or barcode already exists"
        )

    product = Product(
        sku=sku,
        barcode=payload.barcode,
        name=payload.name,
        category=payload.category,
        unit_price=payload.unit_price,
        stock_quantity=payload.initial_stock,
        low_stock_threshold=payload.low_stock_threshold,
    )
    session.add(product)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="SKU or barcode already exists"
        ) from exc

    if payload.initial_stock:
        session.add(
            StockMovement(
                product_id=product.id,
                quantity_delta=payload.initial_stock,
                reason="Initial stock",
                reference_type="initial",
            )
        )
    return product


@router.get("/products", response_model=list[ProductRead])
async def list_products(
    search: str | None = None,
    active_only: bool = True,
    low_stock_only: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    _staff: Staff = Depends(get_current_staff),
) -> list[Product]:
    statement = select(Product)
    if active_only:
        statement = statement.where(Product.is_active.is_(True))
    if low_stock_only:
        statement = statement.where(Product.stock_quantity <= Product.low_stock_threshold)
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(Product.name.ilike(term), Product.sku.ilike(term), Product.barcode.ilike(term))
        )
    result = await session.scalars(
        statement.order_by(Product.name, Product.id).offset(offset).limit(limit)
    )
    return list(result.all())


@router.get("/products/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    _staff: Annotated[Staff, Depends(get_current_staff)],
) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.patch("/products/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[Staff, Depends(require_admin)],
) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    changes = payload.model_dump(exclude_unset=True)
    nullable_fields = {"barcode", "category"}
    if any(value is None and field not in nullable_fields for field, value in changes.items()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Fields cannot be null"
        )
    if "sku" in changes or "barcode" in changes:
        sku = changes.get("sku", product.sku)
        barcode = changes.get("barcode", product.barcode)
        duplicate_query = select(Product.id).where(Product.id != product_id, Product.sku == sku)
        if barcode is not None:
            duplicate_query = select(Product.id).where(
                Product.id != product_id, or_(Product.sku == sku, Product.barcode == barcode)
            )
        duplicate = await session.scalar(duplicate_query)
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="SKU or barcode already exists"
            )

    for field, value in changes.items():
        setattr(product, field, value)
    return product


@router.post("/products/{product_id}/stock-adjustments", response_model=ProductRead)
async def adjust_stock(
    product_id: int,
    payload: StockAdjustmentCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[Staff, Depends(require_admin)],
) -> Product:
    if payload.quantity_delta == Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="quantity_delta must not be zero",
        )
    product = await session.scalar(
        select(Product).where(Product.id == product_id).with_for_update()
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    new_quantity = product.stock_quantity + payload.quantity_delta
    if new_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Stock cannot be reduced below zero"
        )
    product.stock_quantity = new_quantity
    session.add(
        StockMovement(
            product_id=product.id,
            quantity_delta=payload.quantity_delta,
            reason=payload.reason,
        )
    )
    return product
