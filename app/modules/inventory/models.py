from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_products_unit_price_nonnegative"),
        CheckConstraint(
            "cost_price IS NULL OR cost_price >= 0",
            name="ck_products_cost_price_nonnegative",
        ),
        CheckConstraint("stock_quantity >= 0", name="ck_products_stock_nonnegative"),
        CheckConstraint("low_stock_threshold >= 0", name="ck_products_threshold_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str | None] = mapped_column(String(80))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    low_stock_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    stock_movements: Mapped[list["StockMovement"]] = relationship(back_populates="product")


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity_delta != 0", name="ck_stock_movements_nonzero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    reason: Mapped[str] = mapped_column(String(200))
    reference_type: Mapped[str] = mapped_column(String(32), default="adjustment")
    reference_id: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="stock_movements")
