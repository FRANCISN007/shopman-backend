from sqlalchemy.orm import Session
from fastapi import HTTPException
from . import models
from app.stock.inventory.adjustments.models import StockAdjustment

from app.stock.inventory.models import Inventory
from app.stock.products.models import  Product

from app.purchase.models import  Purchase

# --------------------------
# Read-only: list inventory
# --------------------------
def list_inventory(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    product_id: int | None = None,
    product_name: str | None = None,
):
    # 1️⃣ Base query for inventory joined with product
    query = (
        db.query(
            Inventory.id,
            Inventory.product_id,
            Product.name.label("product_name"),
            Inventory.quantity_in,
            Inventory.quantity_out,
            Inventory.adjustment_total,
            Inventory.current_stock,
            Inventory.created_at,
            Inventory.updated_at,
        )
        .join(Product, Product.id == Inventory.product_id)
        .order_by(Inventory.id.asc())
    )

    # 2️⃣ Filter by product ID
    if product_id is not None:
        query = query.filter(Inventory.product_id == product_id)

    # 3️⃣ Filter by product name
    if product_name:
        query = query.filter(Product.name.ilike(f"%{product_name}%"))

    inventory_list = query.offset(skip).limit(limit).all()

    result = []
    grand_total = 0

    for item in inventory_list:
        # 4️⃣ Get latest purchase cost for this product
        latest_purchase = (
            db.query(Purchase)
            .filter(Purchase.product_id == item.product_id)
            .order_by(Purchase.id.desc())  # latest first
            .first()
        )
        latest_cost = latest_purchase.cost_price if latest_purchase else 0

        # 5️⃣ Calculate inventory valuation for this product
        inventory_value = item.current_stock * latest_cost

        grand_total += inventory_value

        result.append({
            "id": item.id,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "quantity_in": item.quantity_in,
            "quantity_out": item.quantity_out,
            "adjustment_total": item.adjustment_total,
            "current_stock": item.current_stock,
            "latest_cost": latest_cost,
            "inventory_value": inventory_value,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        })

    return {
        "inventory": result,
        "grand_total": grand_total
    }




def get_inventory_orm_by_product(db: Session, product_id: int):
    return (
        db.query(Inventory)
        .filter(Inventory.product_id == product_id)
        .first()
    )


# --------------------------
# Internal: add stock (Purchase)
# --------------------------
def add_stock(db: Session, product_id: int, quantity: float, commit: bool = False):
    inventory = get_inventory_orm_by_product(db, product_id)

    if not inventory:
        inventory = Inventory(
            product_id=product_id,
            quantity_in=quantity,
            quantity_out=0,
            adjustment_total=0,
            current_stock=quantity,
        )
        db.add(inventory)
    else:
        inventory.quantity_in += quantity
        inventory.current_stock = (
            inventory.quantity_in
            - inventory.quantity_out
            + inventory.adjustment_total
        )

    if commit:
        db.commit()
        db.refresh(inventory)

    return inventory


# --------------------------
# Internal: remove stock (Sale)
# --------------------------
def remove_stock(db: Session, product_id: int, quantity: float, commit: bool = False):
    inventory = get_inventory_orm_by_product(db, product_id)

    if not inventory:
        inventory = Inventory(
            product_id=product_id,
            quantity_in=0,
            quantity_out=0,
            adjustment_total=0,
            current_stock=0,
        )
        db.add(inventory)
        db.flush()

    inventory.quantity_out += quantity
    inventory.current_stock = (
        inventory.quantity_in
        - inventory.quantity_out
        + inventory.adjustment_total
    )

    if commit:
        db.commit()
        db.refresh(inventory)

    return inventory


# --------------------------
# Admin-only: Adjust stock
# --------------------------
def adjust_stock(
    db: Session,
    product_id: int,
    quantity: float,
    reason: str,
    adjusted_by: int,
):
    with db.begin():
        inventory = get_inventory_orm_by_product(db, product_id)
        if not inventory:
            raise HTTPException(status_code=404, detail="Inventory not found")

        quantity_in = inventory.quantity_in or 0
        quantity_out = inventory.quantity_out or 0
        adjustment_total = inventory.adjustment_total or 0

        new_stock = quantity_in - quantity_out + adjustment_total + quantity
        if new_stock < 0:
            raise HTTPException(
                status_code=400,
                detail="Adjustment would result in negative stock",
            )

        inventory.adjustment_total = adjustment_total + quantity
        inventory.current_stock = new_stock

        adjustment = StockAdjustment(
            product_id=product_id,
            inventory_id=inventory.id,
            quantity=quantity,
            reason=reason,
            adjusted_by=adjusted_by,
        )

        db.add(adjustment)
        db.flush()
        db.refresh(inventory)

        return adjustment


# --------------------------
# Revert stock when deleting Purchase
# --------------------------
def revert_purchase_stock(db: Session, product_id: int, quantity: float):
    with db.begin():
        inventory = get_inventory_orm_by_product(db, product_id)
        if not inventory:
            return
        inventory.quantity_in -= quantity
        inventory.current_stock = inventory.quantity_in - inventory.quantity_out + inventory.adjustment_total
        if inventory.quantity_in < 0:
            inventory.quantity_in = 0
            inventory.current_stock = max(inventory.current_stock, 0)
        db.flush()
        db.refresh(inventory)


# --------------------------
# Revert stock when deleting Sale
# --------------------------
def revert_sale_stock(db: Session, product_id: int, quantity: float):
    with db.begin():
        inventory = get_inventory_orm_by_product(db, product_id)
        if not inventory:
            return
        inventory.quantity_out -= quantity
        inventory.current_stock = inventory.quantity_in - inventory.quantity_out + inventory.adjustment_total
        if inventory.quantity_out < 0:
            inventory.quantity_out = 0
        db.flush()
        db.refresh(inventory)
