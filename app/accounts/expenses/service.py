from sqlalchemy.orm import Session
from fastapi import HTTPException

from sqlalchemy.orm import joinedload

from sqlalchemy import func

from datetime import datetime, timedelta
from sqlalchemy import func


from datetime import date
from typing import Optional


from . import models, schemas


# =========================
# Helper: payment validation
# =========================
def validate_payment_method(payment_method: str, bank_id: int | None):
    method = payment_method.lower()

    if method == "cash" and bank_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Bank must NOT be selected for cash payment"
        )

    if method in ["transfer", "pos"] and bank_id is None:
        raise HTTPException(
            status_code=400,
            detail="Bank is required for transfer or POS payment"
        )


# =========================
# Helper: serialize expense
# =========================
def serialize_expense(expense: models.Expense):
    return {
        "id": expense.id,
        "ref_no": expense.ref_no,
        "vendor_id": expense.vendor_id,
        "vendor_name": (
            expense.vendor.business_name
            if expense.vendor and expense.vendor.business_name
            else expense.vendor.name
            if expense.vendor
            else None
        ),
        "account_type": expense.account_type,
        "description": expense.description,
        "amount": expense.amount,
        "payment_method": expense.payment_method,

        "bank_id": expense.bank_id,
        "bank_name": expense.bank.name if expense.bank else None,

        "expense_date": expense.expense_date,
        "status": expense.status,
        "is_active": expense.is_active,
        "created_at": expense.created_at,
        "created_by": expense.created_by,

        # ✅ FIXED
        "created_by_username": (
            expense.creator.username
            if expense.creator
            else None
        ),
    }





# =========================
# Create Expense
# =========================
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

def create_expense(
    db: Session,
    expense: schemas.ExpenseCreate,
    user_id: int
):
    # ✅ Enforce cash / bank rules
    validate_payment_method(expense.payment_method, expense.bank_id)

    new_expense = models.Expense(
        ref_no=expense.ref_no,
        vendor_id=expense.vendor_id,
        account_type=expense.account_type,
        description=expense.description,
        amount=expense.amount,
        payment_method=expense.payment_method,
        bank_id=expense.bank_id,
        expense_date=expense.expense_date,
        created_by=user_id
    )

    try:
        db.add(new_expense)
        db.commit()
        db.refresh(new_expense)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reference number already exists"
        )

    return serialize_expense(new_expense)


# =========================
# List Expenses
# =========================

def list_expenses(
    db: Session,
    start_date: str | None = None,
    end_date: str | None = None,
    account_type: str | None = None,
):
    query = db.query(models.Expense).filter(models.Expense.is_active == True)

    # =========================
    # DATE FILTER (FIXED)
    # =========================
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(models.Expense.expense_date >= start_dt)

    if end_date:
        # Move to next day midnight, then use <
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(models.Expense.expense_date < end_dt)

    # =========================
    # ACCOUNT TYPE FILTER
    # =========================
    if account_type:
        query = query.filter(
            func.lower(func.trim(models.Expense.account_type))
            == func.lower(account_type.strip())
        )

    expenses = (
        query
        .order_by(models.Expense.expense_date.desc())
        .all()
    )

    total_expenses = sum(exp.amount for exp in expenses)

    return {
        "total_expenses": total_expenses,
        "expenses": [serialize_expense(exp) for exp in expenses],
    }


# =========================
# Get Expense by ID
# =========================
def get_expense_by_id(db: Session, expense_id: int):
    expense = (
        db.query(models.Expense)
        .filter(
            models.Expense.id == expense_id,
            models.Expense.is_active == True
        )
        .first()
    )

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    return serialize_expense(expense)


# =========================
# Update Expense
# =========================
def update_expense(
    db: Session,
    expense_id: int,
    expense_data: schemas.ExpenseUpdate
):
    expense = (
        db.query(models.Expense)
        .filter(
            models.Expense.id == expense_id,
            models.Expense.is_active == True
        )
        .first()
    )

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    data = expense_data.dict(exclude_unset=True)

    # ===============================
    # RESOLVE FINAL VALUES
    # ===============================
    payment_method = data.get("payment_method", expense.payment_method)
    bank_id = data.get("bank_id", expense.bank_id)

    validate_payment_method(payment_method, bank_id)

    # ===============================
    # EXPLICIT FIELD UPDATES (SAFE)
    # ===============================
    if "ref_no" in data:
        expense.ref_no = data["ref_no"]

    if "vendor_id" in data:
        expense.vendor_id = data["vendor_id"]

    if "account_type" in data:
        expense.account_type = data["account_type"]  # ✅ FIXED

    if "description" in data:
        expense.description = data["description"]

    if "amount" in data:
        expense.amount = data["amount"]

    if "payment_method" in data:
        expense.payment_method = data["payment_method"]

    if "bank_id" in data:
        expense.bank_id = data["bank_id"]

    if "expense_date" in data:
        expense.expense_date = data["expense_date"]

    if "status" in data:
        expense.status = data["status"]

    db.commit()
    db.refresh(expense)

    return serialize_expense(expense)



# =========================
# Delete Expense
# =========================
def delete_expense(db: Session, expense_id: int):
    expense = db.query(models.Expense).filter(
        models.Expense.id == expense_id,
        models.Expense.is_active == True
    ).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    expense.is_active = False
    db.commit()

    return {
        "id": expense_id,
        "detail": "Expense successfully deleted"
    }
