from sqlalchemy.orm import Session
from app.vendor import models, schemas
from app.users.schemas import UserDisplaySchema


def create_vendor(db: Session, vendor: schemas.VendorCreate):
    new_vendor = models.Vendor(**vendor.dict())
    db.add(new_vendor)
    db.commit()
    db.refresh(new_vendor)
    return new_vendor


def get_all_vendors_simple(db: Session, current_user: UserDisplaySchema):
    """
    Return vendors for dropdowns with multi-tenant safety.
    """
    query = db.query(models.Vendor)

    # Users/Admins → restrict to their business
    if current_user.business_id is not None and "super_admin" not in current_user.roles:
        query = query.filter(models.Vendor.business_id == current_user.business_id)

    # Super admin → no filter

    return query.all()



def get_vendors_by_business(db: Session, business_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.Vendor)\
             .filter(models.Vendor.business_id == business_id)\
             .offset(skip).limit(limit).all()


def get_vendor(db: Session, vendor_id: int, current_user: UserDisplaySchema):
    query = db.query(models.Vendor).filter(models.Vendor.id == vendor_id)

    # Restrict non-super-admins to their business
    if current_user.business_id is not None and "super_admin" not in current_user.roles:
        query = query.filter(models.Vendor.business_id == current_user.business_id)

    return query.first()



def get_vendors(db: Session, current_user: UserDisplaySchema, skip: int = 0, limit: int = 100):
    query = db.query(models.Vendor)

    # Users/Admins: filter by current user's business if they have one
    if current_user.business_id is not None and "super_admin" not in current_user.roles:
        query = query.filter(models.Vendor.business_id == current_user.business_id)

    # Super admin: no filter, sees all

    return query.offset(skip).limit(limit).all()



def update_vendor(
    db: Session,
    vendor_id: int,
    vendor_update: schemas.VendorUpdate,
    current_user: UserDisplaySchema
):
    query = db.query(models.Vendor).filter(models.Vendor.id == vendor_id)

    # Restrict non-super-admins to their business
    if current_user.business_id is not None and "super_admin" not in current_user.roles:
        query = query.filter(models.Vendor.business_id == current_user.business_id)

    vendor = query.first()
    if not vendor:
        return None

    # Apply updates safely
    for key, value in vendor_update.dict(exclude_unset=True).items():
        setattr(vendor, key, value)

    db.commit()
    db.refresh(vendor)
    return vendor



def delete_vendor(db: Session, vendor_id: int, current_user: UserDisplaySchema):
    query = db.query(models.Vendor).filter(models.Vendor.id == vendor_id)

    # Restrict admins to their own business
    if "super_admin" not in current_user.roles:
        query = query.filter(models.Vendor.business_id == current_user.business_id)

    vendor = query.first()
    if not vendor:
        return None

    db.delete(vendor)
    db.commit()

    return {"message": "Vendor deleted successfully"}
