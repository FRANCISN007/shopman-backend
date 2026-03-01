from sqlalchemy.orm import Session
from fastapi import HTTPException
from . import models
from app.stock.inventory.adjustments.models import StockAdjustment

from app.stock.inventory.models import Inventory
from app.stock.products.models import  Product

from app.purchase.models import  Purchase, PurchaseItem
from datetime import datetime, date, time
from zoneinfo import ZoneInfo


LAGOS_TZ = ZoneInfo("Africa/Lagos")



def list_inventory(
    db: Session,
    current_user,
    skip: int = 0,
    limit: int = 100,
    product_id: int | None = None,
    product_name: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    # Base query: join inventory with product
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
            Inventory.business_id
        )
        .join(Product, Product.id == Inventory.product_id)
        .order_by(Inventory.id.asc())  # column.asc() is safe
    )

    # Tenant Filter
    roles = getattr(current_user, "roles", [])
    if "super_admin" not in roles:
        user_business_id = getattr(current_user, "business_id", None)
        if not user_business_id:
            raise HTTPException(
                status_code=400,
                detail="User does not belong to any business"
            )
        query = query.filter(Inventory.business_id == user_business_id)

    # Optional filters
    if product_id is not None:
        query = query.filter(Inventory.product_id == product_id)
    if product_name:
        query = query.filter(Product.name.ilike(f"%{product_name}%"))

    # Date filters (timezone-aware)
    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=LAGOS_TZ)
        query = query.filter(Inventory.created_at >= start_dt)
    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=LAGOS_TZ)
        query = query.filter(Inventory.created_at <= end_dt)

    inventory_list = query.offset(skip).limit(limit).all()

    result = []
    grand_total = 0

    for item in inventory_list:
        # Latest purchase cost for valuation
        latest_purchase_item = (
            db.query(PurchaseItem)
            .join(Purchase)
            .filter(
                PurchaseItem.product_id == item.product_id,
                Purchase.business_id == item.business_id  # tenant safety
            )
            .order_by(PurchaseItem.id.desc())
            .first()
        )

        latest_cost = latest_purchase_item.cost_price if latest_purchase_item else 0


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
            "business_id": item.business_id,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        })

    return {
        "inventory": result,
        "grand_total": grand_total
    }



# --------------------------
# ORM helper: get inventory for a product in the current business
# --------------------------
def get_inventory_orm_by_product(db: Session, product_id: int, current_user=None):
    query = db.query(Inventory).filter(Inventory.product_id == product_id)

    # Tenant isolation: restrict to current user's business if not super admin
    if current_user and "super_admin" not in getattr(current_user, "roles", []):
        business_id = getattr(current_user, "business_id", None)
        if not business_id:
            raise HTTPException(400, "User does not belong to any business")
        query = query.filter(Inventory.business_id == business_id)

    return query.first()


# --------------------------
# Internal: add stock (Purchase)
# --------------------------
def add_stock(db: Session, product_id: int, quantity: float, current_user=None, commit: bool = False):
    inventory = get_inventory_orm_by_product(db, product_id, current_user)

    if not inventory:
        business_id = None
        if current_user and "super_admin" not in getattr(current_user, "roles", []):
            business_id = getattr(current_user, "business_id", None)
        inventory = Inventory(
            product_id=product_id,
            business_id=business_id,
            quantity_in=quantity,
            quantity_out=0,
            adjustment_total=0,
            current_stock=quantity,
        )
        db.add(inventory)
    else:
        inventory.quantity_in += quantity
        inventory.current_stock = inventory.quantity_in - inventory.quantity_out + inventory.adjustment_total

    if commit:
        db.commit()
        db.refresh(inventory)

    return inventory


# --------------------------
# Internal: remove stock (Sale)
# --------------------------
def remove_stock(db: Session, product_id: int, quantity: float, current_user=None, commit: bool = False):
    inventory = get_inventory_orm_by_product(db, product_id, current_user)

    if not inventory:
        business_id = None
        if current_user and "super_admin" not in getattr(current_user, "roles", []):
            business_id = getattr(current_user, "business_id", None)
        inventory = Inventory(
            product_id=product_id,
            business_id=business_id,
            quantity_in=0,
            quantity_out=0,
            adjustment_total=0,
            current_stock=0,
        )
        db.add(inventory)
        db.flush()

    inventory.quantity_out += quantity
    inventory.current_stock = inventory.quantity_in - inventory.quantity_out + inventory.adjustment_total

    if commit:
        db.commit()
        db.refresh(inventory)

    return inventory


# --------------------------
# Admin-only: Adjust stock
# --------------------------
def adjust_stock(db: Session, product_id: int, quantity: float, reason: str, adjusted_by: int, current_user=None):
    with db.begin():
        inventory = get_inventory_orm_by_product(db, product_id, current_user)
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
def revert_purchase_stock(db: Session, product_id: int, quantity: float, current_user=None):
    with db.begin():
        inventory = get_inventory_orm_by_product(db, product_id, current_user)
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
def revert_sale_stock(db: Session, product_id: int, quantity: float, current_user=None):
    with db.begin():
        inventory = get_inventory_orm_by_product(db, product_id, current_user)
        if not inventory:
            return

        inventory.quantity_out -= quantity
        inventory.current_stock = inventory.quantity_in - inventory.quantity_out + inventory.adjustment_total
        if inventory.quantity_out < 0:
            inventory.quantity_out = 0

        db.flush()
        db.refresh(inventory)