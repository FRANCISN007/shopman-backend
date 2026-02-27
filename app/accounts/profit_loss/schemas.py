# app/reports/schemas.py
from pydantic import BaseModel
from datetime import datetime
from typing import Dict


class ProfitLossPeriod(BaseModel):
    start_date: datetime
    end_date: datetime


class ProfitLossResponse(BaseModel):
    period: ProfitLossPeriod
    revenue: Dict[str, float]          # category_name → revenue
    total_revenue: float
    cost_of_sales: float
    gross_profit: float
    expenses: Dict[str, float]         # account_type → expense total
    total_expenses: float
    net_profit: float

    class Config:
        from_attributes = True