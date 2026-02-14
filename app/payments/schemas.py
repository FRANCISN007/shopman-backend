from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from pydantic import Field
import pytz

# -------------------------
# Base Schema
# -------------------------
class PaymentBase(BaseModel):
    amount_paid: float
    
    payment_method: str                 # cash / transfer / pos
    bank_id: Optional[int] = None
    reference_no: Optional[str] = None
    payment_date: Optional[datetime] = Field(default_factory=lambda: datetime.now(pytz.timezone("Africa/Lagos")))

# -------------------------
# Create Payment
# -------------------------
class PaymentCreate(PaymentBase):
    pass  # sale_id comes from the URL

# -------------------------
# Output / Response Schema
# -------------------------


class PaymentOut(PaymentBase):
    id: int
    invoice_no: int = Field(alias="sale_invoice_no")
    balance_due: float
    status: str
    created_by: Optional[int]
    created_at: datetime

    # ✅ Existing extras
    bank_name: Optional[str] = None
    created_by_name: Optional[str] = None
    total_amount: Optional[float] = None

    # ✅ NEW
    customer_name: Optional[str] = None

    class Config:
        from_attributes = True
        populate_by_name = True



# -------------------------
# Update Payment Schema
# -------------------------
class PaymentUpdate(BaseModel):
    amount_paid: Optional[float] = None

    payment_method: Optional[str] = None  # cash / transfer / pos
    bank_id: Optional[int] = None
    payment_date: Optional[datetime] = None
