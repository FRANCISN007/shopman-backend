from fastapi import APIRouter, HTTPException, UploadFile, File
import os
import subprocess
from urllib.parse import urlparse

router = APIRouter()

# Postgres connection (from .env or hardcode for restore)
DB_URL = os.getenv("DB_URL2")  # e.g., postgresql://REPOMAN:password@localhost:5432/db_url2_eswk
RESTORE_DIR = os.path.join(os.getcwd(), "restore_files")
os.makedirs(RESTORE_DIR, exist_ok=True)


@router.post("/restore/db")
def restore_database(file: UploadFile = File(...)):
    if not DB_URL or not DB_URL.startswith("postgresql://"):
        raise HTTPException(status_code=400, detail="Only PostgreSQL restores are supported.")

    try:
        # Save uploaded file temporarily
        filepath = os.path.join(RESTORE_DIR, file.filename)
        with open(filepath, "wb") as f:
            f.write(file.file.read())

        # Parse DB connection
        parsed = urlparse(DB_URL)
        db_user = parsed.username or "REPOMAN"
        db_password = parsed.password
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432
        db_name = parsed.path.lstrip("/")

        # Build restore command
        pg_restore_cmd = [
            "pg_restore",
            "-U", db_user,
            "-h", db_host,
            "-p", str(db_port),
            "-d", db_name,
            "--clean",       # drop existing objects first
            "--no-owner",    # avoid ownership issues
            "-v",            # verbose output
            filepath
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = db_password or ""

        subprocess.run(pg_restore_cmd, env=env, check=True)

        return {"detail": f"Database '{db_name}' restored successfully from {file.filename}"}

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"pg_restore failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
