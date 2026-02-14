import json
import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.license.models import LicenseKey

LICENSE_FILE = "license.json"

# Helper to save license to local file
def save_license_to_file(key: str, expiration_date: datetime):
    data = {
        "key": key,
        "expiration_date": expiration_date.isoformat(),
        "valid": True
    }
    with open(LICENSE_FILE, "w") as f:
        json.dump(data, f)

# Helper to read license from local file
def read_license_from_file():
    if not os.path.exists(LICENSE_FILE):
        return None
    try:
        with open(LICENSE_FILE, "r") as f:
            data = json.load(f)
        data["expiration_date"] = datetime.fromisoformat(data["expiration_date"])
        return data
    except Exception:
        return None


def create_license_key(db: Session, key: str):
    # Deactivate all other licenses in DB
    db.query(LicenseKey).update({LicenseKey.is_active: False})

    expiration = datetime.utcnow() + timedelta(days=365)
    license_key = LicenseKey(key=key, expiration_date=expiration, is_active=True)
    
    db.add(license_key)
    db.commit()
    db.refresh(license_key)

    # ✅ Save to local file
    save_license_to_file(key, expiration)

    return license_key


def verify_license_key(db: Session, key: str):
    license_entry = db.query(LicenseKey).filter(
        LicenseKey.key == key, LicenseKey.is_active == True
    ).first()

    if not license_entry:
        # ✅ fallback: check local file
        file_license = read_license_from_file()
        if file_license and file_license["key"] == key:
            if file_license["expiration_date"] > datetime.utcnow():
                return {"valid": True, "expires_on": file_license["expiration_date"]}
            else:
                return {"valid": False, "message": "License expired"}
        return {"valid": False, "message": "Invalid or inactive license key"}

    if license_entry.expiration_date < datetime.utcnow():
        license_entry.is_active = False
        db.commit()
        return {"valid": False, "message": "License expired"}

    # ✅ keep file in sync
    save_license_to_file(license_entry.key, license_entry.expiration_date)

    return {"valid": True, "expires_on": license_entry.expiration_date}
