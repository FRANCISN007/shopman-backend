# app/stock/inventory/adjustments/schemas.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class StockAdjustmentBase(BaseModel):
    product_id: int
    quantity: float = Field(..., description="Positive = add stock, Negative = remove stock")
    reason: str


class StockAdjustmentCreate(StockAdjustmentBase):
    pass


class StockAdjustmentOut(BaseModel):
    id: int
    business_id: int
    product_id: int
    inventory_id: int
    quantity: float
    reason: str
    adjusted_by: Optional[int]
    adjusted_at: datetime

    # Enriched fields
    product_name: Optional[str] = None
    adjusted_by_name: Optional[str] = None

    class Config:
        from_attributes = True

