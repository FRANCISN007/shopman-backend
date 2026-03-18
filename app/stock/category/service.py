from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from fastapi import Query, HTTPException, status
from typing import List, Optional
from . import models, schemas
from app.users.schemas import UserDisplaySchema
from app.stock.products import models as product_models



# ================= SERVICE =================
def create_category(
    db: Session,
    category: schemas.CategoryCreate,
    current_user
):
    """
    SaaS-safe category creation:
    - Tenant-scoped uniqueness
    - Super admin must provide business_id
    """

    # 🔹 Determine business_id
    if "super_admin" in getattr(current_user, "roles", []):
        # Require super admin to provide business_id
        business_id = getattr(category, "business_id", None)
        if not business_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Super admin must provide a business_id"
            )
    else:
        # Normal user uses their own business
        business_id = getattr(current_user, "business_id", None)
        if not business_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User does not belong to any business"
            )

    # 🔹 Check if category already exists in this scope
    existing = (
        db.query(models.Category)
        .filter(
            models.Category.name == category.name.strip(),
            models.Category.business_id == business_id
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category '{category.name}' already exists "
                   f"{'for this business' if business_id else 'globally'}"
        )

    # 🔹 Create category
    db_category = models.Category(
        name=category.name.strip(),
        description=category.description,
        business_id=business_id
    )

    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category



# ================= SERVICE =================
def list_categories(db: Session, current_user, business_id: Optional[int] = None):
    """
    SaaS-safe category listing:
    - Super admin → see all categories or filter by business_id
    - Normal users → see global + their business categories only
    """
    roles = getattr(current_user, "roles", [])

    # 🔹 Super Admin
    if "super_admin" in roles:
        query = db.query(models.Category)
        if business_id is not None:
            # Only categories for that business
            query = query.filter(models.Category.business_id == business_id)
        return query.order_by(models.Category.name).all()

    # 🔹 Normal users
    business_id = getattr(current_user, "business_id", None)
    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to any business"
        )

    return (
        db.query(models.Category)
        .filter(
            (models.Category.business_id == business_id) |
            (models.Category.business_id.is_(None))  # include global categories
        )
        .order_by(models.Category.name)
        .all()
    )

# ================= SIMPLE LIST =================
def list_categories_simple(db: Session, current_user):
    """
    Lightweight tenant-safe category list for dropdowns
    """

    # 🔹 Super Admin → all categories
    if "super_admin" in getattr(current_user, "roles", []):
        return (
            db.query(models.Category)
            .order_by(models.Category.name)
            .all()
        )

    # 🔹 Normal users
    business_id = getattr(current_user, "business_id", None)

    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to any business"
        )

    return (
        db.query(models.Category)
        .filter(
            (models.Category.business_id == business_id) |
            (models.Category.business_id.is_(None))
        )
        .order_by(models.Category.name)
        .all()
    )



# ================= UPDATE =================
def update_category(
    db: Session,
    category_id: int,
    category: schemas.CategoryUpdate,
    current_user
):
    """
    SaaS-safe category update:
    - Super admin → can update any category
    - Others → only their business categories
    """

    db_category = (
        db.query(models.Category)
        .filter(models.Category.id == category_id)
        .first()
    )

    if not db_category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    # 🔹 Authorization check
    if "super_admin" not in getattr(current_user, "roles", []):
        user_business_id = getattr(current_user, "business_id", None)

        if not user_business_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User does not belong to any business"
            )

        # Prevent editing global category
        if db_category.business_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot modify global categories"
            )

        # Prevent editing another business category
        if db_category.business_id != user_business_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this category"
            )

    # 🔹 Name Update (Tenant Scoped Uniqueness)
    if category.name:
        new_name = category.name.strip()

        name_exists = (
            db.query(models.Category)
            .filter(
                models.Category.name == new_name,
                models.Category.business_id == db_category.business_id,
                models.Category.id != category_id
            )
            .first()
        )

        if name_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category with this name already exists in this scope"
            )

        db_category.name = new_name

    # 🔹 Description Update
    if category.description is not None:
        db_category.description = category.description

    db.commit()
    db.refresh(db_category)
    return db_category


# ================= DELETE =================
def delete_category(db: Session, category_id: int, current_user):
    """
    SaaS-safe category deletion:
    - Super admin → can delete any category
    - Admin/Manager → only their business categories
    - Category cannot be deleted if products exist
    """

    # 🔹 Get category
    db_category = (
        db.query(models.Category)
        .filter(models.Category.id == category_id)
        .first()
    )

    if not db_category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    # ===============================
    # 🔐 SaaS Authorization Check
    # ===============================

    if "super_admin" not in getattr(current_user, "roles", []):
        user_business_id = getattr(current_user, "business_id", None)

        if not user_business_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User does not belong to any business"
            )

        # ❌ Prevent deleting global category
        if db_category.business_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot delete global categories"
            )

        # ❌ Prevent deleting another business category
        if db_category.business_id != user_business_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this category"
            )

    # ===============================
    # 🔴 Prevent Delete If Products Exist
    # ===============================

    product_count = (
        db.query(product_models.Product)
        .filter(product_models.Product.category_id == category_id)
        .count()
    )

    if product_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete category because it is linked to existing products. Delete products first."
        )

    # ===============================
    # 🗑 Delete Category
    # ===============================

    db.delete(db_category)
    db.commit()

    return {"message": "Category deleted successfully"}
