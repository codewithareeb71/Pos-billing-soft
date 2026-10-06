"""Supplier management, purchase history and outstanding balances."""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ...core.exceptions import AppError
from ...core.money import format_minor, parse_input
from .. import icons, theme, widgets


class SupplierDialog(widgets.FormDialog):
    def __init__(self, ctx, parent=None, supplier: dict | None = None):
        super().__init__(parent, "Edit supplier" if supplier else "New supplier",
                         "Save supplier")
        self.ctx = ctx
        self.supplier = supplier
        self.supplier_id = supplier["id"] if supplier else None
        self.setMinimumWidth(540)
        self.name = QLineEdit(supplier.get("name", "") if supplier else "")
        self.company = QLineEdit(supplier.get("company", "") if supplier else "")
        self.phone = QLineEdit(supplier.get("phone", "") if supplier else "")
        self.whatsapp = QLineEdit(supplier.get("whatsapp", "") if supplier else "")
        self.address = QLineEdit(supplier.get("address", "") if supplier else "")
        self.email = QLineEdit(supplier.get("email", "") if supplier else "")
        self.notes = QPlainTextEdit(supplier.get("notes", "") if supplier else "")
        self.notes.setFixedHeight(70)
        self.add_field("Name *", self.name)
        self.add_field("Company", self.company)
        self.add_field("Phone", self.phone)
        self.add_field("WhatsApp", self.whatsapp)
        self.add_field("Address", self.address)
        self.add_field("Email", self.email)
        self.add_field("Notes", self.notes)

    def validate(self) -> str:
        if not self.name.text().strip():
            return "Supplier name is required."
        return ""

    def accept(self) -> None:
        payload = {field: widget.text().strip()
                   for field, widget in (
                       ("name", self.name), ("company", self.company),
                       ("phone", self.phone), ("whatsapp", self.whatsapp),
                       ("address", self.address), ("email", self.email))}
        payload["notes"] = self.notes.toPlainText().strip()
        try:
            if self.supplier_id:
                self.ctx.suppliers.update(self.supplier_id, payload)
            else:
                self.supplier_id = self.ctx.suppliers.create(payload)
        except AppError as exc:
            self.set_error(exc.message)
            return
        super().accept()


class SupplierPaymentDialog(widgets.FormDialog):
    def __init__(self, ctx, supplier: dict, parent=None):
        super().__init__(parent, f"Pay supplier - {supplier['name']}", "Record payment")
        self.ctx = ctx
        self.supplier = supplier
        outstanding = int(supplier.get("outstanding", 0))
        info = QLabel(f"Outstanding balance: "
                      f"{format_minor(outstanding, ctx.settings.currency)}")
        info.setObjectName("MutedLabel")
        self.root.insertWidget(0, info)
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("0.00")
        self.method = QComboBox()
        self.method.addItems(["Cash", "Card", "Bank Transfer", "Other"])
        self.note = QLineEdit()
        self.add_field("Amount *", self.amount)
        self.add_field("Method", self.method)
        self.add_field("Note", self.note)

    def validate(self) -> str:
        try:
            amount = parse_input(self.amount.text(), "Amount")
        except AppError as exc:
            return exc.message
        if amount <= 0:
            return "Amount must be greater than zero."
        return ""

    def accept(self) -> None:
        try:
            self.ctx.suppliers.record_payment(
                self.supplier["id"], self.amount.text(),
                self.method.currentText(), self.note.text().strip())
        except AppError as exc:
            self.set_error(exc.message)
            return
        super().accept()


class SupplierDetailDialog(QDialog):
    def __init__(self, ctx, supplier: dict, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.supplier_id = supplier["id"]
        self.setWindowTitle(f"{supplier['name']} - supplier record")
        self.setModal(True)
        self.setMinimumSize(760, 500)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        self.info = QLabel()
        self.info.setObjectName("MutedLabel")
        root.addWidget(self.info)
        self.tables: list[tuple] = []
        self._purchases_table = self._section(
            root, "Purchases",
            [widgets.Column("purchase_no", "Purchase #", 130),
             widgets.Column("purchase_date", "Date", 110),
             widgets.Column("total", "Total", 120, "right",
                            lambda v: format_minor(v, ctx.settings.currency)),
             widgets.Column("paid", "Paid", 120, "right",
                            lambda v: format_minor(v, ctx.settings.currency)),
             widgets.Column("balance", "Balance", 120, "right",
                            lambda v: format_minor(v, ctx.settings.currency)),
             widgets.Column("status", "Status", 100, "center")])
        self._payments_table = self._section(
            root, "Payment history",
            [widgets.Column("created_at", "Date", 160),
             widgets.Column("method", "Method", 110),
             widgets.Column("amount", "Amount", 130, "right",
                            lambda v: format_minor(v, ctx.settings.currency)),
             widgets.Column("note", "Note", 200)])

        buttons = QHBoxLayout()
        if ctx.can("purchases.create"):
            pay = QPushButton("Record payment")
            pay.setProperty("variant", "primary")
            pay.clicked.connect(self._record_payment)
            buttons.addWidget(pay)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        self.reload()

    @staticmethod
    def _section(parent_layout, title: str, columns) -> tuple:
        parent_layout.addWidget(widgets.section_title(title))
        table, model = widgets.make_table(columns, [])
        table.setMaximumHeight(170)
        parent_layout.addWidget(table)
        return table, model

    def reload(self) -> None:
        supplier = self.ctx.suppliers.get(self.supplier_id)
        suppliers = self.ctx.suppliers.search(term=supplier["name"], limit=5)
        record = next((s for s in suppliers if s["id"] == self.supplier_id), {})
        self.info.setText(
            f"{supplier.get('company') or ''}  •  {supplier.get('phone') or 'no phone'}"
            f"  •  Outstanding: "
            f"{format_minor(record.get('outstanding', 0), self.ctx.settings.currency)}")
        _, purchases_model = self._purchases_table
        purchases_model.set_rows(self.ctx.suppliers.purchases(self.supplier_id))
        _, payments_model = self._payments_table
        payments_model.set_rows(self.ctx.suppliers.payment_history(self.supplier_id))

    def _record_payment(self) -> None:
        supplier = self.ctx.suppliers.get(self.supplier_id)
        suppliers = self.ctx.suppliers.search(term=supplier["name"], limit=5)
        record = next((s for s in suppliers if s["id"] == self.supplier_id), supplier)
        dialog = SupplierPaymentDialog(self.ctx, record, self)
        if dialog.exec() == QDialog.Accepted:
            self.reload()
            widgets.notify(self, "Payment recorded", "success")


class SuppliersPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = widgets.PageHeader("Suppliers",
                                    "Who you buy from and what you still owe")
        if ctx.can("suppliers.manage"):
            add = QPushButton("New supplier")
            add.setProperty("variant", "primary")
            add.setIcon(icons.icon("add", "primary", 16))
            add.clicked.connect(self.add_supplier)
            header.add_action(add)
        if ctx.can("products.export"):
            export = QPushButton("Export CSV")
            export.setIcon(icons.icon("export", "primary", 16))
            export.clicked.connect(self.export_csv)
            header.add_action(export)
        root.addWidget(header)

        self.search = widgets.SearchBox("Search supplier, company or phone")
        self.search.changed.connect(lambda _t: self.refresh())
        root.addWidget(self.search)

        columns = [
            widgets.Column("name", "Supplier", 200),
            widgets.Column("company", "Company", 180),
            widgets.Column("phone", "Phone", 140),
            widgets.Column("purchase_count", "Purchases", 90, "right"),
            widgets.Column("total_purchased", "Purchased", 140, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("outstanding", "Outstanding", 140, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("last_purchase", "Last purchase", 130),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        self.table.doubleClicked.connect(lambda *_: self.open_supplier())
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        if ctx.can("suppliers.manage"):
            edit = QPushButton("Edit")
            edit.setIcon(icons.icon("edit", "primary", 16))
            edit.clicked.connect(self.edit_supplier)
            footer.addWidget(edit)
        details = QPushButton("Purchases & payments")
        details.setIcon(icons.icon("truck", "primary", 16))
        details.clicked.connect(self.open_supplier)
        footer.addWidget(details)
        footer.addStretch(1)
        self.count_label = widgets.hint("")
        footer.addWidget(self.count_label)
        root.addLayout(footer)

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        rows = self.ctx.suppliers.search(self.search.text(), limit=2000)
        self.model.set_rows(rows)
        self.count_label.setText(f"{len(rows)} supplier(s)")
        self.table.resizeColumnsToContents()

    def _selected(self) -> dict | None:
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select a supplier first.", "warning")
        return record

    def add_supplier(self) -> None:
        dialog = SupplierDialog(self.ctx, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "Supplier added", "success")

    def edit_supplier(self) -> None:
        record = self._selected()
        if not record:
            return
        dialog = SupplierDialog(self.ctx, self, self.ctx.suppliers.get(record["id"]))
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "Supplier updated", "success")

    def open_supplier(self) -> None:
        record = self._selected()
        if not record:
            return
        SupplierDetailDialog(self.ctx, self.ctx.suppliers.get(record["id"]),
                             self).exec()
        self.refresh()

    def export_csv(self) -> None:
        path = widgets.file_save_dialog(self, "Export suppliers",
                                        "CSV files (*.csv)", "suppliers.csv")
        if not path:
            return
        try:
            self.ctx.csv.export_suppliers(path)
        except Exception as exc:  # pragma: no cover
            widgets.error_box(self, exc, "Export failed")
            return
        widgets.notify(self, f"Exported to {path}", "success")


def create(ctx, parent=None) -> SuppliersPage:
    return SuppliersPage(ctx, parent)
