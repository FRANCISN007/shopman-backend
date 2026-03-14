from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.database import Base


class Bank(Base):
    __tablename__ = "banks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    # 🔑 Multi-tenant link
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 🔒 Ensure uniqueness per business
    __table_args__ = (
        UniqueConstraint("name", "business_id", name="uix_bank_name_business"),
        Index("idx_bank_business_name", "business_id", "name"),  # For faster queries by business
    )

    business = relationship("Business", back_populates="banks")

    # Payments relationship
    payments = relationship(
        "Payment",
        back_populates="bank",
        cascade="all, delete-orphan",
    )
