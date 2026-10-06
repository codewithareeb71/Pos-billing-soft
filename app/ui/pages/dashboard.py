"""Dashboard: live KPIs, quick actions and recent transactions."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from .. import icons, theme, widgets
from ...core.money import format_minor


class DashboardPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        header = widgets.PageHeader(
            "Dashboard", "Live figures from your local database")
        root.addWidget(header)

        # ------------------------------------------------------------- KPIs
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        self.cards = {
            "today_total": widgets.StatCard("Today's sales", "-", "money", "primary"),
            "today_transactions": widgets.StatCard("Today's transactions", "-",
                                                   "receipt", "accent"),
            "today_profit": widgets.StatCard("Today's gross profit", "-", "chart",
                                             "success"),
            "today_expenses": widgets.StatCard("Today's expenses", "-", "money",
                                               "warning"),
            "products_total": widgets.StatCard("Products", "-", "tag", "primary"),
            "low_stock": widgets.StatCard("Low stock", "-", "warning", "warning"),
            "out_of_stock": widgets.StatCard("Out of stock", "-", "error", "danger"),
            "month_total": widgets.StatCard("This month's sales", "-", "chart",
                                            "accent"),
        }
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 4, index % 4)
        root.addWidget(grid_host)

        # ---------------------------------------------------- quick actions
        actions_card = widgets.card()
        actions_layout = actions_card.layout()
        actions_layout.setSpacing(10)
        actions_layout.addWidget(widgets.section_title("Quick actions"))
        actions = [
            ("New Sale", "pos", "sales.create"),
            ("Products", "tag", "products.view"),
            ("Inventory", "inventory", "inventory.view"),
            ("Purchases", "truck", "purchases.view"),
            ("Customers", "user", "customers.view"),
            ("Suppliers", "users", "suppliers.view"),
            ("Sales History", "receipt", "sales.view"),
            ("Reports", "chart", "reports.view"),
            ("Expenses", "money", "expenses.view"),
            ("Settings", "settings", "settings.view"),
        ]
        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        row1.setSpacing(8)
        row2.setSpacing(8)
        for index, (label, glyph_name, permission) in enumerate(actions):
            if not self.ctx.can(permission):
                continue
            button = QPushButton(f"  {label}")
            button.setProperty("variant", "flat")
            button.setIcon(icons.icon(glyph_name, "primary", 16))
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(38)
            target = {"New Sale": "pos", "Products": "products",
                      "Inventory": "inventory", "Purchases": "purchases",
                      "Customers": "customers", "Suppliers": "suppliers",
                      "Sales History": "sales", "Reports": "reports",
                      "Expenses": "expenses", "Settings": "settings"}[label]
            button.clicked.connect(lambda _c, k=target: self._open(k))
            (row1 if index % 2 == 0 else row2).addWidget(button)
        row1.addStretch(1)
        row2.addStretch(1)
        actions_layout.addLayout(row1)
        actions_layout.addLayout(row2)
        root.addWidget(actions_card)

        # ----------------------------------------------------- lower panels
        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        recent_card = widgets.card()
        recent_layout = recent_card.layout()
        recent_layout.setSpacing(8)
        recent_layout.addWidget(widgets.section_title("Recent transactions"))
        columns = [
            widgets.Column("invoice_no", "Invoice", 105),
            widgets.Column("created_at", "Date / time", 132),
            widgets.Column("customer", "Customer", 120),
            widgets.Column("cashier_name", "Cashier", 85),
            widgets.Column("payment_method", "Payment", 85),
            widgets.Column("total", "Total", 105, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("status", "Status", 110, "center"),
        ]
        self.recent_table, self.recent_model = widgets.make_table(columns, [])
        self.recent_table.setMinimumHeight(240)
        self.recent_table.doubleClicked.connect(self._open_invoice)
        recent_layout.addWidget(self.recent_table)
        bottom.addWidget(recent_card, 3)

        alert_card = widgets.card()
        alert_layout = alert_card.layout()
        alert_layout.setSpacing(8)
        alert_layout.addWidget(widgets.section_title("Stock alerts"))
        alert_columns = [
            widgets.Column("name", "Product", 150),
            widgets.Column("stock", "Stock", 60, "right"),
            widgets.Column("min_stock", "Min", 55, "right"),
            widgets.Column("status", "Status", 100, "center"),
        ]
        self.alert_table, self.alert_model = widgets.make_table(alert_columns, [])
        alert_layout.addWidget(self.alert_table)
        if self.ctx.can("inventory.view"):
            open_button = QPushButton("Open inventory")
            open_button.setProperty("variant", "flat")
            open_button.clicked.connect(lambda: self._open("inventory"))
            alert_layout.addWidget(open_button)
        bottom.addWidget(alert_card, 2)
        root.addLayout(bottom, 1)

    # ------------------------------------------------------------- behaviour
    def _open(self, key: str) -> None:
        window = self.window()
        if hasattr(window, "show_page"):
            window.show_page(key)

    def _open_invoice(self) -> None:
        if self.ctx.can("sales.view"):
            self._open("sales")

    def on_show(self) -> None:
        stats = self.ctx.dashboard.stats()
        currency = stats["currency"]
        self.cards["today_total"].set_value(format_minor(stats["today_total"], currency))
        self.cards["today_transactions"].set_value(str(stats["today_transactions"]))
        self.cards["today_profit"].set_value(format_minor(stats["today_profit"], currency))
        self.cards["today_expenses"].set_value(format_minor(stats["today_expenses"], currency))
        self.cards["products_total"].set_value(str(stats["products_total"]))
        self.cards["low_stock"].set_value(str(stats["low_stock"]))
        self.cards["out_of_stock"].set_value(str(stats["out_of_stock"]))
        self.cards["month_total"].set_value(format_minor(stats["month_total"], currency))

        self.recent_model.set_rows([
            {**row, "total": row["total"]} for row in stats["recent"]
        ])
        alerts = (self.ctx.inventory.low_stock() + self.ctx.inventory.out_of_stock())[:40]
        self.alert_model.set_rows(alerts)
        self.recent_table.resizeColumnsToContents()


def create(ctx, parent=None) -> DashboardPage:
    return DashboardPage(ctx, parent)
