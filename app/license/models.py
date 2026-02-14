from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from app.database import Base

class LicenseKey(Base):
    __tablename__ = "license_keys"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)  # Determines if the license is valid
    created_at = Column(DateTime, default=datetime.utcnow)  # License creation date
    expiration_date = Column(DateTime, nullable=False)  # License expiration date
