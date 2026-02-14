from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from app.stock.products import models, schemas
from app.stock.inventory import models as inventory_models
from app.purchase import models as purchase_models
from app.stock.category import models as category_models
from app.stock.category.models import Category
import re


from sqlalchemy import func

from app.stock.products.schemas import ProductOut, ProductPriceUpdate

from fastapi import HTTPException, UploadFile

import pandas as pd

from .models import Product



def create_product(db: Session, product: schemas.ProductCreate):

    # 1️⃣ Find category by name
    category = (
        db.query(category_models.Category)
        .filter(category_models.Category.name == product.category.strip())
        .first()
    )

    if not category:
        raise HTTPException(
            status_code=400,
            detail=f"Category '{product.category}' does not exist."
        )

    # 2️⃣ Duplicate check (name + category)
    exists = (
        db.query(models.Product)
        .filter(
            models.Product.name == product.name.strip(),
            models.Product.category_id == category.id
        )
        .first()
    )

    if exists:
        raise HTTPException(
            status_code=400,
            detail="Product already exists in this category."
        )

    # 3️⃣ Create product
    db_product = models.Product(
        name=product.name.strip(),
        type=product.type.strip() if product.type else None,
        category_id=category.id,
        cost_price=product.cost_price,
        selling_price=product.selling_price
    )

    db.add(db_product)
    db.flush()  # 🔥 get product ID without committing yet

    # 4️⃣ AUTO-CREATE INVENTORY RECORD (ZERO STOCK)
    inventory = inventory_models.Inventory(
        product_id=db_product.id,
        quantity_in=0,
        quantity_out=0,
        adjustment_total=0,
        current_stock=0
    )

    db.add(inventory)

    # 5️⃣ Commit once (atomic)
    db.commit()
    db.refresh(db_product)

    return db_product
    

def get_products(
    db: Session,
    category: Optional[str] = None,
    name: Optional[str] = None,
    active_only: bool = False,  # 🔹 default to False
):
    query = db.query(models.Product).options(joinedload(models.Product.category))

    if active_only:  # still allows active-only filter if explicitly requested
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






def get_products_simple(db: Session):
    return (
        db.query(
            models.Product.id,
            models.Product.name,
            models.Product.selling_price
        )
        .order_by(models.Product.name.asc())
        .all()
    )


def get_product_by_id(
    db: Session,
    product_id: int
):
    return (
        db.query(models.Product)
        .options(joinedload(models.Product.category))
        .filter(models.Product.id == product_id)
        .first()
    )

def update_product(
    db: Session,
    product_id: int,
    product: schemas.ProductUpdate
):
    db_product = (
        db.query(models.Product)
        .options(joinedload(models.Product.category))
        .filter(models.Product.id == product_id)
        .first()
    )

    if not db_product:
        return None

    update_data = product.model_dump(exclude_unset=True)

    # -----------------------
    # Handle category update
    # -----------------------
    if "category" in update_data:
        category_name = update_data.pop("category").strip()

        category = (
            db.query(category_models.Category)
            .filter(category_models.Category.name == category_name)
            .first()
        )

        if not category:
            raise HTTPException(
                status_code=400,
                detail=f"Category '{category_name}' does not exist."
            )

        db_product.category_id = category.id

    # -----------------------
    # Duplicate protection
    # -----------------------
    new_name = update_data.get("name", db_product.name)

    duplicate = (
        db.query(models.Product)
        .filter(
            models.Product.id != product_id,
            models.Product.name == new_name,
            models.Product.category_id == db_product.category_id
        )
        .first()
    )

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




def delete_product(db: Session, product_id: int):
    product = get_product_by_id(db, product_id)
    if not product:
        return None

    # Check if product has any inventory
    inventory_entry = db.query(inventory_models.Inventory).filter(
        inventory_models.Inventory.product_id == product_id
    ).first()
    if inventory_entry and inventory_entry.current_stock > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete product with existing stock"
        )

    # Check if product has any purchases
    purchase_entry = db.query(purchase_models.Purchase).filter(
        purchase_models.Purchase.product_id == product_id
    ).first()
    if purchase_entry:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete product with existing purchase records"
        )

    db.delete(product)
    db.commit()
    return {"detail": "Product deleted successfully"}



def update_product_price(
    db: Session,
    product_id: int,
    price_update: ProductPriceUpdate
):
    product = (
        db.query(models.Product)
        .options(joinedload(models.Product.category))
        .filter(models.Product.id == product_id)
        .first()
    )

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


# --------------------------------------------------
# Main Service
# --------------------------------------------------
def import_products_from_excel(
    db: Session,
    file: UploadFile
):
    try:
        # -----------------------
        # Validate file type
        # -----------------------
        if not file.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Upload .xlsx or .xls"
            )

        # -----------------------
        # Read Excel
        # -----------------------
        df = pd.read_excel(file.file)

        required_columns = {
            "name",
            "category",
            "type",
            "cost_price",
            "selling_price"
        }

        # Normalize column names (important!)
        df.columns = [c.strip().lower() for c in df.columns]

        if not required_columns.issubset(df.columns):
            raise HTTPException(
                status_code=400,
                detail=f"Excel must contain columns: {required_columns}"
            )

        # -----------------------
        # Normalize helper
        # -----------------------
        def normalize(text: str) -> str:
            return " ".join(text.lower().strip().split())

        # -----------------------
        # Cache categories
        # -----------------------
        categories = {
            normalize(c.name): c.id
            for c in db.query(Category).all()
        }

        if not categories:
            raise HTTPException(
                status_code=400,
                detail="No categories found. Create categories first."
            )

        # -----------------------
        # Cache existing products
        # -----------------------
        existing_products = {
            (p.name.lower().strip(), p.category_id)
            for p in db.query(Product.name, Product.category_id).all()
        }

        products_to_add = []
        skipped = 0

        # -----------------------
        # Process rows
        # -----------------------
        for _, row in df.iterrows():

            # Required fields
            if pd.isna(row["name"]) or pd.isna(row["category"]):
                skipped += 1
                continue

            name = str(row["name"]).strip()
            category_key = normalize(str(row["category"]))

            if category_key not in categories:
                skipped += 1
                continue

            category_id = categories[category_key]

            key = (name.lower(), category_id)
            if key in existing_products:
                skipped += 1
                continue

            product = Product(
                name=name,
                category_id=category_id,
                type=None if pd.isna(row["type"]) else str(row["type"]).strip(),
                cost_price=clean_price(row["cost_price"]),
                selling_price=clean_price(row["selling_price"]),
            )

            products_to_add.append(product)
            existing_products.add(key)

        # -----------------------
        # Nothing imported
        # -----------------------
        if not products_to_add:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Import unsuccessful",
                    "imported": 0,
                    "skipped": skipped,
                    "reason": "All rows were invalid or duplicated"
                }
            )

        # -----------------------
        # Save
        # -----------------------
        db.add_all(products_to_add)
        db.commit()

        return {
            "message": "Import completed successfully",
            "imported": len(products_to_add),
            "skipped": skipped
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}"
        )
    

def update_product_status(
    db: Session,
    product_id: int,
    is_active: bool
):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        return None

    product.is_active = is_active
    db.commit()
    db.refresh(product)

    return product


