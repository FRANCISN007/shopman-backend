from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session


from datetime import date
from typing import List, Optional




from app.database import get_db
from . import schemas, service
from app.users.auth import get_current_user
from app.users.schemas import UserDisplaySchema

router = APIRouter()

# -------------------------
# Create Payment for Sale
# -------------------------
@router.post("/sale/{invoice_no}", response_model=schemas.PaymentOut)
def create_payment_for_sale(
    invoice_no: int,
    payment: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(get_current_user),
):
    return service.create_payment(
        db=db,
        invoice_no=invoice_no,
        payment=payment,
        user_id=current_user.id
    )

@router.get("/", response_model=List[schemas.PaymentOut])
def list_payments_endpoint(
    invoice_no: Optional[str] = Query(None, description="Filter by invoice number"),
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    status: Optional[str] = Query(None, description="Payment status: completed, part_paid, pending"),
    bank_id: Optional[int] = Query(None, description="Filter by bank ID"),
    payment_method: Optional[str] = Query(None, description="cash | transfer | pos"),  # ✅ NEW
    db: Session = Depends(get_db),
):
    return service.list_payments(
        db=db,
        invoice_no=invoice_no,
        start_date=start_date,
        end_date=end_date,
        status=status,
        bank_id=bank_id,
        payment_method=payment_method,  # ✅ NEW
    )


# -------------------------
# List payments by sale
# -------------------------
@router.get("/sale/{invoice_no}", response_model=List[schemas.PaymentOut])
def list_payments_by_sale(
    invoice_no: int,
    db: Session = Depends(get_db),
):
    return service.list_payments_by_sale(db, invoice_no)




@router.put("/{payment_id}", response_model=schemas.PaymentOut)
def update_payment(
    payment_id: int,
    payment_update: schemas.PaymentUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(get_current_user),
):
    return service.update_payment(
        db=db,
        payment_id=payment_id,
        payment_update=payment_update,
        user_id=current_user.id
    )



# -------------------------
# Delete a payment
# -------------------------
@router.delete("/{payment_id}")
def delete_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(get_current_user),
):
    return service.delete_payment(db, payment_id)
