# app/stock/inventory/adjustments/models.py
from sqlalchemy import Column, Integer, Float, ForeignKey, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
from zoneinfo import ZoneInfo





LAGOS_TZ = ZoneInfo("Africa/Lagos")



class StockAdjustment(Base):
    __tablename__ = "stock_adjustments"

    id = Column(Integer, primary_key=True, index=True)

    # Multi-tenant key - required
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    business = relationship("Business", back_populates="stock_adjustments")

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )

    inventory_id = Column(
        Integer,
        ForeignKey("inventory.id", ondelete="CASCADE"),
        nullable=False
    )

    quantity = Column(Float, nullable=False)  # +ve = increase, -ve = decrease

    reason = Column(String, nullable=False)

    adjusted_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    #adjusted_at = Column(DateTime, default=datetime.utcnow)
    adjusted_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(LAGOS_TZ)  # timezone-aware default
    )
    # Relationships
    product = relationship("Product")
    inventory = relationship("Inventory")
    user = relationship("User")