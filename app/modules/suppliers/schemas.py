from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class SupplierCreate(BaseModel):
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
            raise ValueError("Supplier name cannot be blank")
        return value

    @field_validator("contact_name", "phone", "address")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class SupplierUpdate(BaseModel):
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
            raise ValueError("Supplier name cannot be blank")
        return value

    @field_validator("contact_name", "phone", "address")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    is_active: bool
    created_at: datetime


class SupplierReceiptItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity_received: Decimal = Field(
        gt=0, max_digits=12, decimal_places=3, allow_inf_nan=False
    )


class SupplierReceiptCreate(BaseModel):
    supplier_id: int = Field(gt=0)
    supplier_reference: str | None = Field(default=None, max_length=80)
    items: list[SupplierReceiptItemCreate] = Field(min_length=1, max_length=100)

    @field_validator("supplier_reference")
    @classmethod
    def clean_reference(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def validate_unique_products(self) -> "SupplierReceiptCreate":
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Each product may appear only once in a supplier receipt")
        return self


class SupplierReceiptItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    sku: str
    quantity_received: Decimal


class SupplierReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    supplier_name: str
    supplier_reference: str | None
    received_by_id: int
    received_by_name: str
    received_at: datetime
    items: list[SupplierReceiptItemRead]
