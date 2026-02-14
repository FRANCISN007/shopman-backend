from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from . import models, schemas

# ================= CREATE =================
def create_category(db: Session, category: schemas.CategoryCreate):
    existing = (
        db.query(models.Category)
        .filter(models.Category.name == category.name)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category '{category.name}' already exists"
        )

    db_category = models.Category(
        name=category.name.strip(),
        description=category.description
    )

    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


# ================= LIST =================
def list_categories(db: Session):
    return db.query(models.Category).order_by(models.Category.name).all()


# ================= UPDATE =================
def update_category(
    db: Session,
    category_id: int,
    category: schemas.CategoryUpdate
):
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

    if category.name:
        name_exists = (
            db.query(models.Category)
            .filter(models.Category.name == category.name)
            .filter(models.Category.id != category_id)
            .first()
        )
        if name_exists:
            raise HTTPException(
                status_code=400,
                detail="Another category with this name already exists"
            )
        db_category.name = category.name.strip()

    if category.description is not None:
        db_category.description = category.description

    db.commit()
    db.refresh(db_category)
    return db_category


# ================= DELETE =================
def delete_category(db: Session, category_id: int):
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

    db.delete(db_category)
    db.commit()
    return {"message": "Category deleted successfully"}
