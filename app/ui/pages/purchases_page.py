"""Purchases module: stock-in documents that update inventory automatically."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QDoubleSpinBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTableView, QVBoxLayout, QWidget)

from ...core.exceptions import AppError
from ...core.money import format_minor, from_minor, parse_input, to_minor
from .. import icons, theme, widgets


class PurchaseDialog(widgets.FormDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent, "New purchase", "Save purchase")
        self.ctx = ctx
        self.items: list[dict] = []
        self.purchase: dict | None = None
        self.setMinimumSize(860, 640)
        self._updating = False

        # header ----------------------------------------------------------
        head = QWidget()
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(8)
        self.supplier = QComboBox()
        self.supplier.setEditable(True)
        self.supplier.setInsertPolicy(QComboBox.NoInsert)
        self.supplier.setMinimumWidth(240)
        self._load_suppliers()
        self.purchase_date = QDateEdit()
        self.purchase_date.setCalendarPopup(True)
        self.purchase_date.setDate(date.today())
        self.purchase_date.setDisplayFormat("yyyy-MM-dd")
        head_layout.addWidget(QLabel("Supplier"))
        head_layout.addWidget(self.supplier, 1)
        head_layout.addWidget(QLabel("Date"))
        head_layout.addWidget(self.purchase_date)
        self.form.addRow("Purchase", head)

        # product picker ---------------------------------------------------
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type a product name, SKU or barcode and press "
                                       "Enter")
        self.search.returnPressed.connect(self._add_from_search)
        self.results, self.results_model = widgets.make_table(
            [widgets.Column("name", "Product", 220),
             widgets.Column("barcode", "Barcode", 130),
             widgets.Column("stock", "Stock", 70, "right"),
             widgets.Column("purchase_price", "Last cost", 100, "right",
                            lambda v: format_minor(v, "", False))], [])
        self.results.setMaximumHeight(150)
        self.results.doubleClicked.connect(lambda *_: self._add_selected())
        picker = QVBoxLayout()
        picker.setSpacing(6)
        picker.addWidget(self.search)
        picker.addWidget(self.results)
        self.form.addRow("Add product", picker)

        # cart -------------------------------------------------------------
        self.table, self.model = widgets.make_table(
            [widgets.Column("name", "Product", 240),
             widgets.Column("quantity", "Qty", 80, "right"),
             widgets.Column("unit_price", "Unit cost", 120, "right",
                            lambda v: format_minor(v, "", False)),
             widgets.Column("line_total", "Line total", 130, "right",
                            lambda v: format_minor(v, "", False))], [])
        self.table.setMinimumHeight(180)
        self.form.addRow("Items", self.table)

        # line editor ------------------------------------------------------
        line = QWidget()
        line_layout = QHBoxLayout(line)
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(6)
        line_layout.addWidget(QLabel("Qty"))
        self.qty_spin = QDoubleSpinBox()
        self.qty_spin.setRange(0.001, 1_000_000)
        self.qty_spin.setDecimals(3)
        self.qty_spin.setKeyboardTracking(False)
        self.qty_spin.valueChanged.connect(self._on_line_changed)
        line_layout.addWidget(self.qty_spin)
        line_layout.addSpacing(8)
        line_layout.addWidget(QLabel("Unit cost"))
        self.price_edit = QLineEdit()
        self.price_edit.setAlignment(Qt.AlignRight)
        self.price_edit.editingFinished.connect(self._on_line_changed)
        line_layout.addWidget(self.price_edit)
        remove = QPushButton("Remove line")
        remove.setProperty("variant", "danger")
        remove.clicked.connect(self._remove_line)
        line_layout.addWidget(remove)
        line_layout.addStretch(1)
        self.form.addRow("Selected item", line)
        self.table.selectionModel().currentChanged.connect(
            lambda *_: self._bind_line())

        # totals -----------------------------------------------------------
        self.subtotal_label = QLabel("-")
        self.discount_edit = QLineEdit("0")
        self.discount_edit.setAlignment(Qt.AlignRight)
        self.discount_edit.editingFinished.connect(self._recompute)
        self.total_label = QLabel("-")
        self.total_label.setStyleSheet("font-size:14pt; font-weight:800;")
        self.paid_edit = QLineEdit("0")
        self.paid_edit.setAlignment(Qt.AlignRight)
        self.paid_edit.editingFinished.connect(self._recompute)
        self.balance_label = QLabel("-")
        self.balance_label.setStyleSheet(f"font-weight:800; color:{theme.WARNING};")
        for label, widget in (("Subtotal", self.subtotal_label),
                              ("Discount", self.discount_edit),
                              ("Total", self.total_label),
                              ("Paid now", self.paid_edit),
                              ("Balance due", self.balance_label)):
            row = QHBoxLayout()
            left = QLabel(label)
            left.setObjectName("MutedLabel")
            row.addWidget(left)
            row.addStretch(1)
            row.addWidget(widget)
            self.form.addRow("", row)

        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Optional notes")
        self.add_field("Notes", self.notes)
        self._recompute()

    # ------------------------------------------------------------------
    def _load_suppliers(self) -> None:
        self.supplier.clear()
        self.supplier.addItem("(No supplier)", None)
        for supplier in self.ctx.suppliers.search(limit=1000):
            self.supplier.addItem(supplier["name"], supplier["id"])

    def _supplier_id(self) -> int | None:
        data = self.supplier.currentData()
        if data:
            return int(data)
        name = self.supplier.currentText().strip()
        if not name:
            return None
        try:
            return self.ctx.suppliers.create({"name": name})
        except AppError:
            return None

    def _refresh_results(self) -> None:
        term = self.search.text().strip()
        rows = self.ctx.catalog.search(term, limit=25) if term else []
        self.results_model.set_rows(rows)

    def _add_from_search(self) -> None:
        self._refresh_results()
        if self.results_model.rows:
            self._add_product(self.results_model.rows[0])

    def _add_selected(self) -> None:
        record = widgets.selected_row(self.results)
        if record:
            self._add_product(record)

    def _add_product(self, product: dict) -> None:
        for entry in self.items:
            if entry["product_id"] == product["id"]:
                entry["quantity"] = round(float(entry["quantity"]) + 1, 3)
                self.search.clear()
                self._recompute()
                return
        self.items.append({
            "product_id": product["id"],
            "name": product["name"],
            "quantity": 1.0,
            "unit_price": int(product["purchase_price"]),
        })
        self.search.clear()
        self.results_model.set_rows([])
        self._recompute()
        self.table.selectRow(len(self.items) - 1)

    def _current_index(self) -> int:
        index = self.table.currentIndex()
        return index.row() if index.isValid() else -1

    def _bind_line(self) -> None:
        if self._updating:
            return
        position = self._current_index()
        enabled = 0 <= position < len(self.items)
        self.qty_spin.setEnabled(enabled)
        self.price_edit.setEnabled(enabled)
        if not enabled:
            return
        item = self.items[position]
        self._updating = True
        self.qty_spin.setValue(float(item["quantity"]))
        self.price_edit.setText(f"{from_minor(item['unit_price']):.2f}")
        self._updating = False

    def _on_line_changed(self) -> None:
        if self._updating:
            return
        position = self._current_index()
        if not 0 <= position < len(self.items):
            return
        self.items[position]["quantity"] = round(self.qty_spin.value(), 3)
        try:
            self.items[position]["unit_price"] = parse_input(
                self.price_edit.text(), "Unit cost")
        except AppError:
            pass
        self._recompute()

    def _remove_line(self) -> None:
        position = self._current_index()
        if 0 <= position < len(self.items):
            self.items.pop(position)
            self._recompute()

    def _recompute(self) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            subtotal = 0
            rows = []
            for item in self.items:
                line_total = int(round(item["unit_price"] * item["quantity"]))
                subtotal += line_total
                rows.append({**item, "line_total": line_total})
            try:
                discount = parse_input(self.discount_edit.text() or "0", "Discount")
                paid = parse_input(self.paid_edit.text() or "0", "Paid amount")
            except AppError:
                discount, paid = 0, 0
            discount = min(discount, subtotal)
            total = subtotal - discount
            self.subtotal_label.setText(format_minor(subtotal, "", False))
            self.total_label.setText(format_minor(total, self.ctx.settings.currency))
            self.balance_label.setText(
                format_minor(max(0, total - paid), self.ctx.settings.currency))
            self.model.set_rows(rows)
        finally:
            self._updating = False

    def validate(self) -> str:
        if not self.items:
            return "Add at least one product to this purchase."
        try:
            paid = parse_input(self.paid_edit.text() or "0", "Paid amount")
            discount = parse_input(self.discount_edit.text() or "0", "Discount")
        except AppError as exc:
            return exc.message
        subtotal = sum(int(i["unit_price"] * i["quantity"]) for i in self.items)
        if discount > subtotal:
            return "Discount cannot exceed the purchase total."
        if paid > subtotal - discount:
            return "Paid amount cannot exceed the purchase total."
        return ""

    def accept(self) -> None:
        error = self.validate()
        if error:
            self.set_error(error)
            return
        supplier_id = self._supplier_id()
        # the service takes money in major units, the cart holds minor units
        items = [{**entry,
                  "unit_price": f"{from_minor(int(entry['unit_price'])):.2f}"}
                 for entry in self.items]
        try:
            self.purchase = self.ctx.purchases.create_purchase(
                supplier_id, items,
                paid=self.paid_edit.text() or "0",
                discount=self.discount_edit.text() or "0",
                purchase_date=self.purchase_date.date().toString("yyyy-MM-dd"),
                notes=self.notes.text().strip(), session=self.ctx.session)
        except AppError as exc:
            self.set_error(exc.message)
            return
        except Exception as exc:  # pragma: no cover
            widgets.error_box(self, exc)
            return
        super().accept()


class PurchaseDetailDialog(QDialog):
    def __init__(self, ctx, purchase_id: int, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        purchase = ctx.purchases.get_purchase(purchase_id)
        self.setWindowTitle(f"Purchase {purchase['purchase_no']}")
        self.setModal(True)
        self.setMinimumSize(640, 460)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        info = QLabel(
            f"{purchase['purchase_no']}   •   {purchase['supplier']}   •   "
            f"{purchase['purchase_date']}\n"
            f"Status: {purchase['status']}   •   Created by: "
            f"{purchase.get('created_by') or '-'}")
        info.setObjectName("MutedLabel")
        root.addWidget(info)
        table, model = widgets.make_table(
            [widgets.Column("product_name", "Product", 240),
             widgets.Column("quantity", "Qty", 80, "right"),
             widgets.Column("unit_price", "Unit cost", 110, "right",
                            lambda v: format_minor(v, "", False)),
             widgets.Column("line_total", "Total", 120, "right",
                            lambda v: format_minor(v, "", False))],
            purchase["items"])
        root.addWidget(table, 1)
        totals = QLabel(
            f"Subtotal: {format_minor(purchase['subtotal'], '', False)}    "
            f"Discount: {format_minor(purchase['discount'], '', False)}    "
            f"Total: {format_minor(purchase['total'], self.ctx.settings.currency)}\n"
            f"Paid: {format_minor(purchase['paid'], self.ctx.settings.currency)}    "
            f"Balance: {format_minor(purchase['balance'], self.ctx.settings.currency)}")
        totals.setStyleSheet("font-weight:700;")
        root.addWidget(totals)
        if purchase.get("notes"):
            root.addWidget(widgets.muted(purchase["notes"]))
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        root.addLayout(row)


class PurchasesPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = widgets.PageHeader("Purchases",
                                    "Record stock coming in from suppliers")
        if ctx.can("purchases.create"):
            new_button = QPushButton("New purchase")
            new_button.setProperty("variant", "primary")
            new_button.setIcon(icons.icon("add", "primary", 16))
            new_button.clicked.connect(self.new_purchase)
            header.add_action(new_button)
        root.addWidget(header)

        summary = QHBoxLayout()
        summary.setSpacing(10)
        self.cards = {
            "total": widgets.StatCard("Purchases (period)", "-", "truck", "primary"),
            "paid": widgets.StatCard("Paid", "-", "money", "success"),
            "balance": widgets.StatCard("Outstanding", "-", "warning", "warning"),
        }
        for card in self.cards.values():
            summary.addWidget(card)
        summary.addStretch(1)
        root.addLayout(summary)

        filters = QWidget()
        filter_layout = QHBoxLayout(filters)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)
        self.search = widgets.SearchBox("Search purchase number or supplier")
        self.search.changed.connect(lambda _t: self.refresh())
        filter_layout.addWidget(self.search, 1)
        from PySide6.QtWidgets import QDateEdit
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
        filter_layout.addWidget(QLabel("From"))
        filter_layout.addWidget(self.date_from)
        filter_layout.addWidget(QLabel("To"))
        filter_layout.addWidget(self.date_to)
        root.addWidget(filters)

        columns = [
            widgets.Column("purchase_no", "Purchase #", 130),
            widgets.Column("purchase_date", "Date", 110),
            widgets.Column("supplier", "Supplier", 200),
            widgets.Column("item_count", "Items", 70, "center"),
            widgets.Column("total", "Total", 120, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("paid", "Paid", 120, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("balance", "Balance", 120, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("status", "Status", 100, "center"),
            widgets.Column("created_by", "By", 110),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        self.table.doubleClicked.connect(self.view_purchase)
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.addWidget(widgets.hint("Double-click a purchase to view it."))
        footer.addStretch(1)
        self.count_label = widgets.hint("")
        footer.addWidget(self.count_label)
        root.addLayout(footer)

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        rows = self.ctx.purchases.list_purchases(
            self.date_from.date().toString("yyyy-MM-dd"),
            self.date_to.date().toString("yyyy-MM-dd"),
            self.search.text())
        self.model.set_rows(rows)
        self.count_label.setText(f"{len(rows)} purchase(s)")
        self.table.resizeColumnsToContents()
        totals = self.ctx.purchases.totals_between(
            self.date_from.date().toString("yyyy-MM-dd"),
            self.date_to.date().toString("yyyy-MM-dd"))
        currency = self.ctx.settings.currency
        self.cards["total"].set_value(format_minor(totals["total"], currency))
        self.cards["paid"].set_value(format_minor(totals["paid"], currency))
        self.cards["balance"].set_value(format_minor(totals["balance"], currency))

    def new_purchase(self) -> None:
        dialog = PurchaseDialog(self.ctx, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "Purchase recorded and stock updated", "success")

    def view_purchase(self) -> None:
        record = widgets.selected_row(self.table)
        if not record:
            return
        PurchaseDetailDialog(self.ctx, record["id"], self).exec()


def create(ctx, parent=None) -> PurchasesPage:
    return PurchasesPage(ctx, parent)
