from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# ================= CREATE =================
class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None


# ================= UPDATE =================
class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# ================= RESPONSE =================
class CategoryOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
