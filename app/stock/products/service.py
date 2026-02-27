from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError


from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from app.stock.products import models, schemas
from app.stock.inventory import models as inventory_models
from app.purchase import models as purchase_models
from app.stock.category import models as category_models
from app.stock.category.models import Category
from app.business.dependencies import get_current_business
import re




from sqlalchemy import func

from app.stock.products.schemas import ProductOut, ProductPriceUpdate

from fastapi import HTTPException, UploadFile

import pandas as pd

from .models import Product

import logging




def create_product(db: Session, product: schemas.ProductCreate):

    product_name = product.name.strip()
    product_type = product.type.strip() if product.type else None
    category_name = product.category.strip()
    business_id = product.business_id

    # -------------------------------------------------
    # 1️⃣ CATEGORY LOOKUP (strictly tenant-based)
    # -------------------------------------------------
    category = (
        db.query(category_models.Category)
        .filter(
            category_models.Category.name == category_name,
            category_models.Category.business_id == business_id,
        )
        .first()
    )

    if not category:
        raise HTTPException(
            status_code=400,
            detail="Category not found for this business",
        )

    # -------------------------------------------------
    # 2️⃣ DUPLICATE CHECK
    # -------------------------------------------------
    exists = (
        db.query(models.Product)
        .filter(
            models.Product.name == product_name,
            models.Product.category_id == category.id,
            models.Product.business_id == business_id,
        )
        .first()
    )

    if exists:
        raise HTTPException(
            status_code=400,
            detail="Product already exists for this business",
        )

    # -------------------------------------------------
    # 3️⃣ CREATE PRODUCT
    # -------------------------------------------------
    db_product = models.Product(
        name=product_name,
        type=product_type,
        category_id=category.id,
        cost_price=product.cost_price,
        selling_price=product.selling_price,
        business_id=business_id,
    )

    db.add(db_product)
    db.flush()

    # -------------------------------------------------
    # 4️⃣ CREATE INVENTORY
    # -------------------------------------------------
    db.add(
        inventory_models.Inventory(
            product_id=db_product.id,
            quantity_in=0,
            quantity_out=0,
            adjustment_total=0,
            current_stock=0,
            business_id=business_id,
        )
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Product already exists for this business",
        )

    db.refresh(db_product)
    return db_product



def get_products(
    db: Session,
    current_user,
    category: Optional[str] = None,
    name: Optional[str] = None,
    business_id: Optional[int] = None,   # ✅ NEW
    active_only: bool = False,
):
    query = db.query(models.Product).options(
        joinedload(models.Product.category)
    )

    # 🔑 TENANT ISOLATION
    if "super_admin" in current_user.roles:
        # Super admin can filter by business_id if provided
        if business_id:
            query = query.filter(models.Product.business_id == business_id)
        # else → no filter = see all businesses

    else:
        # Normal users restricted
        query = query.filter(
            models.Product.business_id == current_user.business_id
        )

    # 🔹 Optional filters
    if active_only:
        query = query.filter(models.Product.is_active.is_(True))

    if category:
        query = query.join(models.Product.category).filter(
            func.lower(models.Category.name) == category.lower().strip()
        )

    if name:
        query = query.filter(
            func.lower(models.Product.name).contains(name.lower().strip())
        )

    return query.order_by(models.Product.created_at.desc()).all()




def search_products(db: Session, query: str, current_user):

    q = db.query(Product)

    # 🔐 Tenant isolation (same as bank logic)
    if (
        "admin" in current_user.roles
        or "manager" in current_user.roles
        or "user" in current_user.roles
    ):
        q = q.filter(Product.business_id == current_user.business_id)

    # 🔎 Name filter
    q = q.filter(Product.name.ilike(f"%{query.strip()}%"))

    return (
        q.order_by(Product.name.asc())
         .limit(20)
         .all()
    )



def get_products_simple(db: Session, current_user):

    query = db.query(models.Product)

    # 🔐 Tenant isolation (same as bank pattern)
    if (
        "admin" in current_user.roles
        or "manager" in current_user.roles
        or "user" in current_user.roles
    ):
        query = query.filter(
            models.Product.business_id == current_user.business_id
        )

    return (
        query
        .order_by(models.Product.name.asc())
        .all()
    )



def get_products_simple(db: Session, current_user):

    query = db.query(models.Product)

    # 🔐 Tenant isolation
    if (
        "admin" in current_user.roles
        or "manager" in current_user.roles
        or "user" in current_user.roles
    ):
        query = query.filter(
            models.Product.business_id == current_user.business_id
        )

    return (
        query
        .order_by(models.Product.name.asc())
        .all()
    )


def get_product_by_id(
    db: Session,
    product_id: int,
    current_user
):
    query = db.query(models.Product).filter(
        models.Product.id == product_id
    )

    # 🔐 Tenant Isolation
    if "super_admin" not in current_user.roles:
        query = query.filter(
            models.Product.business_id == current_user.business_id
        )

    return query.first()




def update_product(
    db: Session,
    product_id: int,
    product: schemas.ProductUpdate,
    current_user
):
    query = (
        db.query(models.Product)
        .options(joinedload(models.Product.category))
        .filter(models.Product.id == product_id)
    )

    # 🔐 Tenant isolation
    if "super_admin" not in current_user.roles:
        query = query.filter(
            models.Product.business_id == current_user.business_id
        )

    db_product = query.first()

    if not db_product:
        return None

    update_data = product.model_dump(exclude_unset=True)

    # -----------------------
    # Handle category update (Tenant Safe)
    # -----------------------
    if "category" in update_data:
        category_name = update_data.pop("category").strip()

        category_query = db.query(category_models.Category).filter(
            category_models.Category.name == category_name
        )

        if "super_admin" not in current_user.roles:
            category_query = category_query.filter(
                category_models.Category.business_id == current_user.business_id
            )

        category = category_query.first()

        if not category:
            raise HTTPException(
                status_code=400,
                detail=f"Category '{category_name}' does not exist."
            )

        db_product.category_id = category.id

    # -----------------------
    # Duplicate protection (Tenant Safe)
    # -----------------------
    new_name = update_data.get("name", db_product.name)

    duplicate_query = db.query(models.Product).filter(
        models.Product.id != product_id,
        models.Product.name == new_name,
        models.Product.category_id == db_product.category_id,
    )

    if "super_admin" not in current_user.roles:
        duplicate_query = duplicate_query.filter(
            models.Product.business_id == current_user.business_id
        )

    duplicate = duplicate_query.first()

    if duplicate:
        raise HTTPException(
            status_code=400,
            detail="Product with same name already exists in this category."
        )

    # -----------------------
    # Update remaining fields
    # -----------------------
    for field, value in update_data.items():
        setattr(db_product, field, value)

    db.commit()
    db.refresh(db_product)

    return db_product




def delete_product(db: Session, product_id: int, current_user):
    """
    Permanently deletes a product, only if:
    - Inventory is empty
    - No purchase records exist
    - Tenant isolation is respected
    """

    # 🔹 Tenant-aware query
    query = db.query(models.Product)
    if "super_admin" not in current_user.roles:
        query = query.filter(models.Product.business_id == current_user.business_id)

    product = query.filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # 🔹 Check inventory
    inventory_entry = (
        db.query(inventory_models.Inventory)
        .filter(inventory_models.Inventory.product_id == product_id)
        .first()
    )

    if inventory_entry and inventory_entry.current_stock > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete product: inventory is not empty",
        )

    # 🔹 Check purchase records
    purchase_entry = (
        db.query(purchase_models.Purchase)
        .filter(purchase_models.Purchase.product_id == product_id)
        .first()
    )

    if purchase_entry:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete product: purchase records exist",
        )

    # 🔹 Delete dependent inventory first (even if quantity=0)
    if inventory_entry:
        db.delete(inventory_entry)

    # 🔹 Delete the product
    db.delete(product)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Failed to delete product due to database constraints",
        )

    return {"detail": "Product deleted successfully"}



def update_product_price(
    db: Session,
    product_id: int,
    price_update: ProductPriceUpdate,
    current_user
):
    query = db.query(models.Product).options(joinedload(models.Product.category)).filter(
        models.Product.id == product_id
    )

    # 🔐 Tenant isolation
    if "super_admin" not in current_user.roles:
        query = query.filter(models.Product.business_id == current_user.business_id)

    product = query.first()

    if not product:
        return None

    # -----------------------
    # Validate price
    # -----------------------
    if price_update.selling_price < 0:
        raise HTTPException(
            status_code=400,
            detail="Selling price cannot be negative."
        )

    product.selling_price = price_update.selling_price

    db.commit()
    db.refresh(product)

    return product






# --------------------------------------------------
# Helper: Clean price values from Excel
# --------------------------------------------------
def clean_price(value):
    """
    Accepts: int, float, str (₦1,200.50), or NaN
    Returns: float
    """
    if value is None or pd.isna(value):
        return 0.0

    # If already numeric
    if isinstance(value, (int, float)):
        return float(value)

    # If string → remove currency symbols & commas
    value = str(value)
    value = re.sub(r"[^\d.]", "", value)

    try:
        return float(value)
    except ValueError:
        return 0.0


def import_products_from_excel(
    db: Session,
    file: UploadFile,
    current_user,
    business_id: Optional[int] = None,
):
    try:
        # ------------------- Determine target business -------------------
        if "super_admin" in current_user.roles:
            if not business_id:
                raise HTTPException(400, detail="Super admin must provide business_id")
            target_business_id = business_id
        else:
            target_business_id = current_user.business_id
            if not target_business_id:
                raise HTTPException(403, detail="User is not associated with any business")

        # ------------------- Validate Excel file -------------------
        if not file.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(400, detail="Only .xlsx and .xls files are supported")

        df = pd.read_excel(file.file)
        df.columns = [str(c).strip().lower() for c in df.columns]

        required = {"name", "category", "cost_price", "selling_price"}
        if not required.issubset(df.columns):
            missing = required - set(df.columns)
            raise HTTPException(400, detail=f"Missing required columns: {', '.join(missing)}")

        # ------------------- Helper: normalize strings -------------------
        def normalize(s: str) -> str:
            return " ".join(str(s).lower().strip().split())

        # ------------------- Load business categories -------------------
        categories = {
            normalize(c.name): c.id
            for c in db.query(Category)
            .filter(Category.business_id == target_business_id)
            .all()
        }

        if not categories:
            raise HTTPException(400, detail="This business has no categories defined")

        # ------------------- Cache existing products -------------------
        existing = {
            (p.name.strip().lower(), p.category_id)
            for p in db.query(Product.name, Product.category_id)
            .filter(Product.business_id == target_business_id)
            .all()
        }

        products_to_add = []
        stats = {
            "skipped": 0,
            "duplicates": 0,
            "invalid": 0,
            "unknown_category": 0,
        }

        for _, row in df.iterrows():
            name_val = row.get("name")
            cat_val = row.get("category")

            if pd.isna(name_val) or pd.isna(cat_val) or not str(name_val).strip() or not str(cat_val).strip():
                stats["invalid"] += 1
                stats["skipped"] += 1
                continue

            name = str(name_val).strip()
            cat_key = normalize(cat_val)

            if cat_key not in categories:
                stats["unknown_category"] += 1
                stats["skipped"] += 1
                continue

            cat_id = categories[cat_key]
            key = (name.lower(), cat_id)

            if key in existing:
                stats["duplicates"] += 1
                stats["skipped"] += 1
                continue

            # ------------------- Create product -------------------
            product = Product(
                name=name,
                category_id=cat_id,
                type=str(row["type"]).strip() if not pd.isna(row.get("type")) else None,
                cost_price=clean_price(row["cost_price"]),
                selling_price=clean_price(row["selling_price"]),
                business_id=target_business_id,
            )

            products_to_add.append(product)
            existing.add(key)  # prevent duplicates in the same import

        # ------------------- Handle no new products -------------------
        if not products_to_add:
            detail = {
                "message": "No new products were imported",
                "reason": "All rows were either duplicates, missing required fields, or had unrecognized categories.",
                "total_rows": len(df),
                **stats,
            }
            raise HTTPException(status_code=409, detail=detail)

        # ------------------- Save to DB -------------------
        db.add_all(products_to_add)
        db.commit()

        return {
            "message": "Import completed successfully",
            "imported": len(products_to_add),
            "skipped": stats["skipped"],
            "duplicates": stats["duplicates"],
            "invalid_rows": stats["invalid"],
            "unknown_categories": stats["unknown_category"],
            "total_rows": len(df),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, detail=f"Import failed: {str(e)}")
        
            

def update_product_status(
    db: Session,
    product_id: int,
    is_active: bool,
    current_user
):
    query = db.query(Product).filter(Product.id == product_id)

    # 🔐 Tenant isolation
    if "super_admin" not in current_user.roles:
        query = query.filter(
            Product.business_id == current_user.business_id
        )

    product = query.first()

    if not product:
        return None

    product.is_active = is_active

    db.commit()
    db.refresh(product)

    return product

