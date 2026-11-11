from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=80)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    initial_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    low_stock_threshold: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=12, decimal_places=3
    )


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=80)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    low_stock_threshold: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=3
    )
    is_active: bool | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    barcode: str | None
    name: str
    category: str | None
    unit_price: Decimal
    stock_quantity: Decimal
    low_stock_threshold: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StockAdjustmentCreate(BaseModel):
    quantity_delta: Decimal = Field(allow_inf_nan=False, max_digits=12, decimal_places=3)
    reason: str = Field(min_length=1, max_length=200)
