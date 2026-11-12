from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.modules.auth.dependencies import require_admin
from app.modules.auth.models import Staff
from app.modules.inventory.models import Product, StockMovement
from app.modules.suppliers.models import Supplier, SupplierReceipt, SupplierReceiptItem
from app.modules.suppliers.schemas import (
    SupplierCreate,
    SupplierRead,
    SupplierReceiptCreate,
    SupplierReceiptRead,
    SupplierUpdate,
)

router = APIRouter()


@router.get("", response_model=list[SupplierRead])
async def list_suppliers(
    active_only: bool = True,
    session: AsyncSession = Depends(get_db),
    _admin: Staff = Depends(require_admin),
) -> list[Supplier]:
    statement = select(Supplier)
    if active_only:
        statement = statement.where(Supplier.is_active.is_(True))
    result = await session.scalars(statement.order_by(Supplier.name, Supplier.id))
    return list(result.all())


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    payload: SupplierCreate,
    session: AsyncSession = Depends(get_db),
    _admin: Staff = Depends(require_admin),
) -> Supplier:
    supplier = Supplier(**payload.model_dump())
    session.add(supplier)
    await session.flush()
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierRead)
async def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    session: AsyncSession = Depends(get_db),
    _admin: Staff = Depends(require_admin),
) -> Supplier:
    supplier = await session.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")

    changes = payload.model_dump(exclude_unset=True)
    if any(value is None for field, value in changes.items() if field in {"name", "is_active"}):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Supplier name and active status cannot be null",
        )
    for field, value in changes.items():
        setattr(supplier, field, value)
    return supplier


@router.get("/receipts", response_model=list[SupplierReceiptRead])
async def list_supplier_receipts(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    _admin: Staff = Depends(require_admin),
) -> list[SupplierReceipt]:
    result = await session.scalars(
        select(SupplierReceipt)
        .options(selectinload(SupplierReceipt.items))
        .order_by(SupplierReceipt.received_at.desc(), SupplierReceipt.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())


@router.post(
    "/receipts",
    response_model=SupplierReceiptRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_supplier_receipt(
    payload: SupplierReceiptCreate,
    session: AsyncSession = Depends(get_db),
    admin: Staff = Depends(require_admin),
) -> SupplierReceipt:
    supplier = await session.get(Supplier, payload.supplier_id)
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    if not supplier.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot record a receipt for an inactive supplier",
        )

    if payload.supplier_reference:
        duplicate = await session.scalar(
            select(SupplierReceipt.id).where(
                SupplierReceipt.supplier_id == supplier.id,
                SupplierReceipt.supplier_reference == payload.supplier_reference,
            )
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This supplier reference has already been recorded",
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

    receipt = SupplierReceipt(
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        supplier_reference=payload.supplier_reference,
        received_by_id=admin.id,
        received_by_name=admin.full_name,
        items=[],
    )
    session.add(receipt)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This supplier reference has already been recorded",
        ) from exc

    for item in payload.items:
        product = products[item.product_id]
        product.stock_quantity += item.quantity_received
        receipt_item = SupplierReceiptItem(
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            quantity_received=item.quantity_received,
        )
        receipt.items.append(receipt_item)
        session.add(
            StockMovement(
                product_id=product.id,
                quantity_delta=item.quantity_received,
                reason=f"Supplier receipt {receipt.id}",
                reference_type="supplier_receipt",
                reference_id=receipt.id,
            )
        )

    await session.flush()
    return receipt
