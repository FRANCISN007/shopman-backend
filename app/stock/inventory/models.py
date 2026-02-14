from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, String
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)

    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    product = relationship("Product")

    quantity_in = Column(Float, default=0)
    quantity_out = Column(Float, default=0)

    # 🔥 NEW
    adjustment_total = Column(Float, default=0)

    current_stock = Column(Float, default=0)


    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
