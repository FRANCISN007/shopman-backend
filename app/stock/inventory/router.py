from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from typing import Optional
from fastapi import Depends

from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema
from app.users.auth import get_current_user





from app.database import get_db
from app.stock.inventory import schemas, service

router = APIRouter()




@router.get("/", response_model=dict)
def list_inventory(
    skip: int = 0,
    limit: int = 100,
    product_id: Optional[int] = None,
    product_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user","manager","admin","super_admin"])
    ),
):
    """
    SaaS-safe inventory list:
    - Admin/Manager/User → only their business inventory
    - Super admin → all businesses
    """
    return service.list_inventory(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        product_id=product_id,
        product_name=product_name,
    )
