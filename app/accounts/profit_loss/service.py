# app/reports/profit_loss/service.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, time
from fastapi import HTTPException
from typing import List, Optional

from app.sales import models as sales_models
from app.stock.products import models as product_models
from app.accounts.expenses import models as expense_models
from app.stock.category import models as category_models
from app.users.schemas import UserDisplaySchema
from app.accounts.profit_loss.schemas import ProfitLossResponse
from app.stock.inventory.adjustments import models as adjustments_models

from zoneinfo import ZoneInfo
LAGOS_TZ = ZoneInfo("Africa/Lagos")



def get_profit_and_loss(
    db: Session,
    current_user: UserDisplaySchema,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    business_id: Optional[int] = None
) -> ProfitLossResponse:

    today = datetime.utcnow()

    if start_date is None:
        start_date = date(today.year, today.month, 1)
    if end_date is None:
        end_date = date(today.year, today.month, today.day)

    start_dt = datetime.combine(start_date, time.min, tzinfo=LAGOS_TZ)
    end_dt   = datetime.combine(end_date, time.max, tzinfo=LAGOS_TZ)

    sale_filter = []
    expense_filter = []
    adjustment_filter = []

    # ───────────────── Tenant Filtering ─────────────────
    if "super_admin" in current_user.roles:
        if business_id is not None:
            sale_filter.append(sales_models.Sale.business_id == business_id)
            expense_filter.append(expense_models.Expense.business_id == business_id)
            adjustment_filter.append(adjustments_models.StockAdjustment.business_id == business_id)
    else:
        if not current_user.business_id:
            raise HTTPException(403, "Current user does not belong to any business")

        sale_filter.append(sales_models.Sale.business_id == current_user.business_id)
        expense_filter.append(expense_models.Expense.business_id == current_user.business_id)
        adjustment_filter.append(adjustments_models.StockAdjustment.business_id == current_user.business_id)

    # ───────────────── Revenue ─────────────────
    revenue_query = (
        db.query(
            category_models.Category.name.label("category"),
            func.sum(
                sales_models.SaleItem.quantity * sales_models.SaleItem.selling_price
            ).label("revenue")
        )
        .join(sales_models.Sale, sales_models.Sale.invoice_no == sales_models.SaleItem.sale_invoice_no)
        .join(product_models.Product, product_models.Product.id == sales_models.SaleItem.product_id)
        .join(category_models.Category, category_models.Category.id == product_models.Product.category_id)
        .filter(
            sales_models.Sale.sold_at >= start_dt,
            sales_models.Sale.sold_at <= end_dt,
            *sale_filter
        )
        .group_by(category_models.Category.name)
    )

    revenue_rows = revenue_query.all()
    revenue = {row.category: float(row.revenue or 0) for row in revenue_rows}
    total_revenue = sum(revenue.values())

    # ───────────────── Normal Cost of Sales (from sales) ─────────────────
    cos_query = (
        db.query(
            func.sum(
                sales_models.SaleItem.quantity * sales_models.SaleItem.cost_price
            ).label("cos")
        )
        .join(sales_models.Sale, sales_models.Sale.invoice_no == sales_models.SaleItem.sale_invoice_no)
        .filter(
            sales_models.Sale.sold_at >= start_dt,
            sales_models.Sale.sold_at <= end_dt,
            *sale_filter
        )
        .scalar()
    )

    normal_cost_of_sales = float(cos_query or 0)

    # ───────────────── Stock Adjustment Loss ─────────────────
    adjustment_loss_query = (
        db.query(
            func.sum(
                func.abs(adjustments_models.StockAdjustment.quantity) *
                product_models.Product.cost_price
            ).label("adjustment_loss")
        )
        .select_from(adjustments_models.StockAdjustment)  # 🔥 IMPORTANT
        .join(
            product_models.Product,
            product_models.Product.id == adjustments_models.StockAdjustment.product_id
        )
        .filter(
            adjustments_models.StockAdjustment.adjusted_at >= start_dt,
            adjustments_models.StockAdjustment.adjusted_at <= end_dt,
            adjustments_models.StockAdjustment.quantity < 0,
            *adjustment_filter
        )
        .scalar()
    )


    stock_adjustment_loss = float(adjustment_loss_query or 0)

    # ───────────────── Final Cost of Sales ─────────────────
    cost_of_sales = normal_cost_of_sales 

    gross_profit = total_revenue - cost_of_sales - stock_adjustment_loss

    # ───────────────── Expenses ─────────────────
    expense_query = (
        db.query(
            expense_models.Expense.account_type.label("account_type"),
            func.sum(expense_models.Expense.amount).label("total")
        )
        .filter(
            expense_models.Expense.expense_date >= start_dt,
            expense_models.Expense.expense_date <= end_dt,
            expense_models.Expense.is_active == True,
            *expense_filter
        )
        .group_by(expense_models.Expense.account_type)
    )

    expense_rows = expense_query.all()
    expenses = {row.account_type: float(row.total or 0) for row in expense_rows}
    total_expenses = sum(expenses.values())

    net_profit = gross_profit - total_expenses

    return ProfitLossResponse(
        period={
            "start_date": start_dt,
            "end_date": end_dt
        },
        revenue=revenue,
        total_revenue=total_revenue,
        cost_of_sales=cost_of_sales,
        gross_profit=gross_profit,
        expenses=expenses,
        total_expenses=total_expenses,
        net_profit=net_profit,

        # 🔥 OPTIONAL: show separately for transparency
        stock_adjustment_loss=stock_adjustment_loss
    )
