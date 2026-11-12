from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


class WholesaleCustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Shop name cannot be blank")
        return value

    @field_validator("contact_name", "phone", "address")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class WholesaleCustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Shop name cannot be blank")
        return value

    @field_validator("contact_name", "phone", "address")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class WholesaleCustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    is_active: bool
    created_at: datetime


class WholesaleSaleItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3, allow_inf_nan=False)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)


class WholesalePaymentCreate(BaseModel):
    method: Literal["cash", "mpesa"]
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
    cash_received: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False
    )
    mpesa_reference: str | None = Field(default=None, max_length=64)

    @field_validator("mpesa_reference")
    @classmethod
    def clean_reference(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def validate_method_fields(self) -> "WholesalePaymentCreate":
        if self.method == "mpesa" and self.cash_received is not None:
            raise ValueError("cash_received is only valid for cash payments")
        if self.method == "cash" and self.mpesa_reference is not None:
            raise ValueError("mpesa_reference is only valid for M-Pesa payments")
        return self


class WholesaleSaleCreate(BaseModel):
    customer_id: int = Field(gt=0)
    delivery_reference: str | None = Field(default=None, max_length=80)
    items: list[WholesaleSaleItemCreate] = Field(min_length=1, max_length=100)
    payments: list[WholesalePaymentCreate] = Field(default_factory=list, max_length=2)

    @field_validator("delivery_reference")
    @classmethod
    def clean_reference(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def validate_unique_lines_and_payment_methods(self) -> "WholesaleSaleCreate":
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Each product may appear only once in a wholesale delivery")
        methods = [payment.method for payment in self.payments]
        if len(methods) != len(set(methods)):
            raise ValueError("Each payment method may appear only once per delivery")
        if len(methods) != len(set(methods)):
            raise ValueError("Each payment method may appear only once per delivery")
        return self


class WholesalePaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    method: str
    amount: Decimal
    cash_received: Decimal
    change_given: Decimal
    mpesa_reference: str | None


class WholesaleSaleItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    sku: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class WholesaleSaleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    customer_name: str
    delivery_reference: str | None
    created_by_id: int
    created_by_name: str
    currency: str
    total: Decimal
    created_at: datetime
    items: list[WholesaleSaleItemRead]
    payments: list[WholesalePaymentRead]

    @computed_field
    @property
    def amount_paid(self) -> Decimal:
        return sum((payment.amount for payment in self.payments), Decimal("0.00"))

    @computed_field
    @property
    def balance_due(self) -> Decimal:
        return self.total - self.amount_paid

    @computed_field
    @property
    def payment_status(self) -> Literal["unpaid", "partial", "paid"]:
        if self.balance_due == 0:
            return "paid"
        return "partial" if self.amount_paid > 0 else "unpaid"
