from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_sales_subtotal_nonnegative"),
        CheckConstraint("total >= 0", name="ck_sales_total_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", order_by="SaleItem.id"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", order_by="Payment.id"
    )


class SaleItem(Base):
    __tablename__ = "sale_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sale_items_price_nonnegative"),
        CheckConstraint("line_total >= 0", name="ck_sale_items_total_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    sku: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    sale: Mapped[Sale] = relationship(back_populates="items")


class SaleReturnRecord(Base):
    __tablename__ = "sale_returns"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_returns_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sale_returns_price_nonnegative"),
        CheckConstraint("method IN ('cash', 'mpesa')", name="ck_sale_returns_method_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    sku: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str | None] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16), default="return")
    replacement_product_name: Mapped[str | None] = mapped_column(String(160))
    replacement_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint(
            "method != 'cash' OR cash_received >= amount",
            name="ck_payments_cash_received_gte_amount",
        ),
        CheckConstraint("method IN ('cash', 'mpesa')", name="ck_payments_method_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cash_received: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    change_given: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    mpesa_reference: Mapped[str | None] = mapped_column(String(64))

    sale: Mapped[Sale] = relationship(back_populates="payments")
