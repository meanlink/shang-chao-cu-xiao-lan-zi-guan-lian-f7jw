from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

Quantity = Annotated[int, Field(ge=1, le=100)]
Reference = Annotated[str, StringConstraints(
    strip_whitespace=True, pattern=r'^[A-Za-z0-9][A-Za-z0-9-]{2,39}$',
)]
Sku = Annotated[str, StringConstraints(
    strip_whitespace=True, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,29}$',
)]


class OfferTermsIn(BaseModel):
    per_receipt_cap: Quantity
    minimums: dict[Annotated[str, StringConstraints(min_length=1, max_length=80)], Quantity] = Field(
        min_length=1, max_length=8,
    )


class ReceiptLineIn(BaseModel):
    sku: Sku
    quantity: Quantity

    @field_validator('sku')
    @classmethod
    def normalize_sku(cls, sku):
        return sku.upper()


class BasketReceiptIn(BaseModel):
    receipt_no: Reference
    lines: list[ReceiptLineIn] = Field(min_length=1, max_length=50)

    @field_validator('receipt_no')
    @classmethod
    def normalize_reference(cls, reference):
        return reference.upper()

    @field_validator('lines')
    @classmethod
    def unique_skus(cls, lines):
        if len({line.sku for line in lines}) != len(lines):
            raise ValueError('同一 SKU 请合并为一行')
        return lines


class VoidReceiptIn(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
