from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# =========================
# Base
# =========================
class ExpenseBase(BaseModel):
    vendor_id: int
    ref_no: str
    account_type: str
    description: Optional[str] = None
    amount: float
    payment_method: str          # cash / transfer / pos
    bank_id: Optional[int] = None
    expense_date: datetime


# =========================
# Create
# =========================
class ExpenseCreate(ExpenseBase):
    pass


# =========================
# Update
# =========================
class ExpenseUpdate(BaseModel):
    vendor_id: Optional[int] = None
    ref_no: Optional[str] = None
    account_type: Optional[str] = None   # Transpot, Rent, Utilities, Salary, Maintenance, general, Cost of Sales, Telephone Expense, Generator & fuel etc.
    description: Optional[str] = None
    amount: Optional[float] = None
    payment_method: Optional[str] = None
    bank_id: Optional[int] = None
    expense_date: Optional[datetime] = None
    status: Optional[str] = None


# =========================
# Output
# =========================
class ExpenseOut(ExpenseBase):
    id: int
    status: str
    is_active: bool
    created_at: datetime

    created_by: int | None
    created_by_username: str | None
    bank_name: Optional[str] = None

    class Config:
        from_attributes = True


# ─── NEW: Proper response model for list ────────────────────────────────
class ExpenseListResponse(BaseModel):
    total_expenses: float = Field(..., description="Sum of amounts in filtered results")
    count: int = Field(..., description="Number of expenses returned (after pagination)")
    expenses: List[ExpenseOut]

    class Config:
        from_attributes = True