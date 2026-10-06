"""POS billing screen - scan, add, pay, print with minimal clicks."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSplitter, QTableView,
                               QVBoxLayout, QWidget)

from ... import config
from ...core import exceptions
from ...core.exceptions import AppError
from ...core.money import format_minor, from_minor, parse_input, to_minor
from ...services.sale_service import compute_totals
from .. import icons, theme, widgets


# ===========================================================================
# Dialogs
# ===========================================================================
class SaleCompleteDialog(QDialog):
    """Shown once a sale is committed: total, change, print options."""

    def __init__(self, detail: dict, currency: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sale completed")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.action = "print"
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)

        ok = QLabel("SALE COMPLETED")
        ok.setStyleSheet(f"color:{theme.SUCCESS}; font-size:13pt; font-weight:800;")
        ok.setAlignment(Qt.AlignCenter)
        root.addWidget(ok)

        invoice = QLabel(detail["invoice_no"])
        invoice.setStyleSheet(f"color:{theme.PRIMARY}; font-size:20pt; font-weight:700;")
        invoice.setAlignment(Qt.AlignCenter)
        root.addWidget(invoice)

        rows = [
            ("Total", format_minor(detail["total"], currency)),
            ("Paid", format_minor(detail["paid"], currency)),
            ("Change", format_minor(detail["change_due"], currency)),
            ("Payment method", detail["payment_method"]),
            ("Items", str(len(detail["items"]))),
        ]
        grid = QFrame()
        grid.setProperty("card", True)
        grid_layout = QVBoxLayout(grid)
        grid_layout.setContentsMargins(16, 12, 16, 12)
        grid_layout.setSpacing(6)
        for label, value in rows:
            line = QHBoxLayout()
            left = QLabel(label)
            left.setObjectName("MutedLabel")
            right = QLabel(value)
            right.setStyleSheet("font-weight:700; font-size:11pt;")
            if label == "Change":
                right.setStyleSheet(f"color:{theme.SUCCESS}; font-weight:800;"
                                    "font-size:13pt;")
            line.addWidget(left)
            line.addStretch(1)
            line.addWidget(right)
            grid_layout.addLayout(line)
        root.addWidget(grid)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        print_button = QPushButton("Print receipt (Enter)")
        print_button.setProperty("variant", "primary")
        print_button.clicked.connect(lambda: self._choose("print"))
        preview_button = QPushButton("Print preview")
        preview_button.clicked.connect(lambda: self._choose("preview"))
        skip_button = QPushButton("No print")
        skip_button.clicked.connect(lambda: self._choose("skip"))
        buttons.addWidget(print_button, 1)
        buttons.addWidget(preview_button, 1)
        buttons.addWidget(skip_button, 1)
        root.addLayout(buttons)
        hint = widgets.hint("The sale is already saved. Printing is optional.")
        hint.setAlignment(Qt.AlignCenter)
        root.addWidget(hint)
        self.print_button = print_button
        print_button.setDefault(True)

    def _choose(self, action: str) -> None:
        self.action = action
        self.accept()


class HeldSalesDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Held sales")
        self.setModal(True)
        self.setMinimumSize(520, 340)
        self.ctx = ctx
        self.selected_id: int | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.addWidget(widgets.hint("Resume a sale that was placed on hold earlier."))
        columns = [
            widgets.Column("label", "Label", 180),
            widgets.Column("username", "Cashier", 120),
            widgets.Column("created_at", "Held at", 160),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        self.table.doubleClicked.connect(self._resume)
        root.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        resume = QPushButton("Resume")
        resume.setProperty("variant", "primary")
        resume.clicked.connect(self._resume)
        discard = QPushButton("Discard")
        discard.setProperty("variant", "danger")
        discard.clicked.connect(self._discard)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(resume)
        buttons.addWidget(discard)
        buttons.addStretch(1)
        buttons.addWidget(close)
        root.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        self.model.set_rows(self.ctx.sales.list_held_sales())

    def _current(self) -> dict | None:
        return widgets.selected_row(self.table)

    def _resume(self, *_args) -> None:
        record = self._current()
        if not record:
            return
        self.selected_id = record["id"]
        self.accept()

    def _discard(self) -> None:
        record = self._current()
        if not record:
            return
        if widgets.confirm(self, f"Discard held sale '{record['label']}'?", "Discard"):
            self.ctx.sales.delete_held_sale(record["id"])
            self.refresh()


# ===========================================================================
# Page
# ===========================================================================
class PosPage(QWidget):
    """The cashier's home screen."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.items: list[dict] = []
        self.totals: dict = {"subtotal": 0, "item_discount": 0, "bill_discount": 0,
                             "total": 0, "items": [], "goods_total": 0,
                             "bill_discount_type": "None", "bill_discount_value": 0}
        self.customer_id: int | None = None
        self._auto_paid = True
        self._updating = False
        self._products: list[dict] = []
        self._customers: list[dict] = []
        self.installEventFilter(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # ------------------------------------------------------ scan strip
        scan_row = QHBoxLayout()
        scan_row.setSpacing(10)
        self.barcode = widgets.BarcodeInput()
        self.barcode.submitted.connect(self.scan)
        self.barcode.setMinimumHeight(46)
        scan_row.addWidget(self.barcode, 3)
        focus_hint = widgets.hint(
            "USB scanner ready - just scan.  F6 refocuses the barcode field.")
        focus_hint.setAlignment(Qt.AlignCenter)
        scan_row.addWidget(focus_hint, 2)
        self.held_button = QPushButton("Held sales")
        self.held_button.setIcon(icons.icon("history", "muted", 16))
        self.held_button.clicked.connect(self.show_held_sales)
        scan_row.addWidget(self.held_button)
        self.new_sale_button = QPushButton("New sale")
        self.new_sale_button.setIcon(icons.icon("plus", "primary", 16))
        self.new_sale_button.clicked.connect(self.new_sale)
        scan_row.addWidget(self.new_sale_button)
        root.addLayout(scan_row)

        # ------------------------------------------------------- splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_product_panel())
        splitter.addWidget(self._build_cart_panel())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([560, 720])
        root.addWidget(splitter, 1)

        self._install_shortcuts()
        self._recompute()

    # ----------------------------------------------------------- structure
    def _build_product_panel(self) -> QWidget:
        panel = QFrame()
        panel.setProperty("card", True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.search = widgets.SearchBox("Search product name, SKU or barcode")
        self.search.changed.connect(self.refresh_products)
        self.search.returnPressed.connect(lambda: self.add_first_result())
        top.addWidget(self.search, 1)
        self.category_filter = QComboBox()
        self.category_filter.setMinimumWidth(150)
        self.category_filter.currentIndexChanged.connect(lambda *_: self.refresh_products())
        top.addWidget(self.category_filter)
        layout.addLayout(top)

        columns = [
            widgets.Column("name", "Product", 210),
            widgets.Column("barcode", "Barcode", 130),
            widgets.Column("stock", "Stock", 70, "right"),
            widgets.Column("selling_price", "Price", 110, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
        ]
        self.product_table, self.product_model = widgets.make_table(columns, [])
        self.product_table.doubleClicked.connect(
            lambda *_: self.add_row(widgets.selected_row(self.product_table)))
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.product_table, 1)
        self.empty_label = widgets.hint(
            "No products to show. Add products in the Products module.")
        layout.addWidget(self.empty_label)

        footer = QHBoxLayout()
        add_button = QPushButton("Add selected  (Enter)")
        add_button.setProperty("variant", "primary")
        add_button.clicked.connect(lambda: self.add_row(
            widgets.selected_row(self.product_table)))
        footer.addWidget(add_button)
        footer.addStretch(1)
        self.result_count = widgets.hint("")
        footer.addWidget(self.result_count)
        layout.addLayout(footer)
        return panel

    def _build_cart_panel(self) -> QWidget:
        panel = QFrame()
        panel.setProperty("card", True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        # customer --------------------------------------------------------
        customer_row = QHBoxLayout()
        customer_row.setSpacing(8)
        customer_row.addWidget(widgets.muted("Customer"))
        self.customer_combo = QComboBox()
        self.customer_combo.setEditable(True)
        self.customer_combo.setInsertPolicy(QComboBox.NoInsert)
        self.customer_combo.setMinimumWidth(220)
        self.customer_combo.activated.connect(self._on_customer_selected)
        self.customer_combo.editTextChanged.connect(self._on_customer_typed)
        customer_row.addWidget(self.customer_combo, 1)
        new_customer = QPushButton()
        new_customer.setProperty("variant", "flat")
        new_customer.setIcon(icons.icon("add", "primary", 16))
        new_customer.setToolTip("Add a new customer (F4)")
        new_customer.clicked.connect(self.add_customer)
        customer_row.addWidget(new_customer)
        layout.addLayout(customer_row)

        # cart ------------------------------------------------------------
        self.cart_table, self.cart_model = widgets.make_table([], [])
        self.cart_table.setMinimumHeight(180)
        self.cart_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.cart_table.selectionModel().currentChanged.connect(
            lambda *_: self._bind_line_editor())
        layout.addWidget(self.cart_table, 1)

        # line editor -----------------------------------------------------
        line_row = QHBoxLayout()
        line_row.setSpacing(6)
        line_row.addWidget(widgets.muted("Qty"))
        self.qty_spin = QDoubleSpinBox()
        self.qty_spin.setDecimals(3)
        self.qty_spin.setRange(0.001, 1_000_000)
        self.qty_spin.setSingleStep(1)
        self.qty_spin.setKeyboardTracking(False)
        self.qty_spin.valueChanged.connect(self._on_qty_changed)
        line_row.addWidget(self.qty_spin)
        minus = QPushButton("-")
        minus.setFixedWidth(32)
        minus.clicked.connect(lambda: self._step_qty(-1))
        plus = QPushButton("+")
        plus.setFixedWidth(32)
        plus.clicked.connect(lambda: self._step_qty(1))
        line_row.addWidget(minus)
        line_row.addWidget(plus)

        line_row.addSpacing(10)
        line_row.addWidget(widgets.muted("Item discount"))
        self.line_discount_type = QComboBox()
        self.line_discount_type.addItems(["None", "Percentage", "Fixed"])
        self.line_discount_type.currentIndexChanged.connect(
            lambda *_: self._on_discount_type_changed())
        line_row.addWidget(self.line_discount_type)
        self.line_discount_value = QDoubleSpinBox()
        self.line_discount_value.setDecimals(2)
        self.line_discount_value.setRange(0, 100_000_000)
        self.line_discount_value.setKeyboardTracking(False)
        self.line_discount_value.valueChanged.connect(self._on_discount_value_changed)
        line_row.addWidget(self.line_discount_value)

        remove = QPushButton()
        remove.setProperty("variant", "danger")
        remove.setIcon(icons.icon("delete", "danger", 16))
        remove.setToolTip("Remove selected line")
        remove.clicked.connect(self.remove_selected_line)
        line_row.addWidget(remove)
        line_row.addStretch(1)
        layout.addLayout(line_row)

        # totals ----------------------------------------------------------
        totals_box = QFrame()
        totals_box.setStyleSheet(f"background:{theme.BG}; border:1px solid "
                                 f"{theme.BORDER}; border-radius:8px;")
        totals_layout = QVBoxLayout(totals_box)
        totals_layout.setContentsMargins(14, 10, 14, 10)
        totals_layout.setSpacing(4)

        def _line(label: str) -> tuple[QLabel, QLabel]:
            row = QHBoxLayout()
            left = QLabel(label)
            left.setObjectName("MutedLabel")
            right = QLabel("-")
            right.setStyleSheet("font-weight:600;")
            row.addWidget(left)
            row.addStretch(1)
            row.addWidget(right)
            totals_layout.addLayout(row)
            return left, right

        _, self.subtotal_label = _line("Subtotal")
        _, self.item_discount_label = _line("Item discounts")

        bill_row = QHBoxLayout()
        bill_row.addWidget(QLabel("Bill discount"))
        bill_row.addStretch(1)
        self.bill_discount_type = QComboBox()
        self.bill_discount_type.addItems(["None", "Percentage", "Fixed"])
        self.bill_discount_type.setFixedWidth(110)
        self.bill_discount_type.currentIndexChanged.connect(
            lambda *_: self._on_bill_discount_changed())
        self.bill_discount_value = QDoubleSpinBox()
        self.bill_discount_value.setDecimals(2)
        self.bill_discount_value.setRange(0, 100_000_000)
        self.bill_discount_value.setFixedWidth(110)
        self.bill_discount_value.setKeyboardTracking(False)
        self.bill_discount_value.valueChanged.connect(
            lambda *_: self._on_bill_discount_changed())
        bill_row.addWidget(self.bill_discount_type)
        bill_row.addWidget(self.bill_discount_value)
        totals_layout.addLayout(bill_row)

        grand_row = QHBoxLayout()
        grand_left = QLabel("GRAND TOTAL")
        grand_left.setStyleSheet("font-size:12pt; font-weight:800;")
        self.grand_label = QLabel(format_minor(0, self.ctx.settings.currency))
        self.grand_label.setStyleSheet(
            f"font-size:20pt; font-weight:800; color:{theme.PRIMARY};")
        grand_row.addWidget(grand_left)
        grand_row.addStretch(1)
        grand_row.addWidget(self.grand_label)
        totals_layout.addLayout(grand_row)
        layout.addWidget(totals_box)

        # payment ---------------------------------------------------------
        pay_row = QHBoxLayout()
        pay_row.setSpacing(8)
        pay_row.addWidget(widgets.muted("Paid"))
        self.paid_edit = QLineEdit()
        self.paid_edit.setPlaceholderText("0.00")
        self.paid_edit.setAlignment(Qt.AlignRight)
        self.paid_edit.textChanged.connect(self._on_paid_changed)
        self.paid_edit.setMinimumHeight(38)
        pay_row.addWidget(self.paid_edit)
        exact = QPushButton("Exact")
        exact.clicked.connect(self._pay_exact)
        pay_row.addWidget(exact)
        self.quick_buttons: list[QPushButton] = []
        for _ in range(3):
            button = QPushButton()
            button.clicked.connect(self._quick_cash)
            pay_row.addWidget(button)
            self.quick_buttons.append(button)
        pay_row.addSpacing(10)
        pay_row.addWidget(widgets.muted("Method"))
        self.method_combo = QComboBox()
        self.method_combo.addItems(list(config.PAYMENT_METHODS))
        self.method_combo.setCurrentText(
            self.ctx.settings.get("pos.default_payment_method", "Cash"))
        pay_row.addWidget(self.method_combo)
        layout.addLayout(pay_row)

        change_row = QHBoxLayout()
        change_left = QLabel("Change due")
        change_left.setStyleSheet(f"color:{theme.MUTED}; font-size:11pt;")
        self.change_label = QLabel(format_minor(0, self.ctx.settings.currency))
        self.change_label.setStyleSheet(
            f"color:{theme.SUCCESS}; font-size:18pt; font-weight:800;")
        self.error_label = QLabel("")
        self.error_label.setObjectName("ErrorLabel")
        change_row.addWidget(change_left)
        change_row.addWidget(self.change_label)
        change_row.addStretch(1)
        change_row.addWidget(self.error_label)
        layout.addLayout(change_row)

        # actions ---------------------------------------------------------
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        cancel = QPushButton("Cancel  (Esc)")
        cancel.clicked.connect(self.cancel_sale)
        hold = QPushButton("Hold  (F9)")
        hold.setIcon(icons.icon("history", "muted", 16))
        hold.clicked.connect(self.hold_sale)
        complete = QPushButton("Complete sale  (F8)")
        complete.setProperty("variant", "primary")
        complete.setIcon(icons.icon("check", "primary", 18))
        complete.setStyleSheet("QPushButton{font-size:12pt; font-weight:800; "
                               "padding:12px;}")
        complete.clicked.connect(self.complete_sale)
        action_row.addWidget(cancel)
        action_row.addWidget(hold)
        action_row.addStretch(1)
        action_row.addWidget(complete)
        layout.addLayout(action_row)
        return panel

    def _install_shortcuts(self) -> None:
        pairs = [
            ("F6", self.focus_barcode),
            ("F2", lambda: self.search.setFocus()),
            ("F4", self.focus_customer),
            ("F8", self.complete_sale),
            ("F9", self.hold_sale),
            ("Del", self.remove_selected_line),
        ]
        for sequence, handler in pairs:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)

    # ------------------------------------------------------------ products
    def on_show(self) -> None:
        self.refresh_categories()
        self.refresh_products()
        self.refresh_customers()
        self.focus_barcode()

    def refresh_categories(self) -> None:
        current = self.category_filter.currentData()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All categories", None)
        for category in self.ctx.catalog.categories():
            self.category_filter.addItem(category["name"], category["id"])
        index = self.category_filter.findData(current)
        if index >= 0:
            self.category_filter.setCurrentIndex(index)
        self.category_filter.blockSignals(False)

    def refresh_products(self, term: str = "") -> None:
        term = term if isinstance(term, str) else ""
        rows = self.ctx.catalog.search(
            term, category_id=self.category_filter.currentData(), limit=300)
        self._products = rows
        self.product_model.set_rows(rows)
        self.product_table.resizeColumnsToContents()
        self.empty_label.setVisible(not rows)
        self.result_count.setText(f"{len(rows)} product(s)")

    def add_first_result(self) -> None:
        if self._products:
            self.add_product(self._products[0])

    def add_row(self, record: dict | None) -> None:
        if not record:
            return
        self.add_product(record)

    # ------------------------------------------------------------ scanning
    def scan(self, code: str) -> None:
        code = (code or "").strip()
        if not code:
            return
        product = (self.ctx.catalog.find_by_barcode(code)
                   or self.ctx.catalog.find_by_sku(code))
        if not product:
            self._fail(f"Product not found for barcode {code}.")
            self.focus_barcode()
            return
        added = self.add_product(product, focus_barcode=True)
        if added:
            self.show_toast(f"{product['name']} added", "success", 1500)

    def add_product(self, product: dict, focus_barcode: bool = True) -> bool:
        if not self.ctx.can("sales.create"):
            self._fail("You do not have permission to create sales.")
            return False
        quantity = 0.0
        for entry in self.items:
            if entry["product_id"] == product["id"]:
                quantity = float(entry["quantity"]) + 1
                break
        else:
            quantity = 1.0

        allow_negative = self.ctx.settings.get_bool("pos.allow_negative_stock", False)
        available = float(product.get("stock", 0) or 0)
        if not allow_negative and quantity > available + 1e-9:
            self._fail(
                f"Insufficient stock available for '{product['name']}' "
                f"(available: {available:g})."
            )
            return False

        for entry in self.items:
            if entry["product_id"] == product["id"]:
                entry["quantity"] = round(quantity, 3)
                break
        else:
            self.items.append({
                "product_id": product["id"],
                "name": product["name"],
                "sku": product.get("sku") or "",
                "barcode": product.get("barcode") or "",
                "quantity": round(quantity, 3),
                "unit_price": int(product["selling_price"]),
                "discount_type": product.get("discount_type") or "None",
                "discount_value": int(product.get("discount_value") or 0)
                if (product.get("discount_type") or "None") == "Fixed"
                else float(product.get("discount_value") or 0),
            })
        self._clear_error()
        self._recompute()
        if focus_barcode:
            self.focus_barcode()
        return True

    # ----------------------------------------------------------- cart edit
    def _current_index(self) -> int:
        index = self.cart_table.currentIndex()
        return index.row() if index.isValid() else -1

    def _bind_line_editor(self) -> None:
        if self._updating:
            return
        position = self._current_index()
        enabled = 0 <= position < len(self.items)
        self.qty_spin.setEnabled(enabled)
        self.line_discount_type.setEnabled(enabled)
        self.line_discount_value.setEnabled(enabled)
        if not enabled:
            return
        item = self.items[position]
        allow_decimal = self._is_decimal_item(item)
        self._updating = True
        try:
            # changing the decimals re-emits valueChanged - keep it guarded
            self.qty_spin.setDecimals(3 if allow_decimal else 0)
            self.qty_spin.setValue(float(item["quantity"]))
            discount_type = item.get("discount_type", "None")
            self.line_discount_type.setCurrentText(discount_type)
            self.line_discount_value.setEnabled(discount_type != "None")
            if discount_type == "Fixed":
                self.line_discount_value.setMaximum(100_000_000)
                self.line_discount_value.setValue(from_minor(
                    int(item.get("discount_value") or 0)))
            elif discount_type == "Percentage":
                self.line_discount_value.setMaximum(100)
                self.line_discount_value.setValue(float(item.get("discount_value") or 0))
            else:
                self.line_discount_value.setValue(0)
        finally:
            self._updating = False

    def _is_decimal_item(self, item: dict) -> bool:
        for product in self._products:
            if product["id"] == item["product_id"]:
                return bool(product.get("allow_decimal"))
        return True

    def _on_qty_changed(self, value: float) -> None:
        if self._updating:
            return
        position = self._current_index()
        if not 0 <= position < len(self.items):
            return
        entry = self.items[position]
        allow_negative = self.ctx.settings.get_bool("pos.allow_negative_stock", False)
        if not allow_negative:
            available = self._available_stock(entry["product_id"])
            others = sum(float(e["quantity"]) for e in self.items
                         if e["product_id"] == entry["product_id"] and e is not entry)
            if value + others > available + 1e-9:
                self._fail(f"Insufficient stock available (available: {available:g}).")
                self._updating = True
                self.qty_spin.setValue(float(entry["quantity"]))
                self._updating = False
                return
        entry["quantity"] = round(float(value), 3)
        self._clear_error()
        self._recompute()

    def _step_qty(self, delta: int) -> None:
        if self._current_index() < 0:
            return
        decimals = self.qty_spin.decimals()
        value = round(self.qty_spin.value() + delta, decimals)
        self.qty_spin.setValue(max(0.001 if decimals else 1, value))

    def _on_discount_type_changed(self) -> None:
        if self._updating:
            return
        position = self._current_index()
        if not 0 <= position < len(self.items):
            return
        discount_type = self.line_discount_type.currentText()
        self.items[position]["discount_type"] = discount_type
        self._updating = True
        self.line_discount_value.setEnabled(discount_type != "None")
        if discount_type == "Percentage":
            self.line_discount_value.setMaximum(100)
            self.line_discount_value.setValue(0)
        elif discount_type == "Fixed":
            self.line_discount_value.setMaximum(100_000_000)
            self.line_discount_value.setValue(0)
        else:
            self.items[position]["discount_value"] = 0
            self.line_discount_value.setValue(0)
        self._updating = False
        self._recompute()

    def _on_discount_value_changed(self, value: float) -> None:
        if self._updating:
            return
        position = self._current_index()
        if not 0 <= position < len(self.items):
            return
        if self.line_discount_type.currentText() == "Fixed":
            self.items[position]["discount_value"] = to_minor(value)
        else:
            self.items[position]["discount_value"] = float(value)
        self._recompute()

    def remove_selected_line(self) -> None:
        position = self._current_index()
        if not 0 <= position < len(self.items):
            return
        removed = self.items.pop(position)
        self._recompute()
        self.show_toast(f"{removed['name']} removed from the cart", "info", 1500)
        self.focus_barcode()

    def _available_stock(self, product_id: int) -> float:
        for product in self._products:
            if product["id"] == product_id:
                return float(product.get("stock", 0) or 0)
        return float(self.ctx.inventory.stock_of(product_id))

    # ----------------------------------------------------------- totals
    def _on_bill_discount_changed(self) -> None:
        if self._updating:
            return
        discount_type = self.bill_discount_type.currentText()
        value = self.bill_discount_value.value()
        self.bill_discount_value.setEnabled(discount_type != "None")
        if discount_type == "Percentage":
            self.bill_discount_value.setMaximum(100)
            value = min(value, 100)
        elif discount_type == "Fixed":
            self.bill_discount_value.setMaximum(100_000_000)
        self.totals["bill_discount_type"] = discount_type
        self.totals["bill_discount_value"] = value
        self._recompute()

    def _on_paid_changed(self, text: str) -> None:
        if self._updating:
            return
        self._auto_paid = False
        self._update_change()

    def _pay_exact(self) -> None:
        self._auto_paid = True
        self.paid_edit.setText(f"{from_minor(self.totals['total']):.2f}")
        self._update_change()

    def _quick_cash(self) -> None:
        button = self.sender()
        amount = button.property("amount")
        if amount is None:
            return
        self._auto_paid = False
        self.paid_edit.setText(f"{float(amount):.2f}")
        self._update_change()

    def _refresh_quick_buttons(self) -> None:
        total = float(from_minor(self.totals["total"]))
        denominations = [50, 100, 500, 1000, 5000, 10000, 20000, 50000]
        suggestions = [d for d in denominations if d > total][:3]
        if not suggestions:
            suggestions = [denominations[-1]]
        for button, value in zip(self.quick_buttons, suggestions):
            button.setText(f"{value:,.0f}")
            button.setProperty("amount", value)

    def _update_change(self) -> None:
        currency = self.ctx.settings.currency
        try:
            paid = parse_input(self.paid_edit.text(), "Paid amount")
        except AppError:
            paid = 0
        total = self.totals["total"]
        change = paid - total
        self.change_label.setText(format_minor(change, currency))
        self.change_label.setStyleSheet(
            f"color:{theme.DANGER if change < 0 else theme.SUCCESS}; "
            f"font-size:18pt; font-weight:800;")
        if change < 0:
            self.error_label.setText("Paid amount is less than the invoice total.")
            self.error_label.show()
        elif self.error_label.text().startswith("Paid amount"):
            self._clear_error()

    def _recompute(self) -> None:
        if self._updating:
            return
        try:
            totals = compute_totals(
                self.items,
                self.totals.get("bill_discount_type", "None"),
                self.totals.get("bill_discount_value", 0),
            )
        except AppError as exc:
            self._fail(exc.message)
            return
        self.totals = totals
        currency = self.ctx.settings.currency

        self._updating = True
        try:
            rows = []
            for item in totals["items"]:
                rows.append({
                    "name": item["name"],
                    "quantity": float(item["quantity"]),
                    "unit_price": item["unit_price"],
                    "discount": item["discount_amount"],
                    "line_total": item["line_total"],
                })
            if len(self.cart_model.columns) != 5:
                columns = [
                    widgets.Column("name", "Product", 200),
                    widgets.Column("quantity", "Qty", 60, "right"),
                    widgets.Column("unit_price", "Price", 100, "right",
                                   lambda v: format_minor(v, currency, False)),
                    widgets.Column("discount", "Disc", 90, "right",
                                   lambda v: (f"-{format_minor(v, currency, False)}"
                                              if v else "")),
                    widgets.Column("line_total", "Amount", 110, "right",
                                   lambda v: format_minor(v, currency, False)),
                ]
                self.cart_model.columns = columns
            self.cart_model.set_rows(rows)
            self.subtotal_label.setText(format_minor(totals["subtotal"], currency))
            self.item_discount_label.setText(
                f"-{format_minor(totals['item_discount'], currency)}"
                if totals["item_discount"] else format_minor(0, currency))
            self.grand_label.setText(format_minor(totals["total"], currency))
            if self._auto_paid:
                self.paid_edit.blockSignals(True)
                self.paid_edit.setText(f"{from_minor(totals['total']):.2f}")
                self.paid_edit.blockSignals(False)
            self._refresh_quick_buttons()
            if not self.items:
                self.bill_discount_type.setCurrentText("None")
                self.bill_discount_value.setValue(0)
                self.totals["bill_discount_type"] = "None"
                self.totals["bill_discount_value"] = 0
        finally:
            self._updating = False
        self._update_change()

    # -------------------------------------------------------------- state
    def build_cart(self) -> dict:
        paid_text = self.paid_edit.text().strip()
        return {
            "items": self.items,
            "bill_discount_type": self.totals.get("bill_discount_type", "None"),
            "bill_discount_value": self.totals.get("bill_discount_value", 0),
            "customer_id": self.customer_id,
            "payment_method": self.method_combo.currentText(),
            "paid": parse_input(paid_text, "Paid amount") if paid_text else 0,
            "notes": "",
        }

    def new_sale(self, force: bool = False) -> None:
        if self.items and not force:
            if not widgets.confirm(self, "Clear the current sale and start a new one?",
                                   "New sale"):
                return
        self.reset_sale()

    def reset_sale(self) -> None:
        self.items = []
        self.customer_id = None
        self._auto_paid = True
        self.totals["bill_discount_type"] = "None"
        self.totals["bill_discount_value"] = 0
        self._updating = True
        self.bill_discount_type.setCurrentText("None")
        self.bill_discount_value.setValue(0)
        self.customer_combo.setEditText("Walk-in Customer")
        self.method_combo.setCurrentText(
            self.ctx.settings.get("pos.default_payment_method", "Cash"))
        self._updating = False
        self._recompute()
        self.cart_table.clearSelection()
        self.focus_barcode()

    def cancel_sale(self) -> None:
        if not self.items:
            self.reset_sale()
            return
        if widgets.confirm(self, "Cancel this sale? The cart will be cleared.",
                           "Cancel sale"):
            self.reset_sale()
            self.show_toast("Sale cancelled", "info")

    def handle_escape(self) -> None:
        if self.items:
            self.cancel_sale()
        else:
            self.focus_barcode()

    def focus_barcode(self) -> None:
        if self.ctx.settings.get_bool("pos.auto_focus_barcode", True):
            self.barcode.setFocus()
            self.barcode.selectAll()

    def focus_customer(self) -> None:
        self.customer_combo.setFocus()
        self.customer_combo.lineEdit().selectAll()

    # ---------------------------------------------------------- completing
    def complete_sale(self) -> None:
        if not self.items:
            self._fail("The cart is empty. Scan or select a product first.")
            return
        try:
            cart = self.build_cart()
        except AppError as exc:
            self._fail(exc.message)
            return
        try:
            detail = self.ctx.sales.complete_sale(cart)
        except AppError as exc:
            self._fail(exc.message)
            if isinstance(exc, exceptions.ValidationError) and "Paid" in exc.message:
                self.paid_edit.setFocus()
                self.paid_edit.selectAll()
            return
        except Exception as exc:  # pragma: no cover - defensive
            from ...core.logging_setup import get_logger, log_exception
            log_exception(get_logger("pos"), "Sale failed", exc)
            self._fail("Unable to complete this operation. Your data has not been "
                       "changed.")
            return

        currency = self.ctx.settings.currency
        dialog = SaleCompleteDialog(detail, currency, self)
        choice = "print"
        if dialog.exec() == QDialog.Accepted:
            choice = dialog.action
        if choice in ("print", "preview"):
            self._print_receipt(detail, preview=(choice == "preview"),
                                reprint=False)
        self.show_toast(f"Invoice {detail['invoice_no']} saved "
                        f"- change {format_minor(detail['change_due'], currency)}",
                        "success")
        self.reset_sale()
        window = self.window()
        if hasattr(window, "refresh_page"):
            window.refresh_page("dashboard")

    def _print_receipt(self, detail: dict, preview: bool = False,
                       reprint: bool = False) -> None:
        try:
            html_text = self.ctx.receipts.receipt_html(
                detail, reprint=reprint, note="" if not reprint else "Reprint")
            if preview:
                self.ctx.receipts.preview(self, html_text,
                                          title=f"Invoice {detail['invoice_no']}")
            else:
                self.ctx.receipts.print_html(html_text)
        except Exception as exc:  # pragma: no cover - printer drivers vary
            from ...core.logging_setup import get_logger, log_exception
            log_exception(get_logger("pos"), "Receipt printing failed", exc)
            self.show_toast("The receipt could not be printed. Check your printer "
                            "settings under Settings > Hardware.", "warning", 5000)

    # ------------------------------------------------------------- holding
    def hold_sale(self) -> None:
        if not self.items:
            self._fail("There is nothing to hold - the cart is empty.")
            return
        from PySide6.QtWidgets import QInputDialog
        label, ok = QInputDialog.getText(
            self, "Hold sale", "Label (optional):",
            text=f"Customer {self.customer_combo.currentText()}".strip())
        if not ok:
            return
        try:
            self.ctx.sales.hold_sale(self.build_cart(), label)
        except AppError as exc:
            self._fail(exc.message)
            return
        self.reset_sale()
        self.show_toast("Sale placed on hold", "info")

    def show_held_sales(self) -> None:
        dialog = HeldSalesDialog(self.ctx, self)
        if dialog.exec() != QDialog.Accepted or dialog.selected_id is None:
            return
        try:
            cart = self.ctx.sales.get_held_sale(dialog.selected_id)
        except AppError as exc:
            self._fail(exc.message)
            return
        if self.items and not widgets.confirm(
                self, "Resume the held sale? The current cart will be replaced.",
                "Resume held sale"):
            return
        self.items = cart.get("items", [])
        self.customer_id = cart.get("customer_id")
        self.method_combo.setCurrentText(
            cart.get("payment_method", self.method_combo.currentText()))
        self.totals["bill_discount_type"] = cart.get("bill_discount_type", "None")
        self.totals["bill_discount_value"] = cart.get("bill_discount_value", 0)
        self._updating = True
        self.bill_discount_type.setCurrentText(
            str(cart.get("bill_discount_type", "None")))
        self.bill_discount_value.setValue(float(cart.get("bill_discount_value", 0) or 0))
        self._updating = False
        self.ctx.sales.delete_held_sale(dialog.selected_id)
        self._recompute()
        self._select_customer_by_id(self.customer_id)
        self.show_toast("Held sale resumed", "success")
        self.focus_barcode()

    # ----------------------------------------------------------- customers
    def refresh_customers(self) -> None:
        self._customers = self.ctx.customers.search(limit=1000)
        current_text = self.customer_combo.currentText()
        self.customer_combo.blockSignals(True)
        self.customer_combo.clear()
        self.customer_combo.addItem("Walk-in Customer", None)
        for customer in self._customers:
            label = customer["name"]
            if customer["phone"]:
                label += f"  •  {customer['phone']}"
            self.customer_combo.addItem(label, customer["id"])
        self.customer_combo.setEditText(current_text or "Walk-in Customer")
        self.customer_combo.blockSignals(False)
        if self.customer_id:
            self._select_customer_by_id(self.customer_id)

    def _select_customer_by_id(self, customer_id: int | None) -> None:
        if not customer_id:
            self.customer_id = None
            return
        index = self.customer_combo.findData(customer_id)
        if index >= 0:
            self.customer_combo.setCurrentIndex(index)
            self.customer_id = customer_id
        else:
            self.customer_id = None

    def _on_customer_selected(self, index: int) -> None:
        self.customer_id = self.customer_combo.itemData(index)

    def _on_customer_typed(self, text: str) -> None:
        if text.strip().lower() in ("", "walk-in", "walk-in customer"):
            self.customer_id = None
            return
        for customer in self._customers:
            if text.strip().lower() == customer["name"].lower():
                self.customer_id = customer["id"]
                return
        self.customer_id = None

    def add_customer(self) -> None:
        from .customers_page import CustomerDialog
        dialog = CustomerDialog(self.ctx, self)
        if dialog.exec() == QDialog.Accepted and dialog.customer_id:
            self.refresh_customers()
            self._select_customer_by_id(dialog.customer_id)
            self.show_toast("Customer added", "success")

    # ------------------------------------------------------------- feedback
    def show_toast(self, message: str, kind: str = "info", duration: int = 3000) -> None:
        window = self.window()
        if hasattr(window, "show_toast"):
            window.show_toast(message, kind, duration)
            return
        widgets.notify(self, message, kind)

    def _fail(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
        self.show_toast(message, "error", 4000)

    def _clear_error(self) -> None:
        self.error_label.clear()
        self.error_label.hide()

    # ------------------------------------------------------- scanner bridge
    def eventFilter(self, watched, event):  # noqa: N802
        """Keystrokes typed anywhere on this screen reach the barcode field."""
        if event.type() == QEvent.KeyPress and watched is self:
            key = event.key()
            text = event.text()
            if text and text.isprintable() and key not in (
                    Qt.Key_Escape, Qt.Key_F1, Qt.Key_F2, Qt.Key_F4, Qt.Key_F6,
                    Qt.Key_F8, Qt.Key_F9):
                focused = self.focusWidget()
                editable = isinstance(focused, (QLineEdit, QComboBox,
                                                QDoubleSpinBox))
                if not editable:
                    self.barcode.setFocus()
                    from PySide6.QtWidgets import QApplication
                    QApplication.sendEvent(self.barcode, event)
                    return True
        return super().eventFilter(watched, event)


def create(ctx, parent=None) -> PosPage:
    return PosPage(ctx, parent)
