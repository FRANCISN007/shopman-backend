from fastapi import APIRouter, Depends, HTTPException, status,  Query
from sqlalchemy.orm import Session
from typing import List
from datetime import date
from typing import Optional
from sqlalchemy import text

from app.sales.schemas import SaleOut,  SaleOut2, SaleFullCreate, OutstandingSalesResponse, SalesListResponse, ItemSoldResponse
from app.sales import models as sales_models
from app.payments.models import Payment

from app.database import get_db
from . import schemas, service
from app.users.schemas import UserDisplaySchema
from app.users.permissions import role_required
import uuid

from app.sales.service import get_sales_by_customer







router = APIRouter()





# ────────────────────────────────────────────────────────────────
# router.py
# ────────────────────────────────────────────────────────────────

@router.post("/", response_model=schemas.SaleOut, status_code=201)
def create_sale(
    sale_data: schemas.SaleFullCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    ),
):
    """
    Create a new sale (header + items) in one atomic operation.
    Super admin must provide business_id in a future version or via header/query.
    """
    # For now we pass business_id=None → function will use user's business
    # Later you can add query param ?business_id=123 for super_admin
    created_sale = service.create_sale_full(
        db=db,
        sale_data=sale_data,
        current_user=current_user,
        business_id=None,           # change later if you add ?business_id=
    )

    # Enrich response with product names (if not already attached)
    items_out = []
    for item in created_sale.items:
        items_out.append(
            schemas.SaleItemOut(
                id=item.id,
                sale_invoice_no=item.sale_invoice_no,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                quantity=item.quantity,
                selling_price=item.selling_price,
                gross_amount=item.gross_amount,
                discount=item.discount,
                net_amount=item.net_amount,
            )
        )

    return schemas.SaleOut(
        id=created_sale.id,
        invoice_no=created_sale.invoice_no,
        invoice_date=created_sale.invoice_date,
        customer_name=created_sale.customer_name,
        customer_phone=created_sale.customer_phone,
        ref_no=created_sale.ref_no,
        total_amount=created_sale.total_amount,
        sold_by=created_sale.sold_by,
        sold_at=created_sale.sold_at,
        items=items_out,
    )



# router.py
@router.post("/items", response_model=schemas.SaleItemOut, status_code=201)
def add_sale_item(
    item: schemas.SaleItemCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    ),
):
    """
    Add a single item to an **existing** sale.
    Enforces tenant isolation.
    """
    created_item = service.create_sale_item(db, item, current_user)
    
    # Enrich response with product name
    product_name = None
    if created_item.product:
        product_name = created_item.product.name
    
    return schemas.SaleItemOut(
        id=created_item.id,
        sale_invoice_no=created_item.sale_invoice_no,
        product_id=created_item.product_id,
        product_name=product_name,
        quantity=created_item.quantity,
        selling_price=created_item.selling_price,
        gross_amount=created_item.gross_amount,
        discount=created_item.discount,
        net_amount=created_item.net_amount,
    )



@router.get("/", response_model=schemas.SalesListResponse)
def list_sales(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    # ─── Super-admin only filter ───
    business_id: Optional[int] = Query(
        None,
        description="Filter by specific business (super admin only)"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    List sales with full tenant isolation.
    Normal users see only their business.
    Super admin can see everything or filter by business_id.
    """
    sales_data = service.list_sales(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        business_id=business_id,
    )

    return sales_data



@router.get("/invoices", response_model=List[int])
def list_invoice_numbers(
    business_id: Optional[int] = Query(
        None,
        description="Filter by specific business (super admin only)"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Returns a list of all invoice numbers (sale.invoice_no).
    
    - Regular users/managers/admins → only their own business
    - Super admin → all businesses, or filtered by ?business_id=xxx
    """
    invoice_nos = service.get_all_invoice_numbers(
        db=db,
        current_user=current_user,
        business_id=business_id
    )
    return invoice_nos


# router.py
@router.get("/invoice/{invoice_no}", response_model=schemas.SaleReprintOut)
def get_sale_by_invoice(
    invoice_no: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Get full sale details by invoice number (for reprint / view).
    
    - Normal users → only their own business sales
    - Super admin → any sale
    """
    sale_data = service.get_sale_by_invoice_no(
        db=db,
        invoice_no=invoice_no,
        current_user=current_user
    )

    if not sale_data:
        raise HTTPException(
            status_code=404,
            detail=f"Sale with invoice_no {invoice_no} not found "
                   f"or does not belong to your business"
        )

    return sale_data





# router.py
@router.get(
    "/report/staff",
    response_model=List[schemas.SaleOutStaff]
)
def staff_sales_report(
    staff_id: Optional[int] = Query(None, description="Filter by specific staff/user ID"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    business_id: Optional[int] = Query(
        None,
        description="Filter by business (super admin only)"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    )
):
    """
    Sales performance report by staff (sold_by user).
    
    - Managers/Admins → only their own business
    - Super admin → all businesses or filtered by ?business_id=xxx
    Optional filters: staff_id, start_date, end_date
    """
    return service.staff_sales_report(
        db=db,
        current_user=current_user,
        staff_id=staff_id,
        start_date=start_date,
        end_date=end_date,
        business_id=business_id
    )



@router.get(
    "/outstanding",
    response_model=schemas.OutstandingSalesResponse
)
def outstanding_sales(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    customer_name: Optional[str] = Query(None, description="Filter by customer name (partial match)"),
    business_id: Optional[int] = Query(
        None,
        description="Filter by specific business (super admin only)"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    List outstanding (unpaid or partially paid) sales with tenant isolation.
    
    - Normal users → only their own business
    - Super admin → all businesses or filtered by ?business_id=
    - Defaults to current month if no dates provided
    """
    return service.outstanding_sales_service(
        db=db,
        current_user=current_user,
        start_date=start_date,
        end_date=end_date,
        customer_name=customer_name,
        business_id=business_id
    )




# router.py
@router.get("/by-customer", response_model=List[schemas.SaleOut2])
def sales_by_customer(
    customer_name: str | None = Query(None, description="Customer name (partial match)"),
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    business_id: int | None = Query(
        None,
        description="Filter by specific business (super admin only)"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Get all sales for a specific customer (partial name match) with tenant isolation.
    
    - Normal users → only their own business
    - Super admin → all businesses or filtered by ?business_id=
    """
    if not customer_name or not customer_name.strip():
        return []

    return service.get_sales_by_customer(
        db=db,
        current_user=current_user,
        customer_name=customer_name.strip(),
        start_date=start_date,
        end_date=end_date,
        business_id=business_id
    )



from typing import Optional
from datetime import date

# router.py
@router.get(
    "/item-sold",
    response_model=schemas.ItemSoldResponse
)
def list_item_sold(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD) - required"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD) - required"),
    invoice_no: Optional[int] = Query(None, description="Filter by invoice number"),
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    product_name: Optional[str] = Query(None, description="Partial product name filter"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    business_id: Optional[int] = Query(
        None,
        description="Filter by specific business (super admin only)"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Report of sold items with filters (date range required).
    
    - Normal users → only their own business
    - Super admin → all businesses or filtered by ?business_id=
    - Returns paginated sales + total quantity & net amount summary
    """
    return service.list_item_sold(
        db=db,
        current_user=current_user,
        start_date=start_date,
        end_date=end_date,
        invoice_no=invoice_no,
        product_id=product_id,
        product_name=product_name,
        skip=skip,
        limit=limit,
        business_id=business_id
    )





# router.py
@router.put("/{invoice_no}", response_model=schemas.SaleOut)
def update_sale_header(
    invoice_no: int,
    sale_update: schemas.SaleUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    )
):
    """
    Update sale header fields (customer name, phone, ref_no, etc.).
    
    - Managers/Admins → only their own business sales
    - Super admin → any sale
    - Cannot update invoice_no or totals directly
    """
    updated_sale = service.update_sale(
        db=db,
        invoice_no=invoice_no,
        sale_update=sale_update,
        current_user=current_user
    )

    if not updated_sale:
        raise HTTPException(
            status_code=404,
            detail=f"Sale with invoice_no {invoice_no} not found "
                   f"or does not belong to your business"
        )

    return updated_sale


# router.py
@router.get(
    "/report/analysis",
    response_model=schemas.SaleAnalysisOut
)
def sales_analysis(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    product_id: Optional[int] = Query(None, description="Filter by specific product"),
    business_id: Optional[int] = Query(
        None,
        description="Filter by specific business (super admin only)"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    )
):
    """
    Sales performance analysis report (by product) with historical margins.
    
    - Uses frozen cost_price from SaleItem → margins never retroactively change
    - Managers/Admins → only their own business
    - Super admin → all businesses or filtered by ?business_id=
    """
    return service.sales_analysis(
        db=db,
        current_user=current_user,
        start_date=start_date,
        end_date=end_date,
        product_id=product_id,
        business_id=business_id
    )



# router.py
@router.put(
    "/{invoice_no}/items",
    response_model=schemas.SaleItemOut,
    status_code=200
)
def update_sale_item(
    invoice_no: int,
    item_update: schemas.SaleItemUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    )
):
    """
    Update an existing sale item (product, quantity, price, discount).
    
    - Managers/Admins → only their own business sales
    - Super admin → any sale
    - Automatically adjusts stock, historical cost, totals
    """
    updated_item = service.update_sale_item(
        db=db,
        invoice_no=invoice_no,
        item_update=item_update,
        current_user=current_user
    )

    if not updated_item:
        raise HTTPException(
            status_code=404,
            detail=f"Sale item not found for invoice_no {invoice_no} "
                   f"or does not belong to your business"
        )

    # Enrich response with product name
    product_name = updated_item.product.name if updated_item.product else None

    return schemas.SaleItemOut(
        id=updated_item.id,
        sale_invoice_no=updated_item.sale_invoice_no,
        product_id=updated_item.product_id,
        product_name=product_name,
        quantity=updated_item.quantity,
        selling_price=updated_item.selling_price,
        gross_amount=updated_item.gross_amount,
        discount=updated_item.discount,
        net_amount=updated_item.net_amount,
    )


from sqlalchemy.orm import joinedload

# router.py
@router.get("/receipt/{invoice_no}", response_model=schemas.SaleOut2)
def get_sale_invoice_reprint(
    invoice_no: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Get sale data formatted for receipt / reprint.
    
    - Regular users → only their own business receipts
    - Super admin → any receipt
    """
    receipt_data = service.get_receipt_data(
        db=db,
        invoice_no=invoice_no,
        current_user=current_user
    )

    if not receipt_data:
        raise HTTPException(
            status_code=404,
            detail=f"Receipt with invoice_no {invoice_no} not found "
                   f"or does not belong to your business"
        )

    return receipt_data



# router.py
@router.delete("/{invoice_no}")
def delete_sale(
    invoice_no: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    )
):
    """
    Delete a sale and restore inventory.
    
    - Managers/Admins → only their own business sales
    - Super admin → any sale
    - Cannot delete if payments exist
    """
    from app.payments import service as payment_service

    # Check for payments first (tenant-safe inside service)
    payments = payment_service.list_payments_by_sale(db, invoice_no)
    if payments:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete sale: payments exist. Please delete the payment(s) first."
        )

    deleted = service.delete_sale(
        db=db,
        invoice_no=invoice_no,
        current_user=current_user
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Sale with invoice_no {invoice_no} not found "
                   f"or does not belong to your business"
        )

    return {"message": "Sale deleted successfully"}



@router.delete("/business/{business_id}/sales/all")
def delete_all_sales_of_business(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin"]))
):
    """
    SUPER DANGEROUS – only super admin.
    Deletes ALL sales of ONE specific business and restores stock.
    """
    # Only super admin can run this
    if "super_admin" not in current_user.roles:
        raise HTTPException(403, "Only super admin can delete all sales of a business")

    # Optional: require confirmation token / second factor
    # if not confirmed: raise 400 "Confirmation required"

    count = service.delete_all_sales_of_business(db, business_id)

    return {
        "message": f"All {count} sales of business {business_id} deleted and stock restored",
        "deleted_count": count
    }