from pydantic import BaseModel

class BankBase(BaseModel):
    name: str

class BankCreate(BankBase):
    pass

class BankUpdate(BankBase):
    pass

class BankDisplay(BankBase):
    id: int

    class Config:
        from_attributes = True


class BankSimpleSchema(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True