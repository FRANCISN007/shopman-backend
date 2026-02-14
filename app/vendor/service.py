from sqlalchemy.orm import Session
from app.vendor import models, schemas

def create_vendor(db: Session, vendor: schemas.VendorCreate):
    new_vendor = models.Vendor(**vendor.dict())
    db.add(new_vendor)
    db.commit()
    db.refresh(new_vendor)
    return new_vendor



def get_all_vendors_simple(db: Session):
    """
    Return all vendors for dropdowns
    """
    return db.query(models.Vendor).all()



def get_vendor(db: Session, vendor_id: int):
    return db.query(models.Vendor).filter(models.Vendor.id == vendor_id).first()

def get_vendors(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Vendor).offset(skip).limit(limit).all()



def update_vendor(db: Session, vendor_id: int, vendor_update: schemas.VendorUpdate):
    vendor = db.query(models.Vendor).filter(models.Vendor.id == vendor_id).first()
    if not vendor:
        return None
    for key, value in vendor_update.dict(exclude_unset=True).items():
        setattr(vendor, key, value)
    db.commit()
    db.refresh(vendor)
    return vendor

def delete_vendor(db: Session, vendor_id: int):
    vendor = db.query(models.Vendor).filter(models.Vendor.id == vendor_id).first()
    if not vendor:
        return None
    db.delete(vendor)
    db.commit()
    return {"message": "Vendor deleted successfully"}
