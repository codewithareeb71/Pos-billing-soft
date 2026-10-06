"""Reporting engine - every figure comes straight from the database."""
from __future__ import annotations

from ..core.db import rows, row, scalar
from .. import config


def _range(date_from: str, date_to: str) -> tuple[str, str]:
    date_from = (date_from or "").strip() or "1970-01-01"
    date_to = (date_to or "").strip() or "2999-12-31"
    return date_from, date_to


SALES_WHERE = ("s.status IN ('completed','partially_returned') "
               "AND date(s.created_at) >= date(?) AND date(s.created_at) <= date(?)")


class ReportService:
    def __init__(self, db, settings=None, expenses=None, purchases=None):
        self.db = db
        self.settings = settings
        self.expenses = expenses
        self.purchases = purchases

    # ---------------------------------------------------------- sales
    def sales_summary(self, date_from: str, date_to: str) -> dict:
        date_from, date_to = _range(date_from, date_to)
        with self.db.read() as conn:
            summary = row(
                conn,
                "SELECT COUNT(*) AS transactions, "
                "COALESCE(SUM(subtotal),0) AS gross, "
                "COALESCE(SUM(item_discount),0) AS item_discounts, "
                "COALESCE(SUM(bill_discount),0) AS bill_discounts, "
                "COALESCE(SUM(total),0) AS total, COALESCE(SUM(paid),0) AS paid "
                f"FROM sales s WHERE {SALES_WHERE}",
                (date_from, date_to),
            ) or {}
            refunds = scalar(
                conn,
                "SELECT COALESCE(SUM(total),0) FROM returns "
                "WHERE status='completed' AND date(created_at) >= date(?) "
                "AND date(created_at) <= date(?)",
                (date_from, date_to), 0,
            )
            voided = scalar(
                conn,
                "SELECT COUNT(*) FROM sales WHERE status='voided' "
                "AND date(created_at) >= date(?) AND date(created_at) <= date(?)",
                (date_from, date_to), 0,
            )
            cogs = scalar(
                conn,
                "SELECT COALESCE(SUM(si.cost_price * (si.quantity - si.returned_qty)),0) "
                "FROM sale_items si JOIN sales s ON s.id = si.sale_id "
                f"WHERE {SALES_WHERE}",
                (date_from, date_to), 0,
            )
            by_method = rows(
                conn,
                "SELECT payment_method, COUNT(*) AS transactions, SUM(total) AS total "
                f"FROM sales s WHERE {SALES_WHERE} GROUP BY payment_method ORDER BY total DESC",
                (date_from, date_to),
            )
        net_sales = int(summary.get("total", 0)) - int(refunds)
        gross_profit = net_sales - int(cogs)
        expenses = (self.expenses.total_between(date_from, date_to)
                    if self.expenses else 0)
        return {
            "date_from": date_from,
            "date_to": date_to,
            "transactions": int(summary.get("transactions", 0) or 0),
            "gross": int(summary.get("gross", 0) or 0),
            "item_discounts": int(summary.get("item_discounts", 0) or 0),
            "bill_discounts": int(summary.get("bill_discounts", 0) or 0),
            "total": int(summary.get("total", 0) or 0),
            "paid": int(summary.get("paid", 0) or 0),
            "refunds": int(refunds),
            "net_sales": net_sales,
            "cogs": int(cogs),
            "gross_profit": gross_profit,
            "expenses": int(expenses),
            "net_profit": gross_profit - int(expenses),
            "voided": int(voided),
            "by_method": by_method,
            "avg_basket": int(net_sales // summary["transactions"]) if summary.get("transactions") else 0,
        }

    def sales_by_day(self, date_from: str, date_to: str) -> list[dict]:
        date_from, date_to = _range(date_from, date_to)
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT date(created_at) AS day, COUNT(*) AS transactions, "
                "SUM(total) AS total, SUM(item_discount + bill_discount) AS discounts "
                f"FROM sales s WHERE {SALES_WHERE} GROUP BY day ORDER BY day",
                (date_from, date_to),
            )

    def sales_by_invoice(self, date_from: str, date_to: str, limit: int = 5000) -> list[dict]:
        date_from, date_to = _range(date_from, date_to)
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT s.invoice_no, s.created_at, s.total, s.payment_method, s.status, "
                "s.cashier_name, COALESCE(cu.name,'Walk-in Customer') AS customer, "
                "(SELECT COUNT(*) FROM sale_items si WHERE si.sale_id = s.id) AS items "
                "FROM sales s LEFT JOIN customers cu ON cu.id = s.customer_id "
                f"WHERE {SALES_WHERE} ORDER BY s.id DESC LIMIT ?",
                (date_from, date_to, limit),
            )

    # -------------------------------------------------- product performance
    def product_sales(self, date_from: str, date_to: str) -> list[dict]:
        date_from, date_to = _range(date_from, date_to)
        with self.db.read() as conn:
            result = rows(
                conn,
                "SELECT si.product_id, si.product_name, si.sku, "
                "SUM(si.quantity) AS quantity, SUM(si.returned_qty) AS returned, "
                "SUM(si.line_total) AS gross, SUM(si.discount_amount) AS discounts, "
                "SUM(si.line_total - si.discount_amount) AS net, "
                "SUM(si.cost_price * si.quantity) AS cost "
                "FROM sale_items si JOIN sales s ON s.id = si.sale_id "
                f"WHERE {SALES_WHERE} GROUP BY si.product_id, si.product_name "
                "ORDER BY net DESC",
                (date_from, date_to),
            )
        for record in result:
            qty = float(record["quantity"] or 0)
            returned = float(record["returned"] or 0)
            net = int(record["net"] or 0)
            cost = int(record["cost"] or 0)
            # remove the cost/revenue of returned units
            if qty > 0 and returned:
                factor = (qty - returned) / qty
                net = int(round(net * factor))
                cost = int(round(cost * factor))
            record["net"] = net
            record["cost"] = cost
            record["profit"] = net - cost
            record["quantity_net"] = round(qty - returned, 3)
        return result

    # --------------------------------------------------------- purchases
    def purchases_report(self, date_from: str, date_to: str) -> list[dict]:
        date_from, date_to = _range(date_from, date_to)
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT p.purchase_no, p.purchase_date, p.total, p.paid, p.balance, "
                "p.status, COALESCE(s.name,'(No supplier)') AS supplier, "
                "(SELECT COUNT(*) FROM purchase_items pi WHERE pi.purchase_id = p.id) AS items "
                "FROM purchases p LEFT JOIN suppliers s ON s.id = p.supplier_id "
                "WHERE date(p.purchase_date) >= date(?) AND date(p.purchase_date) <= date(?) "
                "ORDER BY p.id DESC",
                (date_from, date_to),
            )

    # ---------------------------------------------------------- inventory
    def inventory_report(self) -> list[dict]:
        with self.db.read() as conn:
            result = rows(
                conn,
                "SELECT p.id, p.name, p.sku, p.barcode, p.purchase_price, p.selling_price, "
                "p.min_stock, p.max_stock, COALESCE(i.quantity,0) AS stock, "
                "c.name AS category, b.name AS brand, s.name AS supplier, "
                "u.short_code AS unit_short, p.is_active "
                "FROM products p "
                "LEFT JOIN inventory i ON i.product_id = p.id "
                "LEFT JOIN categories c ON c.id = p.category_id "
                "LEFT JOIN brands b ON b.id = p.brand_id "
                "LEFT JOIN suppliers s ON s.id = p.supplier_id "
                "LEFT JOIN units u ON u.id = p.unit_id "
                "ORDER BY p.name",
            )
        for record in result:
            stock = float(record["stock"] or 0)
            record["stock_value"] = int(round(stock * int(record["purchase_price"] or 0)))
            record["retail_value"] = int(round(stock * int(record["selling_price"] or 0)))
            if stock <= 0:
                record["status"] = "Out of stock"
            elif stock <= float(record["min_stock"] or 0):
                record["status"] = "Low stock"
            else:
                record["status"] = "In stock"
        return result

    # ---------------------------------------------------------- customers
    def customers_report(self) -> list[dict]:
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT c.id, c.name, c.phone, c.email, c.address, "
                "COUNT(s.id) AS visits, COALESCE(SUM(s.total),0) AS spent, "
                "MAX(s.created_at) AS last_visit "
                "FROM customers c LEFT JOIN sales s ON s.customer_id = c.id "
                "AND s.status != 'voided' GROUP BY c.id ORDER BY spent DESC",
            )

    def suppliers_report(self) -> list[dict]:
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT s.id, s.name, s.company, s.phone, "
                "COUNT(p.id) AS purchases, COALESCE(SUM(p.total),0) AS purchased, "
                "COALESCE(SUM(p.balance),0) AS outstanding, MAX(p.purchase_date) AS last_purchase "
                "FROM suppliers s LEFT JOIN purchases p ON p.supplier_id = s.id "
                "GROUP BY s.id ORDER BY purchased DESC",
            )

    # ------------------------------------------------------------ cashier
    def cashier_performance(self, date_from: str, date_to: str) -> list[dict]:
        date_from, date_to = _range(date_from, date_to)
        with self.db.read() as conn:
            result = rows(
                conn,
                "SELECT s.user_id, s.cashier_name AS cashier, COUNT(*) AS transactions, "
                "SUM(s.total) AS total, SUM(s.item_discount + s.bill_discount) AS discounts, "
                "COALESCE(SUM(r.total),0) AS refunds "
                "FROM sales s LEFT JOIN returns r ON r.sale_id = s.id AND r.status='completed' "
                f"WHERE {SALES_WHERE} GROUP BY s.user_id, s.cashier_name ORDER BY total DESC",
                (date_from, date_to),
            )
        for record in result:
            record["net"] = int(record["total"] or 0) - int(record["refunds"] or 0)
            count = int(record["transactions"] or 0)
            record["average"] = int(record["net"] // count) if count else 0
        return result

    # ------------------------------------------------------------ expenses
    def expenses_report(self, date_from: str, date_to: str) -> list[dict]:
        date_from, date_to = _range(date_from, date_to)
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT e.id, e.title, e.category, e.amount, e.expense_date, "
                "e.payment_method, e.notes, u.username AS created_by "
                "FROM expenses e LEFT JOIN users u ON u.id = e.user_id "
                "WHERE date(e.expense_date) >= date(?) AND date(e.expense_date) <= date(?) "
                "ORDER BY e.expense_date DESC, e.id DESC",
                (date_from, date_to),
            )

    # ------------------------------------------------------------- profit
    def profit_report(self, date_from: str, date_to: str) -> dict:
        """Gross profit = net sales - cost of goods sold.

        Net profit additionally subtracts recorded business expenses.
        Both figures are clearly labelled in the UI.
        """
        summary = self.sales_summary(date_from, date_to)
        return {
            "date_from": summary["date_from"],
            "date_to": summary["date_to"],
            "net_sales": summary["net_sales"],
            "cogs": summary["cogs"],
            "gross_profit": summary["gross_profit"],
            "expenses": summary["expenses"],
            "net_profit": summary["net_profit"],
            "refunds": summary["refunds"],
            "transactions": summary["transactions"],
        }
