"""Products module: catalogue management, barcode generation and CSV tools."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from ... import config
from ...core.exceptions import AppError
from ...core.money import format_minor, from_minor, parse_input
from .. import icons, theme, widgets


# ===========================================================================
# Product editor
# ===========================================================================
class ProductDialog(widgets.FormDialog):
    def __init__(self, ctx, parent=None, product: dict | None = None):
        super().__init__(parent, "Edit product" if product else "New product",
                         "Save product")
        self.ctx = ctx
        self.product = product
        self.product_id: int | None = product["id"] if product else None
        self.image_path = product.get("image_path", "") if product else ""
        self.setMinimumSize(640, 640)

        self.name = QLineEdit(product["name"] if product else "")
        self.name.setPlaceholderText("Product name *")
        self.sku = QLineEdit(product.get("sku") or "" if product else "")
        self.sku.setPlaceholderText("SKU (optional)")

        barcode_row = QHBoxLayout()
        self.barcode = QLineEdit(product.get("barcode") or "" if product else "")
        self.barcode.setPlaceholderText("Barcode (EAN-13, UPC, Code 128...)")
        generate_barcode = QPushButton("Generate")
        generate_barcode.setIcon(icons.icon("barcode", "primary", 15))
        generate_barcode.setToolTip("Assign an in-house barcode when the product "
                                    "has none")
        generate_barcode.clicked.connect(self._generate_barcode)
        barcode_row.addWidget(self.barcode, 1)
        barcode_row.addWidget(generate_barcode)
        barcode_widget = QWidget()
        barcode_widget.setLayout(barcode_row)

        self.category = self._combo(ctx.catalog.categories(), product and
                                    product.get("category_id"), "New category...")
        self.brand = self._combo(ctx.catalog.brands(), product and
                                 product.get("brand_id"), "New brand...")
        self.unit = self._combo(ctx.catalog.units(), product and
                                product.get("unit_id"), None, label_key="name")
        self.supplier = self._combo(ctx.suppliers.search(limit=1000),
                                    product and product.get("supplier_id"),
                                    None)

        self.purchase_price = QLineEdit(
            f"{from_minor(product['purchase_price']):.2f}" if product else "")
        self.purchase_price.setPlaceholderText("0.00")
        self.selling_price = QLineEdit(
            f"{from_minor(product['selling_price']):.2f}" if product else "")
        self.selling_price.setPlaceholderText("0.00")

        discount_row = QHBoxLayout()
        self.discount_type = QComboBox()
        self.discount_type.addItems(["None", "Percentage", "Fixed"])
        self.discount_type.setCurrentText(
            product.get("discount_type", "None") if product else "None")
        self.discount_value = QLineEdit(
            str(product.get("discount_value", 0)) if product else "0")
        self.discount_value.setPlaceholderText("0")
        discount_row.addWidget(self.discount_type, 1)
        discount_row.addWidget(self.discount_value, 1)
        discount_widget = QWidget()
        discount_widget.setLayout(discount_row)

        stock_row = QHBoxLayout()
        self.min_stock = QDoubleSpinBox()
        self.min_stock.setRange(0, 1_000_000)
        self.min_stock.setDecimals(3)
        self.min_stock.setValue(float(product.get("min_stock", 0)) if product else 0)
        self.max_stock = QDoubleSpinBox()
        self.max_stock.setRange(0, 1_000_000)
        self.max_stock.setDecimals(3)
        self.max_stock.setValue(float(product.get("max_stock", 0)) if product else 0)
        stock_row.addWidget(QLabel("Min"))
        stock_row.addWidget(self.min_stock, 1)
        stock_row.addWidget(QLabel("Max"))
        stock_row.addWidget(self.max_stock, 1)
        stock_widget = QWidget()
        stock_widget.setLayout(stock_row)

        self.opening_stock = QDoubleSpinBox()
        self.opening_stock.setRange(0, 1_000_000)
        self.opening_stock.setDecimals(3)
        self.opening_stock.setKeyboardTracking(False)
        if product is None:
            self.add_field("Opening stock", self.opening_stock)

        self.allow_decimal = QCheckBox("Allow decimal quantities (weight/volume)")
        self.allow_decimal.setChecked(bool(product.get("allow_decimal")) if product else False)
        self.active = QCheckBox("Product is active (available at the POS)")
        self.active.setChecked(bool(product.get("is_active", 1)) if product else True)

        image_row = QHBoxLayout()
        self.image_path_edit = QLineEdit(self.image_path)
        self.image_path_edit.setReadOnly(True)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_image)
        clear_image = QPushButton("Clear")
        clear_image.setProperty("variant", "flat")
        clear_image.clicked.connect(lambda: (self.image_path_edit.clear(),
                                             setattr(self, "image_path", "")))
        image_row.addWidget(self.image_path_edit, 1)
        image_row.addWidget(browse)
        image_row.addWidget(clear_image)
        image_widget = QWidget()
        image_widget.setLayout(image_row)

        self.description = QPlainTextEdit(product.get("description", "") if product else "")
        self.description.setFixedHeight(70)

        self.add_field("Name *", self.name)
        self.add_field("SKU", self.sku)
        self.add_field("Barcode", barcode_widget)
        self.add_field("Category", self.category)
        self.add_field("Brand", self.brand)
        self.add_field("Unit", self.unit)
        self.add_field("Supplier", self.supplier)
        self.add_field("Purchase price", self.purchase_price)
        self.add_field("Selling price *", self.selling_price)
        self.add_field("Discount", discount_widget)
        self.add_field("Stock levels", stock_widget)
        self.add_field("Image", image_widget)
        self.form.addRow("", self.allow_decimal)
        self.form.addRow("", self.active)
        self.add_field("Description", self.description)

    # ------------------------------------------------------------------
    @staticmethod
    def _combo(records: list[dict], current_id, add_label: str | None = None,
               label_key: str = "name") -> QComboBox:
        combo = QComboBox()
        combo.addItem("(none)", None)
        for record in records:
            combo.addItem(record.get(label_key, ""), record["id"])
        if add_label:
            combo.addItem(add_label, "__add__")
        if current_id:
            index = combo.findData(current_id)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.currentIndexChanged.connect(lambda _i, c=combo, l=add_label:
                                          _maybe_add(c, l))
        return combo

    def _generate_barcode(self) -> None:
        if self.product_id:
            try:
                code = self.ctx.catalog.generate_barcode(self.product_id)
                self.barcode.setText(code)
                widgets.notify(self, f"Barcode {code} assigned", "success")
            except AppError as exc:
                widgets.error_box(self, exc)
        else:
            self.barcode.setPlaceholderText(
                "Barcode is generated automatically after saving")

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select product image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.image_path = path
            self.image_path_edit.setText(path)

    def validate(self) -> str:
        if not self.name.text().strip():
            return "Product name is required."
        if not self.selling_price.text().strip():
            return "Selling price is required."
        try:
            parse_input(self.purchase_price.text(), "Purchase price")
            parse_input(self.selling_price.text(), "Selling price")
            parse_input(self.discount_value.text() or "0", "Discount")
        except AppError as exc:
            return exc.message
        return ""

    def _resolve_reference(self, data, kind: str):
        """Turn a '+ New' combo choice into a real category / brand id."""
        if isinstance(data, str) and data.startswith("__new__"):
            name = data[len("__new__"):]
            try:
                if kind == "category":
                    return self.ctx.catalog.save_category(name)
                if kind == "brand":
                    return self.ctx.catalog.save_brand(name)
            except AppError:
                return None
        return data or None

    def values(self) -> dict:
        image_path = self.image_path
        if image_path and image_path != (self.product or {}).get("image_path"):
            if Path(image_path).exists() and str(config.PRODUCT_IMAGE_DIR) not in image_path:
                try:
                    image_path = self.ctx.catalog.store_image(image_path)
                except AppError:
                    image_path = ""
        return {
            "name": self.name.text().strip(),
            "sku": self.sku.text().strip(),
            "barcode": self.barcode.text().strip(),
            "category_id": self._resolve_reference(self.category.currentData(),
                                                   "category"),
            "brand_id": self._resolve_reference(self.brand.currentData(), "brand"),
            "unit_id": self.unit.currentData() or None,
            "supplier_id": self.supplier.currentData() or None,
            "purchase_price": self.purchase_price.text() or "0",
            "selling_price": self.selling_price.text() or "0",
            "discount_type": self.discount_type.currentText(),
            "discount_value": self.discount_value.text() or "0",
            "min_stock": self.min_stock.value(),
            "max_stock": self.max_stock.value(),
            "opening_stock": self.opening_stock.value(),
            "allow_decimal": self.allow_decimal.isChecked(),
            "is_active": 1 if self.active.isChecked() else 0,
            "description": self.description.toPlainText().strip(),
            "image_path": image_path,
        }

    def accept(self) -> None:
        payload = self.values() if not self.validate() else None
        if payload is None:
            self.set_error(self.validate())
            return
        payload["is_active"] = 1 if self.active.isChecked() else 0
        try:
            if self.product_id:
                self.ctx.catalog.update(self.product_id, payload)
                if bool(self.product.get("is_active", 1)) != bool(payload["is_active"]):
                    self.ctx.catalog.set_active(self.product_id,
                                                bool(payload["is_active"]))
            else:
                self.product_id = self.ctx.catalog.create(payload)
        except AppError as exc:
            self.set_error(exc.message)
            return
        except Exception as exc:  # pragma: no cover
            widgets.error_box(self, exc)
            return
        super().accept()


def _maybe_add(combo: QComboBox, add_label: str | None) -> None:
    """Offer 'add new' entries inside the reference combos."""
    if not add_label or combo.currentData() != "__add__":
        return
    from PySide6.QtWidgets import QInputDialog
    text, ok = QInputDialog.getText(combo, "New entry", "Name:")
    combo.blockSignals(True)
    if ok and text.strip():
        combo.insertItem(1, f"+  {text.strip()}", f"__new__{text.strip()}")
        combo.setCurrentIndex(1)
    else:
        combo.setCurrentIndex(0)
    combo.blockSignals(False)


# ===========================================================================
# Barcode label printing
# ===========================================================================
class BarcodeLabelsDialog(QDialog):
    def __init__(self, ctx, products: list[dict], parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Print barcode labels")
        self.setModal(True)
        self.setMinimumWidth(520)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(10)
        root.addWidget(widgets.hint(
            f"{len(products)} product(s) selected. Existing barcodes are never "
            "overwritten - generate them first if a product has none."))
        self.show_name = QCheckBox("Print the product name")
        self.show_name.setChecked(True)
        self.show_price = QCheckBox("Print the selling price")
        self.show_price.setChecked(True)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(30, 100)
        self.width_spin.setValue(50)
        self.width_spin.setSuffix(" mm")
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(15, 60)
        self.height_spin.setValue(30)
        self.height_spin.setSuffix(" mm")
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Label size"))
        size_row.addWidget(self.width_spin)
        size_row.addWidget(self.height_spin)
        size_row.addStretch(1)
        root.addWidget(self.show_name)
        root.addWidget(self.show_price)
        root.addLayout(size_row)
        self.status = QLabel("")
        self.status.setObjectName("MutedLabel")
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        preview = QPushButton("Print preview")
        preview.clicked.connect(lambda: self._run(preview_mode=True))
        do_print = QPushButton("Print labels")
        do_print.setProperty("variant", "primary")
        do_print.clicked.connect(lambda: self._run(preview_mode=False))
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(preview)
        buttons.addWidget(do_print)
        buttons.addStretch(1)
        buttons.addWidget(close)
        root.addLayout(buttons)
        self._products = products

    def _run(self, preview_mode: bool) -> None:
        try:
            html_text = self.ctx.receipts.labels_html(
                self._products,
                show_price=self.show_price.isChecked(),
                show_name=self.show_name.isChecked(),
                label_w_mm=int(self.width_spin.value()),
                label_h_mm=int(self.height_spin.value()),
            )
            if preview_mode:
                self.ctx.receipts.preview(self, html_text, width_mm=100,
                                          title="Barcode labels")
            else:
                self.ctx.receipts.print_html(
                    html_text, width_mm=100,
                    printer_name=self.ctx.settings.get("receipt.printer", ""))
            self.status.setText("Labels sent to the printer." if not preview_mode else "")
        except Exception as exc:  # pragma: no cover
            from ...core.logging_setup import get_logger, log_exception
            log_exception(get_logger("products"), "Label printing failed", exc)
            self.status.setText("Printing failed - check the printer settings.")


# ===========================================================================
# CSV import
# ===========================================================================
class ImportDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Import products from CSV")
        self.setModal(True)
        self.setMinimumSize(760, 520)
        self.preview: dict | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.addWidget(widgets.muted(
            "Required columns: Product Name, Selling Price. Optional: SKU, Barcode, "
            "Category, Brand, Unit, Purchase Price, Stock, Minimum Stock, Supplier, "
            "Description."))
        head.addStretch(1)
        choose = QPushButton("Choose CSV file...")
        choose.setIcon(icons.icon("folder", "primary", 16))
        choose.clicked.connect(self._choose)
        head.addWidget(choose)
        root.addLayout(head)

        columns = [
            widgets.Column("row", "Row", 50, "center"),
            widgets.Column("name", "Product", 200),
            widgets.Column("barcode", "Barcode", 120),
            widgets.Column("selling_price", "Price", 90, "right"),
            widgets.Column("stock", "Stock", 70, "right"),
            widgets.Column("result", "Validation", 240),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        root.addWidget(self.table, 1)
        self.summary = widgets.hint("No file selected.")
        root.addWidget(self.summary)

        buttons = QHBoxLayout()
        self.commit_button = QPushButton("Import valid rows")
        self.commit_button.setProperty("variant", "primary")
        self.commit_button.setEnabled(False)
        self.commit_button.clicked.connect(self._commit)
        close = QPushButton("Cancel")
        close.clicked.connect(self.reject)
        buttons.addWidget(self.commit_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        root.addLayout(buttons)

    def _choose(self) -> None:
        path = widgets.file_open_dialog(self, "Select a product CSV",
                                        "CSV files (*.csv);;All files (*.*)")
        if not path:
            return
        try:
            self.preview = self.ctx.csv.preview_import(path)
        except AppError as exc:
            widgets.error_box(self, exc, "Import failed")
            return
        rows = []
        for entry in self.preview["valid"]:
            rows.append({**entry, "result": "Ready to import"})
        for entry in self.preview["errors"]:
            rows.append({**entry, "result": "; ".join(entry["problems"])})
        rows.sort(key=lambda r: r["row"])
        self.model.set_rows(rows)
        ok = len(self.preview["valid"])
        bad = len(self.preview["errors"])
        self.summary.setText(
            f"{self.preview['total']} row(s) read  •  {ok} ready  •  {bad} with problems")
        self.commit_button.setEnabled(ok > 0)
        self.commit_button.setText(f"Import {ok} valid row(s)")

    def _commit(self) -> None:
        if not self.preview:
            return
        try:
            result = self.ctx.csv.commit_import(self.preview)
        except AppError as exc:
            widgets.error_box(self, exc, "Import failed")
            return
        widgets.info_box(self,
                         f"Import finished.\n\nCreated: {result['created']}\n"
                         f"Updated: {result['updated']}", "Import complete")
        self.accept()


# ===========================================================================
# Page
# ===========================================================================
class ProductsPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = widgets.PageHeader("Products",
                                    "Manage your catalogue, prices and barcodes")
        if ctx.can("products.create"):
            add = QPushButton("New product")
            add.setProperty("variant", "primary")
            add.setIcon(icons.icon("add", "primary", 16))
            add.clicked.connect(self.add_product)
            header.add_action(add)
        if ctx.can("products.barcode"):
            labels = QPushButton("Print barcodes")
            labels.setIcon(icons.icon("barcode", "primary", 16))
            labels.clicked.connect(self.print_labels)
            header.add_action(labels)
        if ctx.can("products.import"):
            import_button = QPushButton("Import CSV")
            import_button.setIcon(icons.icon("import", "primary", 16))
            import_button.clicked.connect(self.import_csv)
            header.add_action(import_button)
        if ctx.can("products.export"):
            export = QPushButton("Export CSV")
            export.setIcon(icons.icon("export", "primary", 16))
            export.clicked.connect(self.export_csv)
            header.add_action(export)
        root.addWidget(header)

        filters = QWidget()
        filter_layout = QHBoxLayout(filters)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)
        self.search = widgets.SearchBox("Search name, SKU, barcode, category, brand")
        self.search.changed.connect(lambda _t: self.refresh())
        filter_layout.addWidget(self.search, 2)
        self.category_filter = QComboBox()
        self.category_filter.currentIndexChanged.connect(lambda *_: self.refresh())
        filter_layout.addWidget(self.category_filter)
        self.brand_filter = QComboBox()
        self.brand_filter.currentIndexChanged.connect(lambda *_: self.refresh())
        filter_layout.addWidget(self.brand_filter)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Active only", "Inactive only", "All products"])
        self.status_filter.currentIndexChanged.connect(lambda *_: self.refresh())
        filter_layout.addWidget(self.status_filter)
        root.addWidget(filters)

        columns = [
            widgets.Column("name", "Product", 220),
            widgets.Column("sku", "SKU", 110),
            widgets.Column("barcode", "Barcode", 130),
            widgets.Column("category", "Category", 120),
            widgets.Column("brand", "Brand", 110),
            widgets.Column("purchase_price", "Cost", 110, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("selling_price", "Price", 115, "right",
                           lambda v: format_minor(v, self.ctx.settings.currency)),
            widgets.Column("stock", "Stock", 75, "right"),
            widgets.Column("status_label", "Status", 95, "center"),
        ]
        self.table, self.model = widgets.make_table(columns, [])
        self.table.doubleClicked.connect(lambda *_: self.edit_product())
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.count_label = widgets.hint("")
        if ctx.can("products.edit"):
            edit = QPushButton("Edit")
            edit.setIcon(icons.icon("edit", "primary", 16))
            edit.clicked.connect(self.edit_product)
            footer.addWidget(edit)
        if ctx.can("products.deactivate"):
            self.toggle_button = QPushButton("Deactivate")
            self.toggle_button.clicked.connect(self.toggle_active)
            footer.addWidget(self.toggle_button)
        if ctx.can("products.barcode"):
            generate = QPushButton("Generate barcode")
            generate.setIcon(icons.icon("barcode", "primary", 16))
            generate.clicked.connect(self.generate_barcode)
            footer.addWidget(generate)
        footer.addStretch(1)
        footer.addWidget(self.count_label)
        root.addLayout(footer)

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self.refresh_filters()
        self.refresh()

    def refresh_filters(self) -> None:
        for combo, loader, label in (
                (self.category_filter, self.ctx.catalog.categories, "All categories"),
                (self.brand_filter, self.ctx.catalog.brands, "All brands")):
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
        active_only = self.status_filter.currentText() != "Inactive only"
        rows = self.ctx.catalog.search(
            self.search.text(), category_id=self.category_filter.currentData(),
            brand_id=self.brand_filter.currentData(), active_only=active_only,
            limit=5000)
        if self.status_filter.currentText() == "Active only":
            rows = [r for r in rows if r["is_active"]]
        for record in rows:
            record["status_label"] = "Active" if record["is_active"] else "Inactive"
            record["status"] = record["status_label"]
        self.model.set_rows(rows)
        self.count_label.setText(f"{len(rows)} product(s)")
        self.table.resizeColumnsToContents()

    def _selected(self) -> dict | None:
        record = widgets.selected_row(self.table)
        if not record:
            widgets.notify(self, "Select a product first.", "warning")
        return record

    # ------------------------------------------------------------- actions
    def add_product(self) -> None:
        dialog = ProductDialog(self.ctx, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "Product created", "success")

    def edit_product(self) -> None:
        record = self._selected()
        if not record:
            return
        dialog = ProductDialog(self.ctx, self, self.ctx.catalog.get(record["id"]))
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            widgets.notify(self, "Product updated", "success")

    def toggle_active(self) -> None:
        record = self._selected()
        if not record:
            return
        activate = not record["is_active"]
        verb = "reactivate" if activate else "deactivate"
        if not widgets.confirm(self, f"{verb.capitalize()} '{record['name']}'?",
                               "Please confirm"):
            return
        try:
            self.ctx.catalog.set_active(record["id"], activate)
        except AppError as exc:
            widgets.error_box(self, exc)
            return
        self.refresh()
        widgets.notify(self, f"Product {verb}d", "success")

    def generate_barcode(self) -> None:
        record = self._selected()
        if not record:
            return
        try:
            code = self.ctx.catalog.generate_barcode(record["id"])
        except AppError as exc:
            widgets.error_box(self, exc)
            return
        self.refresh()
        widgets.notify(self, f"Barcode assigned: {code}", "success")

    def print_labels(self) -> None:
        rows = [r for r in self.model.rows if r.get("is_active")]
        selected = widgets.selected_row(self.table)
        products = [self.ctx.catalog.get(selected["id"])] if selected else rows
        if not products:
            widgets.notify(self, "There are no products to print.", "warning")
            return
        products = products[:200]
        missing = [p for p in products if not p.get("barcode")]
        if missing and not widgets.confirm(
                self,
                f"{len(missing)} selected product(s) have no barcode yet. Continue? "
                "Their labels will print without a barcode image.",
                "Missing barcodes"):
            return
        BarcodeLabelsDialog(self.ctx, products, self).exec()

    def import_csv(self) -> None:
        ImportDialog(self.ctx, self).exec()
        self.refresh()

    def export_csv(self) -> None:
        path = widgets.file_save_dialog(
            self, "Export products", "CSV files (*.csv)", "products.csv")
        if not path:
            return
        try:
            self.ctx.csv.export_products(path)
        except Exception as exc:  # pragma: no cover
            widgets.error_box(self, exc, "Export failed")
            return
        widgets.notify(self, f"Exported to {path}", "success")


def create(ctx, parent=None) -> ProductsPage:
    return ProductsPage(ctx, parent)
