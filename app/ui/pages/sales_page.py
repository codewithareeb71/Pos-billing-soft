"""Sales history: search, invoice view, reprint, returns and voids."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QDoubleSpinBox,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from ...core.exceptions import AppError
from ...core.money import format_minor, from_minor
from .. import icons, theme, widgets


# ===========================================================================
# Return processing
# ===========================================================================
class ReturnDialog(widgets.FormDialog):
    def __init__(self, ctx, sale: dict, parent=None):
        super().__init__(parent, f"Process return - {sale['invoice_no']}",
                         "Confirm return")
        self.ctx = ctx
        self.sale = sale
        self.result: dict | None = None
        self.setMinimumSize(640, 480)
        info = QLabel(f"Customer: {sale.get('customer', 'Walk-in Customer')}   •   "
                      f"Invoice total: "
                      f"{format_minor(sale['total'], ctx.settings.currency)}")
        info.setObjectName("MutedLabel")
        info.setWordWrap(True)
        self.root.insertWidget(0, info)

        self.lines = self.ctx.returns.returnable_items(sale["id"])
        if not self.lines:
            raise AppError("There is nothing left to return on this invoice.")
        columns = [
            widgets.Column("product_name", "Product", 220),
            widgets.Column("quantity", "Sold", 60, "right"),
            widgets.Column("already", "Returned", 80, "right"),
            widgets.Column("returnable", "Returnable", 90, "right"),
            widgets.Column("unit_price", "Price", 100, "right",
                           lambda v: format_minor(v, "", False)),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        for line in self.lines:
            line["already"] = round(
                float(line["quantity"]) - float(line["returnable"]), 3)
        self.model.set_rows(self.lines)
        self.form.addRow("Invoice items", self.table)

        qty_row = QHBoxLayout()
        qty_row.addWidget(QLabel("Return quantity"))
        self.qty_spin = QDoubleSpinBox()
        self.qty_spin.setRange(0, 1_000_000)
        self.qty_spin.setDecimals(3)
        self.qty_spin.setValue(float(self.lines[0]["returnable"]))
        self.qty_spin.setKeyboardTracking(False)
        qty_row.addWidget(self.qty_spin)
        all_button = QPushButton("All")
        all_button.clicked.connect(self._return_all)
        qty_row.addWidget(all_button)
        qty_row.addStretch(1)
        self.form.addRow("Selected item", qty_row)
        self.table.selectionModel().currentChanged.connect(lambda *_: self._bind())

        self.reason = QLineEdit()
        self.reason.setPlaceholderText("e.g. Damaged, wrong item, customer changed mind")
        self.refund_method = QComboBox()
        self.refund_method.addItems(["Cash", "Card", "Bank Transfer", "Other"])
        self.add_field("Reason", self.reason)
        self.add_field("Refund method", self.refund_method)
        self.preview = QLabel("")
        self.preview.setStyleSheet("font-size:13pt; font-weight:800;")
        self.form.addRow("Refund total", self.preview)
        self.qty_spin.valueChanged.connect(lambda *_: self._bind())
        self._bind()

    def _current_index(self) -> int:
        index = self.table.currentIndex()
        return index.row() if index.isValid() else -1

    def _bind(self) -> None:
        position = self._current_index()
        if not 0 <= position < len(self.lines):
            return
        line = self.lines[position]
        self.qty_spin.setMaximum(float(line["returnable"]))
        if self.qty_spin.value() > float(line["returnable"]):
            self.qty_spin.setValue(float(line["returnable"]))
        self.lines[position]["return_qty"] = round(self.qty_spin.value(), 3)
        self.preview.setText(self._estimate())

    def _estimate(self) -> str:
        """Mirror the service calculation so the cashier sees the refund."""
        sale = self.sale
        goods_total = max(1, int(sale["subtotal"]) - int(sale["item_discount"]))
        refund = 0
        for entry in self.lines:
            qty = float(entry.get("return_qty", 0) or 0)
            if qty <= 0:
                continue
            whole = float(entry["quantity"])
            line_total = int(entry["line_total"])
            line_refund = int(round(line_total * qty / whole)) if whole else 0
            bill_share = int(round(int(sale["bill_discount"]) * line_refund / goods_total))
            refund += max(0, line_refund - bill_share)
        return format_minor(refund, self.ctx.settings.currency)

    def _return_all(self) -> None:
        position = self._current_index()
        if 0 <= position < len(self.lines):
            self.qty_spin.setValue(float(self.lines[position]["returnable"]))

    def validate(self) -> str:
        selected = [{"sale_item_id": entry["sale_item_id"],
                     "quantity": round(float(entry.get("return_qty", 0) or 0), 3)}
                    for entry in self.lines
                    if float(entry.get("return_qty", 0) or 0) > 1e-9]
        if not selected:
            return "Choose a quantity to return."
        return ""

    def accept(self) -> None:
        selected = [{"sale_item_id": entry["sale_item_id"],
                     "quantity": round(float(entry.get("return_qty", 0) or 0), 3)}
                    for entry in self.lines
                    if float(entry.get("return_qty", 0) or 0) > 1e-9]
        try:
            self.result = self.ctx.returns.create_return(
                self.sale["id"], selected, self.reason.text().strip(),
                self.refund_method.currentText())
        except AppError as exc:
            self.set_error(exc.message)
            return
        super().accept()


# ===========================================================================
# Void
# ====================================================================================
class VoidDialog(widgets.FormDialog):
    def __init__(self, ctx, sale: dict, parent=None):
        super().__init__(parent, f"Void invoice {sale['invoice_no']}", "Void invoice")
        self.ctx = ctx
        self.sale = sale
        warning = QLabel(
            "Voiding restores the stock and marks the invoice as voided. "
            "The record is kept for auditing - it is never deleted.")
        warning.setObjectName("ErrorLabel")
        warning.setWordWrap(True)
        self.root.insertWidget(0, warning)
        totals = QLabel(f"Total: {format_minor(sale['total'], ctx.settings.currency)}   "
                        f"•   {sale['cashier_name']}   •   {sale['created_at']}")
        totals.setObjectName("MutedLabel")
        self.root.insertWidget(1, totals)
        self.reason = QPlainTextEdit()
        self.reason.setPlaceholderText("Reason for voiding (required) *")
        self.reason.setFixedHeight(90)
        self.add_field("Reason", self.reason)

    def validate(self) -> str:
        if not self.reason.toPlainText().strip():
            return "A reason is required to void an invoice."
        return ""

    def accept(self) -> None:
        try:
            self.ctx.sales.void_sale(self.sale["id"], self.reason.toPlainText().strip())
        except AppError as exc:
            self.set_error(exc.message)
            return
        super().accept()


# ===========================================================================
# Invoice detail
# ===========================================================================
class InvoiceDialog(QDialog):
    def __init__(self, ctx, sale_id: int, parent=None, on_changed=None):
        super().__init__(parent)
        self.ctx = ctx
        self.sale_id = sale_id
        self.on_changed = on_changed
        self.sale = ctx.sales.get_sale_detail(sale_id)
        self.setWindowTitle(f"Invoice {self.sale['invoice_no']}")
        self.setModal(True)
        self.setMinimumSize(760, 540)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        status = self.sale["status"]
        head = QLabel(
            f"{self.sale['invoice_no']}   •   {self.sale['created_at']}\n"
            f"Customer: {self.sale.get('customer', 'Walk-in Customer')}   •   "
            f"Cashier: {self.sale['cashier_name']}   •   "
            f"Payment: {self.sale['payment_method']}   •   Status: {status}")
        head.setObjectName("MutedLabel")
        head.setWordWrap(True)
        root.addWidget(head)

        columns = [
            widgets.Column("product_name", "Product", 230),
            widgets.Column("sku", "SKU", 110),
            widgets.Column("quantity", "Qty", 60, "right"),
            widgets.Column("unit_price", "Price", 100, "right",
                           lambda v: format_minor(v, "", False)),
            widgets.Column("discount_amount", "Disc", 90, "right",
                           lambda v: (f"-{format_minor(v, '', False)}" if v else "")),
            widgets.Column("line_total", "Amount", 110, "right",
                           lambda v: format_minor(v, "", False)),
            widgets.Column("returned_qty", "Returned", 90, "right"),
        ]
        self.table, self.model = widgets.make_table(columns, self.sale["items"])
        root.addWidget(self.table, 1)

        currency = ctx.settings.currency
        totals = QLabel(
            f"Subtotal {format_minor(self.sale['subtotal'], currency)}    "
            f"Item discounts -{format_minor(self.sale['item_discount'], currency)}    "
            f"Bill discount -{format_minor(self.sale['bill_discount'], currency)}\n"
            f"TOTAL {format_minor(self.sale['total'], currency)}    "
            f"Paid {format_minor(self.sale['paid'], currency)}    "
            f"Change {format_minor(self.sale['change_due'], currency)}")
        totals.setStyleSheet("font-weight:700;")
        root.addWidget(totals)
        if self.sale.get("returns"):
            returned = sum(int(r["total"]) for r in self.sale["returns"])
            root.addWidget(widgets.muted(
                "Returns on this invoice: " + ", ".join(
                    f"{r['return_no']} ({format_minor(r['total'], currency)})"
                    for r in self.sale["returns"]) +
                f"  •  Total refunded {format_minor(returned, currency)}"))
        if self.sale["status"] == "voided":
            root.addWidget(widgets.hint(
                f"Voided: {self.sale.get('void_reason', '')}"))

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        reprint = QPushButton("Reprint")
        reprint.setIcon(icons.icon("print", "primary", 16))
        reprint.clicked.connect(lambda: self._print(preview=False))
        preview = QPushButton("Preview")
        preview.clicked.connect(lambda: self._print(preview=True))
        buttons.addWidget(reprint)
        buttons.addWidget(preview)
        if ctx.can("returns.process") and self.sale["status"] != "voided":
            ret = QPushButton("Process return")
            ret.setIcon(icons.icon("return", "primary", 16))
            ret.clicked.connect(self._process_return)
            buttons.addWidget(ret)
        if ctx.can("sales.void") and self.sale["status"] != "voided":
            void = QPushButton("Void invoice")
            void.setProperty("variant", "danger")
            void.clicked.connect(self._void)
            buttons.addWidget(void)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

    def _changed(self) -> None:
        if callable(self.on_changed):
            self.on_changed()
        self.sale = self.ctx.sales.get_sale_detail(self.sale_id)
        self.model.set_rows(self.sale["items"])

    def _print(self, preview: bool) -> None:
        html_text = self.ctx.receipts.receipt_html(self.sale, reprint=True,
                                                   note="Reprint")
        if preview:
            self.ctx.receipts.preview(self, html_text,
                                      title=f"Invoice {self.sale['invoice_no']}")
            return
        try:
            self.ctx.receipts.print_html(html_text)
        except Exception as exc:  # pragma: no cover
            from ...core.logging_setup import get_logger, log_exception
            log_exception(get_logger("sales"), "Reprint failed", exc)
            widgets.notify(self, "Printing failed - check the printer settings.",
                           "error")

    def _process_return(self) -> None:
        try:
            dialog = ReturnDialog(self.ctx, self.sale, self)
        except AppError as exc:
            widgets.info_box(self, exc.message, "Nothing to return")
            return
        if dialog.exec() == QDialog.Accepted and dialog.result:
            result = dialog.result
            widgets.notify(self,
                           f"{result['return_no']} processed - refund "
                           f"{format_minor(result['total'], self.ctx.settings.currency)}",
                           "success")
            self._changed()

    def _void(self) -> None:
        dialog = VoidDialog(self.ctx, self.sale, self)
        if dialog.exec() == QDialog.Accepted:
            widgets.notify(self, f"Invoice {self.sale['invoice_no']} voided", "success")
            self._changed()


# ===========================================================================
# Page
# ===========================================================================
class SalesPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = widgets.PageHeader("Sales history",
                                    "Every invoice with reprint, return and void "
                                    "controls")
        root.addWidget(header)

        filters = QWidget()
        layout = QHBoxLayout(filters)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.search = widgets.SearchBox("Invoice number, customer or cashier")
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
        self.cashier_filter = QComboBox()
        self.cashier_filter.addItem("All cashiers", None)
        self.cashier_filter.currentIndexChanged.connect(lambda *_: self.refresh())
        layout.addWidget(self.cashier_filter)
        self.payment_filter = QComboBox()
        self.payment_filter.addItem("All payments", None)
        self.payment_filter.addItems(["Cash", "Card", "Bank Transfer", "Other"])
        self.payment_filter.currentIndexChanged.connect(lambda *_: self.refresh())
        layout.addWidget(self.payment_filter)
        self.status_filter = QComboBox()
        self.status_filter.addItem("All statuses", None)
        self.status_filter.addItems(["completed", "partially_returned", "returned",
                                     "voided"])
        self.status_filter.currentIndexChanged.connect(lambda *_: self.refresh())
        layout.addWidget(self.status_filter)
        root.addWidget(filters)

        summary = QHBoxLayout()
        summary.setSpacing(10)
        self.cards = {
            "count": widgets.StatCard("Invoices", "-", "receipt", "primary"),
            "total": widgets.StatCard("Sales total", "-", "money", "success"),
            "refunds": widgets.StatCard("Refunded", "-", "return", "danger"),
        }
        for card in self.cards.values():
            summary.addWidget(card)
        summary.addStretch(1)
        root.addLayout(summary)

        columns = [
            widgets.Column("invoice_no", "Invoice", 140),
            widgets.Column("created_at", "Date / time", 160),
            widgets.Column("customer", "Customer", 180),
            widgets.Column("cashier_name", "Cashier", 120),
            widgets.Column("item_count", "Items", 70, "center"),
            widgets.Column("total", "Total", 130, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("payment_method", "Payment", 120),
            widgets.Column("status", "Status", 140, "center"),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        self.table.doubleClicked.connect(lambda *_: self.view_invoice())
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        view = QPushButton("View invoice")
        view.setIcon(icons.icon("receipt", "primary", 16))
        view.clicked.connect(self.view_invoice)
        footer.addWidget(view)
        reprint = QPushButton("Reprint")
        reprint.setIcon(icons.icon("print", "primary", 16))
        reprint.clicked.connect(self.reprint)
        footer.addWidget(reprint)
        if ctx.can("returns.process"):
            ret = QPushButton("Return")
            ret.setIcon(icons.icon("return", "primary", 16))
            ret.clicked.connect(self.process_return)
            footer.addWidget(ret)
        if ctx.can("sales.void"):
            void = QPushButton("Void")
            void.setProperty("variant", "danger")
            void.clicked.connect(self.void_sale)
            footer.addWidget(void)
        footer.addStretch(1)
        self.count_label = widgets.hint("")
        footer.addWidget(self.count_label)
        root.addLayout(footer)

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self._refresh_cashiers()
        self.refresh()

    def _refresh_cashiers(self) -> None:
        current = self.cashier_filter.currentData()
        self.cashier_filter.blockSignals(True)
        self.cashier_filter.clear()
        self.cashier_filter.addItem("All cashiers", None)
        seen = set()
        for user in self.ctx.auth.list_users():
            if user["id"] in seen:
                continue
            seen.add(user["id"])
            self.cashier_filter.addItem(user["username"], user["id"])
        index = self.cashier_filter.findData(current)
        if index >= 0:
            self.cashier_filter.setCurrentIndex(index)
        self.cashier_filter.blockSignals(False)

    def refresh(self) -> None:
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        rows = self.ctx.sales.list_sales(
            date_from, date_to, self.search.text(),
            cashier=self.cashier_filter.currentData() or "",
            payment=self.payment_filter.currentText().replace("All payments", ""),
            status=self.status_filter.currentText().replace("All statuses", ""),
            limit=2000)
        self.model.set_rows(rows)
        self.count_label.setText(f"{len(rows)} invoice(s)")
        self.table.resizeColumnsToContents()
        summary = self.ctx.sales.sale_totals_summary(date_from, date_to)
        currency = self.ctx.settings.currency
        self.cards["count"].set_value(str(summary.get("txns", 0)))
        self.cards["total"].set_value(format_minor(summary.get("total", 0), currency))
        self.cards["refunds"].set_value(format_minor(summary.get("returned", 0),
                                                     currency))

    def _selected_sale(self) -> dict | None:
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select an invoice first.", "warning")
        return record

    def view_invoice(self) -> None:
        record = self._selected_sale()
        if not record:
            return
        InvoiceDialog(self.ctx, record["id"], self, on_changed=self.refresh).exec()
        self.refresh()

    def reprint(self) -> None:
        record = self._selected_sale()
        if not record:
            return
        sale = self.ctx.sales.get_sale_detail(record["id"])
        html_text = self.ctx.receipts.receipt_html(sale, reprint=True, note="Reprint")
        dialog = widgets.confirm(self, f"Print a copy of {sale['invoice_no']}?",
                                 "Reprint receipt")
        if not dialog:
            return
        try:
            self.ctx.receipts.print_html(html_text)
        except Exception as exc:  # pragma: no cover
            from ...core.logging_setup import get_logger, log_exception
            log_exception(get_logger("sales"), "Reprint failed", exc)
            widgets.notify(self, "Printing failed - check Settings > Hardware.",
                           "error")
            return
        widgets.notify(self, "Receipt sent to the printer", "success")

    def process_return(self) -> None:
        record = self._selected_sale()
        if not record:
            return
        sale = self.ctx.sales.get_sale_detail(record["id"])
        if sale["status"] == "voided":
            widgets.notify(self, "Voided invoices cannot be returned.", "error")
            return
        try:
            dialog = ReturnDialog(self.ctx, sale, self)
        except AppError as exc:
            widgets.info_box(self, exc.message, "Nothing to return")
            return
        if dialog.exec() == QDialog.Accepted and dialog.result:
            widgets.notify(self, f"Return {dialog.result['return_no']} completed",
                           "success")
            self.refresh()

    def void_sale(self) -> None:
        record = self._selected_sale()
        if not record:
            return
        sale = self.ctx.sales.get_sale_detail(record["id"])
        if sale["status"] == "voided":
            widgets.notify(self, "This invoice is already voided.", "warning")
            return
        dialog = VoidDialog(self.ctx, sale, self)
        if dialog.exec() == QDialog.Accepted:
            widgets.notify(self, f"Invoice {sale['invoice_no']} voided", "success")
            self.refresh()


def create(ctx, parent=None) -> SalesPage:
    return SalesPage(ctx, parent)
