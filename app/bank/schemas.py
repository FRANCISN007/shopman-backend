from pydantic import BaseModel
from typing import Optional


class BankBase(BaseModel):
    name: str


class BankCreate(BankBase):
    business_id: Optional[int] = None  # assigned by backend


class BankUpdate(BaseModel):
    name: Optional[str] = None
    business_id: Optional[int] = None


class BankDisplay(BankBase):
    id: int
    business_id: int

    class Config:
        from_attributes = True


class BankSimpleSchema(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
