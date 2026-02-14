from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

# -------------------------------
# Base
# -------------------------------
class ProductBase(BaseModel):
    name: str
    category: str          # category NAME from frontend
    type: Optional[str] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None


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


# -------------------------------
# Output
# -------------------------------
class ProductOut(BaseModel):
    id: int
    name: str
    category: str          # category NAME
    type: Optional[str]
    cost_price: Optional[float]
    selling_price: Optional[float]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)




class ProductStatusUpdate(BaseModel):
    is_active: bool





# ---------------------------------
# Output Schema
# ---------------------------------
class ProductOut(BaseModel):
    id: int
    name: str
    category: Optional[str] = None  # category NAME, not object
    type: Optional[str] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)  # ✅ REQUIRED




# ---------------------------------
# Update Selling Price (Dedicated)
# ---------------------------------
class ProductPriceUpdate(BaseModel):
    selling_price: float

    class Config:
        from_attributes = True



class ProductSimpleSchema(BaseModel):
    id: int
    name: str
    selling_price: Optional[float] = None

    @property
    def selling_price_formatted(self) -> str:
        if self.selling_price is None:
            return "N0"
        return f"N{int(self.selling_price):,}"  # formats as 23,000

    class Config:
        from_attributes = True


# -------------------------------
# Simple product list for dropdown
# -------------------------------

class ProductSimpleSchema1(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True

