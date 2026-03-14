from fastapi import APIRouter, HTTPException, UploadFile, File
import os
import subprocess
from urllib.parse import urlparse

router = APIRouter()

DB_URL = os.getenv("DB_URL2")

RESTORE_DIR = os.path.join(os.getcwd(), "restore_files")
os.makedirs(RESTORE_DIR, exist_ok=True)


@router.post("/restore/db")
def restore_database(file: UploadFile = File(...)):

    if not DB_URL or not DB_URL.startswith("postgresql://"):
        raise HTTPException(
            status_code=400,
            detail="Only PostgreSQL restores are supported."
        )

    try:

        filepath = os.path.join(RESTORE_DIR, file.filename)

        with open(filepath, "wb") as f:
            f.write(file.file.read())

        parsed = urlparse(DB_URL)

        db_user = parsed.username or "postgres"
        db_password = parsed.password or ""
        db_host = parsed.hostname or "localhost"
        db_port = str(parsed.port or 5432)
        db_name = parsed.path.lstrip("/")

        pg_restore_cmd = [
            "pg_restore",
            "-U", db_user,
            "-h", db_host,
            "-p", db_port,
            "-d", db_name,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "-v",
            filepath
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = db_password

        result = subprocess.run(
            pg_restore_cmd,
            env=env,
            capture_output=True,
            text=True
        )

        if result.returncode not in (0, 1):
            raise HTTPException(
                status_code=500,
                detail="Database restore failed."
            )

        # delete backup file after restore
        os.remove(filepath)

        return {
            "detail": f"Database '{db_name}' restored successfully from {file.filename}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
