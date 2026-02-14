from pydantic import BaseModel
from typing import List, Optional
from typing import Literal
from datetime import date
from pydantic import validator


# -------- USERS --------
class UserSchema(BaseModel):
    username: str
    password: str
    roles: List[str] = ["user"]  
    admin_password: Optional[str] = None


class UserUpdateSchema(BaseModel):
    password: Optional[str] = None
    roles: Optional[List[str]] = None


class UserDisplaySchema(BaseModel):
    id: int
    username: str
    roles: List[str] = []

    @validator("roles", pre=True)
    def ensure_roles_list(cls, v):
        # Normalize: None -> empty list, "a,b" -> ["a","b"], list -> stripped strings
        if v is None:
            return []
        if isinstance(v, str):
            return [r.strip() for r in v.split(",") if r.strip()]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        # fallback
        return []


    class Config:
        from_attributes = True


