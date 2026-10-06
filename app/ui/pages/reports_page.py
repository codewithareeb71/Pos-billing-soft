"""Reporting suite: sales, profit, inventory, partners and performance."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDateEdit, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout, QWidget)

from ...core.money import format_minor, from_minor
from .. import icons, theme, widgets

REPORTS = [
    ("Daily sales", "Daily sales summary"),
    ("Weekly sales", "Weekly sales summary"),
    ("Monthly sales", "Monthly sales summary"),
    ("Sales invoices", "Individual invoices in the selected period"),
    ("Product sales", "Quantity, revenue and profit per product"),
    ("Profit", "Gross profit and net profit"),
    ("Purchases", "Stock purchased from suppliers"),
    ("Inventory", "Stock on hand and its value"),
    ("Low stock", "Products at or below their minimum level"),
    ("Out of stock", "Products with no stock left"),
    ("Customers", "Customer activity and lifetime value"),
    ("Suppliers", "Supplier purchases and outstanding balances"),
    ("Expenses", "Recorded business expenses"),
    ("Cashier performance", "Sales per cashier"),
]


class ReportsPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._rows: list[dict] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = widgets.PageHeader("Reports",
                                    "Every figure is calculated from your database")
        run = QPushButton("Run report")
        run.setProperty("variant", "primary")
        run.setIcon(icons.icon("play", "primary", 16))
        run.clicked.connect(self.run_report)
        header.add_action(run)
        if ctx.can("reports.export"):
            export = QPushButton("Export CSV")
            export.setIcon(icons.icon("export", "primary", 16))
            export.clicked.connect(self.export_csv)
            header.add_action(export)
        print_button = QPushButton("Print")
        print_button.setIcon(icons.icon("print", "primary", 16))
        print_button.clicked.connect(self.print_report)
        header.add_action(print_button)
        root.addWidget(header)

        controls = QWidget()
        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Report"))
        self.report_combo = QComboBox()
        for name, description in REPORTS:
            self.report_combo.addItem(name)
        self.report_combo.currentIndexChanged.connect(lambda *_: self.run_report())
        layout.addWidget(self.report_combo)
        layout.addSpacing(12)
        layout.addWidget(QLabel("From"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setDate(date.today() - timedelta(days=30))
        layout.addWidget(self.date_from)
        layout.addWidget(QLabel("To"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setDate(date.today())
        layout.addWidget(self.date_to)
        quick = QComboBox()
        quick.addItems(["Last 7 days", "Last 30 days", "This month", "Last month",
                        "This year", "Custom"])
        quick.setCurrentIndex(1)      # matches the default 30 day range
        quick.currentIndexChanged.connect(lambda *_: self._apply_quick(quick.currentText()))
        layout.addWidget(quick)
        layout.addStretch(1)
        root.addWidget(controls)

        self.summary_host = QWidget()
        self.summary_layout = QGridLayout(self.summary_host)
        self.summary_layout.setContentsMargins(0, 0, 0, 0)
        self.summary_layout.setSpacing(10)
        root.addWidget(self.summary_host)

        self.table, self.model = widgets.make_table([], [])
        root.addWidget(self.table, 1)
        self.status = widgets.hint("Choose a report and press Run report.")
        root.addWidget(self.status)

    # ------------------------------------------------------------------
    def _apply_quick(self, label: str) -> None:
        today = date.today()
        if label == "Last 7 days":
            self.date_from.setDate(today - timedelta(days=7))
            self.date_to.setDate(today)
        elif label == "Last 30 days":
            self.date_from.setDate(today - timedelta(days=30))
            self.date_to.setDate(today)
        elif label == "This month":
            self.date_from.setDate(today.replace(day=1))
            self.date_to.setDate(today)
        elif label == "Last month":
            first = today.replace(day=1)
            previous_last = first - timedelta(days=1)
            self.date_from.setDate(previous_last.replace(day=1))
            self.date_to.setDate(previous_last)
        elif label == "This year":
            self.date_from.setDate(today.replace(month=1, day=1))
            self.date_to.setDate(today)

    def on_show(self) -> None:
        if not self.model.rows:
            self.run_report()

    def _range(self) -> tuple[str, str]:
        return (self.date_from.date().toString("yyyy-MM-dd"),
                self.date_to.date().toString("yyyy-MM-dd"))

    def _clear_summary(self) -> None:
        while self.summary_layout.count():
            item = self.summary_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _set_summary(self, pairs: list[tuple[str, str]]) -> None:
        self._clear_summary()
        for index, (label, value) in enumerate(pairs):
            card = widgets.StatCard(label, value, "chart",
                                    "primary" if index % 2 == 0 else "accent")
            self.summary_layout.addWidget(card, 0, index)

    # ------------------------------------------------------------------
    def run_report(self) -> None:
        name = self.report_combo.currentText()
        date_from, date_to = self._range()
        currency = self.ctx.settings.currency
        reports = self.ctx.reports
        summary: list[tuple[str, str]] = []
        columns: list = []
        rows: list[dict] = []
        note = ""

        if name == "Daily sales":
            rows = reports.sales_by_day(date_from, date_to)
            columns = [widgets.Column("day", "Date", 130),
                       widgets.Column("transactions", "Invoices", 90, "right"),
                       widgets.Column("total", "Sales", 140, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("discounts", "Discounts", 130, "right",
                                      lambda v: format_minor(v, currency))]
            totals = reports.sales_summary(date_from, date_to)
            summary = [("Invoices", str(totals["transactions"])),
                       ("Net sales", format_minor(totals["net_sales"], currency)),
                       ("Gross profit", format_minor(totals["gross_profit"], currency))]
        elif name == "Weekly sales":
            days = reports.sales_by_day(date_from, date_to)
            buckets: dict[str, dict] = {}
            for entry in days:
                try:
                    day = date.fromisoformat(entry["day"])
                except ValueError:
                    continue
                key = day.strftime("%Y-W%W")
                bucket = buckets.setdefault(key, {"week": key, "start": entry["day"],
                                                  "transactions": 0, "total": 0})
                bucket["transactions"] += int(entry["transactions"])
                bucket["total"] += int(entry["total"])
                bucket["start"] = min(bucket["start"], entry["day"])
            rows = sorted(buckets.values(), key=lambda b: b["start"])
            columns = [widgets.Column("week", "Week", 120),
                       widgets.Column("start", "Starting", 120),
                       widgets.Column("transactions", "Invoices", 90, "right"),
                       widgets.Column("total", "Sales", 140, "right",
                                      lambda v: format_minor(v, currency))]
            totals = reports.sales_summary(date_from, date_to)
            summary = [("Invoices", str(totals["transactions"])),
                       ("Net sales", format_minor(totals["net_sales"], currency))]
        elif name == "Monthly sales":
            days = reports.sales_by_day(date_from, date_to)
            buckets = {}
            for entry in days:
                key = (entry["day"] or "")[:7]
                bucket = buckets.setdefault(key, {"month": key, "transactions": 0,
                                                  "total": 0})
                bucket["transactions"] += int(entry["transactions"])
                bucket["total"] += int(entry["total"])
            rows = sorted(buckets.values())
            columns = [widgets.Column("month", "Month", 140),
                       widgets.Column("transactions", "Invoices", 90, "right"),
                       widgets.Column("total", "Sales", 140, "right",
                                      lambda v: format_minor(v, currency))]
            totals = reports.sales_summary(date_from, date_to)
            summary = [("Invoices", str(totals["transactions"])),
                       ("Net sales", format_minor(totals["net_sales"], currency))]
        elif name == "Sales invoices":
            rows = reports.sales_by_invoice(date_from, date_to)
            columns = [widgets.Column("invoice_no", "Invoice", 140),
                       widgets.Column("created_at", "Date / time", 160),
                       widgets.Column("customer", "Customer", 170),
                       widgets.Column("cashier_name", "Cashier", 120),
                       widgets.Column("items", "Items", 70, "center"),
                       widgets.Column("total", "Total", 130, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("payment_method", "Payment", 110),
                       widgets.Column("status", "Status", 130, "center")]
            totals = reports.sales_summary(date_from, date_to)
            summary = [("Invoices", str(totals["transactions"])),
                       ("Sales", format_minor(totals["total"], currency)),
                       ("Refunds", format_minor(totals["refunds"], currency))]
        elif name == "Product sales":
            rows = reports.product_sales(date_from, date_to)
            columns = [widgets.Column("product_name", "Product", 240),
                       widgets.Column("sku", "SKU", 120),
                       widgets.Column("quantity_net", "Qty sold", 90, "right"),
                       widgets.Column("net", "Revenue", 130, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("cost", "Cost", 130, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("profit", "Profit", 130, "right",
                                      lambda v: format_minor(v, currency))]
            summary = [("Products sold", str(len(rows))),
                       ("Revenue", format_minor(sum(int(r["net"]) for r in rows),
                                                currency)),
                       ("Profit", format_minor(sum(int(r["profit"]) for r in rows),
                                               currency))]
        elif name == "Profit":
            profit = reports.profit_report(date_from, date_to)
            rows = [{"label": "Net sales (after refunds)",
                     "amount": profit["net_sales"]},
                    {"label": "Cost of goods sold", "amount": -profit["cogs"]},
                    {"label": "GROSS PROFIT", "amount": profit["gross_profit"]},
                    {"label": "Business expenses", "amount": -profit["expenses"]},
                    {"label": "NET PROFIT", "amount": profit["net_profit"]}]
            columns = [widgets.Column("label", "Measure", 340),
                       widgets.Column("amount", "Amount", 180, "right",
                                      lambda v: format_minor(v, currency))]
            summary = [("Net sales", format_minor(profit["net_sales"], currency)),
                       ("Gross profit", format_minor(profit["gross_profit"], currency)),
                       ("Net profit", format_minor(profit["net_profit"], currency))]
            note = ("Gross profit = net sales - cost of goods sold. "
                    "Net profit = gross profit - recorded expenses.")
        elif name == "Purchases":
            rows = reports.purchases_report(date_from, date_to)
            columns = [widgets.Column("purchase_no", "Purchase #", 140),
                       widgets.Column("purchase_date", "Date", 120),
                       widgets.Column("supplier", "Supplier", 200),
                       widgets.Column("items", "Items", 70, "center"),
                       widgets.Column("total", "Total", 140, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("paid", "Paid", 140, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("balance", "Balance", 140, "right",
                                      lambda v: format_minor(v, currency))]
            totals = self.ctx.purchases.totals_between(date_from, date_to)
            summary = [("Purchases", str(totals["count"])),
                       ("Total", format_minor(totals["total"], currency)),
                       ("Outstanding", format_minor(totals["balance"], currency))]
        elif name == "Inventory":
            rows = reports.inventory_report()
            columns = [widgets.Column("name", "Product", 220),
                       widgets.Column("barcode", "Barcode", 130),
                       widgets.Column("category", "Category", 130),
                       widgets.Column("stock", "Stock", 80, "right"),
                       widgets.Column("min_stock", "Min", 70, "right"),
                       widgets.Column("purchase_price", "Cost", 100, "right",
                                      lambda v: format_minor(v, "", False)),
                       widgets.Column("stock_value", "Value", 130, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("status", "Status", 110, "center")]
            summary = [("Products", str(len(rows))),
                       ("Stock value", format_minor(sum(int(r["stock_value"])
                                                        for r in rows), currency))]
        elif name == "Low stock":
            rows = self.ctx.inventory.low_stock()
            columns = [widgets.Column("name", "Product", 240),
                       widgets.Column("barcode", "Barcode", 130),
                       widgets.Column("category", "Category", 130),
                       widgets.Column("stock", "Stock", 80, "right"),
                       widgets.Column("min_stock", "Minimum", 90, "right"),
                       widgets.Column("supplier", "Supplier", 170)]
            summary = [("Low stock items", str(len(rows)))]
        elif name == "Out of stock":
            rows = self.ctx.inventory.out_of_stock()
            columns = [widgets.Column("name", "Product", 240),
                       widgets.Column("barcode", "Barcode", 130),
                       widgets.Column("category", "Category", 130),
                       widgets.Column("min_stock", "Minimum", 90, "right"),
                       widgets.Column("supplier", "Supplier", 170)]
            summary = [("Out of stock items", str(len(rows)))]
        elif name == "Customers":
            rows = reports.customers_report()
            columns = [widgets.Column("name", "Customer", 220),
                       widgets.Column("phone", "Phone", 150),
                       widgets.Column("visits", "Visits", 80, "right"),
                       widgets.Column("spent", "Total spent", 150, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("last_visit", "Last visit", 160)]
            summary = [("Customers", str(len(rows))),
                       ("Total value", format_minor(sum(int(r["spent"] or 0)
                                                        for r in rows), currency))]
        elif name == "Suppliers":
            rows = reports.suppliers_report()
            columns = [widgets.Column("name", "Supplier", 220),
                       widgets.Column("company", "Company", 180),
                       widgets.Column("phone", "Phone", 150),
                       widgets.Column("purchases", "Orders", 80, "right"),
                       widgets.Column("purchased", "Purchased", 150, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("outstanding", "Outstanding", 150, "right",
                                      lambda v: format_minor(v, currency))]
            summary = [("Suppliers", str(len(rows))),
                       ("Outstanding", format_minor(sum(int(r["outstanding"] or 0)
                                                        for r in rows), currency))]
        elif name == "Expenses":
            rows = reports.expenses_report(date_from, date_to)
            columns = [widgets.Column("expense_date", "Date", 120),
                       widgets.Column("title", "Expense", 260),
                       widgets.Column("category", "Category", 150),
                       widgets.Column("amount", "Amount", 140, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("payment_method", "Method", 120),
                       widgets.Column("created_by", "By", 130)]
            summary = [("Entries", str(len(rows))),
                       ("Total", format_minor(sum(int(r["amount"]) for r in rows),
                                              currency))]
        elif name == "Cashier performance":
            rows = reports.cashier_performance(date_from, date_to)
            columns = [widgets.Column("cashier", "Cashier", 200),
                       widgets.Column("transactions", "Invoices", 100, "right"),
                       widgets.Column("total", "Sales", 150, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("refunds", "Refunds", 130, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("discounts", "Discounts", 130, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("net", "Net", 150, "right",
                                      lambda v: format_minor(v, currency)),
                       widgets.Column("average", "Average sale", 130, "right",
                                      lambda v: format_minor(v, currency))]
            summary = [("Cashiers", str(len(rows))),
                       ("Net sales", format_minor(sum(int(r["net"]) for r in rows),
                                                  currency))]

        self.model.columns = columns
        self.model.set_rows(rows)
        self._rows = rows
        self._columns = columns
        self._set_summary(summary)
        self.table.resizeColumnsToContents()
        self.status.setText(
            f"{name}: {len(rows)} row(s) for {date_from} to {date_to}"
            + (f"  •  {note}" if note else ""))

    # ------------------------------------------------------------------
    def export_csv(self) -> None:
        if not self._rows:
            self.run_report()
            if not self._rows:
                widgets.notify(self, "There is nothing to export.", "warning")
                return
        path = widgets.file_save_dialog(
            self, "Export report", "CSV files (*.csv)",
            f"{self.report_combo.currentText().lower().replace(' ', '_')}.csv")
        if not path:
            return
        columns = [c for c in self._columns]
        self.ctx.csv.export_rows(path, [c.title for c in columns], [
            {c.title: (c.format(row.get(c.key)) if c.format else row.get(c.key, ""))
             for c in columns} for row in self._rows])
        widgets.notify(self, f"Exported to {path}", "success")

    def print_report(self) -> None:
        if not self._rows:
            self.run_report()
        if not self._rows:
            widgets.notify(self, "There is nothing to print.", "warning")
            return
        currency = self.ctx.settings.currency
        header_cells = "".join(f"<th>{c.title}</th>" for c in self._columns)
        body = []
        for row in self._rows[:800]:
            cells = []
            for column in self._columns:
                value = column.format(row.get(column.key)) if column.format else \
                    row.get(column.key, "")
                cells.append(f"<td>{value or ''}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        summary_text = "  •  ".join(
            f"{label}: {value}" for label, value in self._summary_pairs())
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><style>
        body {{ font-family:'Segoe UI',sans-serif; font-size:9pt; color:#000; }}
        h1 {{ font-size:14pt; margin:0 0 2px 0; color:{theme.PRIMARY}; }}
        .meta {{ color:#555; font-size:8.5pt; margin-bottom:10px; }}
        table {{ width:100%; border-collapse:collapse; }}
        th {{ background:#EEF3F8; border:1px solid #C9D5E2; padding:4px 6px;
              text-align:left; font-size:8.5pt; }}
        td {{ border:1px solid #DDE4EC; padding:3px 6px; font-size:8.5pt; }}
        </style></head><body>
        <h1>{self.report_combo.currentText()} - ALSHAN POS SYSTEM</h1>
        <div class="meta">{self.ctx.settings.shop_name} &nbsp;•&nbsp;
        {self.date_from.date().toString('yyyy-MM-dd')} to
        {self.date_to.date().toString('yyyy-MM-dd')} &nbsp;•&nbsp;
        Generated {date.today().isoformat()} &nbsp;•&nbsp; {summary_text}</div>
        <table><thead><tr>{header_cells}</tr></thead>
        <tbody>{''.join(body)}</tbody></table></body></html>"""
        try:
            self.ctx.receipts.preview(self, html, width_mm=210,
                                      title="Report preview")
        except Exception as exc:  # pragma: no cover
            from ...core.logging_setup import get_logger, log_exception
            log_exception(get_logger("reports"), "Report printing failed", exc)
            widgets.notify(self, "Printing failed - check the printer settings.",
                           "error")

    def _summary_pairs(self) -> list[tuple[str, str]]:
        pairs = []
        for index in range(self.summary_layout.count()):
            widget = self.summary_layout.itemAt(index).widget()
            if isinstance(widget, widgets.StatCard):
                pairs.append((widget.name_label.text(), widget.value_label.text()))
        return pairs


def create(ctx, parent=None) -> ReportsPage:
    return ReportsPage(ctx, parent)
