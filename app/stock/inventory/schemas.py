from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class InventoryBase(BaseModel):
    product_id: int
    product_name: str
    quantity_in: float
    quantity_out: float
    adjustment_total: float
    current_stock: float
    latest_cost: float  # ✅ Latest purchase cost
    inventory_value: float  # ✅ Valuation of current stock



class InventoryOut(InventoryBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InventoryListOut(BaseModel):
    inventory: list[InventoryOut]
    grand_total: float  # ✅ Total valuation of all inventory

    class Config:
        from_attributes = True