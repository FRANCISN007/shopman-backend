from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from passlib.context import CryptContext  # ✅ Add this
from fastapi import Body
from app.users.auth import pwd_context, authenticate_user, create_access_token, get_current_user
from app.database import get_db
from app.users import crud as user_crud, schemas # Correct import for user CRUD operations
from app.users import models as user_models
import os
from loguru import logger
import os

router = APIRouter()



ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

logger.add("app.log", rotation="500 MB", level="DEBUG")



#log_path = os.path.join(os.getenv("LOCALAPPDATA", "C:\\Temp"), "app.log")
#logger.add("C:/Users/KLOUNGE/Documents/app.log", rotation="500 MB", level="DEBUG")




pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Store your admin password securely (e.g., environment variable)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "supersecret")

@router.post("/register/")
def sign_up(user: schemas.UserSchema, db: Session = Depends(get_db)):
    # Normalize username
    user.username = user.username.strip().lower()

    # Check duplicate username
    existing_user = user_crud.get_user_by_username(db, user.username)
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")

    # 🔒 Enforce admin password for ALL registrations
    if not user.admin_password or user.admin_password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin can register users. Invalid admin password."
        )

    # Hash password and create user
    hashed_password = pwd_context.hash(user.password)
    user_crud.create_user(db, user, hashed_password)

    return {"message": f"User {user.username} registered successfully"}

@router.post("/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    username = form_data.username.strip().lower()
    password = form_data.password

    user = authenticate_user(db, username, password)
    if not user:
        logger.warning(f"Authentication denied for username: {username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": username})
    logger.info(f"✅ User authenticated: {username}")

    # ✅ Return roles in response
    return {
        "id": user.id,
        "username": user.username,
        "roles": user.roles.split(",") if isinstance(user.roles, str) else user.roles,
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get("/", response_model=list[schemas.UserDisplaySchema])
def list_all_users(
    db: Session = Depends(get_db),
    current_user: schemas.UserDisplaySchema = Depends(get_current_user),
):
    if "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return user_crud.get_all_users(db)

@router.put("/{username}/reset_password")
def reset_password(
    username: str,
    new_password: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: schemas.UserDisplaySchema = Depends(get_current_user),
):
    # ✅ Only admin can reset password
    if "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    user = user_crud.get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Hash and update password
    user.hashed_password = pwd_context.hash(new_password)
    db.commit()
    db.refresh(user)

    return {"message": f"Password for {username} has been reset"}




@router.get("/me", response_model=schemas.UserDisplaySchema)
def get_current_user_info(
    current_user: schemas.UserDisplaySchema = Depends(get_current_user),
):
    return current_user


@router.put("/{username}")
def update_user(
    username: str,
    updated_user: schemas.UserUpdateSchema,   # ✅ use update schema
    db: Session = Depends(get_db),
    current_user: schemas.UserDisplaySchema = Depends(get_current_user),
):
    if "admin" not in current_user.roles:
        logger.warning(f"Unauthorized update attempt by {current_user.username}")
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    user = user_crud.get_user_by_username(db, username)
    if not user:
        logger.warning(f"User not found: {username}")
        raise HTTPException(status_code=404, detail="User not found")

    # 🚫 Prevent username change (ignore if frontend sends username by mistake)
    # Do not raise error — just skip
    # if updated_user.username and updated_user.username != username:
    #     raise HTTPException(status_code=400, detail="Username change not allowed")

    # 🔑 Update password only if explicitly provided
    if updated_user.password:
        user.hashed_password = pwd_context.hash(updated_user.password)

    # 🎯 Update roles
    if updated_user.roles is not None:
        user.roles = ",".join(updated_user.roles)

    db.commit()
    db.refresh(user)
    logger.info(f"User {username} updated successfully")
    return {"message": f"User {username} updated successfully"}


@router.delete("/{username}")
def delete_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: schemas.UserDisplaySchema = Depends(get_current_user),
):
    if "admin" not in current_user.roles:
        logger.warning(f"Unauthorized delete attempt by {current_user.username}")
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Prevent self-deletion
    if username == current_user.username:
        logger.warning(f"Admin {current_user.username} attempted to delete themselves.")
        raise HTTPException(status_code=400, detail="You cannot delete yourself.")

    user = user_crud.get_user_by_username(db, username)
    if not user:
        logger.warning(f"User not found: {username}")
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    logger.info(f"User {username} deleted successfully")
    return {"message": f"User {username} deleted successfully"}
