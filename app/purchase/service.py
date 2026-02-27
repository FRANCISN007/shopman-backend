from sqlalchemy.orm import Session
from fastapi import  HTTPException
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

from app.purchase import models as purchase_models, schemas as purchase_schemas
from app.stock.inventory import service as inventory_service
from datetime import datetime
from app.vendor import models as  vendor_models

from datetime import datetime, timedelta


from app.stock.products import models as product_models


def create_purchase(db, purchase, current_user):

    total_cost = purchase.quantity * purchase.cost_price

    # Determine business_id properly
    business_id = purchase.business_id or current_user.business_id

    # 1️⃣ Validate product
    product = db.query(product_models.Product).filter(
        product_models.Product.id == purchase.product_id,
        product_models.Product.business_id == business_id,
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found for this business"
        )

    # 2️⃣ Validate vendor
    vendor_name = None
    if purchase.vendor_id:
        vendor = db.query(vendor_models.Vendor).filter(
            vendor_models.Vendor.id == purchase.vendor_id,
            vendor_models.Vendor.business_id == business_id,
        ).first()

        if not vendor:
            raise HTTPException(
                status_code=404,
                detail="Vendor not found for this business"
            )

        vendor_name = vendor.business_name

    # 3️⃣ Create purchase
    db_purchase = purchase_models.Purchase(
        invoice_no=purchase.invoice_no,
        product_id=purchase.product_id,
        vendor_id=purchase.vendor_id,
        quantity=purchase.quantity,
        cost_price=purchase.cost_price,
        total_cost=total_cost,
        business_id=business_id,
    )

    db.add(db_purchase)
    db.flush()

    # 4️⃣ Update inventory
    inventory_service.add_stock(
        db,
        product_id=purchase.product_id,
        quantity=purchase.quantity,
        current_user=current_user,
        commit=False,
    )

    # 5️⃣ Update product cost
    product.cost_price = purchase.cost_price

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Failed to create purchase"
        )

    db.refresh(db_purchase)

    # 6️⃣ Get updated stock
    inventory = inventory_service.get_inventory_orm_by_product(
        db,
        purchase.product_id,
        current_user
    )
    current_stock = inventory.current_stock if inventory else 0

    return {
        **db_purchase.__dict__,
        "current_stock": current_stock,
        "product_name": product.name,
        "vendor_name": vendor_name,
    }



from datetime import datetime, timedelta

# ------------------------------
# List Purchases Service
# ------------------------------
def list_purchases(
    db: Session,
    current_user,
    skip: int = 0,
    limit: int = 100,
    invoice_no: Optional[str] = None,
    product_id: Optional[int] = None,
    vendor_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    business_id: Optional[int] = None,  # ✅ NEW PARAM
):
    query = db.query(purchase_models.Purchase)

    # 🔐 SaaS Tenant Isolation
    if "admin" in current_user.roles or "manager" in current_user.roles or "user" in current_user.roles:
        query = query.filter(
            purchase_models.Purchase.business_id == current_user.business_id
        )
    elif business_id:
        # ✅ Super admin can filter by any business
        query = query.filter(purchase_models.Purchase.business_id == business_id)

    # ===============================
    # Other Filters
    # ===============================
    if invoice_no:
        query = query.filter(purchase_models.Purchase.invoice_no.ilike(f"%{invoice_no}%"))
    if product_id:
        query = query.filter(purchase_models.Purchase.product_id == product_id)
    if vendor_id:
        query = query.filter(purchase_models.Purchase.vendor_id == vendor_id)
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(purchase_models.Purchase.purchase_date >= start_dt)
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(purchase_models.Purchase.purchase_date < end_dt)

    return query.order_by(purchase_models.Purchase.purchase_date.desc()).offset(skip).limit(limit).all()





def get_purchase(
    db: Session,
    purchase_id: int,
    current_user,
):
    query = db.query(purchase_models.Purchase)

    # 🔑 Tenant isolation
    query = query.filter(
        purchase_models.Purchase.business_id == current_user.business_id
    )

    return query.filter(
        purchase_models.Purchase.id == purchase_id
    ).first()


def update_purchase(
    db: Session,
    purchase_id: int,
    update_data: purchase_schemas.PurchaseUpdate,
    current_user,
):
    # ===================================
    # 1️⃣ Fetch Purchase (Tenant Safe)
    # ===================================

    query = db.query(purchase_models.Purchase)

    if "super_admin" not in current_user.roles:
        query = query.filter(
            purchase_models.Purchase.business_id == current_user.business_id
        )

    purchase = query.filter(
        purchase_models.Purchase.id == purchase_id
    ).first()

    if not purchase:
        return None

    old_product_id = purchase.product_id
    old_quantity = purchase.quantity

    # ===================================
    # 2️⃣ Validate Product (if changed)
    # ===================================

    new_product_id = update_data.product_id or purchase.product_id

    product = db.query(product_models.Product).filter(
        product_models.Product.id == new_product_id,
        product_models.Product.business_id == purchase.business_id,
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found for this business",
        )

    # ===================================
    # 3️⃣ Validate Vendor (if provided)
    # ===================================

    vendor_name = None

    if update_data.vendor_id:
        vendor = db.query(vendor_models.Vendor).filter(
            vendor_models.Vendor.id == update_data.vendor_id,
            vendor_models.Vendor.business_id == purchase.business_id,
        ).first()

        if not vendor:
            raise HTTPException(
                status_code=404,
                detail="Vendor not found for this business",
            )

        vendor_name = vendor.business_name

    elif purchase.vendor:
        vendor_name = purchase.vendor.business_name

    # ===================================
    # 4️⃣ Apply Updates
    # ===================================

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

    # ===================================
    # 5️⃣ Inventory Reverse → Apply
    # ===================================

    # Remove OLD stock
    inventory_service.add_stock(
        db,
        product_id=old_product_id,
        quantity=-old_quantity,
        current_user=current_user,
        commit=False,
    )

    # Add NEW stock
    inventory_service.add_stock(
        db,
        product_id=purchase.product_id,
        quantity=purchase.quantity,
        current_user=current_user,
        commit=False,
    )

    # ===================================
    # 6️⃣ Update Product Cost Price
    # ===================================

    product.cost_price = purchase.cost_price

    # ===================================
    # 7️⃣ Commit Once
    # ===================================

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Failed to update purchase",
        )

    db.refresh(purchase)

    # ===================================
    # 8️⃣ Get Updated Stock
    # ===================================

    inventory = inventory_service.get_inventory_orm_by_product(
        db,
        purchase.product_id,
        current_user,
    )
    current_stock = inventory.current_stock if inventory else 0

    # ===================================
    # 9️⃣ Return Enriched Response
    # ===================================

    return {
        **purchase.__dict__,
        "current_stock": current_stock,
        "product_name": product.name,
        "vendor_name": vendor_name,
    }



def delete_purchase(
    db: Session,
    purchase_id: int,
    current_user,
):
    # ===================================
    # 1️⃣ Fetch Purchase (Tenant Safe)
    # ===================================

    query = db.query(purchase_models.Purchase)

    # Super admin can delete any purchase
    if "super_admin" not in current_user.roles:
        query = query.filter(
            purchase_models.Purchase.business_id == current_user.business_id
        )

    purchase = query.filter(
        purchase_models.Purchase.id == purchase_id
    ).first()

    if not purchase:
        return None

    # ===================================
    # 2️⃣ Reverse Inventory
    # ===================================

    inventory_service.add_stock(
        db,
        product_id=purchase.product_id,
        quantity=-purchase.quantity,  # 🔁 reverse stock
        current_user=current_user,
        commit=False,
    )

    # ===================================
    # 3️⃣ Delete Purchase
    # ===================================

    db.delete(purchase)

    # ===================================
    # 4️⃣ Commit Once
    # ===================================

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Failed to delete purchase",
        )

    return True
