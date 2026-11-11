from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SaleItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class PaymentCreate(BaseModel):
    method: Literal["cash", "mpesa"]
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    cash_received: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    mpesa_reference: str | None = Field(default=None, max_length=64)


class SaleCreate(BaseModel):
    items: list[SaleItemCreate] = Field(min_length=1, max_length=100)
    payments: list[PaymentCreate] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def validate_unique_lines_and_payment_methods(self) -> "SaleCreate":
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Each product may appear only once in a sale")
        methods = [payment.method for payment in self.payments]
        if len(methods) != len(set(methods)):
            raise ValueError("Each payment method may appear only once in a sale")
        for payment in self.payments:
            if payment.method == "mpesa" and payment.cash_received is not None:
                raise ValueError("cash_received is only valid for cash payments")
            if payment.method == "cash" and payment.mpesa_reference is not None:
                raise ValueError("mpesa_reference is only valid for M-Pesa payments")
        return self


class SaleItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    sku: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    method: str
    amount: Decimal
    cash_received: Decimal
    change_given: Decimal
    mpesa_reference: str | None


class SaleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    currency: str
    subtotal: Decimal
    total: Decimal
    created_at: datetime
    items: list[SaleItemRead]
    payments: list[PaymentRead]
