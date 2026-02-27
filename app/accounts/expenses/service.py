from sqlalchemy.orm import Session
from fastapi import HTTPException

from sqlalchemy.orm import joinedload

from sqlalchemy import func

from datetime import datetime, timedelta
from sqlalchemy import func
from datetime import datetime, date, time
from typing import Optional, Dict, Any


from datetime import date
from typing import Optional
from . import models, schemas

from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema
from app.vendor import models as vendor_models
from app.bank import models as bank_models






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
    current_user: UserDisplaySchema
) -> schemas.ExpenseOut:
    """
    Tenant-safe expense creation.
    Validates vendor/bank ownership, payment rules, and business context.
    Auto-sets status to 'paid' for cash, pos, or transfer payments.
    """
    # 1. Determine target business_id
    if "super_admin" in current_user.roles:
        # Super admin: derive from vendor
        vendor = db.query(vendor_models.Vendor).filter(
            vendor_models.Vendor.id == expense.vendor_id
        ).first()
        if not vendor:
            raise HTTPException(404, "Vendor not found")
        target_business_id = vendor.business_id
    else:
        if not current_user.business_id:
            raise HTTPException(403, "User does not belong to any business")
        target_business_id = current_user.business_id

    # 2. Validate vendor belongs to business
    vendor = db.query(vendor_models.Vendor).filter(
        vendor_models.Vendor.id == expense.vendor_id,
        vendor_models.Vendor.business_id == target_business_id
    ).first()
    if not vendor:
        raise HTTPException(
            404,
            f"Vendor {expense.vendor_id} not found or does not belong to this business"
        )

    # 3. Validate payment method & bank rules
    method = expense.payment_method.lower()

    if method == "cash" and expense.bank_id is not None:
        raise HTTPException(400, "Bank must NOT be selected for cash payments")

    if method in ["transfer", "pos"] and expense.bank_id is None:
        raise HTTPException(400, f"Bank is required for {method} payments")

    # Validate bank belongs to same business
    bank_name = None
    if expense.bank_id:
        bank = db.query(bank_models.Bank).filter(
            bank_models.Bank.id == expense.bank_id,
            bank_models.Bank.business_id == target_business_id
        ).first()
        if not bank:
            raise HTTPException(
                404,
                f"Bank {expense.bank_id} not found or does not belong to this business"
            )
        bank_name = bank.name

    # 4. Auto-determine initial status
    # Cash, POS, Transfer → all treated as immediately paid
    if method in ["cash", "pos", "transfer"]:
        initial_status = "paid"
    else:
        initial_status = "pending"

    # 5. Create expense record
    new_expense = models.Expense(
        business_id=target_business_id,
        vendor_id=expense.vendor_id,
        ref_no=expense.ref_no,
        account_type=expense.account_type,
        description=expense.description,
        amount=float(expense.amount),
        payment_method=expense.payment_method,
        bank_id=expense.bank_id,
        expense_date=expense.expense_date,
        status=initial_status,
        is_active=True,
        created_by=current_user.id
    )

    db.add(new_expense)

    try:
        db.commit()
        db.refresh(new_expense, attribute_names=["vendor", "bank", "creator"])

        # Enrich response
        return schemas.ExpenseOut(
            id=new_expense.id,
            business_id=new_expense.business_id,
            vendor_id=new_expense.vendor_id,
            ref_no=new_expense.ref_no,
            account_type=new_expense.account_type,
            description=new_expense.description,
            amount=float(new_expense.amount),
            payment_method=new_expense.payment_method,
            bank_id=new_expense.bank_id,
            expense_date=new_expense.expense_date,
            status=new_expense.status,  # will be "paid" for cash/pos/transfer
            is_active=new_expense.is_active,
            created_at=new_expense.created_at,
            created_by=new_expense.created_by,
            created_by_username=current_user.username if current_user else None,
            bank_name=bank_name,
            vendor_name=vendor.business_name if vendor else None
        )

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e.orig)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create expense: {str(e)}")
    




from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any
from sqlalchemy import func, desc

LAGOS_TZ = ZoneInfo("Africa/Lagos")


from sqlalchemy import func, desc, cast, Date




def list_expenses(
    db: Session,
    current_user: UserDisplaySchema,
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_type: Optional[str] = None,
    business_id: Optional[int] = None
) -> Dict[str, Any]:

    # ─── 1. Base query ───────────────────────────────────────────────
    query = (
        db.query(models.Expense)
        .options(
            joinedload(models.Expense.vendor),
            joinedload(models.Expense.bank),
            joinedload(models.Expense.creator)
        )
        .filter(models.Expense.is_active == True)
    )

    # ─── 2. Tenant isolation ─────────────────────────────────────────
    if "super_admin" in current_user.roles:
        if business_id is not None:
            query = query.filter(models.Expense.business_id == business_id)
    else:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.Expense.business_id == current_user.business_id)

    # ─── 3. Date filters (use plain date, not tz-aware datetime) ─────
    if start_date:
        query = query.filter(cast(models.Expense.expense_date, Date) >= start_date)
    if end_date:
        query = query.filter(cast(models.Expense.expense_date, Date) <= end_date)

    # ─── 4. Account type filter ──────────────────────────────────────
    if account_type:
        query = query.filter(
            func.lower(func.trim(models.Expense.account_type)) == account_type.lower().strip()
        )

    # ─── 5. Total expenses safely ────────────────────────────────────
    total_query = db.query(func.coalesce(func.sum(models.Expense.amount), 0.0)) \
        .filter(models.Expense.is_active == True)

    if start_date:
        total_query = total_query.filter(cast(models.Expense.expense_date, Date) >= start_date)
    if end_date:
        total_query = total_query.filter(cast(models.Expense.expense_date, Date) <= end_date)
    if business_id:
        total_query = total_query.filter(models.Expense.business_id == business_id)

    total_expenses = total_query.scalar() or 0.0

    # ─── 6. Fetch paginated results with ordering ────────────────────
    expenses = (
        query
        .order_by(desc(models.Expense.expense_date), desc(models.Expense.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )

    # ─── 7. Enrich results for display ───────────────────────────────
    enriched_expenses = []
    for exp in expenses:
        enriched_expenses.append(
            schemas.ExpenseOut(
                id=exp.id,
                business_id=exp.business_id,
                vendor_id=exp.vendor_id,
                ref_no=exp.ref_no,
                account_type=exp.account_type,
                description=exp.description,
                amount=float(exp.amount),
                payment_method=exp.payment_method,
                bank_id=exp.bank_id,
                expense_date=exp.expense_date.astimezone(LAGOS_TZ) if exp.expense_date else None,
                status=exp.status,
                is_active=exp.is_active,
                created_at=exp.created_at.astimezone(LAGOS_TZ) if exp.created_at else None,
                created_by=exp.created_by,
                created_by_username=exp.creator.username if exp.creator else None,
                bank_name=exp.bank.name if exp.bank else None,
                vendor_name=exp.vendor.business_name if exp.vendor else None
            )
        )

    # ─── 8. Return response ──────────────────────────────────────────
    return {
        "total_expenses": float(total_expenses),
        "expenses": enriched_expenses,
        "count": len(enriched_expenses)
    }




def get_expense_by_id(
    db: Session,
    expense_id: int,
    current_user: UserDisplaySchema
) -> Optional[schemas.ExpenseOut]:
    """
    Tenant-safe retrieval of a single expense.
    Enriches with vendor_name, bank_name, created_by_username.
    Returns None if not found or unauthorized.
    """
    # 1. Base query with eager loading
    query = (
        db.query(models.Expense)
        .options(
            joinedload(models.Expense.vendor),
            joinedload(models.Expense.bank),
            joinedload(models.Expense.creator)
        )
        .filter(models.Expense.id == expense_id)
        .filter(models.Expense.is_active == True)
    )

    # 2. Tenant isolation
    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(403, "Current user does not belong to any business")
        query = query.filter(models.Expense.business_id == current_user.business_id)

    # 3. Fetch expense
    expense = query.first()

    if not expense:
        return None

    # 4. Enrich and return as Pydantic model
    return schemas.ExpenseOut(
        id=expense.id,
        business_id=expense.business_id,
        vendor_id=expense.vendor_id,
        ref_no=expense.ref_no,
        account_type=expense.account_type,
        description=expense.description,
        amount=float(expense.amount),
        payment_method=expense.payment_method,
        bank_id=expense.bank_id,
        expense_date=expense.expense_date,
        status=expense.status,
        is_active=expense.is_active,
        created_at=expense.created_at,
        created_by=expense.created_by,
        created_by_username=expense.creator.username if expense.creator else None,
        bank_name=expense.bank.name if expense.bank else None,
        vendor_name=expense.vendor.business_name if expense.vendor else None
    )

def update_expense(
    db: Session,
    expense_id: int,
    expense_update: schemas.ExpenseUpdate,
    current_user: UserDisplaySchema
) -> Optional[schemas.ExpenseOut]:
    """
    Tenant-safe update of an expense.
    Validates ownership, re-validates payment rules, and business context.
    """
    # 1. Fetch expense with tenant isolation + eager load relations
    expense_query = db.query(models.Expense).options(
        joinedload(models.Expense.vendor),
        joinedload(models.Expense.bank),
        joinedload(models.Expense.creator)
    )

    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(403, "Current user does not belong to any business")
        expense_query = expense_query.filter(
            models.Expense.business_id == current_user.business_id
        )

    expense = expense_query.filter(
        models.Expense.id == expense_id,
        models.Expense.is_active == True
    ).first()

    if not expense:
        return None

    # 2. Apply updates (only allowed fields)
    update_data = expense_update.dict(exclude_unset=True)

    # Prevent changing immutable fields
    forbidden = {"id", "business_id", "created_by", "created_at"}
    for field in forbidden:
        if field in update_data:
            raise HTTPException(400, f"Cannot update field '{field}'")

    for field, value in update_data.items():
        setattr(expense, field, value)

    # 3. Re-validate payment method & bank after update
    final_method = update_data.get("payment_method", expense.payment_method)
    final_bank_id = update_data.get("bank_id", expense.bank_id)

    validate_payment_method(final_method, final_bank_id)

    # Re-validate bank if changed
    bank_name = expense.bank.name if expense.bank else None
    if "bank_id" in update_data and update_data["bank_id"] != expense.bank_id:
        if update_data["bank_id"]:
            bank = db.query(bank_models.Bank).filter(
                bank_models.Bank.id == update_data["bank_id"],
                bank_models.Bank.business_id == expense.business_id
            ).first()
            if not bank:
                raise HTTPException(
                    404,
                    f"Bank {update_data['bank_id']} not found or does not belong to this business"
                )
            bank_name = bank.name

    # Re-validate vendor if changed
    vendor_name = expense.vendor.business_name if expense.vendor else None
    if "vendor_id" in update_data and update_data["vendor_id"] != expense.vendor_id:
        vendor = db.query(vendor_models.Vendor).filter(
            vendor_models.Vendor.id == update_data["vendor_id"],
            vendor_models.Vendor.business_id == expense.business_id
        ).first()
        if not vendor:
            raise HTTPException(
                404,
                f"Vendor {update_data['vendor_id']} not found or does not belong to this business"
            )
        vendor_name = vendor.business_name

    # 4. Commit & refresh
    try:
        db.commit()
        db.refresh(expense, attribute_names=["vendor", "bank", "creator"])

        # Build enriched response
        return schemas.ExpenseOut(
            id=expense.id,
            business_id=expense.business_id,
            vendor_id=expense.vendor_id,
            ref_no=expense.ref_no,
            account_type=expense.account_type,
            description=expense.description,
            amount=float(expense.amount),
            payment_method=expense.payment_method,
            bank_id=expense.bank_id,
            expense_date=expense.expense_date,
            status=expense.status,
            is_active=expense.is_active,
            created_at=expense.created_at,
            created_by=expense.created_by,
            created_by_username=expense.creator.username if expense.creator else None,
            bank_name=bank_name,
            vendor_name=vendor_name
        )

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e.orig)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update expense: {str(e)}")


def delete_expense(
    db: Session,
    expense_id: int,
    current_user: UserDisplaySchema
) -> bool:
    """
    Tenant-safe soft deletion of an expense.
    Sets is_active = False and preserves history.
    Returns True if deleted, False if not found/unauthorized.
    """
    # 1. Fetch expense with tenant isolation + eager load (optional but safe)
    expense_query = db.query(models.Expense).options(
        joinedload(models.Expense.vendor),
        joinedload(models.Expense.bank),
        joinedload(models.Expense.creator)
    )

    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        expense_query = expense_query.filter(
            models.Expense.business_id == current_user.business_id
        )

    expense = expense_query.filter(
        models.Expense.id == expense_id,
        models.Expense.is_active == True
    ).first()

    if not expense:
        return False

    # 2. Soft delete - mark as inactive
    expense.is_active = False

    # Optional: update status to "voided" if you want clearer audit trail
    # expense.status = "voided"

    # 3. Commit atomically
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
            detail=f"Failed to deactivate expense: {str(e)}"
        )