from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PositiveInt, StringConstraints, model_validator

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=240)]


class PromotionPlanIn(BaseModel):
    rule_id: PositiveInt
    store_id: PositiveInt
    product_id: PositiveInt
    operator_id: PositiveInt
    starts_on: date
    ends_on: date
    unit_discount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    unit_cap: int = Field(ge=1, le=100000)


class SettlementIn(BaseModel):
    pos_reference: Annotated[str, StringConstraints(
        strip_whitespace=True, pattern=r'^[A-Za-z0-9][A-Za-z0-9-]{2,39}$',
    )]
    redeemed_units: int = Field(ge=0, le=100000)
    note: Note = ''


class SettlementReviewIn(BaseModel):
    decision: Literal['confirm', 'return']
    note: Note = ''


class BudgetTransferIn(BaseModel):
    source_plan_id: PositiveInt
    target_plan_id: PositiveInt
    transferred_units: int = Field(ge=1, le=100000)
    request_key: Annotated[str, StringConstraints(
        strip_whitespace=True, min_length=8, max_length=64,
        pattern=r'^[A-Za-z0-9_-]{8,64}$',
    )]
    note: Note = ''

    @model_validator(mode='after')
    def distinct_plans(self):
        if self.source_plan_id == self.target_plan_id:
            raise ValueError('调出与调入档期不能相同')
        return self
