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
PG_DUMP_PATH = os.getenv("PG_DUMP_PATH", "pg_dump")

DB_HOST = os.getenv("PGHOST", "postgres.railway.internal")
DB_USER = os.getenv("PGUSER", "postgres")
DB_PASSWORD = os.getenv("PGPASSWORD")
DB_NAME = os.getenv("PGDATABASE", "railway")
DB_PORT = os.getenv("PGPORT", "5432")

# ---------------- VALIDATION ----------------
if not DB_PASSWORD:
    raise ValueError("❌ PGPASSWORD is not set in environment variables")

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
        print("❌ pg_dump not available (install postgresql in Railway)")
        return False

# ---------------- RUN BACKUP ----------------
def run_auto_backup():
    if not check_pg_dump():
        return None

    try:
        # final safety check
        required = {
            "DB_HOST": DB_HOST,
            "DB_USER": DB_USER,
            "DB_NAME": DB_NAME,
            "DB_PORT": DB_PORT,
            "DB_PASSWORD": DB_PASSWORD,
        }

        for k, v in required.items():
            if not v:
                print(f"❌ Missing env: {k}")
                return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{timestamp}.backup"
        filepath = os.path.join(BACKUP_DIR, filename)

        env = os.environ.copy()
        env["PGPASSWORD"] = DB_PASSWORD
        env["PGSSLMODE"] = "disable"

        pg_dump_cmd = [
            PG_DUMP_PATH,
            "-h", DB_HOST,
            "-U", DB_USER,
            "-p", str(DB_PORT),
            "-d", DB_NAME,
            "-F", "c",
            "-f", filepath,
            "--no-owner",
            "--no-privileges"
        ]

        print("🚀 Running pg_dump (Railway internal)...")
        print(" ".join(pg_dump_cmd))

        result = subprocess.run(
            pg_dump_cmd,
            env=env,
            capture_output=True,
            text=True
        )

        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)

        if result.returncode != 0:
            print("❌ Backup failed")
            return None

        if not os.path.exists(filepath):
            print("❌ Backup file not created")
            return None

        cleanup_old_backups()

        print(f"✅ Backup created: {filename}")
        return filepath

    except Exception as e:
        print(f"❌ Backup exception: {str(e)}")
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
        print("⚠️ Backup failed → using latest backup")
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
