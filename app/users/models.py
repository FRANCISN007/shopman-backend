from app.database import Base
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    username = Column(String(50), unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    roles = Column(String(200), default="user")

    # 🔑 Multi-tenant link
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True)  # ✅ allow NULL


    business = relationship(
        "Business",
        back_populates="users"
    )

    # Existing relationship
    expenses = relationship(
        "Expense",
        back_populates="creator"
    )
