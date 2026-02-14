from sqlalchemy.orm import Session
from app.purchase import models as purchase_models, schemas as purchase_schemas
from app.stock.inventory import service as inventory_service
from datetime import datetime

from datetime import datetime, timedelta


from app.stock.products import models as product_models


def create_purchase(db: Session, purchase: purchase_schemas.PurchaseCreate):
    total_cost = purchase.quantity * purchase.cost_price

    # 1️⃣ Create purchase record
    db_purchase = purchase_models.Purchase(
        invoice_no=purchase.invoice_no, 
        product_id=purchase.product_id,
        vendor_id=purchase.vendor_id,
        quantity=purchase.quantity,
        cost_price=purchase.cost_price,
        total_cost=total_cost
    )
    db.add(db_purchase)

    # 2️⃣ Update inventory
    inventory_service.add_stock(
        db,
        product_id=purchase.product_id,
        quantity=purchase.quantity,
        commit=False
    )

    # 3️⃣ Update product cost price (KEY FIX)
    product = (
        db.query(product_models.Product)
        .filter(product_models.Product.id == purchase.product_id)
        .first()
    )

    if not product:
        raise Exception("Product not found")

    product.cost_price = purchase.cost_price  # 👈 FIX HERE

    # 4️⃣ Commit once
    db.commit()
    db.refresh(db_purchase)

    return db_purchase


from datetime import datetime, timedelta

def list_purchases(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    invoice_no: str | None = None,   # ✅ NEW
    product_id: int | None = None,
    vendor_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    query = db.query(purchase_models.Purchase)

    # ===============================
    # INVOICE NUMBER FILTER
    # ===============================
    if invoice_no:
        query = query.filter(
            purchase_models.Purchase.invoice_no.ilike(f"%{invoice_no}%")
        )

    # ===============================
    # PRODUCT FILTER
    # ===============================
    if product_id:
        query = query.filter(
            purchase_models.Purchase.product_id == product_id
        )

    # ===============================
    # VENDOR FILTER
    # ===============================
    if vendor_id:
        query = query.filter(
            purchase_models.Purchase.vendor_id == vendor_id
        )

    # ===============================
    # DATE RANGE FILTER
    # ===============================
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(
            purchase_models.Purchase.purchase_date >= start_dt
        )

    if end_date:
        end_dt = (
            datetime.strptime(end_date, "%Y-%m-%d")
            + timedelta(days=1)
        )
        query = query.filter(
            purchase_models.Purchase.purchase_date < end_dt
        )

    return (
        query
        .order_by(purchase_models.Purchase.purchase_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )




def get_purchase(db: Session, purchase_id: int):
    return db.query(purchase_models.Purchase).filter(
        purchase_models.Purchase.id == purchase_id
    ).first()


def update_purchase(
    db: Session,
    purchase_id: int,
    update_data: purchase_schemas.PurchaseUpdate
):
    purchase = get_purchase(db, purchase_id)
    if not purchase:
        return None

    old_product_id = purchase.product_id
    old_quantity = purchase.quantity

    # ===============================
    # UPDATE PURCHASE FIELDS
    # ===============================

    if update_data.invoice_no is not None:
        purchase.invoice_no = update_data.invoice_no

    if update_data.product_id is not None:
        purchase.product_id = update_data.product_id

    if update_data.quantity is not None:
        purchase.quantity = update_data.quantity

    if update_data.cost_price is not None:
        purchase.cost_price = update_data.cost_price

    if update_data.vendor_id is not None:
        purchase.vendor_id = update_data.vendor_id

    purchase.total_cost = purchase.quantity * purchase.cost_price

    # ===============================
    # INVENTORY: REVERSE → APPLY
    # ===============================

    # 1️⃣ Remove OLD stock
    inventory_service.add_stock(
        db,
        product_id=old_product_id,
        quantity=-old_quantity,
        commit=False
    )

    # 2️⃣ Add NEW stock
    inventory_service.add_stock(
        db,
        product_id=purchase.product_id,
        quantity=purchase.quantity,
        commit=False
    )

    # ===============================
    # UPDATE PRODUCT COST PRICE
    # ===============================
    product = (
        db.query(product_models.Product)
        .filter(product_models.Product.id == purchase.product_id)
        .first()
    )
    if not product:
        raise Exception("Product not found")

    product.cost_price = purchase.cost_price

    # ===============================
    # COMMIT ONCE
    # ===============================
    db.commit()
    db.refresh(purchase)

    return purchase


def delete_purchase(db: Session, purchase_id: int):
    purchase = get_purchase(db, purchase_id)
    if not purchase:
        return None

    # Revert inventory: subtract quantity_in from stock
    inventory = inventory_service.get_inventory_orm_by_product(db, purchase.product_id)
    if inventory:
        inventory.quantity_in -= purchase.quantity
        inventory.current_stock = inventory.quantity_in - inventory.quantity_out + inventory.adjustment_total
        db.add(inventory)

    db.delete(purchase)
    db.commit()
    return True
