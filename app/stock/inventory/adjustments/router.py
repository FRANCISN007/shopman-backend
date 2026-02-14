from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from . import schemas, service
from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema

from typing import List, Optional
from datetime import date

router = APIRouter()


@router.post("/", response_model=schemas.StockAdjustmentOut)
def create_adjustment(
    adjustment: schemas.StockAdjustmentCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin"]))
):
    """
    Admin-only endpoint to adjust stock.
    Positive quantity = increase stock
    Negative quantity = decrease stock
    """
    return service.create_adjustment(db, adjustment, current_user.id)




@router.get("/", response_model=List[schemas.StockAdjustmentListOut])
def list_adjustments(
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[date] = None,   # ✅ NEW
    end_date: Optional[date] = None,     # ✅ NEW
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin"])
    ),
):
    """
    List all stock adjustments with product name, username,
    and optional date filter
    """
    return service.list_adjustments(
        db=db,
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )



@router.delete("/{adjustment_id}", status_code=200)
def delete_adjustment(
    adjustment_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin"]))
):
    """
    Admin-only endpoint to delete a stock adjustment.
    This will revert its effect on inventory.
    """
    service.delete_adjustment(db, adjustment_id)
    return {"message": "Adjustment deleted successfully"}
