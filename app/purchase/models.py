from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, String
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
from zoneinfo import ZoneInfo
from sqlalchemy import UniqueConstraint


class Purchase(Base):
    __tablename__ = "purchases"


    id = Column(Integer, primary_key=True, index=True)

    # ⚠️ Remove global unique=True
    invoice_no = Column(String(50), index=True, nullable=False)

    # 🔑 Multi-tenant link
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    vendor_id = Column(
        Integer,
        ForeignKey("vendors.id", ondelete="SET NULL"),
        nullable=True
    )

    purchase_date = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )


    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos")),
        nullable=False
    )

    # Optional: store invoice total here
    total_cost = Column(Float, default=0)

    # ================= RELATIONSHIPS =================

    business = relationship("Business", back_populates="purchases")
    vendor = relationship("Vendor")

    # 🔥 IMPORTANT: One Purchase → Many Items
    items = relationship(
        "PurchaseItem",
        back_populates="purchase",
        cascade="all, delete-orphan"
    )






class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True, index=True)

    purchase_id = Column(
        Integer,
        ForeignKey("purchases.id", ondelete="CASCADE"),
        nullable=False
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )


    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )


    quantity = Column(Integer, nullable=False)
    cost_price = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)

    # ================= RELATIONSHIPS =================

    purchase = relationship("Purchase", back_populates="items")
    product = relationship("Product")

