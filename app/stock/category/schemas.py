from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# ================= CREATE =================
class CategoryCreate(BaseModel):
    name: str = Field(..., description="Category name")
    description: Optional[str] = Field(None, description="Optional description")
    business_id: Optional[int] = Field(
        None, description="Required for super admin; ignored for normal users"
    )

# ================= UPDATE =================
class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, description="New category name")
    description: Optional[str] = Field(None, description="New description")

# ================= RESPONSE =================
class CategoryOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    business_id: int  # always include tenant for reference
    created_at: datetime

    class Config:
        from_attributes = True
