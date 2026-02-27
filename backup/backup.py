from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
import subprocess
from urllib.parse import urlparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

DB_URL = os.getenv("DB_URL2")
BACKUP_DIR = os.path.join(os.getcwd(), "backup_files")
os.makedirs(BACKUP_DIR, exist_ok=True)

@router.get("/backup/db")
def backup_database(format: str = "custom"):
    if not DB_URL or not DB_URL.startswith("postgresql://"):
        raise HTTPException(status_code=400, detail="Only PostgreSQL backups are supported.")

    try:
        parsed = urlparse(DB_URL)
        db_user = parsed.username
        db_password = parsed.password
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432
        db_name = parsed.path.lstrip("/")

        if format == "plain":
            file_ext = ".sql"
            pg_format = "p"
        else:
            file_ext = ".backup"
            pg_format = "c"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{db_name}_backup_{timestamp}{file_ext}"
        filepath = os.path.join(BACKUP_DIR, filename)

        # Build command dynamically for cross-platform
        pg_dump_cmd = [
            "pg_dump",  # assumes pg_dump is in PATH
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

        return FileResponse(path=filepath, filename=filename, media_type="application/octet-stream")

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"pg_dump failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
