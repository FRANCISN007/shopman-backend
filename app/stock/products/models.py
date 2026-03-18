from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from app.database import Base

LAGOS_TZ = ZoneInfo("Africa/Lagos")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    # 🔑 Multi-tenant ownership
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    # 🔹 Internal part number
    sku = Column(String, nullable=True, index=True)

    # 🔹 Barcode for scanner
    barcode = Column(String, nullable=True, index=True)

    type = Column(String, nullable=True)

    cost_price = Column(Float, nullable=True)

    selling_price = Column(Float, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(LAGOS_TZ)
    )

    # Relationships
    business = relationship("Business", back_populates="products")

    category = relationship("Category", back_populates="products")

    __table_args__ = (

        # Existing constraint
        UniqueConstraint(
            "name",
            "category_id",
            "business_id",
            name="uq_product_name_category_business"
        ),

        # SKU must be unique per business
        UniqueConstraint(
            "sku",
            "business_id",
            name="uq_product_sku_business"
        ),

        # Barcode must be unique per business
        UniqueConstraint(
            "barcode",
            "business_id",
            name="uq_product_barcode_business"
        ),

        # Fast POS loading
        Index("idx_product_business_active", "business_id", "is_active"),

        Index("idx_product_business_category", "business_id", "category_id"),

        Index("idx_product_business_name", "business_id", "name"),

        # Fast barcode scanning
        Index("idx_product_business_barcode", "business_id", "barcode"),
    )


    __table_args__ = (
        UniqueConstraint("barcode", "business_id", name="uq_barcode_business"),
    )