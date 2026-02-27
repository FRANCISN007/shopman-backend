from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List,  Dict,  Optional

from datetime import date

from app.database import get_db
from . import schemas, service

from app.users.auth import get_current_user
from app.users import schemas as user_schemas

from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema



router = APIRouter()


@router.post("/", response_model=schemas.ExpenseOut, status_code=201)
def create_expense(
    expense: schemas.ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Create a new expense record.
    
    - Regular users → only for their own business
    - Super admin → for any business
    - Validates payment method & bank requirements
    """
    created = service.create_expense(
        db=db,
        expense=expense,
        current_user=current_user
    )

    if not created:
        raise HTTPException(
            status_code=404,
            detail="Vendor or bank not found or does not belong to your business"
        )

    return created


@router.get("/", response_model=schemas.ExpenseListResponse)
def list_expenses(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Max items per page"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD) - inclusive"),
    account_type: Optional[str] = Query(None, description="Filter by account type (case-insensitive)"),
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
    List expenses with tenant isolation, date range, and account type filter.
    
    - Regular users → only expenses from their own business
    - Super admin → all expenses or filtered by ?business_id=
    - Returns enriched list + total expenses summary
    """
    return service.list_expenses(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        account_type=account_type,
        business_id=business_id
    )



@router.get("/{expense_id}", response_model=schemas.ExpenseOut)
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Get details of a single expense by ID.
    
    - Regular users → only expenses from their own business
    - Super admin → any expense
    - Returns enriched data (vendor_name, bank_name, created_by_username)
    """
    expense_data = service.get_expense_by_id(
        db=db,
        expense_id=expense_id,
        current_user=current_user
    )

    if not expense_data:
        raise HTTPException(
            status_code=404,
            detail=f"Expense {expense_id} not found "
                   f"or does not belong to your business"
        )

    return expense_data



@router.put("/{expense_id}", response_model=schemas.ExpenseOut)
def update_expense(
    expense_id: int,
    expense_update: schemas.ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Update an existing expense record.
    
    - Regular users → only expenses in their own business
    - Super admin → any expense
    - Re-validates payment method & bank after update
    - Returns enriched ExpenseOut
    """
    updated = service.update_expense(
        db=db,
        expense_id=expense_id,
        expense_update=expense_update,
        current_user=current_user
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Expense {expense_id} not found "
                   f"or does not belong to your business"
        )

    return updated



@router.delete("/{expense_id}", status_code=status.HTTP_200_OK)
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Soft-delete (deactivate) an expense record.
    
    - Regular users → only expenses in their own business
    - Super admin → any expense
    - Sets is_active = False (soft delete)
    """
    deleted = service.delete_expense(
        db=db,
        expense_id=expense_id,
        current_user=current_user
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Expense {expense_id} not found "
                   f"or does not belong to your business"
        )

    return {
        "id": expense_id,
        "detail": "Expense successfully deactivated (soft delete)"
    }