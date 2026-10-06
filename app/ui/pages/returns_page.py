"""Returns register: every refund with its invoice and stock restoration."""
from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (QDateEdit, QDialog, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from ...core.money import format_minor
from .. import icons, widgets


class ReturnDetailDialog(QDialog):
    def __init__(self, ctx, return_id: int, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        record = ctx.returns.get_return(return_id)
        self.setWindowTitle(f"Return {record['return_no']}")
        self.setModal(True)
        self.setMinimumSize(620, 420)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        currency = ctx.settings.currency
        info = QLabel(
            f"{record['return_no']}   •   Invoice {record['invoice_no']}   •   "
            f"{record['created_at']}\n"
            f"Refund method: {record['refund_method']}   •   "
            f"Reason: {record['reason'] or '-'}")
        info.setObjectName("MutedLabel")
        info.setWordWrap(True)
        root.addWidget(info)
        table, model = widgets.make_table(
            [widgets.Column("product_name", "Product", 240),
             widgets.Column("quantity", "Qty", 70, "right"),
             widgets.Column("unit_price", "Price", 110, "right",
                            lambda v: format_minor(v, "", False)),
             widgets.Column("refund_amount", "Refund", 120, "right",
                            lambda v: format_minor(v, "", False)),
             widgets.Column("reason", "Reason", 180)],
            record["items"])
        root.addWidget(table, 1)
        total = QLabel(f"Total refunded: "
                       f"{format_minor(record['total'], currency)}")
        total.setStyleSheet("font-size:13pt; font-weight:800;")
        root.addWidget(total)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        root.addLayout(row)


class ReturnsPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = widgets.PageHeader("Returns",
                                    "Refunds issued against invoices - stock is "
                                    "restored automatically")
        root.addWidget(header)

        filters = QWidget()
        layout = QHBoxLayout(filters)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.search = widgets.SearchBox("Return number, invoice or customer")
        self.search.changed.connect(lambda _t: self.refresh())
        layout.addWidget(self.search, 2)
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setDate(date.today().replace(day=1))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setDate(date.today())
        for widget in (self.date_from, self.date_to):
            widget.dateChanged.connect(lambda *_: self.refresh())
        layout.addWidget(QLabel("From"))
        layout.addWidget(self.date_from)
        layout.addWidget(QLabel("To"))
        layout.addWidget(self.date_to)
        root.addWidget(filters)

        columns = [
            widgets.Column("return_no", "Return #", 130),
            widgets.Column("invoice_no", "Invoice", 130),
            widgets.Column("created_at", "Date / time", 160),
            widgets.Column("customer", "Customer", 170),
            widgets.Column("item_count", "Items", 70, "center"),
            widgets.Column("total", "Refund", 130, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("refund_method", "Method", 110),
            widgets.Column("processed_by", "By", 110),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        self.table.doubleClicked.connect(lambda *_: self.view_return())
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        view = QPushButton("View return")
        view.setIcon(icons.icon("receipt", "primary", 16))
        view.clicked.connect(self.view_return)
        footer.addWidget(view)
        footer.addStretch(1)
        self.count_label = widgets.hint("")
        footer.addWidget(self.count_label)
        root.addLayout(footer)

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        rows = self.ctx.returns.list_returns(
            self.date_from.date().toString("yyyy-MM-dd"),
            self.date_to.date().toString("yyyy-MM-dd"),
            self.search.text())
        self.model.set_rows(rows)
        self.count_label.setText(f"{len(rows)} return(s)")
        self.table.resizeColumnsToContents()

    def view_return(self) -> None:
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select a return first.", "warning")
            return
        ReturnDetailDialog(self.ctx, record["id"], self).exec()


def create(ctx, parent=None) -> ReturnsPage:
    return ReturnsPage(ctx, parent)
