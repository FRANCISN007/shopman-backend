import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.orm import Session as SessionType
from sqlalchemy.orm import with_loader_criteria

# ============================================================
# 🔐 Load environment variables
# ============================================================
env_path = Path(".") / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(dotenv_path=env_path)
print(f"🔄 Loaded environment from: {env_path}")

SQLALCHEMY_DATABASE_URL = os.getenv("DB_URL2")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("❌ DB_URL2 environment variable is not set!")

print(f"🔍 Using database: {SQLALCHEMY_DATABASE_URL.split('@')[-1]}")

# ============================================================
# ⚙️ SQLAlchemy setup
# ============================================================
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    future=True,  # Use 2.0 style
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=SessionType,
)

Base = declarative_base()

# ============================================================
# 🏢 Tenant context
# ============================================================
from contextvars import ContextVar

_current_business_id: ContextVar[Optional[int]] = ContextVar(
    "current_business_id", default=None
)


def set_current_business(business_id: Optional[int]):
    _current_business_id.set(business_id)


def get_current_business() -> Optional[int]:
    return _current_business_id.get()

# ============================================================
# 🛡️ Tenant filter
# ============================================================
@event.listens_for(SessionType, "do_orm_execute")
def _add_tenant_filter(execute_state):
    """
    Apply tenant isolation ONLY when a business_id exists.
    Super admin (business_id=None) bypasses filtering.
    """

    business_id = get_current_business()

    # 🔴 IMPORTANT: super admin bypass
    if business_id is None:
        return

    if not execute_state.is_select:
        return

    try:
        from app.vendor import models as vendor_models
        from app.business import models as business_models
    except ImportError:
        return

    tenant_models = [vendor_models.Vendor, business_models.Business]

    for model in tenant_models:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                model,
                lambda cls: cls.business_id == business_id,
                include_aliases=True,
            )
        )


# ============================================================
# 🔄 FastAPI dependency
# ============================================================
def get_db():
    """
    Provide a transactional DB session per request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
