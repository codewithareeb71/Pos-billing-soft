"""Inventory: stock levels, alerts, adjustments and movement history."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from ... import config
from ...core.exceptions import AppError
from ...core.money import format_minor, from_minor
from .. import icons, theme, widgets


class AdjustDialog(widgets.FormDialog):
    def __init__(self, ctx, product: dict, parent=None):
        super().__init__(parent, f"Adjust stock - {product['name']}",
                         "Apply adjustment")
        self.ctx = ctx
        self.product = product
        current = float(product.get("stock", 0) or 0)
        info = QLabel(
            f"Current stock: {current:g}  •  Minimum: {float(product.get('min_stock', 0)):g}"
            f"  •  {product.get('barcode') or '-'}")
        info.setObjectName("MutedLabel")
        info.setWordWrap(True)
        self.root.insertWidget(0, info)

        self.new_stock = QDoubleSpinBox()
        self.new_stock.setRange(0, 1_000_000)
        self.new_stock.setDecimals(3)
        self.new_stock.setValue(current)
        self.new_stock.setKeyboardTracking(False)
        self.change_label = QLabel("Change: 0")
        self.change_label.setObjectName("MutedLabel")
        self.new_stock.valueChanged.connect(self._update_change)

        self.reason = QComboBox()
        self.reason.addItems(list(config.STOCK_ADJUST_REASONS))
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional note (e.g. 'Recounted shelf 2')")

        self.add_field("New stock", self.new_stock)
        self.form.addRow("", self.change_label)
        self.add_field("Reason *", self.reason)
        self.add_field("Note", self.note)
        self._update_change()

    def _update_change(self) -> None:
        change = self.new_stock.value() - float(self.product.get("stock", 0) or 0)
        sign = "+" if change > 0 else ""
        self.change_label.setText(f"Change: {sign}{change:g}")

    def validate(self) -> str:
        if not self.reason.currentText().strip():
            return "Please choose a reason for the adjustment."
        return ""

    def accept(self) -> None:
        try:
            self.ctx.inventory.adjust(
                self.product["id"], self.new_stock.value(),
                self.reason.currentText(), session=self.ctx.session,
                note=self.note.text().strip())
        except AppError as exc:
            self.set_error(exc.message)
            return
        super().accept()


class MovementsDialog(QDialog):
    def __init__(self, ctx, product: dict | None = None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        title = (f"Stock movements - {product['name']}" if product
                 else "Stock movement history")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(780, 460)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        columns = [
            widgets.Column("created_at", "Date / time", 150),
            widgets.Column("product_name", "Product", 190),
            widgets.Column("movement", "Type", 100, "center"),
            widgets.Column("quantity_change", "Change", 85, "right",
                           lambda v: f"{float(v):+g}"),
            widgets.Column("quantity_after", "Balance", 85, "right",
                           lambda v: f"{float(v):g}"),
            widgets.Column("reference_type", "Reference", 90, "center"),
            widgets.Column("username", "User", 100),
            widgets.Column("note", "Note", 220),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        root.addWidget(self.table, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        root.addLayout(row)
        rows = self.ctx.inventory.movements(
            product["id"] if product else None, limit=1000)
        self.model.set_rows(rows)


class InventoryPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = widgets.PageHeader("Inventory",
                                    "Live stock levels, values and alerts")
        if ctx.can("inventory.adjust"):
            adjust = QPushButton("Adjust stock")
            adjust.setIcon(icons.icon("edit", "primary", 16))
            adjust.clicked.connect(self.adjust_stock)
            header.add_action(adjust)
        movements = QPushButton("Movement history")
        movements.setIcon(icons.icon("history", "primary", 16))
        movements.clicked.connect(lambda: MovementsDialog(self.ctx, None, self).exec())
        header.add_action(movements)
        if ctx.can("products.export"):
            export = QPushButton("Export CSV")
            export.setIcon(icons.icon("export", "primary", 16))
            export.clicked.connect(self.export_csv)
            header.add_action(export)
        root.addWidget(header)

        summary = QHBoxLayout()
        summary.setSpacing(10)
        self.summary_cards = {
            "value": widgets.StatCard("Stock value (at cost)", "-", "money", "primary"),
            "low": widgets.StatCard("Low stock items", "-", "warning", "warning"),
            "out": widgets.StatCard("Out of stock items", "-", "error", "danger"),
        }
        for card in self.summary_cards.values():
            summary.addWidget(card)
        summary.addStretch(1)
        root.addLayout(summary)

        filters = QWidget()
        filter_layout = QHBoxLayout(filters)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)
        self.search = widgets.SearchBox("Search product, SKU or barcode")
        self.search.changed.connect(lambda _t: self.refresh())
        filter_layout.addWidget(self.search, 2)
        self.category_filter = QComboBox()
        self.category_filter.currentIndexChanged.connect(lambda *_: self.refresh())
        filter_layout.addWidget(self.category_filter)
        self.supplier_filter = QComboBox()
        self.supplier_filter.currentIndexChanged.connect(lambda *_: self.refresh())
        filter_layout.addWidget(self.supplier_filter)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All items", "In stock", "Low stock",
                                     "Out of stock"])
        self.status_filter.currentIndexChanged.connect(lambda *_: self.refresh())
        filter_layout.addWidget(self.status_filter)
        root.addWidget(filters)

        columns = [
            widgets.Column("name", "Product", 210),
            widgets.Column("barcode", "Barcode", 130),
            widgets.Column("category", "Category", 115),
            widgets.Column("supplier", "Supplier", 130),
            widgets.Column("stock", "Stock", 75, "right"),
            widgets.Column("min_stock", "Min", 60, "right"),
            widgets.Column("purchase_price", "Cost", 110, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("selling_price", "Price", 110, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("stock_value", "Value", 120, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("status", "Status", 105, "center"),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        self.table.doubleClicked.connect(lambda *_: self.adjust_stock())
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.count_label = widgets.hint("")
        footer.addStretch(1)
        footer.addWidget(self.count_label)
        root.addLayout(footer)

    def on_show(self) -> None:
        self._refresh_filters()
        self.refresh()

    def _refresh_filters(self) -> None:
        for combo, loader, label in (
                (self.category_filter, self.ctx.catalog.categories, "All categories"),
                (self.supplier_filter, lambda: self.ctx.suppliers.search(limit=1000),
                 "All suppliers")):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(label, None)
            for record in loader():
                combo.addItem(record["name"], record["id"])
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def refresh(self) -> None:
        status_map = {"In stock": "ok", "Low stock": "low", "Out of stock": "out"}
        rows = self.ctx.inventory.list_inventory(
            self.search.text(), category_id=self.category_filter.currentData(),
            supplier_id=self.supplier_filter.currentData(),
            status=status_map.get(self.status_filter.currentText(), ""),
            limit=10000)
        self.model.set_rows(rows)
        self.count_label.setText(f"{len(rows)} product(s)")
        self.table.resizeColumnsToContents()
        stats = self.ctx.inventory.stock_alerts()
        self.summary_cards["value"].set_value(
            format_minor(self.ctx.inventory.stock_value(), self.ctx.settings.currency))
        self.summary_cards["low"].set_value(str(stats["low"]))
        self.summary_cards["out"].set_value(str(stats["out"]))

    def adjust_stock(self) -> None:
        if not self.ctx.can("inventory.adjust"):
            widgets.notify(self, "You do not have permission to adjust stock.", "error")
            return
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select a product to adjust.", "warning")
            return
        dialog = AdjustDialog(self.ctx, self.ctx.catalog.get(record["id"]), self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, f"Stock updated for {record['name']}", "success")

    def export_csv(self) -> None:
        path = widgets.file_save_dialog(self, "Export inventory",
                                        "CSV files (*.csv)", "inventory.csv")
        if not path:
            return
        try:
            self.ctx.csv.export_inventory(path)
        except Exception as exc:  # pragma: no cover
            widgets.error_box(self, exc, "Export failed")
            return
        widgets.notify(self, f"Exported to {path}", "success")


def create(ctx, parent=None) -> InventoryPage:
    return InventoryPage(ctx, parent)
