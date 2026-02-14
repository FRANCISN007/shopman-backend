from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    type = Column(String, nullable=True)
    cost_price = Column(Float, nullable=True)
    selling_price = Column(Float, nullable=True)

    # 🔥 NEW VISIBILITY FLAG
    is_active = Column(Boolean, default=True, nullable=False, index=True)


    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category", back_populates="products")

    __table_args__ = (
        UniqueConstraint(
            "name",
            "category_id",
            name="uq_product_name_category"
        ),
    )
