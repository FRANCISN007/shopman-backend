# app/license/service.py
import json
import os
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.license import schemas, models
from loguru import logger



LICENSE_FILE = "license_status.json"


def save_license_file(data: dict):
    """Save license status to local JSON file (offline fallback)."""
    safe_data = {}
    for k, v in data.items():
        if isinstance(v, datetime):
            safe_data[k] = v.isoformat()
        else:
            safe_data[k] = v

    try:
        with open(LICENSE_FILE, "w") as f:
            json.dump(safe_data, f)
    except Exception as e:
        logger.error(f"Failed to save license file: {e}")


def load_license_file():
    """Load license status from local JSON file."""
    if not os.path.exists(LICENSE_FILE):
        return None
    try:
        with open(LICENSE_FILE, "r") as f:
            data = json.load(f)
        if "expires_on" in data and data["expires_on"]:
            data["expires_on"] = datetime.fromisoformat(data["expires_on"])
        return data
    except Exception as e:
        logger.error(f"Failed to load license file: {e}")
        return None


def create_license_key(
    db: Session,
    data: schemas.LicenseCreate
) -> schemas.LicenseResponse:
    """Create new license key in DB."""
    new_license = models.LicenseKey(
        key=data.key,
        expiration_date=data.expiration_date,
        business_id=data.business_id,
        is_active=True,
    )

    db.add(new_license)
    db.commit()
    db.refresh(new_license)

    return schemas.LicenseResponse.from_orm(new_license)


def verify_license_key(db: Session, key: str, business_id: int) -> dict:
    """Verify license key for a business."""
    license_record = (
        db.query(models.LicenseKey)
        .filter(
            models.LicenseKey.key == key,
            models.LicenseKey.business_id == business_id,
            models.LicenseKey.is_active == True,
        )
        .first()
    )

    if not license_record:
        return {"valid": False, "message": "Invalid license key"}

    if license_record.expiration_date < datetime.utcnow():
        return {"valid": False, "message": "License expired"}

    return {
        "valid": True,
        "expires_on": license_record.expiration_date,
        "message": "License valid"
    }