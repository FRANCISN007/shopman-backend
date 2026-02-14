#Auth file
import os
from datetime import datetime, timedelta
from typing import Optional

#from jose import JWTError, jwt
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.users.models import User
from dotenv import load_dotenv
import os
import sys

#import crud
from app.users import crud
from app.database import get_db

# Load environment variables
load_dotenv()




SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = os.getenv('ALGORITHM', 'HS256')
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 60))

# Cryptography context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
#oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/token")



def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def authenticate_user(db: Session, username: str, password: str):
    print(f"🔍 Looking for user: '{username}'")
    user = crud.get_user_by_username(db, username)
    if not user:
        print("❌ User not found.")
        return None

    print("✅ User found. Checking password...")
    if not verify_password(password, user.hashed_password):
        print("❌ Password incorrect.")
        return None

    print("✅ Password correct.")
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


from app.users import schemas as user_schemas

def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = crud.get_user_by_username(db, username)
    if not user:
        raise credentials_exception

    # 🔑 Convert roles from CSV string → list
    roles = user.roles.split(",") if user.roles else ["user"]

    return user_schemas.UserDisplaySchema(
        id=user.id,
        username=user.username,
        roles=roles
    )
