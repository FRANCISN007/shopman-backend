# app/license/models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
from zoneinfo import ZoneInfo


class LicenseKey(Base):
    __tablename__ = "license_keys"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)

    # License control flags
    is_active = Column(Boolean, default=True, index=True)  # manual deactivation possible
    #created_at = Column(DateTime, default=datetime.utcnow)
    created_at = datetime.now(ZoneInfo("Africa/Lagos"))

    expiration_date = Column(DateTime, nullable=False, index=True)

    # Multi-tenant link
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    business = relationship("Business", back_populates="licenses")

    def is_currently_valid(self) -> bool:
        """Computed: true if active flag is set AND not expired"""
        return self.is_active and self.expiration_date >= datetime.utcnow()