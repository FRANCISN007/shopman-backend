from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional
from datetime import datetime


# -------------------------------
# Base
# -------------------------------
class ProductBase(BaseModel):
    name: str
    category: str
    type: Optional[str] = None

    sku: Optional[str] = None        # internal part number
    barcode: Optional[str] = None    # scanner code

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
    type: Optional[str] = None
    category: Optional[str] = None

    sku: Optional[str] = None
    barcode: Optional[str] = None

    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    business_id: Optional[int] = None

# -------------------------------
# Output
# -------------------------------




from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime

class ProductOut(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    type: Optional[str] = None

    sku: Optional[str] = None
    barcode: Optional[str] = None

    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    is_active: bool
    business_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True  # <-- allows reading from SQLAlchemy models

    # 🔹 Convert Category ORM object → string name
    @validator("category", pre=True, always=True)
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
    barcode: Optional[str] = None
    selling_price: Optional[float] = None
    business_id: int

    class Config:
        from_attributes = True


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
    barcode: Optional[str] = None
    selling_price: Optional[float] = None
    business_id: int

    class Config:
        from_attributes = True



class ProductScanSchema(BaseModel):
    barcode: Optional[str] = None
    sku: Optional[str] = None

