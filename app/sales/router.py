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





@router.post("/", response_model=SaleOut, status_code=201)
def create_sale_endpoint(
    sale_data: SaleFullCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["user", "manager", "admin"]))
):
    """
    Create a sale + all items in a single transaction.
    """
    return service.create_sale_full(db, sale_data, current_user.id)


@router.post("/items")
def create_sale_item(
    item: schemas.SaleItemCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["user", "manager", "admin"]))
):
    return service.create_sale_item(db, item)




@router.get("/", response_model=schemas.SalesListResponse)
def list_sales(
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin"])
    )
):
    return service.list_sales(
        db=db,
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date
    )


@router.get("/invoices", response_model=list[int])
def list_invoice_numbers(
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["user", "manager", "admin"]))
):
    return service.get_all_invoice_numbers(db)



@router.get("/invoice/{invoice_no}", response_model=schemas.SaleReprintOut)
def get_sale_by_invoice(
    invoice_no: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["user", "manager", "admin"]))
):
    return service.get_sale_by_invoice_no(db, invoice_no)


@router.get(
    "/report/staff",
    response_model=List[schemas.SaleOutStaff]
)
def staff_sales_report(
    staff_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin"])
    )
):
    """
    Sales made by staff (sold_by).
    Optional filters:
    - staff_id
    - start_date / end_date
    """
    return service.staff_sales_report(
        db=db,
        staff_id=staff_id,
        start_date=start_date,
        end_date=end_date
    )


@router.get(
    "/outstanding",
    response_model=OutstandingSalesResponse
)
def outstanding_sales(
    start_date: date | None = None,
    end_date: date | None = None,
    customer_name: str | None = None,
    db: Session = Depends(get_db)
):
    """
    Get outstanding sales between start_date and end_date.
    If no dates are provided, defaults to today.
    """
    return service.outstanding_sales_service(
        db=db,
        start_date=start_date,
        end_date=end_date,
        customer_name=customer_name
    )



@router.get("/by-customer", response_model=List[SaleOut2])
def sales_by_customer(
    customer_name: str | None = Query(None, description="Customer name"),
    start_date: date | None = Query(None, description="Start date"),
    end_date: date | None = Query(None, description="End date"),
    db: Session = Depends(get_db)
):
    return get_sales_by_customer(
        db=db,
        customer_name=customer_name,
        start_date=start_date,
        end_date=end_date
    )




from typing import Optional
from datetime import date

@router.get(
    "/item-sold",
    response_model=ItemSoldResponse
)
def list_item_sold(
    start_date: date,
    end_date: date,
    invoice_no: Optional[int] = None,
    product_id: Optional[int] = None,
    product_name: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin"])
    )
):
    return service.list_item_sold(
        db=db,
        start_date=start_date,
        end_date=end_date,
        invoice_no=invoice_no,
        product_id=product_id,
        product_name=product_name,
        skip=skip,
        limit=limit
    )





@router.put("/{invoice_no}", response_model=schemas.SaleOut)
def update_sale_header(
    invoice_no: int,
    sale_update: schemas.SaleUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin"])
    )
):
    """
    Update sale header information.
    Totals and balance are recalculated automatically (net_amount considered).
    """
    return service.update_sale(db, invoice_no, sale_update)



@router.get("/report/analysis", response_model=schemas.SaleAnalysisOut)
def sales_analysis(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    product_id: Optional[int] = None,   # ✅ NEW
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin"])
    )
):
    return service.sales_analysis(
        db=db,
        start_date=start_date,
        end_date=end_date,
        product_id=product_id,   # ✅ PASS TO SERVICE
    )




@router.put(
    "/{invoice_no}/items",
    response_model=schemas.SaleItemOut
)
def update_sale_item(
    invoice_no: int,
    item_update: schemas.SaleItemUpdate,  # contains product_id, quantity, price, etc.
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin"])
    )
):
    return service.update_sale_item(
        db,
        invoice_no,
        item_update
    )



from sqlalchemy.orm import joinedload

@router.get("/receipt/{invoice_no}", response_model=schemas.SaleOut2)
def get_sale_invoice_reprint(
    invoice_no: int,
    db: Session = Depends(get_db)
):
    # 1️⃣ Fetch sale WITH items + product
    sale = (
        db.query(sales_models.Sale)
        .options(
            joinedload(sales_models.Sale.items)
                .joinedload(sales_models.SaleItem.product),
            joinedload(sales_models.Sale.payments)
        )
        .filter(sales_models.Sale.invoice_no == invoice_no)
        .first()
    )

    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    # 2️⃣ Recalculate totals from NET AMOUNTS
    total_amount = sum((item.net_amount or 0) for item in sale.items)

    payments = sale.payments or []
    total_paid = sum(float(p.amount_paid or 0) for p in payments)
    balance_due = total_amount - total_paid

    # 3️⃣ Payment status logic
    if total_paid == 0:
        payment_status = "pending"
    elif balance_due > 0:
        payment_status = "part_paid"
    else:
        payment_status = "completed"

    # 4️⃣ Return receipt (discount-aware)
    return schemas.SaleOut2(
        id=sale.id,
        invoice_no=sale.invoice_no,
        invoice_date=sale.invoice_date,
        customer_name=sale.customer_name or "Walk-in",
        customer_phone=getattr(sale, "customer_phone", None),
        ref_no=sale.ref_no,
        total_amount=total_amount,
        total_paid=total_paid,
        balance_due=balance_due,
        payment_status=payment_status,
        sold_at=sale.sold_at,
        items=[
            schemas.SaleItemOut2(
                id=item.id,
                sale_invoice_no=item.sale_invoice_no,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                quantity=item.quantity,
                selling_price=item.selling_price,
                gross_amount=item.gross_amount,
                discount=item.discount,
                net_amount=item.net_amount
            )
            for item in (sale.items or [])
        ]
    )




@router.delete("/{invoice_no}")
def delete_sale(
    invoice_no: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin"]))
):
    # 1️⃣ Check if there are payments tied to this sale
    from app.payments import service as payment_service

    payments = payment_service.list_payments_by_sale(db, invoice_no)
    if payments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete sale: payments exist. Please delete the payment(s) first."
        )

    # 2️⃣ Delete the sale
    deleted = service.delete_sale(db, invoice_no)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Sale not found"
        )

    return {"message": "Sale deleted successfully"}




@router.delete("/clear/all", status_code=status.HTTP_200_OK)
def delete_all_sales(
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin"]))
):
    """
    Delete ALL sales records.
    Admin only.
    """
    return service.delete_all_sales(db)
