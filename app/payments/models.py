from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    # 🔑 Multi-tenant link
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    business = relationship("Business", back_populates="payments")

    # Reference sales.invoice_no
    sale_invoice_no = Column(
        Integer,
        ForeignKey("sales.invoice_no", ondelete="CASCADE"),
        nullable=False
    )

    amount_paid = Column(Float, nullable=False)

    discount_allowed = Column(Float, default=0.0)

    payment_method = Column(String, nullable=False)

    bank_id = Column(
        Integer,
        ForeignKey("banks.id", ondelete="SET NULL"),
        nullable=True
    )

    reference_no = Column(String, nullable=True)

    balance_due = Column(Float, default=0.0)

    status = Column(
        String,
        default="pending"
    )

    payment_date = Column(
        DateTime,
        default=datetime.utcnow,
        index=True
    )

    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos")),
        nullable=False
    )

    # Relationships
    sale = relationship(
        "Sale",
        primaryjoin="Payment.sale_invoice_no == foreign(Sale.invoice_no)",
        viewonly=True,
        uselist=False
    )

    bank = relationship("Bank")

    user = relationship("User")

    # Composite indexes for speed
    __table_args__ = (

        # Payment lookup for a sale
        Index(
            "idx_payment_business_invoice",
            "business_id",
            "sale_invoice_no"
        ),

        # Payment reports
        Index(
            "idx_payment_business_date",
            "business_id",
            "payment_date"
        ),

        # Payment status queries
        Index(
            "idx_payment_business_status",
            "business_id",
            "status"
        ),
    )
