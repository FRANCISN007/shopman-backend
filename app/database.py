import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base, Session, with_loader_criteria
from contextvars import ContextVar

# ============================================================
# 🔐 Load environment variables
# ============================================================
env_path = Path(".") / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(dotenv_path=env_path)
print(f"🔄 Loaded environment from: {env_path}")

# ============================================================
# 🌐 ENV VARIABLES
# ============================================================
SQLALCHEMY_DATABASE_URL = os.getenv("DB_URL3")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("❌ DB_URL3 environment variable is not set!")

print(f"🔍 Using database host: {SQLALCHEMY_DATABASE_URL.split('@')[-1]}")

# ============================================================
# ⚙️ SQLAlchemy Engine (SYNC + Render SSL)
# ============================================================
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=1800,

    # 🔥 IMPORTANT for Render (avoids connection crash)
    connect_args={"sslmode": "require"},
)

# ============================================================
# ⚙️ SessionLocal
# ============================================================
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()

# ============================================================
# 🏢 Tenant context
# ============================================================
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
@event.listens_for(Session, "do_orm_execute")
def _add_tenant_filter(execute_state):
    business_id = get_current_business()

    # Super admin → no filter
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
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
