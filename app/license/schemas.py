from pydantic import BaseModel
from datetime import datetime

class LicenseBase(BaseModel):
    key: str

class LicenseCreate(LicenseBase):
    expiration_date: datetime  # License expiry date
    
  

class LicenseResponse(LicenseBase):
    is_active: bool
    expiration_date: datetime

    class Config:
        from_attributes = True
