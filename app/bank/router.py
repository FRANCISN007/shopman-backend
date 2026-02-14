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
    current_user: UserDisplaySchema = Depends(role_required(["manager", "admin"]))
):
    return service.create_bank(db, bank)


# ----------------------------------------
# LIST BANKS
# ----------------------------------------
@router.get("/", response_model=List[schemas.BankDisplay])
def list_banks(
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["manager", "admin"]))
):
    return service.list_banks(db)


@router.get("/simple", response_model=List[BankSimpleSchema])
def list_banks_simple(
    db: Session = Depends(get_db),
    #current_user: UserDisplaySchema = Depends(role_required(["user","manager", "admin"]))
):
    banks = service.list_banks(db)
    # Return only id and name
    return [{"id": b.id, "name": b.name} for b in banks]


# ----------------------------------------
# UPDATE BANK
# ----------------------------------------
@router.put("/{bank_id}", response_model=schemas.BankDisplay)
def update_bank(
    bank_id: int,
    bank: schemas.BankUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["manager", "admin"]))
):
    updated = service.update_bank(db, bank_id, bank)
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
    current_user: UserDisplaySchema = Depends(role_required(["admin"]))
):
    deleted = service.delete_bank(db, bank_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bank not found")
    return deleted
