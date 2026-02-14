from pydantic import BaseModel

class VendorBase(BaseModel):
    business_name: str
    address: str
    phone_number: str

class VendorCreate(VendorBase):
    pass

class VendorUpdate(BaseModel):
    business_name: str | None = None
    address: str | None = None
    phone_number: str | None = None

class VendorOut(VendorBase):
    id: int

    class Config:
        from_attributes = True
