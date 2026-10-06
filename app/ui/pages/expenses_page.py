"""Expense tracking with categories, dates and reports."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from ... import config
from ...core.exceptions import AppError
from ...core.money import format_minor, parse_input
from ...services.expense_service import EXPENSE_CATEGORIES
from .. import icons, widgets


class ExpenseDialog(widgets.FormDialog):
    def __init__(self, ctx, parent=None, expense: dict | None = None):
        super().__init__(parent, "Edit expense" if expense else "New expense",
                         "Save expense")
        self.ctx = ctx
        self.expense = expense
        self.expense_id = expense["id"] if expense else None

        self.title = QLineEdit(expense.get("title", "") if expense else "")
        self.title.setPlaceholderText("e.g. Shop rent for October")
        self.category = QComboBox()
        self.category.addItems(list(EXPENSE_CATEGORIES))
        if expense and expense.get("category") not in EXPENSE_CATEGORIES:
            self.category.addItem(expense["category"])
        if expense:
            self.category.setCurrentText(expense.get("category", "General"))
        self.amount = QLineEdit(
            f"{expense['amount'] / 100:.2f}" if expense else "")
        self.amount.setPlaceholderText("0.00")
        self.expense_date = QDateEdit()
        self.expense_date.setCalendarPopup(True)
        self.expense_date.setDisplayFormat("yyyy-MM-dd")
        if expense:
            self.expense_date.setDate(
                date.fromisoformat(expense.get("expense_date") or
                                   date.today().isoformat()))
        else:
            self.expense_date.setDate(date.today())
        self.method = QComboBox()
        self.method.addItems(list(config.PAYMENT_METHODS))
        if expense:
            self.method.setCurrentText(expense.get("payment_method", "Cash"))
        self.notes = QLineEdit(expense.get("notes", "") if expense else "")

        self.add_field("Title *", self.title)
        self.add_field("Category", self.category)
        self.add_field("Amount *", self.amount)
        self.add_field("Date", self.expense_date)
        self.add_field("Payment method", self.method)
        self.add_field("Notes", self.notes)

    def validate(self) -> str:
        if not self.title.text().strip():
            return "Expense title is required."
        try:
            amount = parse_input(self.amount.text(), "Amount")
        except AppError as exc:
            return exc.message
        if amount <= 0:
            return "Amount must be greater than zero."
        return ""

    def accept(self) -> None:
        payload = {
            "title": self.title.text().strip(),
            "category": self.category.currentText(),
            "amount": self.amount.text(),
            "expense_date": self.expense_date.date().toString("yyyy-MM-dd"),
            "payment_method": self.method.currentText(),
            "notes": self.notes.text().strip(),
        }
        try:
            if self.expense_id:
                self.ctx.expenses.update(self.expense_id, payload)
            else:
                self.ctx.expenses.create(payload)
        except AppError as exc:
            self.set_error(exc.message)
            return
        super().accept()


class ExpensesPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = widgets.PageHeader("Expenses",
                                    "Operating costs included in net profit reports")
        if ctx.can("expenses.manage"):
            add = QPushButton("New expense")
            add.setProperty("variant", "primary")
            add.setIcon(icons.icon("add", "primary", 16))
            add.clicked.connect(self.add_expense)
            header.add_action(add)
        root.addWidget(header)

        summary = QHBoxLayout()
        summary.setSpacing(10)
        self.total_card = widgets.StatCard("Expenses (period)", "-", "money", "warning")
        self.count_card = widgets.StatCard("Entries", "-", "list", "primary")
        summary.addWidget(self.total_card)
        summary.addWidget(self.count_card)
        summary.addStretch(1)
        root.addLayout(summary)

        filters = QWidget()
        layout = QHBoxLayout(filters)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.search = widgets.SearchBox("Search title, notes or category")
        self.search.changed.connect(lambda _t: self.refresh())
        layout.addWidget(self.search, 2)
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setDate(date.today() - timedelta(days=30))
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
        self.category_filter = QComboBox()
        self.category_filter.addItem("All categories", None)
        self.category_filter.addItems(EXPENSE_CATEGORIES)
        self.category_filter.currentIndexChanged.connect(lambda *_: self.refresh())
        layout.addWidget(self.category_filter)
        root.addWidget(filters)

        columns = [
            widgets.Column("expense_date", "Date", 110),
            widgets.Column("title", "Expense", 260),
            widgets.Column("category", "Category", 140),
            widgets.Column("amount", "Amount", 140, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("payment_method", "Method", 120),
            widgets.Column("created_by", "Recorded by", 130),
            widgets.Column("notes", "Notes", 220),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        self.table.doubleClicked.connect(lambda *_: self.edit_expense())
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        if ctx.can("expenses.manage"):
            edit = QPushButton("Edit")
            edit.setIcon(icons.icon("edit", "primary", 16))
            edit.clicked.connect(self.edit_expense)
            footer.addWidget(edit)
            delete = QPushButton("Delete")
            delete.setProperty("variant", "danger")
            delete.clicked.connect(self.delete_expense)
            footer.addWidget(delete)
        footer.addStretch(1)
        self.count_label = widgets.hint("")
        footer.addWidget(self.count_label)
        root.addLayout(footer)

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        rows = self.ctx.expenses.list(
            date_from, date_to, self.search.text(),
            category=self.category_filter.currentText()
            if self.category_filter.currentIndex() > 0 else "")
        self.model.set_rows(rows)
        self.count_label.setText(f"{len(rows)} expense(s)")
        self.table.resizeColumnsToContents()
        self.total_card.set_value(format_minor(
            self.ctx.expenses.total_between(date_from, date_to),
            self.ctx.settings.currency))
        self.count_card.set_value(str(len(rows)))

    def add_expense(self) -> None:
        dialog = ExpenseDialog(self.ctx, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "Expense recorded", "success")

    def edit_expense(self) -> None:
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select an expense first.", "warning")
            return
        dialog = ExpenseDialog(self.ctx, self, record)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "Expense updated", "success")

    def delete_expense(self) -> None:
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select an expense first.", "warning")
            return
        if not widgets.confirm(self, f"Delete expense '{record['title']}'?",
                               "Delete expense"):
            return
        try:
            self.ctx.expenses.delete(record["id"])
        except AppError as exc:
            widgets.error_box(self, exc)
            return
        self.refresh()
        widgets.notify(self, "Expense deleted", "success")


def create(ctx, parent=None) -> ExpensesPage:
    return ExpensesPage(ctx, parent)
