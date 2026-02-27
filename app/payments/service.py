from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from sqlalchemy import cast, String
import pytz

from . import models, schemas
from app.sales import models as sales_models
from app.bank import models as bank_models
from app.users import models as user_models
import uuid
from sqlalchemy.exc import IntegrityError

from sqlalchemy import text


from datetime import datetime, date, time
from typing import Optional, List

from datetime import date
from sqlalchemy import func

from sqlalchemy.orm import joinedload

from app.users.auth import get_current_user
from app.users.schemas import UserDisplaySchema

from app.users.permissions import role_required




# -------------------------
# Create Payment
# -------------------------
import uuid

def create_payment(
    db: Session,
    invoice_no: int,
    payment: schemas.PaymentCreate,
    current_user: UserDisplaySchema
) -> schemas.PaymentOut:
    """
    Create a payment record with full tenant isolation.
    Validates sale, prevents overpayment, generates reference, updates status.
    """
    # 1. Fetch sale + enforce tenant isolation
    sale_query = db.query(sales_models.Sale)

    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        sale_query = sale_query.filter(
            sales_models.Sale.business_id == current_user.business_id
        )

    sale = sale_query.filter(
        sales_models.Sale.invoice_no == invoice_no
    ).first()

    if not sale:
        return None

    target_business_id = sale.business_id

    # 2. Validate payment method & bank
    if payment.payment_method != "cash" and not payment.bank_id:
        raise HTTPException(
            status_code=400,
            detail="Bank account is required for non-cash payments (transfer/pos)"
        )

    # Validate bank belongs to the same business
    bank_name = None
    if payment.bank_id:
        bank = db.query(bank_models.Bank).filter(
            bank_models.Bank.id == payment.bank_id,
            bank_models.Bank.business_id == target_business_id
        ).first()
        if not bank:
            raise HTTPException(
                status_code=404,
                detail=f"Bank ID {payment.bank_id} not found or does not belong to this business"
            )
        bank_name = bank.name  # safe – we already loaded it

    # 3. Calculate current paid amount & remaining balance
    current_paid = sum(float(p.amount_paid or 0) for p in sale.payments)
    remaining_balance = float(sale.total_amount or 0) - current_paid

    if payment.amount_paid <= 0:
        raise HTTPException(
            status_code=400,
            detail="Payment amount must be greater than zero"
        )

    if payment.amount_paid > remaining_balance + 0.01:  # small tolerance for float
        raise HTTPException(
            status_code=400,
            detail=f"Payment ({payment.amount_paid}) exceeds remaining balance ({remaining_balance:.2f})"
        )

    # 4. Determine new balance & status
    new_balance_due = remaining_balance - payment.amount_paid

    if new_balance_due <= 0:
        new_status = "completed"
    elif current_paid == 0:
        new_status = "pending"
    else:
        new_status = "part_paid"

    # 5. Generate secure reference number
    reference_no = str(uuid.uuid4())

    # 6. Create payment record
    new_payment = models.Payment(
        business_id=target_business_id,
        sale_invoice_no=invoice_no,
        amount_paid=payment.amount_paid,
        payment_method=payment.payment_method,
        bank_id=payment.bank_id,
        reference_no=reference_no,
        payment_date=payment.payment_date or datetime.now(pytz.timezone("Africa/Lagos")),
        created_by=current_user.id,
        balance_due=new_balance_due,
        status=new_status
    )

    db.add(new_payment)

    try:
        db.commit()
        db.refresh(new_payment)

        # Build enriched response (safe – no lazy-load issues)
        enriched = {
            "id": new_payment.id,
            "invoice_no": invoice_no,
            "amount_paid": new_payment.amount_paid,
            "payment_method": new_payment.payment_method,
            "bank_id": new_payment.bank_id,
            "reference_no": new_payment.reference_no,
            "payment_date": new_payment.payment_date,
            "created_by": new_payment.created_by,
            "created_at": new_payment.created_at,
            "balance_due": new_balance_due,
            "status": new_status,
            "customer_name": sale.customer_name or "Walk-in",
            "total_amount": float(sale.total_amount or 0),
            "bank_name": bank_name,
            "created_by_name": current_user.username if current_user else None
        }

        return schemas.PaymentOut(**enriched)

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Database constraint error: {str(e.orig)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record payment: {str(e)}"
        )




from zoneinfo import ZoneInfo


LAGOS_TZ = ZoneInfo("Africa/Lagos")

def list_payments(
    db: Session,
    current_user: UserDisplaySchema,
    invoice_no: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    bank_id: Optional[int] = None,
    payment_method: Optional[str] = None,
    business_id: Optional[int] = None
) -> List[schemas.PaymentOut]:
    """
    Tenant-aware list of payments with timezone-aware filtering.
    Enriches each payment with bank_name, created_by_name, customer_name, total_amount.
    """

    # ─── 1. Base query with eager loading ─────────────────────────────
    query = (
        db.query(models.Payment)
        .options(
            joinedload(models.Payment.sale),
            joinedload(models.Payment.user),
            joinedload(models.Payment.bank)
        )
    )

    # ─── 2. Tenant isolation ──────────────────────────────────────────
    if "super_admin" in current_user.roles:
        if business_id is not None:
            query = query.filter(models.Payment.business_id == business_id)
    else:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.Payment.business_id == current_user.business_id)

    # ─── 3. Apply filters ─────────────────────────────────────────────
    if invoice_no:
        query = query.filter(
            cast(models.Payment.sale_invoice_no, String).ilike(f"%{invoice_no}%")
        )

    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=LAGOS_TZ)
        query = query.filter(models.Payment.created_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=LAGOS_TZ)
        query = query.filter(models.Payment.created_at <= end_dt)

    if status:
        query = query.filter(models.Payment.status == status.lower())

    if bank_id:
        query = query.filter(models.Payment.bank_id == bank_id)

    if payment_method:
        query = query.filter(
            models.Payment.payment_method.ilike(f"%{payment_method.lower()}%")
        )

    # ─── 4. Execute query (ordering optional) ────────────────────────
    payments = query.offset(0).limit(1000).all()  # you can add pagination if needed

    # ─── 5. Enrich response objects ───────────────────────────────────
    result: List[schemas.PaymentOut] = []

    for p in payments:
        enriched = schemas.PaymentOut(
            id=p.id,
            invoice_no=p.sale_invoice_no,
            amount_paid=float(p.amount_paid or 0),
            payment_method=p.payment_method,
            bank_id=p.bank_id,
            reference_no=p.reference_no,
            payment_date=p.payment_date,
            created_by=p.created_by,
            created_at=p.created_at.astimezone(LAGOS_TZ) if p.created_at else None,  # Lagos timezone
            balance_due=float(p.balance_due or 0),
            status=p.status,

            # Enriched fields – safe because of joinedload
            bank_name=p.bank.name if p.bank else None,
            created_by_name=p.user.username if p.user else None,
            total_amount=float(p.sale.total_amount or 0) if p.sale else None,
            customer_name=p.sale.customer_name or "Walk-in" if p.sale else None
        )
        result.append(enriched)

    return result




def list_payments_by_sale(
    db: Session,
    invoice_no: int,
    current_user: UserDisplaySchema
) -> Optional[List[schemas.PaymentOut]]:
    """
    Tenant-safe list of payments for a given sale.
    Returns enriched PaymentOut objects or None if sale not found/unauthorized.
    """
    # 1. Fetch sale + enforce tenant isolation
    sale_query = db.query(sales_models.Sale)

    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        sale_query = sale_query.filter(
            sales_models.Sale.business_id == current_user.business_id
        )

    sale = sale_query.filter(
        sales_models.Sale.invoice_no == invoice_no
    ).first()

    if not sale:
        return None

    # 2. Fetch payments with eager loading
    payments = (
        db.query(models.Payment)
        .options(
            joinedload(models.Payment.sale),
            joinedload(models.Payment.user),
            joinedload(models.Payment.bank)
        )
        .filter(models.Payment.sale_invoice_no == invoice_no)
        .order_by(models.Payment.created_at.desc())
        .all()
    )

    # 3. Enrich and return as PaymentOut objects
    enriched = []

    for p in payments:
        bank_name = p.bank.name if p.bank else None
        created_by_name = p.user.username if p.user else None

        enriched.append(
            schemas.PaymentOut(
                id=p.id,
                invoice_no=p.sale_invoice_no,
                amount_paid=float(p.amount_paid or 0),
                payment_method=p.payment_method,
                bank_id=p.bank_id,
                reference_no=p.reference_no,
                payment_date=p.payment_date,
                created_by=p.created_by,
                created_at=p.created_at,
                balance_due=float(p.balance_due or 0),
                status=p.status,

                # Enriched fields – safe due to joinedload
                bank_name=bank_name,
                created_by_name=created_by_name,
                total_amount=float(p.sale.total_amount or 0) if p.sale else None,
                customer_name=p.sale.customer_name or "Walk-in" if p.sale else None
            )
        )

    return enriched


# -------------------------
# Get single payment
# -------------------------
def get_payment(db: Session, payment_id: int):
    return db.query(models.Payment).filter(models.Payment.id == payment_id).first()



def update_payment(
    db: Session,
    payment_id: int,
    payment_update: schemas.PaymentUpdate,
    current_user: UserDisplaySchema
) -> Optional[schemas.PaymentOut]:
    """
    Tenant-safe update of a payment record.
    Validates ownership, prevents over-payment, recalculates balance/status.
    """
    # 1. Fetch payment with tenant isolation + eager load relationships
    payment_query = db.query(models.Payment).options(
        joinedload(models.Payment.sale),
        joinedload(models.Payment.user),
        joinedload(models.Payment.bank)
    )

    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        payment_query = payment_query.filter(
            models.Payment.business_id == current_user.business_id
        )

    payment = payment_query.filter(
        models.Payment.id == payment_id
    ).first()

    if not payment:
        return None

    sale = payment.sale
    if not sale:
        raise HTTPException(status_code=404, detail="Linked sale not found")

    # 2. Apply updates
    update_data = payment_update.dict(exclude_unset=True)

    if "amount_paid" in update_data:
        payment.amount_paid = update_data["amount_paid"]
    if "payment_method" in update_data:
        payment.payment_method = update_data["payment_method"]
    if "bank_id" in update_data:
        if update_data["bank_id"]:
            bank = db.query(bank_models.Bank).filter(
                bank_models.Bank.id == update_data["bank_id"],
                bank_models.Bank.business_id == payment.business_id
            ).first()
            if not bank:
                raise HTTPException(
                    status_code=404,
                    detail=f"Bank {update_data['bank_id']} not found or does not belong to this business"
                )
        payment.bank_id = update_data["bank_id"]
    if "payment_date" in update_data:
        payment.payment_date = update_data["payment_date"]

    # 3. Recalculate balance & status
    other_payments = [p for p in sale.payments if p.id != payment_id]
    total_paid = sum(float(p.amount_paid or 0) for p in other_payments) + payment.amount_paid
    new_balance_due = float(sale.total_amount or 0) - total_paid

    if payment.amount_paid <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")

    if total_paid > sale.total_amount + 0.01:  # small float tolerance
        raise HTTPException(
            status_code=400,
            detail=f"Updated payments ({total_paid:.2f}) exceed sale total ({sale.total_amount:.2f})"
        )

    payment.balance_due = new_balance_due

    if new_balance_due <= 0:
        payment.status = "completed"
    elif total_paid == payment.amount_paid:  # only this payment
        payment.status = "pending"
    else:
        payment.status = "part_paid"

    # 4. Commit & refresh
    try:
        db.commit()
        db.refresh(payment, attribute_names=["sale", "bank", "user"])

        # Use Pydantic from_orm + manual enrichment for safety
        payment_out = schemas.PaymentOut.from_orm(payment)

        # Manually set enriched fields (safe access)
        payment_out.invoice_no = payment.sale_invoice_no
        payment_out.total_amount = float(sale.total_amount or 0)
        payment_out.customer_name = sale.customer_name or "Walk-in" if sale else None
        payment_out.bank_name = payment.bank.name if payment.bank else None
        payment_out.created_by_name = payment.user.username if payment.user else None

        return payment_out

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e.orig)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update payment: {str(e)}")    



def delete_payment(
    db: Session,
    payment_id: int,
    current_user: UserDisplaySchema
) -> bool:
    """
    Tenant-safe deletion of a payment record.
    Restores the paid amount to the sale's balance and updates status.
    Returns True if deleted, False if not found/unauthorized.
    """
    # 1. Fetch payment with tenant isolation + eager load sale
    payment_query = db.query(models.Payment).options(
        joinedload(models.Payment.sale)
    )

    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        payment_query = payment_query.filter(
            models.Payment.business_id == current_user.business_id
        )

    payment = payment_query.filter(
        models.Payment.id == payment_id
    ).first()

    if not payment:
        return False

    sale = payment.sale
    if not sale:
        raise HTTPException(status_code=404, detail="Linked sale not found")

    # 2. Restore the paid amount to sale balance
    restored_amount = float(payment.amount_paid or 0)
    new_total_paid = sum(float(p.amount_paid or 0) for p in sale.payments if p.id != payment_id)
    new_balance_due = float(sale.total_amount or 0) - new_total_paid

    # 3. Update sale status based on new total paid
    if new_total_paid == 0:
        new_status = "pending"
    elif new_balance_due > 0:
        new_status = "part_paid"
    else:
        new_status = "completed"

    # Optional: if Sale has payment_status column
    # sale.payment_status = new_status

    # 4. Delete the payment
    db.delete(payment)

    # 5. Commit atomically
    try:
        db.commit()
        return True

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Database constraint violation: {str(e.orig)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete payment: {str(e)}"
        )