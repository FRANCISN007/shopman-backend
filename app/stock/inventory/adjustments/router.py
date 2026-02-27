from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy.exc import IntegrityError


from app.database import get_db
from . import schemas, service
from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema

from typing import List, Optional
from datetime import date

router = APIRouter()


@router.post("/", response_model=schemas.StockAdjustmentOut, status_code=201)
def create_adjustment(
    adjustment: schemas.StockAdjustmentCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Create a stock adjustment (+ve = add stock, -ve = remove stock).
    
    - Regular users → only products in their own business
    - Super admin → any product
    - Prevents negative stock
    """
    created = service.create_adjustment(
        db=db,
        adjustment=adjustment,
        current_user=current_user
    )

    if not created:
        raise HTTPException(
            status_code=404,
            detail="Product or inventory not found or does not belong to your business"
        )

    return created




@router.get("/", response_model=List[schemas.StockAdjustmentOut])
def list_adjustments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
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
    List stock adjustments with tenant isolation and filters.
    
    - Regular users → only adjustments from their own business
    - Super admin → all adjustments or filtered by ?business_id=
    - Includes product_name and adjusted_by_name
    """
    adjustments = service.list_adjustments(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        business_id=business_id
    )

    return adjustments




@router.delete("/{adjustment_id}", status_code=status.HTTP_200_OK)
def delete_adjustment(
    adjustment_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    )
):
    """
    Delete (reverse) a stock adjustment and restore inventory.
    
    - Regular users → only adjustments in their own business
    - Super admin → any adjustment
    - Reverses the adjustment effect on stock
    - Prevents negative stock after reversal
    """
    deleted = service.delete_adjustment(
        db=db,
        adjustment_id=adjustment_id,
        current_user=current_user
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Stock adjustment {adjustment_id} not found "
                   f"or does not belong to your business"
        )

    return {"message": "Stock adjustment deleted successfully and inventory restored"}