from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from sqlalchemy import cast, String

from . import models, schemas
from app.sales import models as sales_models
from app.bank import models as bank_models
from app.users import models as user_models
import uuid


from sqlalchemy import text


from datetime import datetime, date, time
from typing import Optional, List

from datetime import date
from sqlalchemy import func

from sqlalchemy.orm import joinedload




# -------------------------
# Create Payment
# -------------------------
import uuid

def create_payment(
    db: Session,
    invoice_no: int,
    payment: schemas.PaymentCreate,
    user_id: int
):
    # Fetch sale
    sale = db.query(sales_models.Sale).filter(sales_models.Sale.invoice_no == invoice_no).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    # Bank is required for non-cash payments
    if payment.payment_method != "cash" and not payment.bank_id:
        raise HTTPException(status_code=400, detail="Bank is required for non-cash payments")

    # Compute total amount already paid
    total_paid = sum(p.amount_paid for p in sale.payments)
    remaining_balance = sale.total_amount - total_paid

    # Prevent overpayment
    if payment.amount_paid > remaining_balance:
        raise HTTPException(status_code=400, detail=f"Payment exceeds balance due ({remaining_balance})")

    # Determine new balance and status
    new_balance_due = remaining_balance - payment.amount_paid
    if new_balance_due == sale.total_amount:
        status = "pending"
    elif new_balance_due > 0:
        status = "part_paid"
    else:
        status = "completed"

    # Force generate reference_no, ignore frontend input
    generated_reference_no = str(uuid.uuid4())

    # Create payment
    new_payment = models.Payment(
        sale_invoice_no=invoice_no,
        amount_paid=payment.amount_paid,
        
        payment_method=payment.payment_method,
        bank_id=payment.bank_id,
        reference_no=generated_reference_no,  # <-- ALWAYS use UUID
        payment_date=payment.payment_date,
        created_by=user_id,
        balance_due=new_balance_due,
        status=status
    )

    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)

    return new_payment

# -------------------------
# List all payments
# -------------------------








def list_payments(
    db: Session,
    invoice_no: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
    bank_id: int | None = None,
    payment_method: str | None = None,
):
    query = db.query(models.Payment).options(
        joinedload(models.Payment.sale),
        joinedload(models.Payment.user),
        joinedload(models.Payment.bank),
    )

    # ----------------- Invoice Filter -----------------
    if invoice_no:
        query = query.filter(
            cast(models.Payment.sale_invoice_no, String).ilike(f"%{invoice_no}%")
        )

    # ----------------- Date Filter -----------------
    if start_date:
        start_dt = datetime.combine(start_date, time.min)
        query = query.filter(models.Payment.created_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max)
        query = query.filter(models.Payment.created_at <= end_dt)

    # ----------------- Status Filter -----------------
    if status:
        query = query.filter(models.Payment.status == status.lower())

    # ----------------- Bank Filter -----------------
    if bank_id:
        query = query.filter(models.Payment.bank_id == bank_id)

    # ----------------- Payment Method Filter -----------------
    if payment_method:
        query = query.filter(models.Payment.payment_method.ilike(payment_method.lower()))

    payments = query.order_by(models.Payment.created_at.desc()).all()

    # ----------------- Attach extra info -----------------
    for p in payments:
        p.bank_name = p.bank.name if p.bank else None
        p.created_by_name = p.user.username if p.user else None
        p.total_amount = p.sale.total_amount if p.sale else None

        # ✅ NEW: attach customer name
        p.customer_name = p.sale.customer_name if p.sale else None

    return payments


# -------------------------
# List payments by sale
# -------------------------
def list_payments_by_sale(db: Session, invoice_no: int):
    return db.query(models.Payment).filter(models.Payment.sale_invoice_no == invoice_no).order_by(models.Payment.created_at.desc()).all()

# -------------------------
# Get single payment
# -------------------------
def get_payment(db: Session, payment_id: int):
    return db.query(models.Payment).filter(models.Payment.id == payment_id).first()



def update_payment(db: Session, payment_id: int, payment_update: schemas.PaymentUpdate, user_id: int):
    existing_payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not existing_payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    sale = db.query(sales_models.Sale).filter(sales_models.Sale.invoice_no == existing_payment.sale_invoice_no).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    # Update fields
    if payment_update.amount_paid is not None:
        existing_payment.amount_paid = payment_update.amount_paid
    
        
    if payment_update.payment_method is not None:
        existing_payment.payment_method = payment_update.payment_method
    if payment_update.bank_id is not None:
        existing_payment.bank_id = payment_update.bank_id
    if payment_update.payment_date is not None:
        existing_payment.payment_date = payment_update.payment_date

    # Recalculate balance and status
    total_paid = sum(p.amount_paid for p in sale.payments if p.id != payment_id) + existing_payment.amount_paid
    new_balance_due = sale.total_amount - total_paid
    existing_payment.balance_due = new_balance_due

    if new_balance_due == sale.total_amount:
        existing_payment.status = "pending"
    elif new_balance_due > 0:
        existing_payment.status = "part_paid"
    else:
        existing_payment.status = "completed"

    db.commit()
    db.refresh(existing_payment)

    # ✅ Populate the related fields
    bank_name = None
    if existing_payment.bank_id:
        bank = db.query(bank_models.Bank).filter(bank_models.Bank.id == existing_payment.bank_id).first()
        if bank:
            bank_name = bank.name

    created_by_name = None
    if existing_payment.created_by:
        user = db.query(user_models.User).filter(user_models.User.id == existing_payment.created_by).first()
        if user:
            created_by_name = user.username  # or user.username

    return schemas.PaymentOut(
        **existing_payment.__dict__,
        bank_name=bank_name,
        created_by_name=created_by_name,
        total_amount=sale.total_amount
    )



# -------------------------
# Delete payment
# -------------------------
def delete_payment(db: Session, payment_id: int):
    payment = get_payment(db, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    db.delete(payment)
    db.commit()

    return {
        "detail": "Payment deleted successfully"
    }
