from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class StockAdjustmentBase(BaseModel):
    product_id: int
    quantity: float
    reason: str


class StockAdjustmentCreate(StockAdjustmentBase):
    pass


class StockAdjustmentOut(BaseModel):
    id: int
    product_id: int
    inventory_id: int
    quantity: float
    reason: str
    adjusted_by: Optional[int]
    adjusted_at: datetime

    class Config:
        from_attributes = True


class StockAdjustmentListOut(StockAdjustmentOut):
    product_name: Optional[str] = None
    adjusted_by_name: Optional[str] = None
