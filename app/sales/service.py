from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime
from typing import Optional, List
from datetime import datetime, time
from datetime import date
from sqlalchemy.orm import joinedload
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from app.users import models as users_models

from app.users.permissions import role_required
from app.users.schemas import UserDisplaySchema
from app.users.auth import get_current_user


from . import models, schemas
from app.stock.inventory import service as inventory_service
from app.stock.products import models as product_models

from app.sales.schemas import SaleOut, SaleOut2, SaleSummary, SalesListResponse, SaleItemOut2, SaleItemOut

from app.stock.products import models as product_models
from app.payments.models import Payment

from sqlalchemy import func
from app.stock.products.models import Product

from sqlalchemy import func, desc
from sqlalchemy import text

from app.purchase.models import Purchase
from app.purchase import  models as purchase_models

from datetime import datetime, time
from zoneinfo import ZoneInfo

LAGOS_TZ = ZoneInfo("Africa/Lagos")




def create_sale_full(
    db: Session,
    sale_data: schemas.SaleFullCreate,
    current_user: UserDisplaySchema,
    business_id: int | None = None,   # only used by super_admin
) -> models.Sale:
    """
    Create a complete sale (header + items) with full tenant isolation.
    """
    warnings_list = []

    # ─── 1. Determine & validate business_id ───────────────────────
    if "super_admin" in current_user.roles:
        if not business_id:
            raise HTTPException(
                status_code=400,
                detail="Super admin must provide business_id"
            )
        target_business_id = business_id
    else:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="User does not belong to any business"
            )
        target_business_id = current_user.business_id

        # Extra safety: reject if someone tries to spoof
        if business_id and business_id != target_business_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot create sale for another business"
            )

    # ─── 2. Create sale header ─────────────────────────────────────
    sale = models.Sale(
        business_id=target_business_id,
        invoice_date=sale_data.invoice_date,
        customer_name=sale_data.customer_name.strip() if sale_data.customer_name else None,
        customer_phone=sale_data.customer_phone,
        ref_no=sale_data.ref_no,
        sold_by=current_user.id,
        total_amount=0.0,           # will be updated later
    )

    db.add(sale)
    db.flush()  # ← this generates invoice_no via Identity

    total_amount = 0.0

    # ─── 3. Process each item ──────────────────────────────────────
    for item_data in sale_data.items:

        # Validate product + tenant
        product = db.query(product_models.Product).filter(
            product_models.Product.id == item_data.product_id,
            product_models.Product.business_id == target_business_id,
        ).first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item_data.product_id} not found or does not belong to this business"
            )

        # Freeze historical cost price
        # Correct way to get latest cost
        latest_purchase_item = (
            db.query(purchase_models.PurchaseItem)
            .join(purchase_models.Purchase)  # join header to get business_id
            .filter(
                purchase_models.PurchaseItem.product_id == item_data.product_id,
                purchase_models.Purchase.business_id == target_business_id
            )
            .order_by(purchase_models.PurchaseItem.id.desc())
            .first()
        )
        historical_cost = latest_purchase_item.cost_price if latest_purchase_item else 0.0


        # Stock check (warning only — your current policy)
        stock_entry = inventory_service.get_inventory_orm_by_product(
            db, item_data.product_id, current_user
        )
        available = stock_entry.current_stock if stock_entry else 0

        if available < item_data.quantity:
            warnings_list.append(
                f"Low stock warning: {product.name} — "
                f"Available: {available}, Requested: {item_data.quantity}"
            )

        # Deduct stock (non-blocking)
        inventory_service.remove_stock(
            db,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            current_user=current_user,
            commit=False
        )

        # Calculate line totals
        gross = item_data.quantity * item_data.selling_price
        discount = item_data.discount or 0.0
        net = gross - discount

        sale_item = models.SaleItem(
            sale_invoice_no=sale.invoice_no,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            selling_price=item_data.selling_price,
            cost_price=historical_cost,     # frozen
            total_amount=net,               # most systems use net here
            gross_amount=gross,
            discount=discount,
            net_amount=net,
        )

        db.add(sale_item)
        total_amount += net

    # ─── 4. Finalize sale ──────────────────────────────────────────
    sale.total_amount = total_amount

    try:
        db.commit()
        db.refresh(sale)

        # Re-attach items with names for response
        db.refresh(sale)  # refresh again to load relationships if needed
        for item in sale.items:
            if item.product:
                item.product_name = item.product.name   # attach temporarily

        # Optional: attach warnings if your frontend wants them
        sale.warnings = warnings_list   # not persisted — only for this response

        return sale

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Database error during sale creation: {str(e.orig)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )
# ============================================================
# ADD SINGLE ITEM TO EXISTING SALE
# ============================================================

# service.py
def create_sale_item(
    db: Session,
    item: schemas.SaleItemCreate,
    current_user: UserDisplaySchema,
) -> models.SaleItem:
    """
    Add a single item to an existing sale with full tenant isolation.
    Updates sale total atomically.
    """

    # ─── 1️⃣ Find the sale + enforce tenant ───────────────────────────
    sale_query = db.query(models.Sale)

    # Non-super-admins can only touch their own business
    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="User does not belong to any business"
            )
        sale_query = sale_query.filter(models.Sale.business_id == current_user.business_id)

    sale = sale_query.filter(models.Sale.invoice_no == item.sale_invoice_no).first()

    if not sale:
        raise HTTPException(
            status_code=404,
            detail=f"Sale with invoice_no {item.sale_invoice_no} not found "
                   "or does not belong to your business"
        )

    target_business_id = sale.business_id

    # ─── 2️⃣ Validate product belongs to same business ────────────────
    product = db.query(product_models.Product).filter(
        product_models.Product.id == item.product_id,
        product_models.Product.business_id == target_business_id,
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail=f"Product {item.product_id} not found or does not belong to business {target_business_id}"
        )

    # ─── 3️⃣ Capture historical cost price (tenant scoped) ────────────
    latest_purchase_item = (
        db.query(purchase_models.PurchaseItem)
        .join(purchase_models.Purchase)
        .filter(
            purchase_models.PurchaseItem.product_id == item.product_id,
            purchase_models.Purchase.business_id == target_business_id
        )
        .order_by(purchase_models.PurchaseItem.id.desc())
        .first()
    )

    historical_cost = latest_purchase_item.cost_price if latest_purchase_item else 0.0

    # ─── 4️⃣ Stock validation ────────────────────────────────────────
    stock_entry = inventory_service.get_inventory_orm_by_product(
        db, item.product_id, current_user=current_user
    )
    available = stock_entry.current_stock if stock_entry else 0

    if available < item.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock for {product.name}. "
                   f"Available: {available}, Requested: {item.quantity}"
        )

    # ─── 5️⃣ Deduct stock ─────────────────────────────────────────────
    inventory_service.remove_stock(
        db,
        product_id=item.product_id,
        quantity=item.quantity,
        current_user=current_user,
        commit=False
    )

    # ─── 6️⃣ Calculate line totals ────────────────────────────────────
    gross_amount = item.quantity * item.selling_price
    discount = item.discount or 0.0
    net_amount = gross_amount - discount

    # ─── 7️⃣ Create sale item ─────────────────────────────────────────
    sale_item = models.SaleItem(
        sale_invoice_no=item.sale_invoice_no,
        product_id=item.product_id,
        quantity=item.quantity,
        selling_price=item.selling_price,
        cost_price=historical_cost,
        gross_amount=gross_amount,
        discount=discount,
        net_amount=net_amount,
        total_amount=net_amount,  # net by default
    )

    db.add(sale_item)

    # ─── 8️⃣ Update sale total ────────────────────────────────────────
    sale.total_amount = (sale.total_amount or 0.0) + net_amount

    # ─── 9️⃣ Commit everything ────────────────────────────────────────
    try:
        db.commit()
        db.refresh(sale_item)
        db.refresh(sale_item, attribute_names=["product"])  # load product relation
        return sale_item

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
            detail=f"Failed to add item: {str(e)}"
        )


    




def list_item_sold(
    db: Session,
    current_user: UserDisplaySchema,
    start_date: date,
    end_date: date,
    invoice_no: Optional[int] = None,
    product_id: Optional[int] = None,
    product_name: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    business_id: Optional[int] = None
) -> schemas.ItemSoldResponse:
    """
    Tenant-aware report of sold items with flexible filters.
    Aggregates total quantity and net amount across matching items.
    """
    # ─── 1. Base query with eager loading ─────────────────────────────
    query = (
        db.query(models.Sale)
        .options(
            joinedload(models.Sale.items).joinedload(models.SaleItem.product)
        )
        .filter(models.Sale.invoice_date >= start_date)
        .filter(models.Sale.invoice_date <= end_date)
    )

    # ─── 2. Tenant isolation ──────────────────────────────────────────
    if "super_admin" in current_user.roles:
        if business_id is not None:
            query = query.filter(models.Sale.business_id == business_id)
    else:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.Sale.business_id == current_user.business_id)

    # ─── 3. Additional filters ────────────────────────────────────────
    if invoice_no is not None:
        query = query.filter(models.Sale.invoice_no == invoice_no)

    sales = (
        query
        .order_by(models.Sale.invoice_no.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # ─── 4. Process sales & items ─────────────────────────────────────
    total_qty = 0
    total_amount = 0.0
    sales_out: List[schemas.SaleOut] = []

    for sale in sales:
        items_out = []

        for item in sale.items:
            # Apply product filters
            if product_id and item.product_id != product_id:
                continue

            if product_name and (
                not item.product or
                product_name.lower() not in item.product.name.lower()
            ):
                continue

            qty = item.quantity or 0
            gross = item.gross_amount or (qty * (item.selling_price or 0))
            discount = item.discount or 0.0
            net = item.net_amount or (gross - discount)

            total_qty += qty
            total_amount += net

            items_out.append(
                schemas.SaleItemOut(
                    id=item.id,
                    sale_invoice_no=item.sale_invoice_no,
                    product_id=item.product_id,
                    product_name=item.product.name if item.product else None,
                    quantity=qty,
                    selling_price=float(item.selling_price or 0),
                    gross_amount=float(gross),
                    discount=float(discount),
                    net_amount=float(net)
                )
            )

        # Skip sales with no matching items after filters
        if not items_out:
            continue

        sales_out.append(
            schemas.SaleOut(
                id=sale.id,
                invoice_no=sale.invoice_no,
                invoice_date=sale.invoice_date,
                customer_name=sale.customer_name or "-",
                customer_phone=sale.customer_phone or "-",
                ref_no=sale.ref_no or "-",
                total_amount=sum(i.net_amount for i in items_out),
                sold_by=sale.sold_by,
                sold_at=sale.sold_at,
                items=items_out
            )
        )

    # ─── 5. Return structured response ────────────────────────────────
    return schemas.ItemSoldResponse(
        sales=sales_out,
        summary=schemas.ItemSoldSummary(
            total_quantity=total_qty,
            total_amount=total_amount
        )
    )




def get_all_invoice_numbers(
    db: Session,
    current_user: UserDisplaySchema,
    business_id: Optional[int] = None
) -> List[int]:
    """
    Tenant-aware retrieval of sale invoice numbers.
    Super admin can see everything or filter by business.
    """
    query = db.query(models.Sale.invoice_no)

    # ─── Apply tenant isolation ──────────────────────────────────────
    if "super_admin" in current_user.roles:
        # Super admin sees everything, unless filtered
        if business_id is not None:
            query = query.filter(models.Sale.business_id == business_id)
    else:
        # Normal users → only their business
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.Sale.business_id == current_user.business_id)

    # ─── Ordering + execution ────────────────────────────────────────
    result = (
        query
        .order_by(models.Sale.invoice_no.asc())   # or .desc() if you prefer recent first
        .all()
    )

    # Extract scalar values
    return [row[0] for row in result]




def get_sale_by_invoice_no(
    db: Session,
    invoice_no: int,
    current_user: UserDisplaySchema
) -> Optional[dict]:
    """
    Fetch a single sale by invoice_no with tenant isolation.
    Returns enriched dict matching SaleReprintOut or None if not found.
    """
    # ─── 1. Build query with eager loading ───────────────────────────
    query = (
        db.query(models.Sale)
        .options(
            joinedload(models.Sale.items).joinedload(models.SaleItem.product),
            joinedload(models.Sale.payments)
        )
        .filter(models.Sale.invoice_no == invoice_no)
    )

    # ─── 2. Apply tenant isolation ───────────────────────────────────
    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(
            models.Sale.business_id == current_user.business_id
        )

    sale = query.first()

    if not sale:
        return None

    # ─── 3. Payment calculations ─────────────────────────────────────
    payments = sale.payments or []
    total_paid = sum(float(p.amount_paid or 0) for p in payments)
    balance_due = float(sale.total_amount or 0) - total_paid

    # Last payment (used for receipt display)
    last_payment = payments[-1] if payments else None

    # Payment status logic
    if balance_due <= 0:
        payment_status = "paid"
    elif total_paid > 0:
        payment_status = "partial"
    else:
        payment_status = "unpaid"

    # ─── 4. Build enriched response dict ─────────────────────────────
    return {
        "id": sale.id,
        "invoice_no": sale.invoice_no,
        "invoice_date": sale.invoice_date.date() if sale.invoice_date else None,
        "customer_name": sale.customer_name,
        "customer_phone": sale.customer_phone,
        "ref_no": sale.ref_no,

        "total_amount": float(sale.total_amount or 0),
        "amount_paid": total_paid,
        "balance_due": balance_due,

        # ─── FIXED ────────────────────────────────────────────────────
        "payment_method": last_payment.payment_method if last_payment else None,
        "bank_id": last_payment.bank_id if last_payment else None,
        # ──────────────────────────────────────────────────────────────

        "payment_status": payment_status,

        "sold_at": sale.sold_at,

        "items": [
            {
                "product_id": item.product_id,
                "product_name": item.product.name if item.product else None,
                "quantity": item.quantity,
                "selling_price": float(item.selling_price or 0),
                "discount": float(item.discount or 0),
                "gross_amount": float(item.gross_amount or 0),
                "net_amount": float(item.net_amount or 0),
            }
            for item in sale.items
        ]
    }





LAGOS_TZ = ZoneInfo("Africa/Lagos")

def list_sales(
    db: Session,
    current_user: UserDisplaySchema,
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    business_id: Optional[int] = None,
) -> schemas.SalesListResponse:
    """
    Tenant-aware sales listing with timezone-aware filtering.
    Enforces business isolation except for super_admin.
    """

    # ─── 1. Build base query with eager loading ───────────────────────
    query = (
        db.query(models.Sale)  # full model
        .options(
            joinedload(models.Sale.items).joinedload(models.SaleItem.product),
            joinedload(models.Sale.payments),
        )
    )

    # ─── 2. Apply tenant isolation ────────────────────────────────────
    if "super_admin" in current_user.roles:
        if business_id is not None:
            query = query.filter(models.Sale.business_id == business_id)
    else:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.Sale.business_id == current_user.business_id)

    # ─── 3. Date filters (timezone-aware) ─────────────────────────────
    if start_date:
        start_datetime = datetime.combine(start_date, time.min, tzinfo=LAGOS_TZ)
        query = query.filter(models.Sale.sold_at >= start_datetime)

    if end_date:
        end_datetime = datetime.combine(end_date, time.max, tzinfo=LAGOS_TZ)
        query = query.filter(models.Sale.sold_at <= end_datetime)

    # ─── 4. Pagination only (no ordering) ────────────────────────────
    sales = query.offset(skip).limit(limit).all()

    # ─── 5. Build enriched response ───────────────────────────────────
    sales_list: List[schemas.SaleOut2] = []
    total_sales_amount = 0.0
    total_paid_sum = 0.0
    total_balance_sum = 0.0

    for sale in sales:
        total_amount = float(sale.total_amount or 0.0)

        payments = sale.payments or []
        total_paid = sum(float(p.amount_paid or 0) for p in payments)
        balance_due = total_amount - total_paid

        if total_paid == 0:
            payment_status = "pending"
        elif balance_due > 0:
            payment_status = "part_paid"
        else:
            payment_status = "completed"

        items = [
            schemas.SaleItemOut2(
                id=item.id,
                sale_invoice_no=item.sale_invoice_no,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                quantity=item.quantity,
                selling_price=item.selling_price,
                gross_amount=item.gross_amount,
                discount=item.discount,
                net_amount=item.net_amount,
            )
            for item in (sale.items or [])
        ]

        sales_list.append(
            schemas.SaleOut2(
                id=sale.id,
                invoice_no=sale.invoice_no,
                invoice_date=sale.invoice_date,
                customer_name=sale.customer_name or "Walk-in",
                customer_phone=sale.customer_phone,
                ref_no=sale.ref_no,
                total_amount=total_amount,
                total_paid=total_paid,
                balance_due=balance_due,
                payment_status=payment_status,
                sold_at=sale.sold_at.astimezone(LAGOS_TZ),
                items=items,
            )
        )

        total_sales_amount += total_amount
        total_paid_sum += total_paid
        total_balance_sum += balance_due

    # ─── 6. Summary ───────────────────────────────────────────────────
    summary = schemas.SaleSummary(
        total_sales=total_sales_amount,
        total_paid=total_paid_sum,
        total_balance=total_balance_sum,
    )

    return schemas.SalesListResponse(
        sales=sales_list,
        summary=summary
    )





def update_sale(
    db: Session,
    invoice_no: int,
    sale_update: schemas.SaleUpdate,
    current_user: UserDisplaySchema
) -> Optional[models.Sale]:
    """
    Tenant-safe update of sale header fields.
    Recalculates total_amount from items and balance from payments.
    """
    # ─── 1. Build query with tenant isolation ────────────────────────
    query = db.query(models.Sale)

    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.Sale.business_id == current_user.business_id)

    sale = query.filter(models.Sale.invoice_no == invoice_no).first()

    if not sale:
        return None

    # ─── 2. Prepare update data ──────────────────────────────────────
    update_data = sale_update.dict(exclude_unset=True)

    # Prevent updating critical/immutable fields
    forbidden_fields = {"invoice_no", "total_amount", "sold_by", "sold_at"}
    for field in forbidden_fields:
        if field in update_data:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot update field '{field}'"
            )

    # ─── 3. Apply allowed header updates ─────────────────────────────
    allowed_fields = {"customer_name", "customer_phone", "ref_no"}
    for field, value in update_data.items():
        if field in allowed_fields:
            setattr(sale, field, value)
        else:
            # Optional: log or warn about ignored fields
            pass

    # ─── 4. Recalculate totals from items (net_amount based) ─────────
    sale.total_amount = sum(float(item.net_amount or 0) for item in sale.items)

    # Payments (if you store balance_due on Sale model)
    total_paid = sum(float(p.amount_paid or 0) for p in (sale.payments or []))
    balance_due = sale.total_amount - total_paid

    # If your Sale model has balance_due field, update it:
    # sale.balance_due = balance_due
    # Otherwise just recalculate when needed in responses

    # ─── 5. Commit & refresh ─────────────────────────────────────────
    try:
        db.commit()
        db.refresh(sale)
        # Optional: reload relationships if you want items/payments in response
        # db.refresh(sale, attribute_names=["items", "payments"])
        return sale

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to update sale: {str(e)}"
        )



def update_sale_item(
    db: Session,
    invoice_no: int,
    item_update: schemas.SaleItemUpdate,
    current_user: UserDisplaySchema
):
    """
    Tenant-safe update of a single sale item.
    Handles product change, stock adjustment, historical cost, totals recalculation.
    """
    # ─── 1. Fetch sale with tenant isolation ─────────────────────────
    sale_query = db.query(models.Sale)

    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        sale_query = sale_query.filter(
            models.Sale.business_id == current_user.business_id
        )

    sale = sale_query.filter(
        models.Sale.invoice_no == invoice_no
    ).first()

    if not sale:
        return None

    target_business_id = sale.business_id

    # ─── 2. Fetch the item to update ─────────────────────────────────
    item_query = db.query(models.SaleItem).filter(
        models.SaleItem.sale_invoice_no == invoice_no
    )

    # Use old_product_id if provided to identify which line to update
    if item_update.old_product_id is not None:
        item_query = item_query.filter(
            models.SaleItem.product_id == item_update.old_product_id
        )

    item = item_query.first()

    if not item:
        return None

    old_product_id = item.product_id
    old_quantity = item.quantity

    # ─── 3. Handle product change (if requested) ─────────────────────
    new_product_id = item_update.product_id or item.product_id

    # Validate new/existing product belongs to business
    product = db.query(product_models.Product).filter(
        product_models.Product.id == new_product_id,
        product_models.Product.business_id == target_business_id,
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail=f"Product {new_product_id} not found or does not belong "
                   f"to business {target_business_id}"
        )

    # Prevent duplicate product in same invoice
    if new_product_id != old_product_id:
        duplicate = db.query(models.SaleItem).filter(
            models.SaleItem.sale_invoice_no == invoice_no,
            models.SaleItem.product_id == new_product_id
        ).first()
        if duplicate:
            raise HTTPException(
                status_code=400,
                detail="This product already exists in the invoice"
            )

    item.product_id = new_product_id

    # ─── 4. Update quantity, price, discount ─────────────────────────
    if item_update.quantity is not None:
        item.quantity = item_update.quantity
    if item_update.selling_price is not None:
        item.selling_price = item_update.selling_price
    if item_update.discount is not None:
        item.discount = item_update.discount

    # ─── 5. Freeze new historical cost price (if product changed) ─────
    if new_product_id != old_product_id:
        latest_purchase = db.query(purchase_models.Purchase).filter(
            purchase_models.Purchase.product_id == new_product_id,
            purchase_models.Purchase.business_id == target_business_id,
        ).order_by(purchase_models.Purchase.id.desc()).first()
        item.cost_price = latest_purchase.cost_price if latest_purchase else 0.0

    # ─── 6. Recalculate item amounts ─────────────────────────────────
    item.gross_amount = item.quantity * item.selling_price
    item.net_amount = item.gross_amount - (item.discount or 0)
    item.total_amount = item.net_amount

    # ─── 7. Stock adjustment (reverse old → apply new) ───────────────
    # Reverse old quantity
    if old_quantity != item.quantity or old_product_id != new_product_id:
        inventory_service.add_stock(   # add = reverse removal
            db,
            product_id=old_product_id,
            quantity=old_quantity,     # putting back
            current_user=current_user,
            commit=False
        )

    # Apply new quantity
    inventory_service.remove_stock(
        db,
        product_id=item.product_id,
        quantity=item.quantity,
        current_user=current_user,
        commit=False
    )

    # ─── 8. Update sale totals ───────────────────────────────────────
    sale.total_amount = sum(float(i.net_amount or 0) for i in sale.items)

    total_paid = sum(float(p.amount_paid or 0) for p in (sale.payments or []))
    balance_due = sale.total_amount - total_paid

    # If Sale model has balance_due field:
    # sale.balance_due = balance_due

    # ─── 9. Commit everything atomically ─────────────────────────────
    try:
        db.commit()
        db.refresh(item)
        # Load product for response enrichment
        db.refresh(item, attribute_names=["product"])
        return item

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
            detail=f"Failed to update sale item: {str(e)}"
        )



def _attach_payment_totals(sale):
    total_paid = sum(p.amount_paid for p in sale.payments)
    sale.total_paid = total_paid
    sale.balance_due = sale.total_amount - total_paid




def staff_sales_report(
    db: Session,
    current_user: UserDisplaySchema,
    staff_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    business_id: Optional[int] = None
) -> List[schemas.SaleOutStaff]:
    """
    Tenant-aware staff sales report.
    Enriches each sale with staff_name, product_names, payment totals, etc.
    Sorted by sold_at descending (latest first).
    """

    # ─── 1. Base query ─────────────────────────────────────────────
    query = (
        db.query(models.Sale)
        .join(users_models.User, models.Sale.sold_by == users_models.User.id, isouter=True)
        .options(
            joinedload(models.Sale.items).joinedload(models.SaleItem.product),
            joinedload(models.Sale.payments),
            joinedload(models.Sale.user)  # for staff_name
        )
    )

    # ─── 2. Tenant isolation ───────────────────────────────────────
    if "super_admin" in current_user.roles:
        if business_id is not None:
            query = query.filter(models.Sale.business_id == business_id)
    else:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.Sale.business_id == current_user.business_id)

    # ─── 3. Staff filter ──────────────────────────────────────────
    if staff_id is not None:
        query = query.filter(models.Sale.sold_by == staff_id)

    # ─── 4. Date filters (timezone-aware) ────────────────────────
    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=LAGOS_TZ)
        query = query.filter(models.Sale.sold_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=LAGOS_TZ)
        query = query.filter(models.Sale.sold_at <= end_dt)

    # ─── 5. Execute query (no SQL desc() for Python datetime) ─────
    sales = query.all()

    # ─── 6. Sort in Python by sold_at descending ──────────────────
    sales.sort(key=lambda x: x.sold_at, reverse=True)

    # ─── 7. Enrich each sale for response ────────────────────────
    result = []

    for sale in sales:
        _attach_payment_totals(sale)  # your existing helper

        sale.customer_name = sale.customer_name or "Walk-in"
        sale.customer_phone = sale.customer_phone or "-"
        sale.ref_no = sale.ref_no or "-"

        staff_name = sale.user.username if sale.user else "-"

        items = [
            schemas.SaleItemOut(
                id=item.id,
                sale_invoice_no=item.sale_invoice_no,
                product_id=item.product_id,
                product_name=item.product.name if item.product else "-",
                quantity=item.quantity,
                selling_price=float(item.selling_price or 0),
                gross_amount=float(item.gross_amount or 0),
                discount=float(item.discount or 0),
                net_amount=float(item.net_amount or 0),
            )
            for item in sale.items
        ]

        enriched_sale = schemas.SaleOutStaff(
            id=sale.id,
            invoice_no=sale.invoice_no,
            invoice_date=sale.invoice_date,
            customer_name=sale.customer_name,
            customer_phone=sale.customer_phone,
            ref_no=sale.ref_no,
            total_amount=float(sale.total_amount or 0),
            sold_by=sale.sold_by,
            staff_name=staff_name,
            sold_at=sale.sold_at,
            items=items,
            # Add payment fields here if needed
        )

        result.append(enriched_sale)

    return result




from datetime import datetime, timedelta

from sqlalchemy import cast, Date
from datetime import datetime, date


from zoneinfo import ZoneInfo

def outstanding_sales_service(
    db: Session,
    current_user: UserDisplaySchema,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    customer_name: Optional[str] = None,
    business_id: Optional[int] = None
) -> schemas.OutstandingSalesResponse:
    """
    Tenant-aware outstanding sales report.
    Returns only sales with balance > 0, newest transactions first.
    """

    today = datetime.now(LAGOS_TZ).date()

    # Default to current month if no date range provided
    if not start_date and not end_date:
        start_date = today.replace(day=1)
        end_date = today

    # ─── 1. Base query with eager loading ─────────────────────────────
    query = (
        db.query(models.Sale)
        .options(
            joinedload(models.Sale.items).joinedload(models.SaleItem.product),
            joinedload(models.Sale.payments)
        )
    )

    # ─── 2. Tenant isolation ──────────────────────────────────────────
    if "super_admin" in current_user.roles:
        if business_id is not None:
            query = query.filter(models.Sale.business_id == business_id)
    else:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.Sale.business_id == current_user.business_id)

    # ─── 3. Date range filter (timezone-aware) ───────────────────────
    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=LAGOS_TZ)
        query = query.filter(models.Sale.sold_at >= start_dt)
    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=LAGOS_TZ)
        query = query.filter(models.Sale.sold_at <= end_dt)

    # ─── 4. Customer name filter ──────────────────────────────────────
    if customer_name:
        query = query.filter(models.Sale.customer_name.ilike(f"%{customer_name}%"))

    # ─── 5. Execute query ─────────────────────────────────────────────
    sales = query.all()

    # ─── 6. Process results ───────────────────────────────────────────
    sales_list = []
    sales_sum = 0.0
    paid_sum = 0.0
    balance_sum = 0.0

    for sale in sales:
        total_amount = sum(float(item.net_amount or 0) for item in sale.items)
        total_paid = sum(float(p.amount_paid or 0) for p in (sale.payments or []))
        balance = total_amount - total_paid

        if balance <= 0:
            continue  # Skip fully paid sales

        items = [
            schemas.OutstandingSaleItem(
                id=item.id,
                sale_invoice_no=sale.invoice_no,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                quantity=item.quantity or 0,
                selling_price=float(item.selling_price or 0),
                gross_amount=float(item.gross_amount or 0),
                discount=float(item.discount or 0),
                net_amount=float(item.net_amount or 0),
            )
            for item in sale.items
        ]

        sales_list.append(
            schemas.OutstandingSale(
                id=sale.id,
                invoice_no=sale.invoice_no,
                invoice_date=sale.invoice_date,
                customer_name=sale.customer_name or "",
                customer_phone=sale.customer_phone or "",
                ref_no=sale.ref_no or "",
                total_amount=total_amount,
                total_paid=total_paid,
                balance_due=balance,
                items=items,
                sold_at=sale.sold_at.astimezone(LAGOS_TZ)  # Lagos timezone for display and sorting
            )
        )

        sales_sum += total_amount
        paid_sum += total_paid
        balance_sum += balance

    # ─── 7. Sort by sold_at descending (newest first) ───────────────
    sales_list.sort(key=lambda x: x.sold_at, reverse=True)

    # ─── 8. Summary ───────────────────────────────────────────────────
    summary = schemas.OutstandingSummary(
        sales_sum=sales_sum,
        paid_sum=paid_sum,
        balance_sum=balance_sum
    )

    return schemas.OutstandingSalesResponse(
        sales=sales_list,
        summary=summary
    )



# ==============================
# SERVICE
# ==============================
from sqlalchemy import func
from datetime import datetime, time


def sales_analysis(
    db: Session,
    current_user: UserDisplaySchema,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    product_id: Optional[int] = None,
    business_id: Optional[int] = None
) -> schemas.SaleAnalysisOut:
    """
    Tenant-aware sales analysis report.
    Aggregates by product using HISTORICAL cost_price from SaleItem.
    """
    # ─── 1. Base aggregation query ───────────────────────────────────
    query = (
        db.query(
            models.SaleItem.product_id,
            product_models.Product.name.label("product_name"),
            func.sum(models.SaleItem.quantity).label("quantity_sold"),
            func.sum(
                models.SaleItem.selling_price * models.SaleItem.quantity
            ).label("gross_sales"),
            func.sum(models.SaleItem.discount).label("total_discount"),
            func.sum(
                models.SaleItem.cost_price * models.SaleItem.quantity
            ).label("total_cost"),
        )
        .join(
            models.Sale,
            models.Sale.invoice_no == models.SaleItem.sale_invoice_no,
        )
        .join(
            product_models.Product,
            product_models.Product.id == models.SaleItem.product_id
        )
    )

    # ─── 2. Tenant isolation ──────────────────────────────────────────
    if "super_admin" in current_user.roles:
        if business_id is not None:
            query = query.filter(models.Sale.business_id == business_id)
    else:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.Sale.business_id == current_user.business_id)

    # ─── 3. Date filters ──────────────────────────────────────────────
    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=LAGOS_TZ)
        query = query.filter(models.Sale.sold_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=LAGOS_TZ)
        query = query.filter(models.Sale.sold_at <= end_dt)

    # ─── 4. Product filter ────────────────────────────────────────────
    if product_id:
        query = query.filter(models.SaleItem.product_id == product_id)

    # ─── 5. Group & execute ───────────────────────────────────────────
    query = query.group_by(
        models.SaleItem.product_id,
        product_models.Product.name
    )

    results = query.all()

    # ─── 6. Build response items ──────────────────────────────────────
    items = []
    total_sales = 0.0
    total_discount_sum = 0.0
    total_cost_sum = 0.0
    total_margin = 0.0

    for row in results:
        quantity = int(row.quantity_sold or 0)
        if quantity == 0:
            continue  # skip zero-activity products

        gross_sales = float(row.gross_sales or 0.0)
        total_discount = float(row.total_discount or 0.0)
        cost_of_sales = float(row.total_cost or 0.0)

        net_sales = gross_sales - total_discount
        avg_selling_price = gross_sales / quantity if quantity else 0.0
        avg_cost_price = cost_of_sales / quantity if quantity else 0.0

        product_margin = net_sales - cost_of_sales

        total_sales += net_sales
        total_discount_sum += total_discount
        total_cost_sum += cost_of_sales
        total_margin += product_margin

        items.append(
            schemas.SaleAnalysisItem(
                product_id=row.product_id,
                product_name=row.product_name,
                quantity_sold=quantity,
                cost_price=avg_cost_price,
                selling_price=avg_selling_price,
                gross_sales=gross_sales,
                discount=total_discount,
                net_sales=net_sales,
                cost_of_sales=cost_of_sales,
                margin=product_margin
            )
        )

    # ─── 7. Final structured response ─────────────────────────────────
    return schemas.SaleAnalysisOut(
        items=items,
        total_sales=total_sales,
        total_discount=total_discount_sum,
        total_cost_of_sales=total_cost_sum,
        total_margin=total_margin
    )


from datetime import datetime, time

from sqlalchemy.orm import joinedload

def get_sales_by_customer(
    db: Session,
    current_user: UserDisplaySchema,
    customer_name: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    business_id: Optional[int] = None
) -> List[schemas.SaleOut2]:
    """
    Tenant-aware sales list filtered by customer name (partial match).
    Enriches each sale with items, payment totals, status, etc.
    """

    # ─── 1. Base query with eager loading ─────────────────────────────
    query = (
        db.query(models.Sale)
        .options(
            joinedload(models.Sale.items).joinedload(models.SaleItem.product),
            joinedload(models.Sale.payments)
        )
        .filter(models.Sale.customer_name.ilike(f"%{customer_name}%"))
    )

    # ─── 2. Tenant isolation ──────────────────────────────────────────
    if "super_admin" in current_user.roles:
        if business_id is not None:
            query = query.filter(models.Sale.business_id == business_id)
    else:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(models.Sale.business_id == current_user.business_id)

    # ─── 3. Date filters (timezone-aware) ────────────────────────────
    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=LAGOS_TZ)
        query = query.filter(models.Sale.sold_at >= start_dt)
    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=LAGOS_TZ)
        query = query.filter(models.Sale.sold_at <= end_dt)

    # ─── 4. Execute query ─────────────────────────────────────────────
    sales = query.all()

    # ─── 5. Sort in Python by sold_at descending ──────────────────────
    sales.sort(key=lambda x: x.sold_at, reverse=True)

    # ─── 6. Enrich and build response ────────────────────────────────
    sales_list = []

    for sale in sales:
        customer_name_display = sale.customer_name or "Walk-in"
        customer_phone = sale.customer_phone or "-"
        ref_no = sale.ref_no or "-"

        # Enrich items
        items_list = []
        total_amount = 0.0
        total_discount = 0.0

        for item in sale.items:
            product_name = item.product.name if item.product else "-"
            gross_amount = float((item.selling_price or 0) * (item.quantity or 0))
            discount = float(item.discount or 0)
            net_amount = gross_amount - discount

            items_list.append({
                "id": item.id,
                "sale_invoice_no": sale.invoice_no,
                "product_id": item.product_id,
                "product_name": product_name,
                "quantity": item.quantity or 0,
                "selling_price": float(item.selling_price or 0),
                "gross_amount": gross_amount,
                "discount": discount,
                "net_amount": net_amount,
            })

            total_amount += net_amount
            total_discount += discount

        # Payments
        total_paid = sum(float(p.amount_paid or 0) for p in (sale.payments or []))
        balance_due = total_amount - total_paid

        if balance_due <= 0:
            payment_status = "completed"
        elif total_paid == 0:
            payment_status = "pending"
        else:
            payment_status = "part_paid"

        # Build SaleOut2 object
        sales_list.append(
            schemas.SaleOut2(
                id=sale.id,
                invoice_no=sale.invoice_no,
                invoice_date=sale.invoice_date,
                customer_name=customer_name_display,
                customer_phone=customer_phone,
                ref_no=ref_no,
                total_amount=total_amount,
                total_paid=total_paid,
                balance_due=balance_due,
                payment_status=payment_status,
                sold_at=sale.sold_at,
                items=items_list
            )
        )

    return sales_list



def get_receipt_data(
    db: Session,
    invoice_no: int,
    current_user: UserDisplaySchema
) -> Optional[schemas.SaleOut2]:
    """
    Tenant-safe retrieval of sale data for receipt printing.
    Returns enriched SaleOut2 object or None if not found / not authorized.
    """
    # ─── 1. Build query with necessary eager loading ─────────────────
    query = (
        db.query(models.Sale)
        .options(
            joinedload(models.Sale.items)
                .joinedload(models.SaleItem.product),
            joinedload(models.Sale.payments)
        )
        .filter(models.Sale.invoice_no == invoice_no)
    )

    # ─── 2. Apply tenant isolation ───────────────────────────────────
    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        query = query.filter(
            models.Sale.business_id == current_user.business_id
        )

    # ─── 3. Fetch sale ───────────────────────────────────────────────
    sale = query.first()

    if not sale:
        return None

    # ─── 4. Recalculate totals from items (using net_amount) ─────────
    total_amount = sum(float(item.net_amount or 0) for item in sale.items)

    # Payments
    payments = sale.payments or []
    total_paid = sum(float(p.amount_paid or 0) for p in payments)
    balance_due = total_amount - total_paid

    # ─── 5. Determine payment status ─────────────────────────────────
    if total_paid == 0:
        payment_status = "pending"
    elif balance_due > 0:
        payment_status = "part_paid"
    else:
        payment_status = "completed"

    # ─── 6. Build enriched SaleOut2 object ───────────────────────────
    return schemas.SaleOut2(
        id=sale.id,
        invoice_no=sale.invoice_no,
        invoice_date=sale.invoice_date,
        customer_name=sale.customer_name or "Walk-in",
        customer_phone=sale.customer_phone or None,
        ref_no=sale.ref_no or None,
        total_amount=total_amount,
        total_paid=total_paid,
        balance_due=balance_due,
        payment_status=payment_status,
        sold_at=sale.sold_at,
        sold_by=sale.sold_by,
        items=[
            schemas.SaleItemOut2(
                id=item.id,
                sale_invoice_no=item.sale_invoice_no,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                quantity=item.quantity or 0,
                selling_price=float(item.selling_price or 0),
                gross_amount=float(item.gross_amount or 0),
                discount=float(item.discount or 0),
                net_amount=float(item.net_amount or 0),
            )
            for item in sale.items
        ]
    )




def delete_sale(
    db: Session,
    invoice_no: int,
    current_user: UserDisplaySchema
) -> bool:
    """
    Tenant-safe deletion of a sale + restore inventory.
    Returns True if deleted, False if not found / not authorized.
    """
    # ─── 1. Fetch sale with tenant isolation ─────────────────────────
    sale_query = db.query(models.Sale)

    if "super_admin" not in current_user.roles:
        if not current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Current user does not belong to any business"
            )
        sale_query = sale_query.filter(
            models.Sale.business_id == current_user.business_id
        )

    sale = sale_query.filter(
        models.Sale.invoice_no == invoice_no
    ).first()

    if not sale:
        return False

    # ─── 2. Restore inventory for each item ──────────────────────────
    for item in sale.items:
        # Reverse the stock removal (add back the quantity sold)
        inventory_service.add_stock(
            db=db,
            product_id=item.product_id,
            quantity=item.quantity,
            current_user=current_user,
            commit=False  # defer commit
        )

    # ─── 3. Delete the sale ──────────────────────────────────────────
    # (SaleItems cascade-deleted if FK is ON DELETE CASCADE)
    db.delete(sale)

    # ─── 4. Commit atomically ────────────────────────────────────────
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
            detail=f"Failed to delete sale: {str(e)}"
        )





def delete_all_sales_of_business(db: Session, business_id: int) -> int:
    sales = (
        db.query(models.Sale)
        .filter(models.Sale.business_id == business_id)
        .all()
    )

    deleted_count = 0

    for sale in sales:
        # Restore stock
        for item in sale.items:
            inventory_service.add_stock(
                db,
                product_id=item.product_id,
                quantity=item.quantity,
                current_user=None,  # system action
                commit=False
            )

        db.delete(sale)
        deleted_count += 1

    db.commit()
    return deleted_count
