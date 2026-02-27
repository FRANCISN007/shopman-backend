from sqlalchemy.orm import Session
from fastapi import HTTPException

from . import models, schemas
from app.payments import models as payment_models





from sqlalchemy.exc import IntegrityError


def create_bank(db: Session, bank: schemas.BankCreate):
    # Optional fast pre-check (user-friendly error)
    existing = (
        db.query(models.Bank)
        .filter(
            models.Bank.name == bank.name,
            models.Bank.business_id == bank.business_id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Bank already exists for this business",
        )

    new_bank = models.Bank(**bank.dict())
    db.add(new_bank)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Bank already exists for this business",
        )

    db.refresh(new_bank)
    return new_bank



def list_banks(db: Session, current_user):
    query = db.query(models.Bank)

    # 🔑 Admin/Manager → only their business
    if "admin" in current_user.roles or "manager" in current_user.roles:
        query = query.filter(models.Bank.business_id == current_user.business_id)

    return query.all()


def list_banks_simple(db: Session, current_user):
    query = db.query(models.Bank.id, models.Bank.name)

    if "admin" in current_user.roles or "manager" in current_user.roles:
        query = query.filter(models.Bank.business_id == current_user.business_id)

    banks = query.all()
    return [{"id": b.id, "name": b.name} for b in banks]




def update_bank(db: Session, bank_id: int, bank: schemas.BankUpdate, current_user):
    query = db.query(models.Bank).filter(models.Bank.id == bank_id)

    # 🔑 Restrict to tenant
    if "admin" in current_user.roles or "manager" in current_user.roles:
        query = query.filter(models.Bank.business_id == current_user.business_id)

    db_bank = query.first()
    if not db_bank:
        return None

    # 🔑 Check duplicate name inside same business
    existing = (
        db.query(models.Bank)
        .filter(
            models.Bank.name == bank.name,
            models.Bank.business_id == db_bank.business_id,
            models.Bank.id != bank_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Bank already exists for this business")

    db_bank.name = bank.name
    db.commit()
    db.refresh(db_bank)
    return db_bank


def delete_bank(db: Session, bank_id: int, current_user):
    query = db.query(models.Bank).filter(models.Bank.id == bank_id)

    # 🔑 Restrict delete to tenant
    if "admin" in current_user.roles:
        query = query.filter(models.Bank.business_id == current_user.business_id)

    db_bank = query.first()
    if not db_bank:
        return None

    # check if bank is used in payments
    usage_count = db.query(payment_models.Payment).filter(
        payment_models.Payment.bank_id == bank_id
    ).count()

    if usage_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete bank '{db_bank.name}'. It has been used in {usage_count} payment(s)."
        )

    db.delete(db_bank)
    db.commit()
    return {"detail": "Bank deleted successfully"}
