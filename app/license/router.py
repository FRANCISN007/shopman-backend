from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.license import schemas as license_schemas, services
from app.license import models as license_models
from app.security.passwords import verify_password
from loguru import logger
from datetime import datetime
from fastapi import Form
import os
import json

router = APIRouter()




logger.add("app.log", rotation="500 MB", level="DEBUG")

# Load hashed admin password from environment
ADMIN_LICENSE_PASSWORD_HASH = os.getenv("ADMIN_LICENSE_PASSWORD_HASH")

# Local license file for offline fallback
LICENSE_FILE = "license_status.json"


def save_license_file(data: dict):
    """Save license status to file (convert datetime to string)."""
    safe_data = {}
    for k, v in data.items():
        if isinstance(v, datetime):
            safe_data[k] = v.isoformat()
        else:
            safe_data[k] = v
    with open(LICENSE_FILE, "w") as f:
        json.dump(safe_data, f)


def load_license_file():
    """Load license status from file if available."""
    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "r") as f:
            return json.load(f)
    return None


# ===========================
# License Endpoints
# ===========================

@router.post("/generate", response_model=license_schemas.LicenseResponse)
def generate_license_key(
    license_password: str = Form(...),
    key: str = Form(...),
    db: Session = Depends(get_db),
):
    """Generate a new license key (Admin only). Requires correct admin license password."""

    if not ADMIN_LICENSE_PASSWORD_HASH:
        raise HTTPException(status_code=500, detail="Admin password not configured.")

    # Secure Argon2 verification
    if not verify_password(license_password, ADMIN_LICENSE_PASSWORD_HASH):
        raise HTTPException(status_code=403, detail="Invalid license password.")

    new_license = services.create_license_key(db, key)

    # Save for offline fallback
    save_license_file({
        "valid": True,
        "expires_on": new_license.expiration_date.isoformat() if new_license.expiration_date else None
    })

    return new_license


@router.get("/verify/{key}")
def verify_license(
    key: str,
    db: Session = Depends(get_db),
):
    """
    Verify a license key against the database.
    """
    result = services.verify_license_key(db, key)

    if not result["valid"]:
        raise HTTPException(status_code=400, detail=result["message"])

    # Save for offline fallback
    save_license_file({
        "valid": result["valid"],
        "expires_on": result["expires_on"].isoformat()
        if isinstance(result.get("expires_on"), datetime)
        else result.get("expires_on")
    })

    return result


@router.get("/license/check")
def check_license_status(db: Session = Depends(get_db)):
    """
    Check current license status (DB first, fallback to local file).
    """
    try:
        license_record = (
            db.query(license_models.LicenseKey)
            .filter(license_models.LicenseKey.is_active == True)
            .order_by(license_models.LicenseKey.expiration_date.desc())
            .first()
        )

        if license_record and license_record.expiration_date > datetime.utcnow():
            data = {
                "valid": True,
                "expires_on": license_record.expiration_date.isoformat()
            }
            save_license_file(data)
            return data

        data = {"valid": False, "expires_on": None}
        save_license_file(data)
        return data

    except Exception as e:
        logger.error(f"DB error, falling back to license file: {e}")
        file_data = load_license_file()
        if file_data:
            if file_data.get("expires_on"):
                exp_date = datetime.fromisoformat(file_data["expires_on"])
                if exp_date > datetime.utcnow():
                    return file_data
            return {"valid": False, "expires_on": file_data.get("expires_on")}
        return {"valid": False, "expires_on": None}
