from contextvars import ContextVar
from typing import Optional

# Holds the current tenant business_id per request
_current_business_id: ContextVar[Optional[int]] = ContextVar("current_business_id", default=None)


def set_current_business(business_id: Optional[int]):
    _current_business_id.set(business_id)


def get_current_business() -> Optional[int]:
    return _current_business_id.get()
