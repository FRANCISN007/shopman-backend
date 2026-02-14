from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.vendor import schemas, service

from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema

router = APIRouter()

@router.post("/", response_model=schemas.VendorOut)
def create_vendor(vendor: schemas.VendorCreate, db: Session = Depends(get_db)):
    return service.create_vendor(db, vendor)

@router.get("/simple", response_model=list[schemas.VendorOut])
def list_vendors_simple(db: Session = Depends(get_db)):
    """
    Simple list of vendors for dropdowns.
    Returns all vendors with id and business_name (or name).
    """
    vendors = service.get_all_vendors_simple(db)
    return vendors


@router.get("/{vendor_id}", response_model=schemas.VendorOut)
def read_vendor(vendor_id: int, db: Session = Depends(get_db)):
    vendor = service.get_vendor(db, vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor

@router.get("/", response_model=list[schemas.VendorOut])
def list_vendors(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return service.get_vendors(db, skip, limit)




@router.put("/{vendor_id}", response_model=schemas.VendorOut)
def update_vendor(vendor_id: int, vendor_update: schemas.VendorUpdate, db: Session = Depends(get_db)):
    vendor = service.update_vendor(db, vendor_id, vendor_update)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor

@router.delete("/{vendor_id}")
def delete_vendor(vendor_id: int, 
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin","manager"]))
    
):
    result = service.delete_vendor(db, vendor_id)
    if not result:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return result
