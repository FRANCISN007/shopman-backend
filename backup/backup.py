from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
import os
import subprocess
from urllib.parse import urlparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

from app.users.permissions import role_required

# ---------------- LOAD ENV ----------------
load_dotenv()

# ---------------- ROUTER (SECURED) ----------------
router = APIRouter(
    prefix="/backup",
    tags=["Database Backup"],
    dependencies=[Depends(role_required(["super_admin"], bypass_admin=False))]
)

# ---------------- CONFIG ----------------
DB_URL = os.getenv("DB_URL3")
PG_DUMP_PATH = os.getenv("PG_DUMP_PATH", "pg_dump")

BACKUP_DIR = os.path.join(os.getcwd(), "backup_files")
os.makedirs(BACKUP_DIR, exist_ok=True)


# ---------------- CLEANUP OLD BACKUPS ----------------
def cleanup_old_backups(days: int = 7):
    now = datetime.now()

    for file in os.listdir(BACKUP_DIR):
        path = os.path.join(BACKUP_DIR, file)

        if os.path.isfile(path):
            file_time = datetime.fromtimestamp(os.path.getmtime(path))

            if now - file_time > timedelta(days=days):
                try:
                    os.remove(path)
                    print(f"Deleted old backup: {file}")
                except Exception as e:
                    print(f"Failed to delete {file}: {str(e)}")


# ---------------- RUN BACKUP ----------------
def run_auto_backup():

    if not DB_URL or not DB_URL.startswith("postgresql://"):
        print("❌ Backup skipped: invalid DB_URL")
        return None

    try:
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

        subprocess.run(pg_dump_cmd, env=env, check=True)

        cleanup_old_backups()

        print(f"✅ Backup created: {filename}")

        return filepath

    except subprocess.CalledProcessError as e:
        print(f"❌ pg_dump failed: {str(e)}")
        return None

    except Exception as e:
        print(f"❌ Backup error: {str(e)}")
        return None


# ---------------- SCHEDULER ----------------
scheduler = BackgroundScheduler()

# Runs every midnight
scheduler.add_job(run_auto_backup, "cron", hour=0, minute=0)

scheduler.start()


# ---------------- GET LATEST BACKUP FILE ----------------
def get_latest_backup():
    files = [
        os.path.join(BACKUP_DIR, f)
        for f in os.listdir(BACKUP_DIR)
        if os.path.isfile(os.path.join(BACKUP_DIR, f))
    ]

    if not files:
        return None

    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


# ---------------- MANUAL BACKUP ENDPOINT ----------------
@router.get("/db")
def backup_database(format: str = "custom"):
    """
    Trigger a manual backup and download the latest file.
    Only accessible by super admin.
    """

    filepath = run_auto_backup()

    # fallback: get latest if new one failed
    if not filepath:
        filepath = get_latest_backup()

    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=500, detail="Backup failed or file not found")

    return FileResponse(
        path=filepath,
        filename=os.path.basename(filepath),
        media_type="application/octet-stream"
    )
