from fastapi import Depends, HTTPException, status
from app.users.auth import get_current_user
from app.users import schemas as user_schemas
from typing import List
from typing import Set  # add at the top


def role_required(allowed_roles: List[str]):
    allowed_set: Set[str] = set(r.strip().lower() for r in (allowed_roles or []))

    def wrapper(current_user: user_schemas.UserDisplaySchema = Depends(get_current_user)):
        # current_user.roles is now reliably a list thanks to the validator
        user_roles = set(r.strip().lower() for r in (current_user.roles or []))

        # Admin bypass
        if "admin" in user_roles:
            return current_user

        if not user_roles.intersection(allowed_set):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )

        return current_user

    return wrapper