from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
import os
import subprocess
from urllib.parse import urlparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

# your auth dependency
from app.users.permissions import role_required

load_dotenv()

router = APIRouter(prefix="/backup", tags=["Database Backup"])

DB_URL = os.getenv("DB_URL2")

BACKUP_DIR = os.path.join(os.getcwd(), "backup_files")
os.makedirs(BACKUP_DIR, exist_ok=True)

# Optional: specify pg_dump path for Windows
PG_DUMP_PATH = os.getenv("PG_DUMP_PATH", "pg_dump")


# ----------- Optional cleanup (keep last 7 days) -----------
def cleanup_old_backups(days: int = 7):
    now = datetime.now()

    for file in os.listdir(BACKUP_DIR):
        path = os.path.join(BACKUP_DIR, file)

        if os.path.isfile(path):
            file_time = datetime.fromtimestamp(os.path.getmtime(path))

            if now - file_time > timedelta(days=days):
                try:
                    os.remove(path)
                except Exception:
                    pass


# ----------- Backup Endpoint -----------

@router.get("/db")
def backup_database(
    format: str = "custom",
    current_user=Depends(role_required(["super_admin"]))
):
    """
    Creates a PostgreSQL database backup.

    format:
        custom  -> .backup (recommended)
        plain   -> .sql
    """

    if not DB_URL or not DB_URL.startswith("postgresql://"):
        raise HTTPException(
            status_code=400,
            detail="Only PostgreSQL databases are supported"
        )

    try:
        parsed = urlparse(DB_URL)

        db_user = parsed.username
        db_password = parsed.password
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432
        db_name = parsed.path.lstrip("/")

        # ----------- Backup format -----------
        if format == "plain":
            file_ext = ".sql"
            pg_format = "p"
        else:
            file_ext = ".backup"
            pg_format = "c"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"{db_name}_backup_{timestamp}{file_ext}"

        filepath = os.path.join(BACKUP_DIR, filename)

        # ----------- pg_dump command -----------

        pg_dump_cmd = [
            PG_DUMP_PATH,
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-F", pg_format,
            "-f", filepath,
            db_name
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = db_password

        subprocess.run(pg_dump_cmd, env=env, check=True)

        # clean old backups
        cleanup_old_backups()

        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="application/octet-stream"
        )

    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"pg_dump failed: {str(e)}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Backup error: {str(e)}"
        )



