from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from . import schemas, service
from app.stock.category import models as category_models
from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema


router = APIRouter()

# ================= CREATE =================
@router.post(
    "/",
    response_model=schemas.CategoryOut,
    status_code=status.HTTP_201_CREATED
)
def create_category(
    category: schemas.CategoryCreate,
    db: Session = Depends(get_db)
):
    return service.create_category(db, category)


# ================= LIST =================
@router.get(
    "/",
    response_model=List[schemas.CategoryOut]
)
def list_categories(db: Session = Depends(get_db)):
    return service.list_categories(db)


# ================= SIMPLE LIST =================
@router.get("/simple", response_model=List[schemas.CategoryOut])
def list_categories_simple(db: Session = Depends(get_db)):
    """
    Returns all categories directly from the database
    Can be used for frontend dropdowns
    """
    return db.query(category_models.Category).order_by(category_models.Category.id).all()


# ================= UPDATE =================
@router.put(
    "/{category_id}",
    response_model=schemas.CategoryOut
)
def update_category(
    category_id: int,
    category: schemas.CategoryUpdate,
    db: Session = Depends(get_db)
):
    return service.update_category(db, category_id, category)


# ================= DELETE =================
@router.delete(
    "/{category_id}"
)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin","manager"]))
    
):
    return service.delete_category(db, category_id)
