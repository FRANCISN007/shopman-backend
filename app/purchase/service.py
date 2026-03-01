from sqlalchemy.orm import Session
from fastapi import  HTTPException
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

from app.purchase import models as purchase_models, schemas as purchase_schemas
from app.stock.inventory import service as inventory_service
from datetime import datetime
from app.vendor import models as  vendor_models

from sqlalchemy.orm import joinedload

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


from app.stock.products import models as product_models


def create_purchase(db, purchase, current_user):
    """
    Create a purchase invoice with multiple items, allowing duplicate invoice numbers
    and returning proper vendor/product info with updated stock.
    """
    if not purchase.items or len(purchase.items) == 0:
        raise HTTPException(
            status_code=400,
            detail="At least one purchase item is required"
        )

    # -------------------- Determine Business --------------------
    business_id = purchase.business_id or current_user.business_id
    if not business_id:
        raise HTTPException(
            status_code=400,
            detail="Business ID is required"
        )

    # -------------------- Validate Vendor --------------------
    vendor = None
    vendor_name = None
    if purchase.vendor_id:
        vendor = db.query(vendor_models.Vendor).filter(
            vendor_models.Vendor.id == purchase.vendor_id,
            vendor_models.Vendor.business_id == business_id
        ).first()
        if not vendor:
            raise HTTPException(
                status_code=404,
                detail="Vendor not found for this business"
            )
        vendor_name = vendor.business_name

    try:
        # -------------------- 1️⃣ Create Purchase Header --------------------
        db_purchase = purchase_models.Purchase(
            invoice_no=purchase.invoice_no,
            vendor_id=purchase.vendor_id,
            business_id=business_id,
            purchase_date=purchase.purchase_date or datetime.now(ZoneInfo("Africa/Lagos"))
        )
        db.add(db_purchase)
        db.flush()  # get db_purchase.id before adding items

        total_invoice_cost = 0
        item_outputs = []

        # -------------------- 2️⃣ Process Each Item --------------------
        for item in purchase.items:
            # Validate product
            product = db.query(product_models.Product).filter(
                product_models.Product.id == item.product_id,
                product_models.Product.business_id == business_id
            ).first()
            if not product:
                raise HTTPException(
                    status_code=404,
                    detail=f"Product {item.product_id} not found for this business"
                )

            # Calculate total
            item_total = item.quantity * item.cost_price
            total_invoice_cost += item_total

            # Create PurchaseItem row
            db_item = purchase_models.PurchaseItem(
                purchase_id=db_purchase.id,
                product_id=item.product_id,
                quantity=item.quantity,
                cost_price=item.cost_price,
                total_cost=item_total
            )
            db.add(db_item)
            db.flush()
            db.refresh(db_item)

            # Update inventory
            inventory_service.add_stock(
                db=db,
                product_id=item.product_id,
                quantity=item.quantity,
                current_user=current_user,
                commit=False
            )

            # Update product cost
            product.cost_price = item.cost_price

            # Get updated stock
            inventory = inventory_service.get_inventory_orm_by_product(
                db=db,
                product_id=item.product_id,
                current_user=current_user
            )
            current_stock = inventory.current_stock if inventory else 0

            # Append item info for response
            item_outputs.append({
                "id": db_item.id,
                "product_id": product.id,
                "product_name": product.name,
                "quantity": item.quantity,
                "cost_price": item.cost_price,
                "total_cost": item_total,
                "current_stock": current_stock
            })

        # -------------------- 3️⃣ Update Purchase Total --------------------
        if hasattr(db_purchase, "total_cost"):
            db_purchase.total_cost = total_invoice_cost

        # Commit everything
        db.commit()
        db.refresh(db_purchase)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Failed to create purchase."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    # -------------------- 4️⃣ Prepare Response --------------------
    return {
        "id": db_purchase.id,
        "invoice_no": db_purchase.invoice_no,
        "vendor_id": db_purchase.vendor_id,
        "vendor_name": vendor_name,
        "business_id": db_purchase.business_id,
        "purchase_date": db_purchase.purchase_date,
        "items": item_outputs,
        "created_at": getattr(db_purchase, "created_at", datetime.now(ZoneInfo("Africa/Lagos")))
    }



from datetime import datetime, timedelta

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
    business_id: Optional[int] = None,
):
    query = db.query(purchase_models.Purchase)

    # 🔐 Tenant / Role Isolation
    if "admin" in current_user.roles or "manager" in current_user.roles or "user" in current_user.roles:
        query = query.filter(
            purchase_models.Purchase.business_id == current_user.business_id
        )
    elif business_id:
        query = query.filter(purchase_models.Purchase.business_id == business_id)

    # Filters
    if invoice_no:
        query = query.filter(purchase_models.Purchase.invoice_no.ilike(f"%{invoice_no}%"))
    if vendor_id:
        query = query.filter(purchase_models.Purchase.vendor_id == vendor_id)
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(purchase_models.Purchase.purchase_date >= start_dt)
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(purchase_models.Purchase.purchase_date < end_dt)

    # Filter by product_id in PurchaseItem table
    if product_id:
        query = query.join(purchase_models.Purchase.items).filter(purchase_models.PurchaseItem.product_id == product_id)

    return query.order_by(purchase_models.Purchase.purchase_date.desc()).offset(skip).limit(limit).all()





def get_purchase(db: Session, purchase_id: int, current_user):
    """
    Fetch a single purchase by ID with tenant isolation, including all items.
    """

    # -------------------- Base Query --------------------
    query = db.query(purchase_models.Purchase).options(
        joinedload(purchase_models.Purchase.items).joinedload(purchase_models.PurchaseItem.product),
        joinedload(purchase_models.Purchase.vendor)
    )

    # -------------------- Tenant Isolation --------------------
    if "super_admin" not in current_user.roles:
        query = query.filter(
            purchase_models.Purchase.business_id == current_user.business_id
        )

    purchase = query.filter(
        purchase_models.Purchase.id == purchase_id
    ).first()

    if not purchase:
        return None

    # -------------------- Process Items --------------------
    item_outputs = []
    for item in purchase.items:
        inventory = inventory_service.get_inventory_orm_by_product(
            db, item.product_id, current_user
        )
        current_stock = inventory.current_stock if inventory else 0

        item_outputs.append({
            "id": item.id,
            "product_id": item.product_id,
            "product_name": item.product.name if item.product else None,
            "quantity": item.quantity,
            "cost_price": item.cost_price,
            "total_cost": item.total_cost,
            "current_stock": current_stock,
        })

    # -------------------- Build Response --------------------
    return {
        "id": purchase.id,
        "invoice_no": purchase.invoice_no,
        "vendor_id": purchase.vendor_id,
        "vendor_name": purchase.vendor.business_name if purchase.vendor else None,
        "business_id": purchase.business_id,
        "purchase_date": purchase.purchase_date,
        "items": item_outputs,
        "total_cost": purchase.total_cost,
        "created_at": purchase.created_at,
    }



def update_purchase(db, purchase_id, update_data, current_user):
    """
    Update a purchase invoice with multiple items.
    """
    # -------------------- 1️⃣ Fetch Purchase --------------------
    query = db.query(purchase_models.Purchase)
    if "super_admin" not in current_user.roles:
        query = query.filter(purchase_models.Purchase.business_id == current_user.business_id)
    purchase = query.filter(purchase_models.Purchase.id == purchase_id).first()
    if not purchase:
        return None

    vendor_name = purchase.vendor.business_name if purchase.vendor else None

    # -------------------- 2️⃣ Update Purchase Header --------------------
    if update_data.invoice_no is not None:
        purchase.invoice_no = update_data.invoice_no

    if update_data.vendor_id is not None:
        vendor = db.query(vendor_models.Vendor).filter(
            vendor_models.Vendor.id == update_data.vendor_id,
            vendor_models.Vendor.business_id == purchase.business_id,
        ).first()
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found for this business")
        purchase.vendor_id = update_data.vendor_id
        vendor_name = vendor.business_name

    total_invoice_cost = 0

    # -------------------- 3️⃣ Update Items --------------------
    if update_data.items:
        for item_update in update_data.items:
            if item_update.id:
                # Existing item → fetch
                item = db.query(purchase_models.PurchaseItem).filter(
                    purchase_models.PurchaseItem.id == item_update.id,
                    purchase_models.PurchaseItem.purchase_id == purchase.id
                ).first()
                if not item:
                    raise HTTPException(status_code=404, detail=f"Purchase item {item_update.id} not found")
                
                # Reverse old stock
                inventory_service.add_stock(
                    db, item.product_id, -item.quantity, current_user, commit=False
                )

                # Update fields
                item.product_id = item_update.product_id
                item.quantity = item_update.quantity
                item.cost_price = item_update.cost_price
                item.total_cost = item_update.quantity * item_update.cost_price

            else:
                # New item → create
                item_total = item_update.quantity * item_update.cost_price
                item = purchase_models.PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=item_update.product_id,
                    quantity=item_update.quantity,
                    cost_price=item_update.cost_price,
                    total_cost=item_total
                )
                db.add(item)

            # Apply new stock
            inventory_service.add_stock(
                db, item_update.product_id, item_update.quantity, current_user, commit=False
            )

            # Update product cost
            product = db.query(product_models.Product).filter(
                product_models.Product.id == item_update.product_id,
                product_models.Product.business_id == purchase.business_id
            ).first()
            if product:
                product.cost_price = item_update.cost_price

            total_invoice_cost += item.quantity * item.cost_price

        purchase.total_cost = total_invoice_cost

    try:
        db.commit()
        db.refresh(purchase)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Failed to update purchase")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    # -------------------- 4️⃣ Return Structured Response --------------------
    item_outputs = []
    for item in purchase.items:
        inventory = inventory_service.get_inventory_orm_by_product(db, item.product_id, current_user)
        current_stock = inventory.current_stock if inventory else 0
        item_outputs.append({
            "id": item.id,
            "product_id": item.product_id,
            "product_name": item.product.name if item.product else None,
            "quantity": item.quantity,
            "cost_price": item.cost_price,
            "total_cost": item.total_cost,
            "current_stock": current_stock,
        })

    return {
        "id": purchase.id,
        "invoice_no": purchase.invoice_no,
        "vendor_id": purchase.vendor_id,
        "vendor_name": vendor_name,
        "business_id": purchase.business_id,
        "purchase_date": purchase.purchase_date,
        "items": item_outputs,
        "total_cost": purchase.total_cost,
        "created_at": purchase.created_at,
    }



def delete_purchase(
    db: Session,
    purchase_id: int,
    current_user,
):
    """
    Delete a purchase and reverse inventory for all items.
    """
    # ===================================
    # 1️⃣ Fetch Purchase (Tenant Safe)
    # ===================================
    query = db.query(purchase_models.Purchase)

    # Super admin can delete any purchase, others limited to their business
    if "super_admin" not in current_user.roles:
        query = query.filter(
            purchase_models.Purchase.business_id == current_user.business_id
        )

    # Include items for stock reversal
    purchase = query.options(
        joinedload(purchase_models.Purchase.items)
    ).filter(
        purchase_models.Purchase.id == purchase_id
    ).first()

    if not purchase:
        return None

    # ===================================
    # 2️⃣ Reverse Inventory for all items
    # ===================================
    for item in purchase.items:
        inventory_service.add_stock(
            db,
            product_id=item.product_id,
            quantity=-item.quantity,  # 🔁 reverse stock
            current_user=current_user,
            commit=False,
        )

    # ===================================
    # 3️⃣ Delete Purchase and Items
    # ===================================
    try:
        # Delete items first (SQLAlchemy will cascade if configured, but safe to remove explicitly)
        for item in purchase.items:
            db.delete(item)

        # Delete the purchase
        db.delete(purchase)

        # ===================================
        # 4️⃣ Commit Once
        # ===================================
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Failed to delete purchase due to integrity error",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to delete purchase: {str(e)}",
        )

    return True
