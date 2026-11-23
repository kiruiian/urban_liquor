from datetime import date, datetime
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


class SaleAmend(BaseModel):
    items: list[SaleItemCreate] = Field(min_length=1, max_length=100)
    settlement_method: Literal["cash", "mpesa"] | None = None
    cash_received: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    mpesa_reference: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_lines_and_settlement(self) -> "SaleAmend":
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Each product may appear only once in a sale")
        if self.settlement_method is None and (
            self.cash_received is not None or self.mpesa_reference is not None
        ):
            raise ValueError("A settlement method is required when recording a payment")
        if self.settlement_method == "mpesa" and self.cash_received is not None:
            raise ValueError("cash_received is only valid for cash payments")
        if self.settlement_method == "cash" and self.mpesa_reference is not None:
            raise ValueError("mpesa_reference is only valid for M-Pesa payments")
        return self


class SaleReturn(BaseModel):
    sale_item_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    settlement_method: Literal["cash", "mpesa"]


class SaleChange(BaseModel):
    sale_item_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    replacement_product_id: int = Field(gt=0)
    replacement_quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    settlement_method: Literal["cash", "mpesa"] | None = None
    cash_received: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    mpesa_reference: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_settlement(self) -> "SaleChange":
        if self.settlement_method is None and (
            self.cash_received is not None or self.mpesa_reference is not None
        ):
            raise ValueError("A settlement method is required when recording a payment")
        if self.settlement_method == "mpesa" and self.cash_received is not None:
            raise ValueError("cash_received is only valid for cash payments")
        if self.settlement_method == "cash" and self.mpesa_reference is not None:
            raise ValueError("mpesa_reference is only valid for M-Pesa payments")
        return self


class SaleReturnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_id: int
    product_name: str
    sku: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    method: str | None
    kind: str
    replacement_product_name: str | None
    replacement_quantity: Decimal | None
    created_at: datetime


class SaleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    currency: str
    subtotal: Decimal
    total: Decimal
    created_at: datetime
    items: list[SaleItemRead]
    payments: list[PaymentRead]


class DailySalesSummary(BaseModel):
    date: date
    sale_count: int
    total: Decimal
    cash_total: Decimal
    mpesa_total: Decimal


class SalesSummary(DailySalesSummary):
    period: Literal["daily", "weekly", "monthly"]
    start_date: date
    end_date: date


class ProfitAndLoss(BaseModel):
    period: Literal["daily", "weekly", "monthly"]
    start_date: date
    end_date: date
    retail_sales: Decimal
    wholesale_sales: Decimal
    cost: Decimal
    uncosted_sales: Decimal
    net: Decimal
