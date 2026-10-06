"""Dashboard figures - all values are read from the live database."""
from __future__ import annotations

from ..core.db import row, rows, scalar
from ..core.money import format_minor


class DashboardService:
    def __init__(self, db, settings, reports, inventory, expenses):
        self.db = db
        self.settings = settings
        self.reports = reports
        self.inventory = inventory
        self.expenses = expenses

    def stats(self) -> dict:
        today = "date('now','localtime')"
        with self.db.read() as conn:
            sales_today = row(
                conn,
                "SELECT COUNT(*) AS transactions, COALESCE(SUM(total),0) AS total "
                "FROM sales WHERE status IN ('completed','partially_returned') "
                f"AND date(created_at) = {today}",
            ) or {}
            refunds_today = scalar(
                conn,
                "SELECT COALESCE(SUM(total),0) FROM returns WHERE status='completed' "
                f"AND date(created_at) = {today}",
                (), 0,
            )
            cogs_today = scalar(
                conn,
                "SELECT COALESCE(SUM(si.cost_price * (si.quantity - si.returned_qty)),0) "
                "FROM sale_items si JOIN sales s ON s.id = si.sale_id "
                f"WHERE s.status IN ('completed','partially_returned') "
                f"AND date(s.created_at) = {today}",
                (), 0,
            )
            products_total = int(scalar(
                conn, "SELECT COUNT(*) FROM products WHERE is_active = 1", (), 0))
            customers_total = int(scalar(
                conn, "SELECT COUNT(*) FROM customers WHERE active = 1", (), 0))
            recent = rows(
                conn,
                "SELECT s.invoice_no, s.created_at, s.total, s.payment_method, s.status, "
                "s.cashier_name, COALESCE(cu.name,'Walk-in Customer') AS customer "
                "FROM sales s LEFT JOIN customers cu ON cu.id = s.customer_id "
                "ORDER BY s.id DESC LIMIT 8",
            )
            month = row(
                conn,
                "SELECT COUNT(*) AS transactions, COALESCE(SUM(total),0) AS total "
                "FROM sales WHERE status IN ('completed','partially_returned') "
                "AND strftime('%Y-%m', created_at) = strftime('%Y-%m','now','localtime')",
            ) or {}
        alerts = self.inventory.stock_alerts()
        from datetime import date as _date
        _today = _date.today().isoformat()
        expenses_today = self.expenses.total_between(_today, _today)
        net_sales = int(sales_today.get("total", 0) or 0) - int(refunds_today)
        return {
            "today_total": net_sales,
            "today_gross": int(sales_today.get("total", 0) or 0),
            "today_transactions": int(sales_today.get("transactions", 0) or 0),
            "today_profit": net_sales - int(cogs_today),
            "today_expenses": expenses_today,
            "month_total": int(month.get("total", 0) or 0),
            "month_transactions": int(month.get("transactions", 0) or 0),
            "products_total": products_total,
            "customers_total": customers_total,
            "low_stock": alerts["low"],
            "out_of_stock": alerts["out"],
            "recent": recent,
            "currency": self.settings.currency,
        }
