from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from app.database import engine, Base

from app.superadmin.router import router as superadmin_router
from app.business.router import router as business_router
from app.users.routers import router as user_router
from app.license.router import router as license_router
from app.stock.products.router import router as product_router
from app.stock.inventory.router import router as inventory_router

from app.stock.category.router import router as category_router

from app.purchase.router import router as purchase_router
from app.vendor.router import router as vendor_router
from app.bank.router import router as bank_router
from app.sales.router import router as sales_router
from app.stock.inventory.adjustments.router import router as adjustment_router
from app.accounts.expenses.router import router as expenses_router
from app.accounts.profit_loss.router import router as profit_loss_router
from app.payments.router import router as payment_router



from backup.backup import router as backup_router


from app.core.tenant_middleware import TenantMiddleware

app = FastAPI()

app.add_middleware(TenantMiddleware)





import uvicorn
import os
import sys
import pytz
from datetime import datetime
from dotenv import load_dotenv
from contextlib import asynccontextmanager


from pathlib import Path

# Find .env even in frozen or packaged mode
POSSIBLE_ENV_PATHS = [
    Path(__file__).resolve().parent.parent / ".env",        # normal
    Path(sys.executable).resolve().parent / ".env",         # frozen exe
    Path.cwd() / ".env",                                   # runtime cwd
]

for env_path in POSSIBLE_ENV_PATHS:
    if env_path.exists():
        #print(f"[INFO] Loading environment from: {env_path}")
        load_dotenv(env_path, override=True)
        break
else:
    print("[WARNING] .env file not found!")

# Load environment variables
#load_dotenv()

SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
print("Running on SERVER_IP:", SERVER_IP)


# Ensure upload folder exists
os.makedirs("uploads/attachments", exist_ok=True)

# Set default timezone to Africa/Lagos
os.environ["TZ"] = "Africa/Lagos"
lagos_tz = pytz.timezone("Africa/Lagos")
current_time = datetime.now(lagos_tz)

# Adjust sys path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Database startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup")
    Base.metadata.create_all(bind=engine)
    yield
    print("Application shutdown")

# Create app
app = FastAPI(
    title="PHONE SHOP APP",
    description="An API for managing shop operations including Purchase, Sales, Stock, and Payments.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, change to specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/files", StaticFiles(directory="uploads"), name="files")


# Static React frontend
react_build_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "react-frontend", "build")
)
react_static_dir = os.path.join(react_build_dir, "static")

# ✅ Only mount if directory exists
# Serve entire React build dir
if os.path.isdir(react_build_dir):
    app.mount("/static", StaticFiles(directory=react_static_dir), name="static")
    print(f"[INFO] Serving static files from {react_static_dir}")
else:
    print(f"[WARNING] React static directory not found: {react_static_dir} — skipping static mount")


# Routers
app.include_router(superadmin_router, prefix="/superadmin", tags=["Super Admin"])
app.include_router(business_router, prefix="/business", tags=["Business"])
app.include_router(user_router, prefix="/users", tags=["Users"])
app.include_router(license_router, prefix="/license", tags=["License"])
app.include_router(bank_router, prefix="/bank", tags=["Bank"])
app.include_router(vendor_router, prefix="/vendor", tags=["Vendor"])
app.include_router(product_router, prefix="/stock/products", tags=["Stock - Products"])
app.include_router(category_router, prefix="/stock/category", tags=["Stock - Category"])
app.include_router(inventory_router, prefix="/stock/inventory", tags=["Stock - Inventory"])
app.include_router(purchase_router, prefix="/purchase", tags=["Purchase"])

app.include_router(sales_router, prefix="/sales", tags=["Sales"])
app.include_router(payment_router, prefix="/payments", tags=["Payments"])
app.include_router(adjustment_router, prefix="/stock/inventory/adjustments", tags=["StoreInventory - Adjustment"])
app.include_router(expenses_router, prefix="/accounts/expenses", tags=["Accounts - Expenses"])
app.include_router(profit_loss_router, prefix="/accounts/profit_loss", tags=["Accounts - Profit-Loss"])



app.include_router(backup_router)



@app.get("/health")
def health_check():
    return {"status": "ok"}

#app.include_router(system_router,  prefix="/system", tags=["System"])



# Simple health check
@app.get("/debug/ping")
def debug_ping():
    return {"status": "ok"}

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index_file = os.path.join(react_build_dir, "index.html")
    request_file = os.path.join(react_build_dir, full_path)

    # If the file exists in build (manifest.json, favicon.ico, etc.), serve it
    if os.path.isfile(request_file):
        return FileResponse(request_file)

    # Otherwise serve React index.html (SPA fallback)
    if os.path.isfile(index_file):
        return FileResponse(index_file)
    return JSONResponse(status_code=404, content={"detail": "Frontend not built or missing."})