from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import engine, Base

# Routers
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
from backup.restore import router as restore_router

from app.core.tenant_middleware import TenantMiddleware

import os
from contextlib import asynccontextmanager

from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


# ---------------------------
# APP SETUP
# ---------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Application startup")
    Base.metadata.create_all(bind=engine)
    yield
    print("🛑 Application shutdown")

app = FastAPI(
    title="SHopMan App",
    version="1.0.0",
    lifespan=lifespan
)


# ---------------------------
# FORCE CORS ON ALL ERRORS
# ---------------------------

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true"
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true"
        },
    )

# ---------------------------
# MIDDLEWARE
# ---------------------------

app.add_middleware(TenantMiddleware)

# 🔥 CRITICAL: CORS (allow all for now to debug)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://shopman-frontend-production.up.railway.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# HANDLE PREFLIGHT (VERY IMPORTANT)
# ---------------------------

@app.options("/{full_path:path}")
async def preflight_handler(request: Request, full_path: str):
    return Response(status_code=200)

# ---------------------------
# STATIC FILES
# ---------------------------

os.makedirs("uploads/attachments", exist_ok=True)
app.mount("/files", StaticFiles(directory="uploads"), name="files")

# ---------------------------
# ROUTERS (API FIRST)
# ---------------------------

app.include_router(superadmin_router, prefix="/superadmin")
app.include_router(business_router, prefix="/business")
app.include_router(user_router, prefix="/users")
app.include_router(license_router, prefix="/license")
app.include_router(bank_router, prefix="/bank")
app.include_router(vendor_router, prefix="/vendor")
app.include_router(product_router, prefix="/stock/products")
app.include_router(category_router, prefix="/stock/category")
app.include_router(inventory_router, prefix="/stock/inventory")
app.include_router(purchase_router, prefix="/purchase")
app.include_router(sales_router, prefix="/sales")
app.include_router(payment_router, prefix="/payments")
app.include_router(adjustment_router, prefix="/stock/inventory/adjustments")
app.include_router(expenses_router, prefix="/accounts/expenses")
app.include_router(profit_loss_router, prefix="/accounts/profit_loss")

app.include_router(backup_router)
app.include_router(restore_router, prefix="/backup")

# ---------------------------
# HEALTH CHECK
# ---------------------------

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/debug/ping")
def debug_ping():
    return {"status": "ok"}

# ---------------------------
# SERVE FRONTEND (VERY LAST)
# ---------------------------

react_build_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "react-frontend", "build")
)

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index_file = os.path.join(react_build_dir, "index.html")
    request_file = os.path.join(react_build_dir, full_path)

    if os.path.isfile(request_file):
        return FileResponse(request_file)

    if os.path.isfile(index_file):
        return FileResponse(index_file)

    return JSONResponse(
        status_code=404,
        content={"detail": "Frontend not built or missing."}
    )
