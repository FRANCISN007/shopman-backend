from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List,  Dict,  Optional

from datetime import date

from app.database import get_db
from . import schemas, service

from app.users.auth import get_current_user
from app.users import schemas as user_schemas


router = APIRouter()


@router.post("/", response_model=schemas.ExpenseOut)
def create_expense(
    expense: schemas.ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(get_current_user)
):
    return service.create_expense(
        db,
        expense,
        user_id=current_user.id
    )



@router.get("/", response_model=dict)
def list_expenses(
    start_date: str | None = None,
    end_date: str | None = None,
    account_type: str | None = None,
    db: Session = Depends(get_db),
):
    return service.list_expenses(
        db,
        start_date=start_date,
        end_date=end_date,
        account_type=account_type,
    )


@router.get("/{expense_id}", response_model=schemas.ExpenseOut)
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
):
    return service.get_expense_by_id(db, expense_id)


@router.put("/{expense_id}", response_model=schemas.ExpenseOut)
def update_expense(
    expense_id: int,
    expense: schemas.ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),  # ✅ ADD THIS
):
    return service.update_expense(db, expense_id, expense)


@router.delete("/{expense_id}")
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
):
    return service.delete_expense(db, expense_id)
