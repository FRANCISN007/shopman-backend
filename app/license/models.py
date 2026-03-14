# app/license/models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
from zoneinfo import ZoneInfo

LAGOS_TZ = ZoneInfo("Africa/Lagos")


class LicenseKey(Base):
    __tablename__ = "license_keys"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)

    # License control flags
    is_active = Column(Boolean, default=True, index=True)  # manual deactivation possible

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(LAGOS_TZ)  # timezone-aware
    )

    expiration_date = Column(DateTime(timezone=True), nullable=False, index=True)

    # 🔑 Multi-tenant link
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    business = relationship("Business", back_populates="licenses")

    def is_currently_valid(self) -> bool:
        """True if active AND not expired"""
        return self.is_active and self.expiration_date >= datetime.utcnow()

    # ✅ Composite index for tenant+active/expiration queries
    __table_args__ = (
        Index(
            "idx_license_business_active_exp",
            "business_id",
            "is_active",
            "expiration_date"
        ),
    )
