from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
from zoneinfo import ZoneInfo


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)  # ❗ removed global unique
    description = Column(String(255), nullable=True)

    #created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = datetime.now(ZoneInfo("Africa/Lagos"))
    # 🔒 Tenant ownership
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)

    # 🔐 Unique داخل نفس البزنس فقط
    __table_args__ = (
        UniqueConstraint("name", "business_id", name="uq_category_name_business"),
    )

    products = relationship(
        "Product",
        back_populates="category"
    )
