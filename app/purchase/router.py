from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional


from app.database import get_db
from app.purchase import schemas, service
from app.stock.inventory import service as inventory_service
from app.vendor import models as vendor_models
from app.stock.products import models as product_models
from . import schemas, service as purchase_service
from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema
from app.users.auth import get_current_user



from typing import Any

router = APIRouter()


@router.post(
    "/",
    response_model=schemas.PurchaseOut,
    status_code=status.HTTP_201_CREATED,
)
def create_purchase(
    purchase: schemas.PurchaseCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    ),
):
    purchase_data = purchase.dict(exclude_unset=True)

    # 🔑 Admin → force their business
    if "admin" in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=400,
                detail="Current user does not belong to any business",
            )
        purchase_data["business_id"] = current_user.business_id

    # 🔑 Super admin → must provide business_id
    elif "super_admin" in current_user.roles:
        if not purchase_data.get("business_id"):
            raise HTTPException(
                status_code=400,
                detail="Super admin must specify a business_id",
            )

    return service.create_purchase(
        db=db,
        purchase=schemas.PurchaseCreate(**purchase_data),
        current_user=current_user,
    )

    

    

@router.get("/", response_model=List[schemas.PurchaseOut])
def list_purchases_route(
    skip: int = 0,
    limit: int = 100,
    invoice_no: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    vendor_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    business_id: Optional[int] = Query(None),  # ✅ NEW FILTER
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    purchases = purchase_service.list_purchases(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        invoice_no=invoice_no,
        product_id=product_id,
        vendor_id=vendor_id,
        start_date=start_date,
        end_date=end_date,
        business_id=business_id,
    )

    result = []
    for p in purchases:
        item_outputs = []
        for item in p.items:
            stock_entry = inventory_service.get_inventory_orm_by_product(db, item.product_id)
            current_stock = stock_entry.current_stock if stock_entry else 0

            item_outputs.append({
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product.name if item.product else None,
                "quantity": item.quantity,
                "cost_price": item.cost_price,
                "total_cost": item.total_cost,
                "current_stock": current_stock,
            })

        result.append({
            "id": p.id,
            "invoice_no": p.invoice_no,
            "vendor_id": p.vendor_id,
            "vendor_name": p.vendor.business_name if p.vendor else None,
            "business_id": p.business_id,
            "purchase_date": p.purchase_date,
            "items": item_outputs,
            "total_cost": p.total_cost,
            "created_at": p.created_at,
        })

    return result

    

@router.get("/{purchase_id}", response_model=schemas.PurchaseOut)
def get_purchase_route(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    purchase = service.get_purchase(
        db=db,
        purchase_id=purchase_id,
        current_user=current_user,
    )

    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase not found",
        )

    return purchase



@router.put(
    "/{purchase_id}",
    response_model=schemas.PurchaseOut
)
def update_purchase(
    purchase_id: int,
    update_data: schemas.PurchaseUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    ),
):
    updated = service.update_purchase(
        db=db,
        purchase_id=purchase_id,
        update_data=update_data,
        current_user=current_user,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase not found",
        )

    return updated



@router.delete("/{purchase_id}")
def delete_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    ),
):
    deleted = service.delete_purchase(
        db=db,
        purchase_id=purchase_id,
        current_user=current_user,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase not found",
        )

    return {"message": "Purchase deleted successfully"}
