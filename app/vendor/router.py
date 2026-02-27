from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.vendor import schemas, service

from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema

router = APIRouter()

@router.post("/", response_model=schemas.VendorOut)
def create_vendor(
    vendor: schemas.VendorCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin","super_admin"]))
):
    # Admin must have a business
    if "admin" in current_user.roles and not current_user.business_id:
        raise HTTPException(
            status_code=400,
            detail="Current user does not belong to any business"
        )

    # Prepare vendor data from client
    vendor_data = vendor.dict(exclude_unset=True)

    # 🔑 Force the business_id from current_user for admins
    if "admin" in current_user.roles:
        vendor_data["business_id"] = current_user.business_id

    # 🔑 Super admin must provide a business_id (optional)
    elif "super_admin" in current_user.roles:
        if not vendor_data.get("business_id"):
            raise HTTPException(
                status_code=400,
                detail="Super admin must specify a business_id"
            )

    # Create vendor
    return service.create_vendor(db, schemas.VendorCreate(**vendor_data))




@router.get("/simple", response_model=list[schemas.VendorOut])
def list_vendors_simple(
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["user", "admin", "super_admin"]))
):
    """
    Simple list of vendors for dropdowns.

    - Users/Admins → vendors of their business only
    - Super admin → all vendors
    """
    return service.get_all_vendors_simple(db, current_user)


@router.get("/{vendor_id}", response_model=schemas.VendorOut)
def read_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["user", "admin", "super_admin"]))
):
    vendor = service.get_vendor(db, vendor_id, current_user)

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    return vendor



@router.get("/", response_model=list[schemas.VendorOut])
def list_vendors(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["user","admin","super_admin"]))
):
    """
    List vendors:

    - Users/Admins: only vendors of their business
    - Super admin: all vendors
    """
    return service.get_vendors(db, current_user, skip, limit)




@router.put("/{vendor_id}", response_model=schemas.VendorOut)
def update_vendor(
    vendor_id: int,
    vendor_update: schemas.VendorUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["user", "admin", "super_admin"]))
):
    vendor = service.update_vendor(db, vendor_id, vendor_update, current_user)

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    return vendor




@router.delete("/{vendor_id}")
def delete_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin", "super_admin"]))
):
    result = service.delete_vendor(db, vendor_id, current_user)

    if not result:
        raise HTTPException(status_code=404, detail="Vendor not found")

    return result
