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
RAW_DB_URL = os.getenv("DB_URL3") or os.getenv("DATABASE_URL")
PG_DUMP_PATH = os.getenv("PG_DUMP_PATH", "pg_dump")

if not RAW_DB_URL:
    raise ValueError("❌ DATABASE_URL / DB_URL3 is not set")

# ---------------- CLEAN DATABASE URL ----------------
def normalize_db_url(url: str) -> str:
    """
    Convert SQLAlchemy / Railway URLs into pg_dump-compatible URL
    """
    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql://", 1)

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url

DB_URL = normalize_db_url(RAW_DB_URL)

print("🔥 FINAL DB_URL (for pg_dump):", DB_URL)

# ---------------- BACKUP DIR ----------------
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
                    print(f"🗑️ Deleted old backup: {file}")
                except Exception as e:
                    print(f"⚠️ Cleanup error: {e}")

# ---------------- CHECK PG_DUMP ----------------
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
        print("❌ pg_dump not available on server (install postgresql-client)")
        return False

# ---------------- RUN BACKUP ----------------
def run_auto_backup():
    if not check_pg_dump():
        return None

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{timestamp}.backup"
        filepath = os.path.join(BACKUP_DIR, filename)

        env = os.environ.copy()

        # 🔐 Railway ALWAYS needs SSL
        env["PGSSLMODE"] = "require"

        pg_dump_cmd = [
            PG_DUMP_PATH,
            "--dbname", DB_URL,
            "-F", "c",
            "-f", filepath,
            "--no-owner",
            "--no-privileges",
            "--verbose"
        ]

        print("🚀 Running pg_dump...")

        result = subprocess.run(
            pg_dump_cmd,
            env=env,
            capture_output=True,
            text=True
        )

        # ---------------- DEBUG OUTPUT ----------------
        if result.stdout:
            print("STDOUT:", result.stdout)

        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode != 0:
            print("❌ pg_dump FAILED")
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", result.stderr)
            print("DB_URL USED:\n", DB_URL)
            return None


        if not os.path.exists(filepath):
            print("❌ Backup file not created")
            return None

        cleanup_old_backups()

        print(f"✅ Backup created: {filename}")
        return filepath

    except Exception as e:
        print(f"❌ Backup exception: {e}")
        return None

# ---------------- GET LATEST BACKUP ----------------
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
        print(f"❌ Latest backup error: {e}")
        return None

# ---------------- ENDPOINT ----------------
@router.get("/db")
def backup_database():
    """
    Trigger database backup and download file
    """

    filepath = run_auto_backup()

    if not filepath:
        print("⚠️ Backup failed → trying latest file...")
        filepath = get_latest_backup()

    if not filepath or not os.path.exists(filepath):
        raise HTTPException(
            status_code=500,
            detail="Backup failed or no backup file exists"
        )

    return FileResponse(
        path=filepath,
        filename=os.path.basename(filepath),
        media_type="application/octet-stream"
    )
