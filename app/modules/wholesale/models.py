from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WholesaleCustomer(Base):
    __tablename__ = "wholesale_customers"

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

    sales: Mapped[list["WholesaleSale"]] = relationship(back_populates="customer")


class WholesaleSale(Base):
    __tablename__ = "wholesale_sales"
    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_wholesale_sales_total_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("wholesale_customers.id"), index=True
    )
    customer_name: Mapped[str] = mapped_column(String(160))
    delivery_reference: Mapped[str | None] = mapped_column(String(80))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    created_by_name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    customer: Mapped[WholesaleCustomer] = relationship(back_populates="sales")
    items: Mapped[list["WholesaleSaleItem"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="WholesaleSaleItem.id",
    )
    payments: Mapped[list["WholesalePayment"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="WholesalePayment.id",
    )


class WholesaleSaleItem(Base):
    __tablename__ = "wholesale_sale_items"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0", name="ck_wholesale_sale_items_quantity_positive"
        ),
        CheckConstraint(
            "unit_price >= 0", name="ck_wholesale_sale_items_price_nonnegative"
        ),
        CheckConstraint(
            "line_total >= 0", name="ck_wholesale_sale_items_total_nonnegative"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("wholesale_sales.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    sku: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    sale: Mapped[WholesaleSale] = relationship(back_populates="items")


class WholesalePayment(Base):
    __tablename__ = "wholesale_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_wholesale_payments_amount_positive"),
        CheckConstraint(
            "method != 'cash' OR cash_received >= amount",
            name="ck_wholesale_payments_cash_received_gte_amount",
        ),
        CheckConstraint(
            "method IN ('cash', 'mpesa')",
            name="ck_wholesale_payments_method_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("wholesale_sales.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cash_received: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0")
    )
    change_given: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0")
    )
    mpesa_reference: Mapped[str | None] = mapped_column(String(64))

    sale: Mapped[WholesaleSale] = relationship(back_populates="payments")
