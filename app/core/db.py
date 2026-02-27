from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.tenant import set_current_business
from app.database import get_db
from app.users.auth import get_current_user
from app.users.schemas import UserDisplaySchema




def db_dependency(
    current_user: UserDisplaySchema = Depends(get_current_user),
):
    """
    Provides a DB session and sets the current tenant automatically.

    - Business users → tenant isolation enabled
    - Super admin (business_id=None) → tenant filter bypass
    """

    # ✅ Set tenant context
    if current_user.business_id:
        set_current_business(current_user.business_id)
    else:
        # Super admin → disable tenant filtering
        set_current_business(None)

    # ✅ Provide DB session safely
    db: Session = next(get_db())
    try:
        yield db
    finally:
        db.close()
