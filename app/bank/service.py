from sqlalchemy.orm import Session
from fastapi import HTTPException

from . import models, schemas
from app.payments import models as payment_models


def create_bank(db: Session, bank: schemas.BankCreate):
    existing = db.query(models.Bank).filter(models.Bank.name == bank.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bank already exists")

    new_bank = models.Bank(name=bank.name)
    db.add(new_bank)
    db.commit()
    db.refresh(new_bank)
    return new_bank


def list_banks(db: Session):
    return db.query(models.Bank).all()


def list_banks_simple(db: Session):
    banks = db.query(models.Bank.id, models.Bank.name).all()
    return [{"id": b.id, "name": b.name} for b in banks]


def update_bank(db: Session, bank_id: int, bank: schemas.BankUpdate):
    db_bank = db.query(models.Bank).filter(models.Bank.id == bank_id).first()
    if not db_bank:
        return None

    db_bank.name = bank.name
    db.commit()
    db.refresh(db_bank)
    return db_bank


def delete_bank(db: Session, bank_id: int):
    db_bank = db.query(models.Bank).filter(models.Bank.id == bank_id).first()
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
