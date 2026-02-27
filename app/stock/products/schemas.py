from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional
from datetime import datetime


# -------------------------------
# Base
# -------------------------------
class ProductBase(BaseModel):
    name: str
    category: str           # category NAME from frontend
    type: Optional[str] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    business_id: Optional[int] = None


# -------------------------------
# Create
# -------------------------------
class ProductCreate(ProductBase):
    pass

# -------------------------------
# Update
# -------------------------------
class ProductUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None       # phone, laptop, accessories
    category: Optional[str] = None   # tecno, hp, apple, etc
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    business_id: Optional[int] = None  # optional update of tenant if needed

# -------------------------------
# Output
# -------------------------------




class ProductOut(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    type: Optional[str] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    is_active: bool
    business_id: Optional[int] = None   # allow NULL for super admin products
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    # 🔑 Convert Category ORM object → string name
    @field_validator("category", mode="before")
    @classmethod
    def extract_category_name(cls, v):
        if hasattr(v, "name"):
            return v.name
        return v

# -------------------------------
# Status Update
# -------------------------------
class ProductStatusUpdate(BaseModel):
    is_active: bool

# -------------------------------
# Dedicated Selling Price Update
# -------------------------------
class ProductPriceUpdate(BaseModel):
    selling_price: float

    class Config:
        from_attributes = True

# -------------------------------
# Simple Product Schemas (Dropdowns, Lists)
# -------------------------------
class ProductSimpleSchema(BaseModel):
    id: int
    name: str
    selling_price: Optional[float] = None
    business_id: int  # include tenant

    @property
    def selling_price_formatted(self) -> str:
        if self.selling_price is None:
            return "N0"
        return f"N{int(self.selling_price):,}"  # formats as 23,000

    class Config:
        from_attributes = True

class ProductSimpleSchema1(BaseModel):
    id: int
    name: str
    business_id: int  # include tenant

    class Config:
        from_attributes = True
