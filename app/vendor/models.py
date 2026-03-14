from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)

    business_name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)

    # 🔑 Multi-tenant link
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    business = relationship("Business", back_populates="vendors")

    # 🔒 Ensure uniqueness of business_name per business
    __table_args__ = (
        UniqueConstraint("business_id", "business_name", name="uq_vendor_business_name"),
        Index("idx_vendor_business_phone", "business_id", "phone_number"),  # optional composite index for searches
    )
