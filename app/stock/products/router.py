from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
import pandas as pd
from typing import List, Optional

from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema
from app.business.dependencies import get_current_business
from app.users.auth import get_current_user


from app.database import get_db
from app.stock.products import schemas, service, models


from app.stock.products.models import Product
from app.stock.products.schemas import ProductPriceUpdate, ProductOut, ProductSimpleSchema, ProductSimpleSchema1

from app.core.db import db_dependency   # ⭐ import this




router = APIRouter()

# -------------------------------
# CREATE PRODUCT
# -------------------------------

@router.post(
    "/",
    response_model=schemas.ProductOut,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    product: schemas.ProductCreate,
    db: Session = Depends(get_db),  # same as bank
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    ),
):
    if "admin" in current_user.roles and not current_user.business_id:
        raise HTTPException(
            status_code=400,
            detail="Current user does not belong to any business",
        )

    product_data = product.dict(exclude_unset=True)

    # 🔑 Admin → force their business
    if "admin" in current_user.roles:
        product_data["business_id"] = current_user.business_id

    # 🔑 Super admin → must provide business_id
    elif "super_admin" in current_user.roles:
        if not product_data.get("business_id"):
            raise HTTPException(
                status_code=400,
                detail="Super admin must specify a business_id",
            )

    return service.create_product(
        db,
        schemas.ProductCreate(**product_data),
    )



@router.get("/", response_model=list[schemas.ProductOut])
def list_products(
    category: Optional[str] = None,
    name: Optional[str] = None,
    business_id: Optional[int] = None,   # ✅ NEW
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    ),
):
    products = service.get_products(
        db,
        current_user=current_user,
        category=category,
        name=name,
        business_id=business_id,   # ✅ PASS IT
    )

    return [
        schemas.ProductOut(
            id=p.id,
            name=p.name,
            category=p.category.name,
            type=p.type,
            cost_price=p.cost_price,
            selling_price=p.selling_price,
            is_active=p.is_active,
            business_id=p.business_id,
            created_at=p.created_at,
        )
        for p in products
    ]


    
@router.get(
    "/search",
    response_model=List[ProductSimpleSchema1]
)
def search_products(
    query: str,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    ),
):
    products = service.search_products(db, query, current_user)
    return products



@router.get(
    "/simple",
    response_model=List[ProductSimpleSchema]
)
def list_products_simple(
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    ),
):
    return service.get_products_simple(db, current_user)



# products/simple-pos
@router.get("/simple-pos")
def simple_products(
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    ),
):
    query = (
        db.query(Product)
        .filter(Product.is_active == True)
    )

    # 🔐 Tenant Isolation
    if "super_admin" not in current_user.roles:
        query = query.filter(
            Product.business_id == current_user.business_id
        )

    products = query.order_by(Product.name.asc()).all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "selling_price": p.selling_price,
            "category_id": p.category_id,
            "category_name": p.category.name if p.category else None
        }
        for p in products
    ]





@router.get(
    "/{product_id}",
    response_model=schemas.ProductOut
)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["user", "manager", "admin", "super_admin"])
    ),
):
    product = service.get_product_by_id(db, product_id, current_user)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return schemas.ProductOut(
        id=product.id,
        name=product.name,
        category=product.category.name if product.category else None,
        type=product.type,
        cost_price=product.cost_price,
        selling_price=product.selling_price,
        is_active=product.is_active,
        business_id=product.business_id,
        created_at=product.created_at,
    )




@router.put(
    "/{product_id}",
    response_model=schemas.ProductOut
)
def update_product(
    product_id: int,
    product: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    ),
):
    updated_product = service.update_product(
        db, product_id, product, current_user
    )

    if not updated_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return schemas.ProductOut(
        id=updated_product.id,
        name=updated_product.name,
        category=updated_product.category.name if updated_product.category else None,
        type=updated_product.type,
        cost_price=updated_product.cost_price,
        selling_price=updated_product.selling_price,
        is_active=updated_product.is_active,
        business_id=product.business_id,
        created_at=updated_product.created_at,
    )




@router.put(
    "/{product_id}/price",
    response_model=schemas.ProductOut
)
def update_product_price(
    product_id: int,
    price_update: schemas.ProductPriceUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    )
):
    product = service.update_product_price(
        db, product_id, price_update, current_user
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return schemas.ProductOut(
        id=product.id,
        name=product.name,
        category=product.category.name if product.category else None,
        type=product.type,
        cost_price=product.cost_price,
        selling_price=product.selling_price,
        is_active=product.is_active,
        business_id=product.business_id,
        created_at=product.created_at,
    )




@router.delete("/{product_id}")
def delete_product_endpoint(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    ),
):
    return service.delete_product(db, product_id, current_user)





# ------------------- IMPORT EXCEL -------------------
@router.post("/import-excel")
def import_products_from_excel(
    file: UploadFile = File(...),
    business_id: Optional[int] = Form(None),  # 🔹 use Form to receive from multipart/form-data
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    ),
):
    return service.import_products_from_excel(
        db, file, current_user, business_id
    )



@router.put(
    "/{product_id}/status",
    response_model=schemas.ProductOut
)
def update_product_status(
    product_id: int,
    payload: schemas.ProductStatusUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    ),
):
    product = service.update_product_status(
        db, product_id, payload.is_active, current_user
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    return schemas.ProductOut(
        id=product.id,
        name=product.name,
        category=product.category.name if product.category else None,
        type=product.type,
        cost_price=product.cost_price,
        selling_price=product.selling_price,
        is_active=product.is_active,
        business_id=product.business_id,
        created_at=product.created_at,
    )



@router.patch(
    "/{product_id}/deactivate",
    response_model=schemas.ProductOut
)
def deactivate_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    ),
):
    product = service.update_product_status(
        db=db,
        product_id=product_id,
        is_active=False,
        current_user=current_user
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return schemas.ProductOut(
        id=product.id,
        name=product.name,
        category=product.category.name if product.category else None,
        type=product.type,
        cost_price=product.cost_price,
        selling_price=product.selling_price,
        is_active=product.is_active,
        business_id=product.business_id,
        created_at=product.created_at,
    )



@router.patch(
    "/{product_id}/activate",
    response_model=schemas.ProductOut
)
def activate_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["manager", "admin", "super_admin"])
    ),
):
    product = service.update_product_status(
        db=db,
        product_id=product_id,
        is_active=True,
        current_user=current_user
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return schemas.ProductOut(
        id=product.id,
        name=product.name,
        category=product.category.name if product.category else None,
        type=product.type,
        cost_price=product.cost_price,
        selling_price=product.selling_price,
        is_active=product.is_active,
        business_id=product.business_id,
        created_at=product.created_at,
    )

