
from sqlalchemy.orm import Session
from app.users.models import User
from app.users import schemas as user_schema


def create_user(db: Session, user: user_schema.UserSchema, hashed_password: str):
    roles_str = ",".join(user.roles) if user.roles else "user"
    new_user = User(
        username=user.username,
        hashed_password=hashed_password,
        roles=roles_str
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# crud.py
# crud.py
def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()



def get_all_users(db: Session, skip: int = 0, limit: int = 50):
    users = db.query(User).offset(skip).limit(limit).all()
    result = []
    for user in users:
        roles = user.roles.split(",") if user.roles else ["user"]
        result.append(
            user_schema.UserDisplaySchema(
                id=user.id,
                username=user.username,
                roles=roles
            )
        )
    return result


def update_user(db: Session, username: str, updated_user: user_schema.UserUpdateSchema, hashed_password: str = None):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None

    if hashed_password:
        user.hashed_password = hashed_password
    if updated_user.roles:
        user.roles = ",".join(updated_user.roles)

    db.commit()
    db.refresh(user)
    return user


def delete_user_by_username(db: Session, username: str):
    user = db.query(User).filter(User.username == username).first()
    if user:
        db.delete(user)
        db.commit()
        return True
    return False
