from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
import os
import subprocess
from urllib.parse import urlparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

from app.users.permissions import role_required

load_dotenv()

router = APIRouter(prefix="/backup", tags=["Database Backup"])

DB_URL = os.getenv("DB_URL2")

BACKUP_DIR = os.path.join(os.getcwd(), "backup_files")
os.makedirs(BACKUP_DIR, exist_ok=True)

PG_DUMP_PATH = os.getenv("PG_DUMP_PATH", "pg_dump")


# ----------- cleanup old backups -----------

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


# ----------- actual backup function -----------

def run_auto_backup():
    if not DB_URL or not DB_URL.startswith("postgresql://"):
        raise Exception("Invalid DB_URL")

    parsed = urlparse(DB_URL)

    db_user = parsed.username
    db_password = parsed.password
    db_host = parsed.hostname or "localhost"
    db_port = parsed.port or 5432
    db_name = parsed.path.lstrip("/")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{db_name}_backup_{timestamp}.backup"
    filepath = os.path.join(BACKUP_DIR, filename)

    pg_dump_cmd = [
        PG_DUMP_PATH,
        "-h", db_host,
        "-p", str(db_port),
        "-U", db_user,
        "-F", "c",
        "-f", filepath,
        db_name
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = db_password

    result = subprocess.run(pg_dump_cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(result.stderr)

    cleanup_old_backups()

    return filepath


# ----------- scheduler -----------

scheduler = BackgroundScheduler()

# run every midnight
scheduler.add_job(run_auto_backup, "cron", hour=0, minute=0)

scheduler.start()


# ----------- manual backup endpoint -----------

@router.get("/db")
def backup_database(
    format: str = "custom",
    current_user=Depends(role_required(["super_admin"]))
):
    try:
        filepath = run_auto_backup()

        return FileResponse(
            path=filepath,
            filename=os.path.basename(filepath),
            media_type="application/octet-stream"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

