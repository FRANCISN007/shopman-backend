import os
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from urllib.parse import urlparse
import subprocess

load_dotenv()
router = APIRouter()

# Use DB_URL2 from Shopman .env
DB_URL = os.getenv("DB_URL2")
BACKUP_DIR = os.path.join(os.getcwd(), "backup_files")
os.makedirs(BACKUP_DIR, exist_ok=True)

@router.get("/backup/db")
def backup_database(format: str = "custom"):
    """
    Backup PostgreSQL database for Shopman project.
    """

    if not DB_URL.startswith("postgresql://"):
        return {"error": "Only PostgreSQL backups are supported."}

    try:
        # -----------------------------
        # Parse DB URL
        # -----------------------------
        parsed = urlparse(DB_URL)
        db_user = parsed.username
        db_password = parsed.password
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432
        db_name = parsed.path.lstrip("/")

        # -----------------------------
        # Determine file format & extension
        # -----------------------------
        if format == "plain":
            file_ext = ".sql"
            pg_format = "p"  # plain SQL
        else:
            file_ext = ".backup"
            pg_format = "c"  # custom format

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{db_name}_backup_{timestamp}{file_ext}"  # dynamic based on DB name
        filepath = os.path.join(BACKUP_DIR, filename)

        # -----------------------------
        # Build pg_dump command
        # -----------------------------
        command = [
            r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-F", pg_format,
            "-f", filepath,
            db_name
        ]

        # Pass password
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password

        subprocess.run(command, env=env, check=True)

        # -----------------------------
        # Return file
        # -----------------------------
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="application/octet-stream"
        )

    except subprocess.CalledProcessError as e:
        return {
            "error": "pg_dump failed",
            "stdout": e.stdout,
            "stderr": e.stderr
        }

    except Exception as e:
        return {"error": str(e)}
