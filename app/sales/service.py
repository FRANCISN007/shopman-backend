from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime
from typing import Optional
from datetime import datetime, time
from datetime import date
from sqlalchemy.orm import joinedload
from sqlalchemy import and_
from app.users.models import User  # adjust import if needed

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




def create_sale_full(
    db: Session,
    sale_data: schemas.SaleFullCreate,
    user_id: int,
):
    """
    Create a sale with all items in one transaction.
    Historical cost price is frozen at the moment of sale.
    """
    warnings = []

    try:
        # 1️⃣ Create Sale Header
        sale = models.Sale(
            invoice_date=sale_data.invoice_date,
            customer_name=sale_data.customer_name,
            customer_phone=sale_data.customer_phone,
            ref_no=sale_data.ref_no,
            sold_by=user_id,
            total_amount=0,
        )
        db.add(sale)
        db.flush()  # ✅ get invoice_no without committing

        total_amount = 0

        # 2️⃣ Process Sale Items
        for item in sale_data.items:

            # 🔹 Validate product
            product = db.query(product_models.Product).filter(
                product_models.Product.id == item.product_id
            ).first()
            if not product:
                raise HTTPException(
                    status_code=404,
                    detail=f"Product {item.product_id} not found",
                )

            # 🔹 Freeze latest purchase cost NOW (historical costing)
            latest_purchase = (
                db.query(purchase_models.Purchase)
                .filter(purchase_models.Purchase.product_id == item.product_id)
                .order_by(purchase_models.Purchase.id.desc())
                .first()
            )
            cost_price = latest_purchase.cost_price if latest_purchase else 0

            # 🔹 Check stock (NO BLOCKING)
            stock = inventory_service.get_inventory_orm_by_product(db, item.product_id)
            if not stock:
                warnings.append(f"No stock record for {product.name}. Sale allowed.")
            elif stock.current_stock < item.quantity:
                warnings.append(
                    f"Insufficient stock for {product.name}. "
                    f"Available: {stock.current_stock}, Sold: {item.quantity}"
                )

            # 🔹 Deduct stock
            inventory_service.remove_stock(db, item.product_id, item.quantity, commit=False)

            # 🔹 Calculate totals
            gross_amount = item.quantity * item.selling_price
            discount = getattr(item, "discount", 0)
            net_amount = gross_amount - discount

            sale_item = models.SaleItem(
                sale_invoice_no=sale.invoice_no,
                product_id=item.product_id,
                quantity=item.quantity,
                selling_price=item.selling_price,
                cost_price=cost_price,  # ✅ HISTORICAL COST SAVED
                gross_amount=gross_amount,
                discount=discount,
                net_amount=net_amount,
                total_amount=net_amount,
            )

            total_amount += net_amount
            db.add(sale_item)

        # 3️⃣ Update Sale Total
        sale.total_amount = total_amount

        db.commit()
        db.refresh(sale)

        # Attach warnings dynamically (not stored in DB)
        sale.warnings = warnings

        return sale

    except Exception:
        db.rollback()
        raise



# ============================================================
# ADD SINGLE ITEM TO EXISTING SALE
# ============================================================

def create_sale_item(db: Session, item: schemas.SaleItemCreate):
    """
    Add a single item to an existing sale.
    Historical cost is frozen at the time of adding the item.
    """
    try:
        sale = db.query(models.Sale).filter(
            models.Sale.invoice_no == item.sale_invoice_no
        ).first()
        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")

        product = db.query(product_models.Product).filter(
            product_models.Product.id == item.product_id
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # 🔹 Freeze historical cost
        latest_purchase = (
            db.query(models.Purchase)
            .filter(models.Purchase.product_id == item.product_id)
            .order_by(models.Purchase.id.desc())
            .first()
        )
        cost_price = latest_purchase.cost_price if latest_purchase else 0

        # 🔹 Validate stock (blocking here)
        stock = inventory_service.get_inventory_orm_by_product(db, item.product_id)
        if not stock or stock.current_stock < item.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        # 🔹 Deduct stock
        inventory_service.remove_stock(db, item.product_id, item.quantity, commit=False)

        # 🔹 Calculate totals
        gross_amount = item.quantity * item.selling_price
        discount = getattr(item, "discount", 0)
        net_amount = gross_amount - discount

        sale_item = models.SaleItem(
            sale_invoice_no=item.sale_invoice_no,
            product_id=item.product_id,
            quantity=item.quantity,
            selling_price=item.selling_price,
            cost_price=cost_price,  # ✅ HISTORICAL COST SAVED
            gross_amount=gross_amount,
            discount=discount,
            net_amount=net_amount,
            total_amount=net_amount,
        )

        # 🔹 Update sale total
        sale.total_amount += net_amount

        db.add(sale_item)
        db.commit()
        db.refresh(sale_item)

        return sale_item

    except Exception:
        db.rollback()
        raise


    




def list_item_sold(
    db: Session,
    start_date: date,
    end_date: date,
    invoice_no: Optional[int] = None,
    product_id: Optional[int] = None,
    product_name: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
):
    query = (
        db.query(models.Sale)
        .options(
            joinedload(models.Sale.items)
            .joinedload(models.SaleItem.product)
        )
        .filter(models.Sale.invoice_date >= start_date)
        .filter(models.Sale.invoice_date <= end_date)
    )

    if invoice_no:
        query = query.filter(models.Sale.invoice_no == invoice_no)

    sales = (
        query
        .order_by(models.Sale.invoice_no.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    total_qty = 0
    total_amount = 0.0
    sales_out: list[SaleOut] = []

    for sale in sales:
        items_out = []

        for item in sale.items:

            # 🔎 PRODUCT FILTERS
            if product_id and item.product_id != product_id:
                continue

            if product_name and (
                not item.product
                or product_name.lower() not in item.product.name.lower()
            ):
                continue

            qty = item.quantity or 0
            gross = item.gross_amount or (qty * item.selling_price)
            discount = item.discount or 0.0
            net = item.net_amount or (gross - discount)

            total_qty += qty
            total_amount += net

            items_out.append(
                SaleItemOut(
                    id=item.id,
                    sale_invoice_no=item.sale_invoice_no,
                    product_id=item.product_id,
                    product_name=item.product.name if item.product else None,
                    quantity=qty,
                    selling_price=item.selling_price,
                    gross_amount=gross,
                    discount=discount,
                    net_amount=net
                )
            )

        # ⛔ Skip sales with no matching items
        if not items_out:
            continue

        sales_out.append(
            SaleOut(
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

    return {
        "sales": sales_out,
        "summary": {
            "total_quantity": total_qty,
            "total_amount": total_amount
        }
    }

def get_all_invoice_numbers(db: Session):
    return [
        i[0]
        for i in db.query(models.Sale.invoice_no)
        .order_by(models.Sale.invoice_no)
        .all()
    ]



def get_sale_by_invoice_no(db: Session, invoice_no: int):
    sale = (
        db.query(models.Sale)
        .options(
            joinedload(models.Sale.items).joinedload(models.SaleItem.product),
            joinedload(models.Sale.payments)
        )
        .filter(models.Sale.invoice_no == invoice_no)
        .first()
    )

    if not sale:
        return None

    # =========================
    # PAYMENT CALCULATION
    # =========================
    total_paid = sum(p.amount_paid for p in sale.payments)
    balance_due = sale.total_amount - total_paid

    # Last payment (for receipt display)
    last_payment = sale.payments[-1] if sale.payments else None

    return {
        "id": sale.id,
        "invoice_no": sale.invoice_no,
        "invoice_date": sale.invoice_date,
        "customer_name": sale.customer_name,
        "customer_phone": sale.customer_phone,
        "ref_no": sale.ref_no,

        # 🔹 totals
        "total_amount": sale.total_amount,
        "amount_paid": total_paid,
        "balance_due": balance_due,

        # 🔹 payment info (USED BY FRONTEND)
        "payment_method": last_payment.payment_method if last_payment else "cash",
        "bank_id": last_payment.bank_id if last_payment else None,

        "payment_status": (
            "paid" if balance_due <= 0 else
            "partial" if total_paid > 0 else
            "unpaid"
        ),

        "sold_at": sale.sold_at,

        # 🔹 items
        "items": [
            {
                "product_id": i.product_id,
                "product_name": i.product.name,
                "quantity": i.quantity,
                "selling_price": i.selling_price,
                "discount": i.discount or 0,
                "gross_amount": i.quantity * i.selling_price,
                "net_amount": (i.quantity * i.selling_price) - (i.discount or 0),
            }
            for i in sale.items
        ]
    }





def list_sales(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    # 🔹 Base query with eager loading (prevents N+1)
    query = (
        db.query(models.Sale)
        .options(
            joinedload(models.Sale.items)
                .joinedload(models.SaleItem.product),
            joinedload(models.Sale.payments),  # ✅ IMPORTANT
        )
    )

    # 🔹 Safe date filters
    try:
        if start_date:
            query = query.filter(
                models.Sale.sold_at >= datetime.combine(start_date, time.min)
            )
        if end_date:
            query = query.filter(
                models.Sale.sold_at <= datetime.combine(end_date, time.max)
            )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date filter: {e}",
        )

    # 🔹 Fetch sales
    sales = (
        query
        .order_by(models.Sale.sold_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    sales_list: list[SaleOut2] = []
    total_sales_amount = 0.0
    total_paid_sum = 0.0
    total_balance_sum = 0.0

    for sale in sales:
        total_amount = float(sale.total_amount or 0)

        payments = sale.payments or []
        total_paid = sum(float(p.amount_paid or 0) for p in payments)
        balance_due = total_amount - total_paid

        # 🔹 Payment status
        if total_paid == 0:
            status = "pending"
        elif balance_due > 0:
            status = "part_paid"
        else:
            status = "completed"

        # 🔹 Sale items with discount & net_amount
        items = [
            SaleItemOut2(
                id=item.id,
                sale_invoice_no=item.sale_invoice_no,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                quantity=item.quantity,
                selling_price=item.selling_price,
                gross_amount=item.gross_amount,  # NEW
                discount=item.discount,          # NEW
                net_amount=item.net_amount,      # NEW
            )
            for item in (sale.items or [])
        ]

        sales_list.append(
            SaleOut2(
                id=sale.id,
                invoice_no=sale.invoice_no,
                invoice_date=sale.invoice_date,
                customer_name=sale.customer_name or "Walk-in",
                customer_phone=sale.customer_phone,
                ref_no=sale.ref_no,
                total_amount=total_amount,
                total_paid=total_paid,
                balance_due=balance_due,
                payment_status=status,
                sold_at=sale.sold_at,
                items=items,
            )
        )

        total_sales_amount += total_amount
        total_paid_sum += total_paid
        total_balance_sum += balance_due

    # 🔹 Summary (ALWAYS returned)
    summary = SaleSummary(
        total_sales=total_sales_amount,
        total_paid=total_paid_sum,
        total_balance=total_balance_sum,
    )

    # ✅ Return predictable structure with updated items
    return {
        "sales": sales_list,
        "summary": summary,
    }


def update_sale(db: Session, invoice_no: int, sale_update: schemas.SaleUpdate):
    sale = (
        db.query(models.Sale)
        .filter(models.Sale.invoice_no == invoice_no)
        .first()
    )

    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    update_data = sale_update.dict(exclude_unset=True)

    # 🔥 Prevent updating invoice number
    if "invoice_no" in update_data:
        raise HTTPException(
            status_code=400,
            detail="Invoice number cannot be updated"
        )

    # Update header fields
    for field, value in update_data.items():
        setattr(sale, field, value)

    # Recalculate totals from sale items (net_amount now)
    sale.total_amount = sum(item.net_amount for item in sale.items)
    total_paid = sum(p.amount_paid for p in sale.payments or [])
    sale.balance_due = sale.total_amount - total_paid

    db.commit()
    db.refresh(sale)

    return sale




def update_sale_item(
    db: Session,
    invoice_no: int,
    item_update: schemas.SaleItemUpdate
):
    """
    Update a sale item by invoice number.
    Allows changing:
      - product_id
      - quantity
      - selling_price
      - discount
    Automatically recalculates net_amount and sale totals.
    """

    # Fetch sale item by invoice_no + optional old_product_id
    query = db.query(models.SaleItem).filter(models.SaleItem.sale_invoice_no == invoice_no)
    if item_update.old_product_id is not None:
        query = query.filter(models.SaleItem.product_id == item_update.old_product_id)

    item = query.first()
    if not item:
        raise HTTPException(status_code=404, detail="Sale item not found for this invoice")

    # Update product_id (prevent duplicates)
    if item_update.product_id is not None:
        existing_item = db.query(models.SaleItem).filter(
            models.SaleItem.sale_invoice_no == invoice_no,
            models.SaleItem.product_id == item_update.product_id
        ).first()
        if existing_item and existing_item.id != item.id:
            raise HTTPException(
                status_code=400,
                detail="This product already exists in the invoice"
            )
        item.product_id = item_update.product_id

    # Update quantity, selling_price, discount
    if item_update.quantity is not None:
        item.quantity = item_update.quantity
    if item_update.selling_price is not None:
        item.selling_price = item_update.selling_price
    if getattr(item_update, "discount", None) is not None:
        item.discount = item_update.discount

    # Recalculate amounts
    item.gross_amount = item.quantity * item.selling_price
    item.net_amount = item.gross_amount - (item.discount or 0)
    item.total_amount = item.net_amount  # keep total_amount for backward compatibility

    # Update sale total_amount and balance_due
    sale = db.query(models.Sale).filter(models.Sale.invoice_no == invoice_no).first()
    if sale:
        sale.total_amount = sum(i.net_amount for i in sale.items)
        total_paid = sum(p.amount_paid for p in sale.payments or [])
        sale.balance_due = sale.total_amount - total_paid

    db.commit()
    db.refresh(item)

    return item




def _attach_payment_totals(sale):
    total_paid = sum(p.amount_paid for p in sale.payments)
    sale.total_paid = total_paid
    sale.balance_due = sale.total_amount - total_paid





def staff_sales_report(
    db: Session,
    staff_id: Optional[int] = None,
    start_date=None,
    end_date=None
):
    query = (
        db.query(models.Sale)
        .join(User, models.Sale.sold_by == User.id)
        .options(
            joinedload(models.Sale.items)
            .joinedload(models.SaleItem.product)
        )
    )

    # Filter by staff (user)
    if staff_id:
        query = query.filter(models.Sale.sold_by == staff_id)

    # Date filters
    if start_date:
        query = query.filter(
            models.Sale.sold_at >= datetime.combine(start_date, time.min)
        )

    if end_date:
        query = query.filter(
            models.Sale.sold_at <= datetime.combine(end_date, time.max)
        )

    sales = query.order_by(models.Sale.sold_at.desc()).all()

    for sale in sales:
        _attach_payment_totals(sale)

        sale.customer_name = sale.customer_name or "Walk-in"
        sale.customer_phone = sale.customer_phone or "-"
        sale.ref_no = sale.ref_no or "-"

        # 🔥 Attach staff name from User
        sale.staff_name = (
            sale.user.username
            if sale.user else "-"
        )


        for item in sale.items:
            item.product_name = item.product.name if item.product else "-"

    return sales




from datetime import datetime, timedelta

from sqlalchemy import cast, Date
from datetime import datetime, date

def outstanding_sales_service(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
    customer_name: str | None = None
):
    today = datetime.now().date()
    
    if not start_date and not end_date:
        start_date = today.replace(day=1)
        end_date = today


    query = db.query(models.Sale).filter(models.Sale.sold_at != None)

    query = query.filter(
        cast(models.Sale.sold_at, Date) >= start_date,
        cast(models.Sale.sold_at, Date) <= end_date
    )

    if customer_name:
        query = query.filter(models.Sale.customer_name.ilike(f"%{customer_name}%"))

    sales = query.all()

    sales_list = []
    sales_sum = 0.0
    paid_sum = 0.0
    balance_sum = 0.0

    for sale in sales:
        # ✅ NET total from items
        total_amount = sum((item.net_amount or 0) for item in sale.items)

        total_paid = sum((p.amount_paid or 0) for p in sale.payments)
        balance = total_amount - total_paid

        if balance <= 0:
            continue  # skip fully paid

        items = []
        for item in sale.items:
            items.append({
                "id": item.id,
                "sale_invoice_no": sale.invoice_no,
                "product_id": item.product_id,
                "product_name": item.product.name if item.product else None,
                "quantity": item.quantity or 0,
                "selling_price": item.selling_price or 0.0,
                "gross_amount": item.gross_amount or 0.0,
                "discount": item.discount or 0.0,
                "net_amount": item.net_amount or 0.0,
            })

        sales_list.append({
            "id": sale.id,
            "invoice_no": sale.invoice_no,
            "invoice_date": sale.invoice_date,
            "customer_name": sale.customer_name or "",
            "customer_phone": sale.customer_phone or "",
            "ref_no": sale.ref_no or "",
            "total_amount": total_amount,     # ✅ NET
            "total_paid": total_paid,
            "balance_due": balance,
            "items": items
        })

        sales_sum += total_amount
        paid_sum += total_paid
        balance_sum += balance

    return {
        "sales": sales_list,
        "summary": {
            "sales_sum": sales_sum,
            "paid_sum": paid_sum,
            "balance_sum": balance_sum
        }
    }




# ==============================
# SERVICE
# ==============================
from sqlalchemy import func
from datetime import datetime, time


def sales_analysis(db: Session, start_date=None, end_date=None, product_id=None):
    """
    Sales analysis based on HISTORICAL COST stored in SaleItem.
    Ensures past margins never change when purchase prices change.
    """

    # ==============================
    # BASE QUERY
    # ==============================
    query = (
        db.query(
            models.SaleItem.product_id,
            Product.name.label("product_name"),
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
        .join(Product, Product.id == models.SaleItem.product_id)
    )

    # ==============================
    # DATE FILTERS
    # ==============================
    if start_date:
        query = query.filter(
            models.Sale.sold_at >= datetime.combine(start_date, time.min)
        )

    if end_date:
        query = query.filter(
            models.Sale.sold_at <= datetime.combine(end_date, time.max)
        )

    # ==============================
    # PRODUCT FILTER
    # ==============================
    if product_id:
        query = query.filter(models.SaleItem.product_id == product_id)

    # ==============================
    # GROUP BY
    # ==============================
    query = query.group_by(
        models.SaleItem.product_id,
        Product.name,
    )

    results = query.all()

    # ==============================
    # BUILD RESPONSE
    # ==============================
    items = []
    total_sales = 0.0
    total_discount_sum = 0.0
    total_cost_sum = 0.0
    total_margin = 0.0

    for row in results:
        quantity = int(row.quantity_sold or 0)
        gross_sales = float(row.gross_sales or 0.0)
        total_discount = float(row.total_discount or 0.0)
        cost_of_sales = float(row.total_cost or 0.0)

        net_sales = gross_sales - total_discount
        avg_selling_price = gross_sales / quantity if quantity else 0.0
        avg_cost_price = cost_of_sales / quantity if quantity else 0.0

        # ✅ Margin formula
        product_margin = net_sales - cost_of_sales

        total_sales += net_sales
        total_discount_sum += total_discount
        total_cost_sum += cost_of_sales
        total_margin += product_margin

        items.append(
            {
                "product_id": row.product_id,
                "product_name": row.product_name,
                "quantity_sold": quantity,
                "cost_price": avg_cost_price,
                "selling_price": avg_selling_price,
                "gross_sales": gross_sales,
                "discount": total_discount,
                "net_sales": net_sales,
                "cost_of_sales": cost_of_sales,
                "margin": product_margin,
            }
        )

    # ==============================
    # FINAL RESPONSE
    # ==============================
    return {
        "items": items,
        "total_sales": total_sales,
        "total_discount": total_discount_sum,
        "total_cost_of_sales": total_cost_sum,
        "total_margin": total_margin,
    }



from datetime import datetime, time

from sqlalchemy.orm import joinedload

def get_sales_by_customer(
    db: Session,
    customer_name: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None
):
    if not customer_name or not customer_name.strip():
        return []

    query = (
        db.query(models.Sale)
        .options(
            joinedload(models.Sale.items)
            .joinedload(models.SaleItem.product),
            joinedload(models.Sale.payments)  # ✅ load payments
        )
        .filter(models.Sale.customer_name.ilike(f"%{customer_name.strip()}%"))
    )

    if start_date:
        query = query.filter(models.Sale.sold_at >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.filter(models.Sale.sold_at <= datetime.combine(end_date, time.max))

    sales = query.order_by(models.Sale.sold_at.desc()).all()
    sales_list = []

    for sale in sales:
        sale.customer_name = sale.customer_name or "Walk-in"
        sale.customer_phone = sale.customer_phone or "-"
        sale.ref_no = sale.ref_no or "-"

        items_list = []
        total_amount = 0
        total_discount = 0

        for item in sale.items:
            product_name = item.product.name if item.product else "-"
            gross_amount = (item.selling_price or 0) * (item.quantity or 0)
            discount = item.discount or 0
            net_amount = gross_amount - discount

            items_list.append({
                "id": item.id,
                "sale_invoice_no": sale.invoice_no,
                "product_id": item.product_id,
                "product_name": product_name,
                "quantity": item.quantity or 0,
                "selling_price": item.selling_price or 0,
                "gross_amount": gross_amount,
                "discount": discount,
                "net_amount": net_amount,
            })

            total_amount += net_amount
            total_discount += discount

        # ✅ Calculate total paid
        total_paid = sum(p.amount_paid or 0 for p in sale.payments)
        balance_due = total_amount - total_paid

        # Payment status
        if balance_due <= 0:
            payment_status = "completed"
        elif total_paid == 0:
            payment_status = "pending"
        else:
            payment_status = "part_paid"

        sales_list.append({
            "id": sale.id,
            "invoice_no": sale.invoice_no,
            "invoice_date": sale.invoice_date,
            "customer_name": sale.customer_name,
            "customer_phone": sale.customer_phone,
            "ref_no": sale.ref_no,
            "total_amount": total_amount,
            "total_paid": total_paid,
            "balance_due": balance_due,
            "payment_status": payment_status,
            "sold_at": sale.sold_at,
            "items": items_list
        })

    return sales_list





def delete_sale(db: Session, invoice_no: int):
    # 1️⃣ Fetch sale by invoice_no
    sale = db.query(models.Sale).filter(models.Sale.invoice_no == invoice_no).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    # 2️⃣ Restore inventory for each sale item
    for item in sale.items:
        inventory = inventory_service.get_inventory_orm_by_product(db, item.product_id)
        if inventory:
            inventory.quantity_out -= item.quantity
            inventory.current_stock = (
                inventory.quantity_in - inventory.quantity_out + inventory.adjustment_total
            )
            db.add(inventory)

    # 3️⃣ Delete sale (SaleItems will be deleted automatically if FK is ON DELETE CASCADE)
    db.delete(sale)
    db.commit()

    return {"detail": f"Sale {invoice_no} deleted successfully"}






def delete_all_sales(db: Session):
    sales = db.query(models.Sale).all()

    if not sales:
        return {
            "message": "No sales to delete",
            "deleted_count": 0
        }

    deleted_count = 0

    for sale in sales:
        # 1️⃣ Restore inventory for each sale item
        for item in sale.items:
            inventory = inventory_service.get_inventory_orm_by_product(
                db, item.product_id
            )
            if inventory:
                inventory.quantity_out -= item.quantity
                inventory.current_stock = (
                    inventory.quantity_in
                    - inventory.quantity_out
                    + inventory.adjustment_total
                )
                db.add(inventory)

        # 2️⃣ Delete sale (SaleItems cascade if FK is ON DELETE CASCADE)
        db.delete(sale)
        deleted_count += 1

    # 3️⃣ OPTIONAL: reset invoice number sequence
    # ⚠️ Only do this if you REALLY want invoices to restart
    db.execute(
        text("ALTER SEQUENCE sales_invoice_no_seq RESTART WITH 1")
    )

    db.commit()

    return {
        "message": "All sales deleted successfully and stock restored",
        "deleted_count": deleted_count
    }

