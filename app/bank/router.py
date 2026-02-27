from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from . import schemas, service
from app.users.schemas import UserDisplaySchema
from app.users.permissions import role_required
from app.bank.schemas import BankSimpleSchema

router = APIRouter()


# ----------------------------------------
# CREATE BANK
# ----------------------------------------
@router.post("/", response_model=schemas.BankDisplay)
def create_bank(
    bank: schemas.BankCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin", "super_admin"])),
):
    # Admin must belong to a business
    if "admin" in current_user.roles and not current_user.business_id:
        raise HTTPException(
            status_code=400,
            detail="Current user does not belong to any business",
        )

    bank_data = bank.dict(exclude_unset=True)

    # 🔑 Force admin business
    if "admin" in current_user.roles:
        bank_data["business_id"] = current_user.business_id

    # 🔑 Super admin must specify business
    elif "super_admin" in current_user.roles:
        if not bank_data.get("business_id"):
            raise HTTPException(
                status_code=400,
                detail="Super admin must specify a business_id",
            )

    return service.create_bank(db, schemas.BankCreate(**bank_data))


# ----------------------------------------
# LIST BANKS
# ----------------------------------------
@router.get("/", response_model=List[schemas.BankDisplay])
def list_banks(
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["user","manager", "admin", "super_admin"])),
):
    return service.list_banks(db, current_user)


@router.get("/simple", response_model=List[BankSimpleSchema])
def list_banks_simple(
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["user", "manager", "admin", "super_admin"])),
):
    return service.list_banks_simple(db, current_user)


# ----------------------------------------
# UPDATE BANK
# ----------------------------------------
@router.put("/{bank_id}", response_model=schemas.BankDisplay)
def update_bank(
    bank_id: int,
    bank: schemas.BankUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["manager", "admin", "super_admin"])),
):
    updated = service.update_bank(db, bank_id, bank, current_user)
    if not updated:
        raise HTTPException(status_code=404, detail="Bank not found")
    return updated


# ----------------------------------------
# DELETE BANK
# ----------------------------------------
@router.delete("/{bank_id}")
def delete_bank(
    bank_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin", "super_admin"])),
):
    deleted = service.delete_bank(db, bank_id, current_user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bank not found")
    return deleted
