# app/accounts/models.py
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"))

    business = relationship("Business", back_populates="accounts")
