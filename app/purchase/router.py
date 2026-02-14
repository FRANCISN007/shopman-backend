from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional


from app.database import get_db
from app.purchase import schemas, service
from app.stock.inventory import service as inventory_service
from app.vendor import models as vendor_models
from app.stock.products import models as product_models
from . import schemas, service as purchase_service

from typing import Any

router = APIRouter()


@router.post("/", response_model=schemas.PurchaseOut)
def create_purchase(purchase: schemas.PurchaseCreate, db: Session = Depends(get_db)):
    try:
        db_purchase = service.create_purchase(db, purchase)
        inventory = inventory_service.get_inventory_orm_by_product(db, db_purchase.product_id)
        current_stock = inventory.current_stock if inventory else 0
        return {**db_purchase.__dict__, "current_stock": current_stock}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    

    

@router.get("/", response_model=List[schemas.PurchaseOut])
def list_purchases_route(
    skip: int = 0,
    limit: int = 100,
    invoice_no: Optional[str] = Query(None, description="Invoice number search"),
    product_id: Optional[int] = Query(None),
    vendor_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    purchases = purchase_service.list_purchases(
        db=db,
        skip=skip,
        limit=limit,
        invoice_no=invoice_no,      # ✅ NEW
        product_id=product_id,
        vendor_id=vendor_id,
        start_date=start_date,
        end_date=end_date,
    )

    result = []

    for p in purchases:
        stock_entry = inventory_service.get_inventory_orm_by_product(
            db, p.product_id
        )
        current_stock = stock_entry.current_stock if stock_entry else 0

        product = (
            db.query(product_models.Product)
            .filter(product_models.Product.id == p.product_id)
            .first()
        )
        product_name = product.name if product else None

        vendor_name = None
        if p.vendor_id:
            vendor = (
                db.query(vendor_models.Vendor)
                .filter(vendor_models.Vendor.id == p.vendor_id)
                .first()
            )
            vendor_name = vendor.business_name if vendor else None

        result.append({
            **p.__dict__,
            "current_stock": current_stock,
            "product_name": product_name,
            "vendor_name": vendor_name,
        })

    return result


@router.get("/{purchase_id}", response_model=schemas.PurchaseOut)
def get_purchase(purchase_id: int, db: Session = Depends(get_db)):
    purchase = service.get_purchase(db, purchase_id)
    if not purchase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found")
    stock_entry = inventory_service.get_inventory_orm_by_product(db, purchase.product_id)
    current_stock = stock_entry.current_stock if stock_entry else 0
    return {**purchase.__dict__, "current_stock": current_stock}


@router.put("/{purchase_id}", response_model=schemas.PurchaseOut)
def update_purchase(
    purchase_id: int,
    update_data: schemas.PurchaseUpdate,
    db: Session = Depends(get_db),
):
    purchase = service.update_purchase(db, purchase_id, update_data)
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase not found"
        )

    # Get current stock
    stock_entry = inventory_service.get_inventory_orm_by_product(
        db, purchase.product_id
    )
    current_stock = stock_entry.current_stock if stock_entry else 0

    # ✅ Get product name
    product = (
        db.query(product_models.Product)
        .filter(product_models.Product.id == purchase.product_id)
        .first()
    )
    product_name = product.name if product else None

    # ✅ Get vendor name
    vendor_name = None
    if purchase.vendor_id:
        vendor = (
            db.query(vendor_models.Vendor)
            .filter(vendor_models.Vendor.id == purchase.vendor_id)
            .first()
        )
        vendor_name = vendor.business_name if vendor else None

    return {
        **purchase.__dict__,
        "product_name": product_name,
        "vendor_name": vendor_name,
        "current_stock": current_stock,
    }


@router.delete("/{purchase_id}")
def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    deleted = service.delete_purchase(db, purchase_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found")
    return {"message": "Purchase deleted successfully"}
