from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from app.database import Base


LAGOS_TZ = ZoneInfo("Africa/Lagos")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)

    # 🔑 Multi-tenant link
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    business = relationship("Business", back_populates="inventory_items")

    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    product = relationship("Product")

    quantity_in = Column(Float, default=0)
    quantity_out = Column(Float, default=0)
    adjustment_total = Column(Float, default=0)
    current_stock = Column(Float, default=0)

    #created_at = Column(DateTime, default=datetime.utcnow)
    #updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 🔹 Correct timezone-aware DateTime columns
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(LAGOS_TZ),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(LAGOS_TZ),
        onupdate=lambda: datetime.now(LAGOS_TZ),
        nullable=False
    )