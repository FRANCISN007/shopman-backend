from fastapi import HTTPException
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from datetime import datetime, date, time
from typing import Optional, List

from . import models, schemas
from app.stock.inventory import service as inventory_service
from app.stock.inventory import models as inventory_models

from app.stock.inventory.adjustments import models as adj_models
from app.stock.products import models as product_models

from app.stock.inventory.adjustments import models as adj_models
from app.stock.products import models as product_models
from app.users import models as user_models

from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema
from app.users.auth import get_current_user

from datetime import datetime
from zoneinfo import ZoneInfo



LAGOS_TZ = ZoneInfo("Africa/Lagos")





def create_adjustment(
    db: Session,
    adjustment: schemas.StockAdjustmentCreate,
    current_user: UserDisplaySchema
) -> schemas.StockAdjustmentOut:
    """
    Tenant-safe stock adjustment creation.
    Validates product/inventory ownership, prevents negative stock.
    """
    # 1. Determine target business_id
    if "super_admin" in current_user.roles:
        # Super admin must provide business context somehow (e.g. via product)
        # Here we get it from product
        product = db.query(product_models.Product).filter(
            product_models.Product.id == adjustment.product_id
        ).first()
        if not product:
            return None
        target_business_id = product.business_id
    else:
        if not current_user.business_id:
            raise HTTPException(status_code=403, detail="User does not belong to any business")
        target_business_id = current_user.business_id

    # 2. Validate product belongs to business
    product = db.query(product_models.Product).filter(
        product_models.Product.id == adjustment.product_id,
        product_models.Product.business_id == target_business_id
    ).first()
    if not product:
        return None

    # 3. Get inventory record
    inventory = inventory_service.get_inventory_orm_by_product(db, adjustment.product_id)
    if not inventory or inventory.business_id != target_business_id:
        raise HTTPException(status_code=404, detail="Inventory not found or does not belong to this business")

    # 4. Calculate new stock
    current_stock = float(inventory.current_stock or 0)
    new_stock = current_stock + adjustment.quantity

    if new_stock < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Adjustment would result in negative stock (current: {current_stock}, after: {new_stock})"
        )

    # 5. Update inventory
    inventory.adjustment_total = float(inventory.adjustment_total or 0) + adjustment.quantity
    inventory.current_stock = new_stock

    # 6. Create adjustment record
    adj = models.StockAdjustment(
        business_id=target_business_id,
        product_id=adjustment.product_id,
        inventory_id=inventory.id,
        quantity=adjustment.quantity,
        reason=adjustment.reason,
        adjusted_by=current_user.id
    )

    db.add(adj)
    db.add(inventory)

    try:
        db.commit()
        db.refresh(adj)
        db.refresh(inventory)

        # Enrich response
        return schemas.StockAdjustmentOut(
            id=adj.id,
            business_id=adj.business_id,
            product_id=adj.product_id,
            inventory_id=adj.inventory_id,
            quantity=adj.quantity,
            reason=adj.reason,
            adjusted_by=adj.adjusted_by,
            adjusted_at=adj.adjusted_at,
            product_name=product.name if product else None,
            adjusted_by_name=current_user.username if current_user else None
        )

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e.orig)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create adjustment: {str(e)}")
    



def list_adjustments(
    db: Session,
    current_user,
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    business_id: Optional[int] = None
) -> List[schemas.StockAdjustmentOut]:
    """
    Tenant-aware list of stock adjustments.
    Enriches with product_name and adjusted_by_name.
    """

    # ─── 1. Base query with joins ─────────────────────────────
    query = (
        db.query(
            models.StockAdjustment,
            product_models.Product.name.label("product_name"),
            user_models.User.username.label("adjusted_by_name")
        )
        .join(
            product_models.Product,
            product_models.Product.id == models.StockAdjustment.product_id
        )
        .outerjoin(
            user_models.User,
            user_models.User.id == models.StockAdjustment.adjusted_by
        )
        .options(
            joinedload(models.StockAdjustment.product),
            joinedload(models.StockAdjustment.user),
            joinedload(models.StockAdjustment.inventory)
        )
    )

    # ─── 2. Tenant isolation ──────────────────────────────────
    if "super_admin" not in getattr(current_user, "roles", []):
        if not getattr(current_user, "business_id", None):
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.StockAdjustment.business_id == current_user.business_id)
    elif business_id is not None:
        query = query.filter(models.StockAdjustment.business_id == business_id)

    # ─── 3. Date range filter (timezone-aware) ──────────────
    if start_date:
        start_dt = datetime.combine(start_date, time.min).replace(tzinfo=LAGOS_TZ)
        query = query.filter(models.StockAdjustment.adjusted_at >= start_dt)
    if end_date:
        end_dt = datetime.combine(end_date, time.max).replace(tzinfo=LAGOS_TZ)
        query = query.filter(models.StockAdjustment.adjusted_at <= end_dt)

    # ─── 4. Execute with ordering + pagination ──────────────
    # Use column itself; SQLAlchemy will handle datetime sorting
    results = (
        query
        .order_by(models.StockAdjustment.adjusted_at)  # ascending order by default
        .offset(skip)
        .limit(limit)
        .all()
    )

    # ─── 5. Build enriched response ─────────────────────────
    adjustments = []
    for adj, product_name, adjusted_by_name in results:
        adjustments.append(
            schemas.StockAdjustmentOut(
                id=adj.id,
                business_id=adj.business_id,
                product_id=adj.product_id,
                inventory_id=adj.inventory_id,
                quantity=float(adj.quantity),
                reason=adj.reason,
                adjusted_by=adj.adjusted_by,
                adjusted_at=adj.adjusted_at,
                product_name=product_name,
                adjusted_by_name=adjusted_by_name
            )
        )

    return adjustments



def delete_adjustment(
    db: Session,
    adjustment_id: int,
    current_user: UserDisplaySchema
) -> bool:
    """
    Tenant-safe deletion of a stock adjustment record.
    Reverses the stock effect and updates inventory.current_stock.
    Returns True if deleted, False if not found/unauthorized.
    """
    # 1. Fetch adjustment with tenant isolation + eager load related data
    adjustment_query = db.query(models.StockAdjustment).options(
        joinedload(models.StockAdjustment.inventory),
        joinedload(models.StockAdjustment.product)
    )

    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        adjustment_query = adjustment_query.filter(
            models.StockAdjustment.business_id == current_user.business_id
        )

    adjustment = adjustment_query.filter(
        models.StockAdjustment.id == adjustment_id
    ).first()

    if not adjustment:
        return False

    inventory = adjustment.inventory
    if not inventory:
        raise HTTPException(status_code=404, detail="Linked inventory not found")

    # 2. Reverse the adjustment effect on inventory
    adjustment_amount = float(adjustment.quantity or 0)
    current_adjustment_total = float(inventory.adjustment_total or 0)

    # Subtract the original adjustment (reverse it)
    new_adjustment_total = current_adjustment_total - adjustment_amount
    new_stock = (
        float(inventory.quantity_in or 0)
        - float(inventory.quantity_out or 0)
        + new_adjustment_total
    )

    if new_stock < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Deleting this adjustment would result in negative stock "
                   f"(current: {inventory.current_stock}, after: {new_stock})"
        )

    inventory.adjustment_total = new_adjustment_total
    inventory.current_stock = new_stock

    # 3. Delete the adjustment record
    db.delete(adjustment)

    # 4. Commit atomically
    try:
        db.commit()
        return True

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Database constraint violation: {str(e.orig)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete stock adjustment: {str(e)}"
        )   
