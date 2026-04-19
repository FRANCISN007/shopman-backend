# app/business/router.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from sqlalchemy import func
from app.users.auth import get_current_user
from app.users.schemas import UserDisplaySchema
from app.license import models as license_models


from app.database import get_db
from app.business import models, schemas
from app.users.permissions import role_required


from datetime import datetime
from zoneinfo import ZoneInfo





router = APIRouter()



LAGOS_TZ = ZoneInfo("Africa/Lagos")

now_lagos = datetime.now(LAGOS_TZ)
# -------------------------------
# CREATE BUSINESS - ONLY SUPER ADMIN
# -------------------------------

@router.post("/", response_model=schemas.BusinessOut, status_code=201)
def create_business(
    business_in: schemas.BusinessCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin"], bypass_admin=False))
):
    """
    Super admin creates a new business.
    """
    # Prevent duplicate business name
    existing = db.query(models.Business).filter(
        models.Business.name == business_in.name.strip()
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Business name already exists")

    # Prevent duplicate owner_username
    existing_owner = db.query(models.Business).filter(
        models.Business.owner_username == business_in.owner_username.strip()
    ).first()
    if existing_owner:
        raise HTTPException(status_code=400, detail="This username is already used as owner for another business")

    # Create business
    business = models.Business(
        name=business_in.name.strip(),
        address=business_in.address,
        phone=business_in.phone,
        email=business_in.email,
        owner_username=business_in.owner_username.strip()
    )

    db.add(business)
    db.commit()
    db.refresh(business)

    # Get latest license info for response
    latest_license = (
        db.query(license_models.LicenseKey)
        .filter(license_models.LicenseKey.business_id == business.id)
        .order_by(license_models.LicenseKey.expiration_date.desc())
        .first()
    )

    is_active = (
        latest_license.is_active and latest_license.expiration_date >= now_lagos
    ) if latest_license else False

    # Return clean dict instead of mutating Pydantic object
    return {
        "id": business.id,
        "name": business.name,
        "address": business.address,
        "phone": business.phone,
        "email": business.email,
        "owner_username": business.owner_username,
        "created_at": business.created_at,
        "license_active": is_active,
        "expiration_date": latest_license.expiration_date if latest_license else None,
    }



@router.get("/", response_model=schemas.BusinessListResponse)
def list_businesses(
    active: Optional[bool] = Query(None),
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin", "admin"]))
):
    roles = set(current_user.roles)

    if "super_admin" in roles:
        query = db.query(models.Business)

        if name:
            query = query.filter(
                func.lower(models.Business.name).ilike(f"%{name.lower().strip()}%")
            )

        if active is not None:
            subquery = (
                db.query(license_models.LicenseKey.business_id)
                .filter(
                    license_models.LicenseKey.is_active == True,
                    license_models.LicenseKey.expiration_date >= now_lagos
                )
                .subquery()
            )
            if active:
                query = query.filter(models.Business.id.in_(subquery))
            else:
                query = query.filter(~models.Business.id.in_(subquery))

        query = query.order_by(models.Business.created_at.desc())
        businesses = query.all()

        enriched = []
        for biz in businesses:
            latest_license = (
                db.query(license_models.LicenseKey)
                .filter(license_models.LicenseKey.business_id == biz.id)
                .order_by(license_models.LicenseKey.expiration_date.desc())
                .first()
            )

            is_active = (
                latest_license.is_active and latest_license.expiration_date >= now_lagos
            ) if latest_license else False

            # Create fresh dict instead of mutating Pydantic object
            biz_dict = {
                "id": biz.id,
                "name": biz.name,
                "address": biz.address,
                "phone": biz.phone,
                "email": biz.email,
                "owner_username": biz.owner_username,
                "created_at": biz.created_at,
                "license_active": is_active,
                "expiration_date": latest_license.expiration_date if latest_license else None,
            }

            enriched.append(biz_dict)

        return {"total": len(enriched), "businesses": enriched}

    else:
        # Admin sees only their own business
        business = db.query(models.Business).filter(
            models.Business.id == current_user.business_id
        ).first()

        if not business:
            return {"total": 0, "businesses": []}

        latest_license = (
            db.query(license_models.LicenseKey)
            .filter(license_models.LicenseKey.business_id == business.id)
            .order_by(license_models.LicenseKey.expiration_date.desc())
            .first()
        )

        is_active = (
            latest_license.is_active and latest_license.expiration_date >= now_lagos
        ) if latest_license else False

        if active is not None and is_active != active:
            return {"total": 0, "businesses": []}

        biz_dict = {
            "id": business.id,
            "name": business.name,
            "address": business.address,
            "phone": business.phone,
            "email": business.email,
            "owner_username": business.owner_username,
            "created_at": business.created_at,
            "license_active": is_active,
            "expiration_date": latest_license.expiration_date if latest_license else None,
        }

        return {"total": 1, "businesses": [biz_dict]}
    
    


from typing import List, Optional
from fastapi import Query
from sqlalchemy import func

@router.get("/simple", response_model=List[schemas.BusinessSimple])
def list_businesses_simple(
    search: Optional[str] = Query(None, description="Search businesses by name"),
    limit: int = Query(50, ge=1, le=100, description="Max number of results"),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin", "admin"]))
):
    """
    Return a simple list of businesses for dropdowns:

    - Super admin → can search all businesses
    - Admin → only their own business
    - Returns only `id` and `name`
    """

    query = db.query(models.Business.id, models.Business.name)

    # Admin → only their own business
    if "super_admin" not in set(current_user.roles):
        query = query.filter(models.Business.id == current_user.business_id)
    else:
        # Super admin → apply optional search
        if search:
            search_term = f"%{search.strip().lower()}%"
            query = query.filter(func.lower(models.Business.name).ilike(search_term))

    return query.order_by(models.Business.name.asc()).limit(limit).all()

    

@router.get("/{business_id}", response_model=schemas.BusinessOut)
def get_business(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin", "admin"]))
):
    """
    Get details of a single business by ID.
    
    - Regular users → only their own business
    - Super admin → any business
    - Includes license_active (computed) and expiration_date from latest license
    """
    # Fetch business
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Permission check
    roles = set(current_user.roles)
    if "super_admin" not in roles and business.id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Safe mapping from ORM
    biz_out = schemas.BusinessOut.from_orm(business)

    # Get latest license for active status and expiration date
    latest_license = (
        db.query(license_models.LicenseKey)
        .filter(license_models.LicenseKey.business_id == business.id)
        .order_by(license_models.LicenseKey.expiration_date.desc())
        .first()
    )

    biz_out.license_active = (
        latest_license.is_active and latest_license.expiration_date >= datetime.now(LAGOS_TZ)

    ) if latest_license else False

    biz_out.expiration_date = latest_license.expiration_date if latest_license else None
    biz_out.owner_username = business.owner_username

    return biz_out


@router.put("/{business_id}", response_model=schemas.BusinessOut)
def update_business(
    business_id: int,
    updated: schemas.BusinessUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin", "admin"]))
):
    """
    Update business details.
    
    - Super admin → any business
    - Admin → only their own business
    - Cannot change owner_username or business_id
    - Returns updated business with computed license_active and expiration_date
    """
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    roles = set(current_user.roles)
    if "super_admin" not in roles and business.id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Apply updates (only allowed fields from schema)
    update_data = updated.dict(exclude_unset=True)

    # Prevent changing protected fields
    protected = {"owner_username", "business_id"}
    for field in protected:
        if field in update_data:
            raise HTTPException(status_code=400, detail=f"Cannot update '{field}'")

    for field, value in update_data.items():
        setattr(business, field, value)

    db.commit()
    db.refresh(business)

    # Safe mapping + computed fields
    biz_out = schemas.BusinessOut.from_orm(business)

    # Latest license for active status and expiration date
    latest_license = (
        db.query(license_models.LicenseKey)
        .filter(license_models.LicenseKey.business_id == business.id)
        .order_by(license_models.LicenseKey.expiration_date.desc())
        .first()
    )

    biz_out.license_active = (
        latest_license.is_active and latest_license.expiration_date >= datetime.now(LAGOS_TZ)

    ) if latest_license else False

    biz_out.expiration_date = latest_license.expiration_date if latest_license else None
    biz_out.owner_username = business.owner_username

    return biz_out


# -------------------------------
# DELETE BUSINESS - SUPER ADMIN ONLY
# -------------------------------
@router.delete("/{business_id}")
def delete_business(
    business_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(role_required(["super_admin", "admin"]))
):
    roles = set(current_user.roles)

    if "super_admin" not in roles:
        raise HTTPException(status_code=403, detail="Only super admin can delete businesses")

    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    db.delete(business)
    db.commit()

    return {"message": f"Business {business.name} deleted successfully"}