from app.database import Base
from sqlalchemy import Column, Integer, String, ForeignKey, Index
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    username = Column(String(50), unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    roles = Column(String(200), default="user")

    # 🔑 Multi-tenant link
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="SET NULL"),
        nullable=True,
        index=True  # ensures fast tenant lookup
    )

    business = relationship(
        "Business",
        back_populates="users"
    )

    # Existing relationships
    expenses = relationship(
        "Expense",
        back_populates="creator"
    )

    # ----------------- Composite Indexes -----------------
    __table_args__ = (
        Index("idx_user_business_username", "business_id", "username"),
    )
