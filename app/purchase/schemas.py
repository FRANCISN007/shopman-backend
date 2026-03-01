from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class PurchaseItemBase(BaseModel):
    product_id: int
    quantity: int
    cost_price: float


class PurchaseItemCreate(PurchaseItemBase):
    pass


class PurchaseItemOut(PurchaseItemBase):
    id: int
    product_name: Optional[str] = None
    total_cost: float
    current_stock: Optional[float] = 0

    class Config:
        from_attributes = True


class PurchaseBase(BaseModel):
    invoice_no: str
    vendor_id: Optional[int] = None
    business_id: Optional[int] = None
    purchase_date: Optional[datetime] = None


class PurchaseCreate(PurchaseBase):
    items: List[PurchaseItemCreate]





class PurchaseItemUpdate(BaseModel):
    id: Optional[int] = None  # existing item id
    product_id: int
    quantity: int
    cost_price: float

class PurchaseUpdate(BaseModel):
    invoice_no: Optional[str] = None
    vendor_id: Optional[int] = None
    items: Optional[List[PurchaseItemUpdate]] = None


class PurchaseOut(PurchaseBase):
    id: int
    vendor_name: Optional[str] = None
    items: List[PurchaseItemOut]
    created_at: datetime

    class Config:
        from_attributes = True
