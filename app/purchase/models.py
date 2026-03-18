from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, String, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from app.database import Base

LAGOS_TZ = ZoneInfo("Africa/Lagos")


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
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
        default=lambda: datetime.now(LAGOS_TZ)
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(LAGOS_TZ),
        nullable=False
    )

    total_cost = Column(Float, default=0)

    # ================= RELATIONSHIPS =================
    business = relationship("Business", back_populates="purchases")
    vendor = relationship("Vendor")
    items = relationship(
        "PurchaseItem",
        back_populates="purchase",
        cascade="all, delete-orphan"
    )

    # ----------------- Composite Indexes -----------------
    __table_args__ = (
        Index("idx_purchase_business_invoice", "business_id", "invoice_no"),
        Index("idx_purchase_business_created", "business_id", "created_at"),
        Index("idx_purchase_business_vendor", "business_id", "vendor_id"),
    


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
        default=lambda: datetime.now(LAGOS_TZ)
    )

    quantity = Column(Integer, nullable=False)
    cost_price = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)

    # ================= RELATIONSHIPS =================
    purchase = relationship("Purchase", back_populates="items")
    product = relationship("Product")

    # ----------------- Composite Indexes -----------------
    __table_args__ = (
        Index("idx_purchase_item_purchase_product", "purchase_id", "product_id"),
        Index("idx_purchase_item_business_created", "purchase_id", "created_at"),
    )
