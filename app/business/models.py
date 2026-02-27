# app/business/models.py (fully rewritten - removed is_active column, added dynamic method)
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship, Session
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database import Base



LAGOS_TZ = ZoneInfo("Africa/Lagos")


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)

    # Basic info
    name = Column(String, nullable=False, unique=True, index=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)

    # NEW: store the username of the creator/primary admin
    owner_username = Column(String, nullable=True, index=True)

    # SaaS control (removed is_active - now dynamic via method)
    #created_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(LAGOS_TZ),
        nullable=False
    )

    # Core relationships
    users = relationship("User", back_populates="business", cascade="all, delete-orphan")
    licenses = relationship("LicenseKey", back_populates="business", cascade="all, delete-orphan")

    # Financial & banking
    banks = relationship("Bank", back_populates="business", cascade="all, delete-orphan")
    #accounts = relationship("Account", back_populates="business", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="business", cascade="all, delete-orphan")

    payments = relationship("Payment", back_populates="business", cascade="all, delete-orphan")

    # Vendors & purchasing
    vendors = relationship("Vendor", back_populates="business", cascade="all, delete-orphan")
    purchases = relationship("Purchase", back_populates="business", cascade="all, delete-orphan")

    # Stock & sales
    products = relationship("Product", back_populates="business", cascade="all, delete-orphan")
    inventory_items = relationship("Inventory", back_populates="business", cascade="all, delete-orphan")
    sales = relationship("Sale", back_populates="business", cascade="all, delete-orphan")

    # Expenses
    expenses = relationship("Expense", back_populates="business", cascade="all, delete-orphan")

    stock_adjustments = relationship(
        "StockAdjustment",
        back_populates="business",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    def is_license_active(self, db: Session) -> bool:
        """
        Dynamically check if this business has an active, non-expired license.
        Returns False if no active license or expired.
        """
        from app.license.models import LicenseKey
        
        latest_license = (
            db.query(LicenseKey)
            .filter(
                LicenseKey.business_id == self.id,
                LicenseKey.is_active == True
            )
            .order_by(LicenseKey.expiration_date.desc())
            .first()
        )
        
        if not latest_license:
            return False
            
        return latest_license.expiration_date >= datetime.utcnow()

# Ensure dependent models are imported AFTER Business is defined
from app.bank.models import Bank
from app.vendor.models import Vendor
from app.purchase.models import Purchase
from app.sales.models import Sale
from app.stock.products.models import Product
from app.stock.inventory.models import Inventory
from app.license.models import LicenseKey
from app.users.models import User
from app.accounts.models import Account