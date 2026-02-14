from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, String
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)

    invoice_no = Column(
        String(50),
        unique=True,
        index=True,
        nullable=False
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )

    vendor_id = Column(
        Integer,
        ForeignKey("vendors.id", ondelete="SET NULL"),
        nullable=True
    )

    quantity = Column(Integer, nullable=False)
    cost_price = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)
    purchase_date = Column(DateTime, default=datetime.utcnow)

    # Relationships
    product = relationship("Product")
    vendor = relationship("Vendor")
