# schemas.py
from pydantic import BaseModel
from typing import List, Optional



class VendorBase(BaseModel):
    business_name: str
    address: str
    phone_number: str

# schemas.py
class VendorCreate(VendorBase):
    business_id: Optional[int] = None  # ← assigned by backend, not client
    

class VendorUpdate(BaseModel):
    business_name: str | None = None
    address: str | None = None
    phone_number: str | None = None
    business_id: int | None = None  # 🔑 Optional for updates

class VendorOut(VendorBase):
    id: int
    business_id: int  # 🔑 Include in output

    class Config:
        from_attributes = True
