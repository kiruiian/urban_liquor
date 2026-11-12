from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(254))
    address: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    receipts: Mapped[list["SupplierReceipt"]] = relationship(back_populates="supplier")


class SupplierReceipt(Base):
    __tablename__ = "supplier_receipts"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id",
            "supplier_reference",
            name="uq_supplier_receipts_supplier_reference",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    supplier_name: Mapped[str] = mapped_column(String(160))
    supplier_reference: Mapped[str | None] = mapped_column(String(80))
    received_by_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    received_by_name: Mapped[str] = mapped_column(String(120))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    supplier: Mapped[Supplier] = relationship(back_populates="receipts")
    items: Mapped[list["SupplierReceiptItem"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="SupplierReceiptItem.id",
    )


class SupplierReceiptItem(Base):
    __tablename__ = "supplier_receipt_items"
    __table_args__ = (
        CheckConstraint(
            "quantity_received > 0",
            name="ck_supplier_receipt_items_quantity_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_receipts.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    sku: Mapped[str] = mapped_column(String(64))
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 3))

    receipt: Mapped[SupplierReceipt] = relationship(back_populates="items")
