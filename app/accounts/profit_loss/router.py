from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Dict, Any

from app.database import get_db
from . import service


# app/reports/router.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Optional

from app.accounts.profit_loss import service
from app.users.schemas import UserDisplaySchema
from app.users.permissions import role_required
from app.accounts.profit_loss.schemas import ProfitLossResponse

router = APIRouter()


@router.get("/profit-loss", response_model=ProfitLossResponse)
def get_profit_loss(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD) – inclusive"),
    business_id: Optional[int] = Query(
        None,
        description="Filter by specific business (super admin only)"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    )
):
   
    return service.get_profit_and_loss(
        db=db,
        current_user=current_user,
        start_date=start_date,
        end_date=end_date,
        business_id=business_id
    )




