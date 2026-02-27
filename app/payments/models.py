from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
from zoneinfo import ZoneInfo


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    # 🔑 Multi-tenant link
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    business = relationship("Business", back_populates="payments")

    # Reference sales.invoice_no instead of sales.id
    sale_invoice_no = Column(
        Integer,
        ForeignKey("sales.invoice_no", ondelete="CASCADE"),
        nullable=False
    )

    amount_paid = Column(Float, nullable=False)
    discount_allowed = Column(Float, default=0.0)

    payment_method = Column(String, nullable=False)  # cash / transfer / pos
    bank_id = Column(
        Integer,
        ForeignKey("banks.id", ondelete="SET NULL"),
        nullable=True
    )
    reference_no = Column(String, nullable=True)

    balance_due = Column(Float, default=0.0)
    status = Column(String, default="pending")  # pending / part_paid / completed / voided

    payment_date = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    #created_at = Column(DateTime, default=datetime.utcnow)
    created_at = datetime.now(ZoneInfo("Africa/Lagos"))

    # Relationships
    sale = relationship(
        "Sale",
        primaryjoin="Payment.sale_invoice_no == foreign(Sale.invoice_no)",
        viewonly=True,
        uselist=False
    )

    bank = relationship("Bank")
    user = relationship("User")
