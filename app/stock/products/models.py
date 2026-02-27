from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from app.database import Base
from sqlalchemy import Index


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

    type = Column(String, nullable=True)
    cost_price = Column(Float, nullable=True)
    selling_price = Column(Float, nullable=True)

    # Visibility flag
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    #created_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(LAGOS_TZ)
    )

    # Relationships
    business = relationship("Business", back_populates="products")
    category = relationship("Category", back_populates="products")

    # ✅ Tenant-safe uniqueness
    __table_args__ = (
    UniqueConstraint(
        "name",
        "category_id",
        "business_id",
        name="uq_product_name_category_business"
    ),
    Index("idx_product_business_active", "business_id", "is_active"),
)

