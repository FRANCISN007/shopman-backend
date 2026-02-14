from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from typing import Optional
from fastapi import Depends




from app.database import get_db
from app.stock.inventory import schemas, service

router = APIRouter()




@router.get("/", response_model=dict)  # Or create a proper Pydantic schema
def list_inventory(
    skip: int = 0,
    limit: int = 100,
    product_id: Optional[int] = None,
    product_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return service.list_inventory(
        db,
        skip=skip,
        limit=limit,
        product_id=product_id,
        product_name=product_name,
    )
