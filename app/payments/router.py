from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session


from datetime import date
from typing import List, Optional

from app.database import get_db
from . import schemas, service
from app.users.auth import get_current_user
from app.users.schemas import UserDisplaySchema

from app.users.permissions import role_required

router = APIRouter()

@router.post(
    "/{invoice_no}/payments",
    response_model=schemas.PaymentOut,
    status_code=status.HTTP_201_CREATED
)
def create_payment_for_sale(
    invoice_no: int,
    payment: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Record a new payment for a sale.
    
    - Regular users: only payments for sales in their own business
    - Super admin: can record payment for any sale
    - Prevents over-payment
    - Automatically updates sale balance & status logic
    """
    created = service.create_payment(
        db=db,
        invoice_no=invoice_no,
        payment=payment,
        current_user=current_user
    )

    if not created:
        raise HTTPException(
            status_code=404,
            detail=f"Sale with invoice_no {invoice_no} not found "
                   f"or does not belong to your business"
        )

    return created




@router.get("/", response_model=List[schemas.PaymentOut])
def list_payments(
    invoice_no: Optional[str] = Query(None, description="Filter by invoice number (partial match)"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filter by status: pending, part_paid, completed"),
    bank_id: Optional[int] = Query(None, description="Filter by bank ID"),
    payment_method: Optional[str] = Query(None, description="Filter by method: cash, transfer, pos"),
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
    List payments with full tenant isolation and flexible filters.
    
    - Regular users → only payments from their own business
    - Super admin → all payments or filtered by ?business_id=
    """
    return service.list_payments(
        db=db,
        current_user=current_user,
        invoice_no=invoice_no,
        start_date=start_date,
        end_date=end_date,
        status=status,
        bank_id=bank_id,
        payment_method=payment_method,
        business_id=business_id
    )



@router.get(
    "/{invoice_no}/payments",
    response_model=List[schemas.PaymentOut],
    status_code=status.HTTP_200_OK
)
def list_payments_by_sale(
    invoice_no: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    List all payments for a specific sale (by invoice_no).
    
    - Regular users → only payments for sales in their own business
    - Super admin → payments for any sale
    """
    payments = service.list_payments_by_sale(
        db=db,
        invoice_no=invoice_no,
        current_user=current_user
    )

    if payments is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sale with invoice_no {invoice_no} not found "
                   f"or does not belong to your business"
        )

    return payments




@router.put(
    "/{payment_id}",
    response_model=schemas.PaymentOut,
    status_code=status.HTTP_200_OK
)
def update_payment(
    payment_id: int,
    payment_update: schemas.PaymentUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Update an existing payment (amount, method, bank, date).
    
    - Regular users → only payments in their own business
    - Super admin → any payment
    - Prevents over-payment after update
    - Recalculates sale balance & status
    """
    updated = service.update_payment(
        db=db,
        payment_id=payment_id,
        payment_update=payment_update,
        current_user=current_user
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Payment {payment_id} not found "
                   f"or does not belong to your business"
        )

    return updated


@router.delete("/{payment_id}")
def delete_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Delete (void) a payment record and restore sale balance/status.
    
    - Regular users → only payments in their own business
    - Super admin → any payment
    - Recalculates sale total_paid, balance_due, and payment_status
    """
    deleted = service.delete_payment(
        db=db,
        payment_id=payment_id,
        current_user=current_user
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Payment {payment_id} not found "
                   f"or does not belong to your business"
        )

    return {"message": "Payment deleted successfully"}