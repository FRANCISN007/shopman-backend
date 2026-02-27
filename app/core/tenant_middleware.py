from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from jose import jwt, JWTError

from app.core.tenant import set_current_business
from app.database import SessionLocal
from app.users import crud
import os

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        db = SessionLocal()

        try:
            auth_header = request.headers.get("Authorization")

            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

                try:
                    # 🔹 Decode JWT (same as get_current_user)
                    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                    username = payload.get("sub")

                    if username:
                        user = crud.get_user_by_username(db, username)

                        if user:
                            roles = (
                                [r.strip().lower() for r in user.roles.split(",")]
                                if user.roles else ["user"]
                            )

                            # 🔹 Super admin → global tenant
                            if "super_admin" in roles:
                                set_current_business(None)
                            else:
                                set_current_business(user.business_id)
                        else:
                            set_current_business(None)
                    else:
                        set_current_business(None)

                except JWTError:
                    set_current_business(None)

            else:
                set_current_business(None)

            response = await call_next(request)
            return response

        finally:
            # 🔹 CRITICAL: prevent tenant leak between requests
            set_current_business(None)
            db.close()
