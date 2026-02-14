from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from app.sales import models as sales_models
from app.stock.products import models as product_models
from app.purchase import models as purchase_models
from app.accounts.expenses import models as expense_models
import calendar

from app.stock.category import models as category_models

def get_profit_and_loss(
    db: Session,
    start_date: datetime | None = None,
    end_date: datetime | None = None
):
    """
    Returns P&L report.
    - Defaults to current month if dates are not provided
    - Supports same-day ranges (e.g. 2015-12-20 → 2015-12-20)
    """

    # -------------------------
    # Date handling
    # -------------------------
    today = datetime.utcnow()

    if start_date is None:
        start_date = datetime(today.year, today.month, 1)

    if end_date is None:
        end_date = datetime(today.year, today.month, today.day, 23, 59, 59)
    else:
        # 🔥 Ensure full-day inclusion
        end_date = end_date.replace(hour=23, minute=59, second=59)

    # -------------------------
    # 1. Revenue by category
    # -------------------------
    

    revenue_query = (
        db.query(
            category_models.Category.name.label("category"),
            func.sum(
                sales_models.SaleItem.quantity *
                sales_models.SaleItem.selling_price
            ).label("revenue")
        )
        .select_from(sales_models.SaleItem)
        .join(
            sales_models.Sale,
            sales_models.Sale.invoice_no == sales_models.SaleItem.sale_invoice_no
        )
        .join(
            product_models.Product,
            product_models.Product.id == sales_models.SaleItem.product_id
        )
        .join(
            category_models.Category,
            category_models.Category.id == product_models.Product.category_id
        )
        .filter(
            sales_models.Sale.sold_at >= start_date,
            sales_models.Sale.sold_at <= end_date
        )
        .group_by(category_models.Category.name)
        .all()
    )




    revenue = {row.category: row.revenue for row in revenue_query}
    total_revenue = sum(revenue.values()) if revenue else 0

    # -------------------------
    # 2. Cost of Sales (from Purchase)
    # -------------------------
    latest_purchase = (
        db.query(
            purchase_models.Purchase.product_id,
            func.max(purchase_models.Purchase.purchase_date).label("latest_date")
        )
        .group_by(purchase_models.Purchase.product_id)
        .subquery()
    )

    cos_query = (
        db.query(
            func.sum(
                purchase_models.Purchase.cost_price *
                sales_models.SaleItem.quantity
            ).label("cos")
        )
        .select_from(sales_models.SaleItem)
        .join(
            sales_models.Sale,
            sales_models.Sale.invoice_no == sales_models.SaleItem.sale_invoice_no
        )
        .join(
            purchase_models.Purchase,
            purchase_models.Purchase.product_id == sales_models.SaleItem.product_id
        )
        .join(
            latest_purchase,
            (latest_purchase.c.product_id == purchase_models.Purchase.product_id)
            & (latest_purchase.c.latest_date == purchase_models.Purchase.purchase_date)
        )
        .filter(
            sales_models.Sale.sold_at >= start_date,
            sales_models.Sale.sold_at <= end_date
        )
        .first()
    )


    cost_of_sales = cos_query.cos or 0
    gross_profit = total_revenue - cost_of_sales

    # -------------------------
    # 3. Expenses
    # -------------------------
    expense_query = (
        db.query(
            expense_models.Expense.account_type.label("account_type"),
            func.sum(expense_models.Expense.amount).label("total")
        )

        .filter(
            expense_models.Expense.expense_date >= start_date,
            expense_models.Expense.expense_date <= end_date
        )
        .group_by(expense_models.Expense.account_type)
        .all()
    )

    expenses = {row.account_type: row.total for row in expense_query}
    total_expenses = sum(expenses.values()) if expenses else 0

    # -------------------------
    # 4. Net Profit
    # -------------------------
    net_profit = gross_profit - total_expenses

    # -------------------------
    # 5. Report
    # -------------------------
    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date
        },
        "revenue": revenue,
        "total_revenue": total_revenue,
        "cost_of_sales": cost_of_sales,
        "gross_profit": gross_profit,
        "expenses": expenses,
        "total_expenses": total_expenses,
        "net_profit": net_profit
    }