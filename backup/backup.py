from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
import os
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv

from app.users.permissions import role_required

# ---------------- LOAD ENV ----------------
load_dotenv()

# ---------------- ROUTER ----------------
router = APIRouter(
    prefix="/backup",
    tags=["Database Backup"],
    dependencies=[Depends(role_required(["super_admin"], bypass_admin=False))]
)

# ---------------- CONFIG ----------------
RAW_DB_URL = os.getenv("DB_URL3")
PG_DUMP_PATH = os.getenv("PG_DUMP_PATH", "pg_dump")

if not RAW_DB_URL:
    raise ValueError("❌ DB_URL3 is not set")

# ✅ Normalize DB URL (CRITICAL for pg_dump)
DB_URL = RAW_DB_URL

if DB_URL.startswith("postgresql+psycopg2://"):
    DB_URL = DB_URL.replace("postgresql+psycopg2://", "postgresql://", 1)

elif DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

print(f"🔍 Using DB_URL: {DB_URL}")

# ---------------- BACKUP DIR ----------------
BACKUP_DIR = os.path.join(os.getcwd(), "backup_files")
os.makedirs(BACKUP_DIR, exist_ok=True)

# ---------------- CLEANUP ----------------
def cleanup_old_backups(days: int = 7):
    now = datetime.now()

    for file in os.listdir(BACKUP_DIR):
        path = os.path.join(BACKUP_DIR, file)

        if os.path.isfile(path):
            file_time = datetime.fromtimestamp(os.path.getmtime(path))

            if now - file_time > timedelta(days=days):
                try:
                    os.remove(path)
                    print(f"🗑️ Deleted old backup: {file}")
                except Exception as e:
                    print(f"⚠️ Cleanup failed: {e}")

# ---------------- CHECK pg_dump ----------------
def check_pg_dump():
    try:
        subprocess.run(
            [PG_DUMP_PATH, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return True
    except Exception:
        print("❌ pg_dump not found. Install postgresql-client on Railway.")
        return False

# ---------------- RUN BACKUP ----------------
def run_auto_backup():
    if not check_pg_dump():
        return None

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"railway_backup_{timestamp}.backup"
        filepath = os.path.join(BACKUP_DIR, filename)

        pg_dump_cmd = [
            PG_DUMP_PATH,
            "--dbname", DB_URL,
            "-F", "c",
            "-f", filepath,
            "--no-owner",
            "--no-privileges"
        ]

        env = os.environ.copy()

        # ✅ Railway requires SSL
        if "localhost" not in DB_URL and "127.0.0.1" not in DB_URL:
            env["PGSSLMODE"] = "require"
            print("🔐 SSL enabled (Railway/remote DB)")
        else:
            print("⚠️ Local DB detected (no SSL)")

        print("🚀 Running pg_dump...")

        result = subprocess.run(
            pg_dump_cmd,
            env=env,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print("❌ pg_dump failed")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return None

        if not os.path.exists(filepath):
            print("❌ Backup file missing after dump")
            return None

        cleanup_old_backups()

        print(f"✅ Backup created: {filename}")
        return filepath

    except Exception as e:
        print(f"❌ Backup error: {e}")
        return None

# ---------------- GET LATEST ----------------
def get_latest_backup():
    try:
        files = [
            os.path.join(BACKUP_DIR, f)
            for f in os.listdir(BACKUP_DIR)
            if os.path.isfile(os.path.join(BACKUP_DIR, f))
        ]

        if not files:
            return None

        files.sort(key=os.path.getmtime, reverse=True)
        return files[0]

    except Exception as e:
        print(f"❌ Failed to get latest backup: {e}")
        return None

# ---------------- ENDPOINT ----------------
@router.get("/db")
def backup_database():
    """
    Trigger backup and download file
    """

    filepath = run_auto_backup()

    if not filepath:
        print("⚠️ Falling back to latest backup...")
        filepath = get_latest_backup()

    if not filepath or not os.path.exists(filepath):
        raise HTTPException(
            status_code=500,
            detail="Backup failed or file not found"
        )

    return FileResponse(
        path=filepath,
        filename=os.path.basename(filepath),
        media_type="application/octet-stream"
    )

