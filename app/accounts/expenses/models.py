from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

from datetime import datetime
from zoneinfo import ZoneInfo




class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    ref_no = Column(String(100), unique=True, index=True, nullable=False)

    # 🔑 Multi-tenant link
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    business = relationship("Business", back_populates="expenses")  # ✅ link to 'expenses'


    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    account_type = Column(String, nullable=False)
    description = Column(String, nullable=True)
    amount = Column(Float, nullable=False)

    payment_method = Column(String, nullable=False)
    bank_id = Column(Integer, ForeignKey("banks.id", ondelete="SET NULL"), nullable=True)

    expense_date = Column(DateTime, nullable=False)
    #created_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )

    status = Column(String, default="paid")
    is_active = Column(Boolean, default=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    vendor = relationship("Vendor")
    bank = relationship("Bank")

    # 🔑 SINGLE relationship
    creator = relationship(
        "User",
        back_populates="expenses",
        foreign_keys=[created_by]
    )
