"""Customer management and purchase history."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from ...core.exceptions import AppError
from ...core.money import format_minor
from .. import icons, theme, widgets


class CustomerDialog(widgets.FormDialog):
    def __init__(self, ctx, parent=None, customer: dict | None = None):
        super().__init__(parent, "Edit customer" if customer else "New customer",
                         "Save customer")
        self.ctx = ctx
        self.customer = customer
        self.customer_id = customer["id"] if customer else None
        self.setMinimumWidth(520)

        self.name = QLineEdit(customer.get("name", "") if customer else "")
        self.name.setPlaceholderText("Customer name *")
        self.phone = QLineEdit(customer.get("phone", "") if customer else "")
        self.phone.setPlaceholderText("0300-0000000")
        self.whatsapp = QLineEdit(customer.get("whatsapp", "") if customer else "")
        self.whatsapp.setPlaceholderText("WhatsApp number (optional)")
        self.address = QLineEdit(customer.get("address", "") if customer else "")
        self.email = QLineEdit(customer.get("email", "") if customer else "")
        self.email.setPlaceholderText("name@example.com")
        self.notes = QPlainTextEdit(customer.get("notes", "") if customer else "")
        self.notes.setFixedHeight(70)

        self.add_field("Name *", self.name)
        self.add_field("Phone", self.phone)
        self.add_field("WhatsApp", self.whatsapp)
        self.add_field("Address", self.address)
        self.add_field("Email", self.email)
        self.add_field("Notes", self.notes)

    def validate(self) -> str:
        if not self.name.text().strip():
            return "Customer name is required."
        email = self.email.text().strip()
        if email and "@" not in email:
            return "Please enter a valid email address."
        return ""

    def accept(self) -> None:
        payload = {
            "name": self.name.text().strip(),
            "phone": self.phone.text().strip(),
            "whatsapp": self.whatsapp.text().strip(),
            "address": self.address.text().strip(),
            "email": self.email.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }
        try:
            if self.customer_id:
                self.ctx.customers.update(self.customer_id, payload)
            else:
                self.customer_id = self.ctx.customers.create(payload)
        except AppError as exc:
            self.set_error(exc.message)
            return
        super().accept()


class CustomerHistoryDialog(QDialog):
    def __init__(self, ctx, customer: dict, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"Purchases - {customer['name']}")
        self.setModal(True)
        self.setMinimumSize(700, 420)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        header = QLabel(
            f"{customer['name']}  •  {customer.get('phone') or 'no phone'}\n"
            f"Total spent: {format_minor(customer.get('total_spent', 0), ctx.settings.currency)}"
            f"   •   Visits: {customer.get('visit_count', 0)}")
        header.setObjectName("MutedLabel")
        root.addWidget(header)
        table, model = widgets.make_table(
            [widgets.Column("invoice_no", "Invoice", 140),
             widgets.Column("created_at", "Date / time", 160),
             widgets.Column("total", "Total", 130, "right",
                            lambda v: format_minor(v, ctx.settings.currency)),
             widgets.Column("payment_method", "Payment", 110),
             widgets.Column("cashier_name", "Cashier", 120),
             widgets.Column("status", "Status", 130, "center")],
            ctx.customers.history(customer["id"]))
        root.addWidget(table, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        root.addLayout(row)


class CustomersPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = widgets.PageHeader("Customers",
                                    "Walk-in and registered customers with their "
                                    "purchase history")
        if ctx.can("customers.manage"):
            add = QPushButton("New customer")
            add.setProperty("variant", "primary")
            add.setIcon(icons.icon("add", "primary", 16))
            add.clicked.connect(self.add_customer)
            header.add_action(add)
        if ctx.can("products.export"):
            export = QPushButton("Export CSV")
            export.setIcon(icons.icon("export", "primary", 16))
            export.clicked.connect(self.export_csv)
            header.add_action(export)
        root.addWidget(header)

        self.search = widgets.SearchBox("Search name, phone, email or address")
        self.search.changed.connect(lambda _t: self.refresh())
        root.addWidget(self.search)

        columns = [
            widgets.Column("name", "Customer", 200),
            widgets.Column("phone", "Phone", 140),
            widgets.Column("address", "Address", 200),
            widgets.Column("visit_count", "Visits", 70, "right"),
            widgets.Column("total_spent", "Total spent", 140, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("last_visit", "Last visit", 150),
            widgets.Column("is_walkin", "Type", 110, "center",
                           lambda v: "Walk-in" if v else "Registered"),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        self.table.doubleClicked.connect(lambda *_: self.edit_customer())
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        if ctx.can("customers.manage"):
            edit = QPushButton("Edit")
            edit.setIcon(icons.icon("edit", "primary", 16))
            edit.clicked.connect(self.edit_customer)
            footer.addWidget(edit)
        history = QPushButton("Purchase history")
        history.setIcon(icons.icon("history", "primary", 16))
        history.clicked.connect(self.show_history)
        footer.addWidget(history)
        footer.addStretch(1)
        self.count_label = widgets.hint("")
        footer.addWidget(self.count_label)
        root.addLayout(footer)

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        rows = self.ctx.customers.search(self.search.text(), limit=2000)
        self.model.set_rows(rows)
        self.count_label.setText(f"{len(rows)} customer(s)")
        self.table.resizeColumnsToContents()

    def _selected(self) -> dict | None:
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select a customer first.", "warning")
        return record

    def add_customer(self) -> None:
        dialog = CustomerDialog(self.ctx, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "Customer added", "success")

    def edit_customer(self) -> None:
        record = self._selected()
        if not record:
            return
        dialog = CustomerDialog(self.ctx, self, self.ctx.customers.get(record["id"]))
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "Customer updated", "success")

    def show_history(self) -> None:
        record = self._selected()
        if not record:
            return
        full = next((c for c in self.model.rows if c["id"] == record["id"]), record)
        CustomerHistoryDialog(self.ctx, full, self).exec()

    def export_csv(self) -> None:
        path = widgets.file_save_dialog(self, "Export customers",
                                        "CSV files (*.csv)", "customers.csv")
        if not path:
            return
        try:
            self.ctx.csv.export_customers(path)
        except Exception as exc:  # pragma: no cover
            widgets.error_box(self, exc, "Export failed")
            return
        widgets.notify(self, f"Exported to {path}", "success")


def create(ctx, parent=None) -> CustomersPage:
    return CustomersPage(ctx, parent)
