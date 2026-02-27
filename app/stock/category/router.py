from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from . import schemas, service
from app.stock.category import models as category_models
from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema
from app.users.auth import get_current_user


router = APIRouter()

# ================= CREATE =================
@router.post(
    "/",
    response_model=schemas.CategoryOut,
    status_code=201
)
def create_category(
    category: schemas.CategoryCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return service.create_category(db, category, current_user) 


# ================= LIST =================
@router.get(
    "/",
    response_model=List[schemas.CategoryOut]
)
def list_categories(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return service.list_categories(db, current_user)



# ================= SIMPLE LIST =================
@router.get("/simple", response_model=List[schemas.CategoryOut])
def list_categories_simple(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Tenant-safe dropdown list:
    - Super admin → all categories
    - Others → global + their business categories
    """
    return service.list_categories_simple(db, current_user)


# ================= UPDATE =================
@router.put(
    "/{category_id}",
    response_model=schemas.CategoryOut
)
def update_category(
    category_id: int,
    category: schemas.CategoryUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return service.update_category(db, category_id, category, current_user)


# ================= DELETE =================
@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["super_admin", "admin", "manager"])
    ),
):
    """
    SaaS-safe category deletion:
    - Only super_admin, admin, manager can delete
    - Admin/Manager → only their business categories
    - Cannot delete category if linked to products
    """
    return service.delete_category(db, category_id, current_user)
