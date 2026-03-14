from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Identity, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
from sqlalchemy.sql import func


class Sale(Base):
    __tablename__ = "sales"

    # ✅ Composite indexes for multi-tenant performance
    __table_args__ = (
        Index("idx_sales_business_soldat", "business_id", "sold_at"),
        Index("idx_sales_business_invoice", "business_id", "invoice_no"),
        Index("idx_sales_business_date", "business_id", "invoice_date"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # 🔑 Multi-tenant link
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    business = relationship("Business", back_populates="sales")

    # Invoice info
    invoice_no = Column(
        Integer,
        Identity(start=1, increment=1),
        unique=True,
        nullable=False,
        index=True
    )

    invoice_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    ref_no = Column(String, nullable=True)

    # Customer info
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)

    # Sale totals
    total_amount = Column(Float, default=0)

    sold_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    sold_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    items = relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    payments = relationship(
        "Payment",
        primaryjoin="Sale.invoice_no == Payment.sale_invoice_no",
        foreign_keys="[Payment.sale_invoice_no]",
        viewonly=True,
        lazy="selectin"
    )


    user = relationship("User", backref="sales")


class SaleItem(Base):
    __tablename__ = "sale_items"

    # ✅ Composite index for fast joins and product reports
    __table_args__ = (
        Index("idx_saleitems_invoice_product", "sale_invoice_no", "product_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    sale_invoice_no = Column(
        Integer,
        ForeignKey("sales.invoice_no", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True
    )

    quantity = Column(Integer, nullable=False)

    selling_price = Column(Float, nullable=False)

    # Historical cost at time of sale
    cost_price = Column(Float, nullable=False, default=0)

    total_amount = Column(Float, nullable=False)

    gross_amount = Column(Float, nullable=False)

    discount = Column(Float, default=0)

    net_amount = Column(Float, nullable=False)

    sale = relationship("Sale", back_populates="items")

    product = relationship("Product")
