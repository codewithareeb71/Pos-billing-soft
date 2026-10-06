"""Settings: shop identity, receipt, POS behaviour, hardware, database, audit."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from ... import config
from ...core.db import rows as db_rows
from ...core.exceptions import AppError
from ...core.money import format_minor
from .. import icons, theme, widgets

CURRENCIES = ("PKR", "USD", "GBP", "EUR", "AED", "SAR", "INR", "BDT", "CNY",
              "JPY", "TRY", "ZAR", "NGN", "KES", "AFN")

# key -> (label, values)
BOOL_SETTINGS = {
    "receipt.show_logo": "Print the shop logo",
    "receipt.show_barcode": "Print the invoice barcode",
    "receipt.show_address": "Print the shop address",
    "receipt.show_phone": "Print the phone number",
    "receipt.show_cashier": "Print the cashier name",
    "receipt.show_customer": "Print the customer name",
    "receipt.show_sku": "Print the SKU on receipts",
    "pos.auto_focus_barcode": "Focus the barcode field automatically",
    "pos.allow_negative_stock": "Allow selling below zero stock",
    "pos.require_customer": "Require a customer before payment",
    "pos.beep_on_scan": "Beep when a barcode is scanned",
    "pos.show_product_images": "Show product images in the cart",
    "inventory.low_stock_alert": "Show low stock alerts on the dashboard",
}


class ScannerTestPanel(QWidget):
    """Live USB HID scanner test: buffers keystrokes until Enter."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._buffer = ""
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(150)
        self.setProperty("card", True)
        self.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = widgets.section_title("Barcode scanner test")
        self.status = QLabel("READY - waiting for a scan")
        self.status.setStyleSheet(f"color:{theme.SUCCESS}; font-weight:800;")
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.status)
        layout.addLayout(head)

        layout.addWidget(widgets.hint(
            "Click inside this panel, then scan a barcode. The scanner works as a "
            "keyboard, so every scan must appear below within about a second."))

        self.code_label = QLabel("Last barcode:  -")
        self.code_label.setStyleSheet("font-size:14pt; font-weight:800;")
        self.time_label = QLabel("Time:  -")
        self.result_label = QLabel("Product:  -")
        self.result_label.setWordWrap(True)
        for label in (self.code_label, self.time_label, self.result_label):
            layout.addWidget(label)

        footer = QHBoxLayout()
        clear = QPushButton("Clear")
        clear.setIcon(icons.icon("refresh", "primary", 15))
        clear.clicked.connect(self._clear)
        focus = QPushButton("Focus this panel")
        focus.clicked.connect(self.setFocus)
        footer.addWidget(clear)
        footer.addWidget(focus)
        footer.addStretch(1)
        layout.addLayout(footer)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._submit(self._buffer)
                self._buffer = ""
                return True
            if key == Qt.Key_Backspace:
                self._buffer = self._buffer[:-1]
                return True
            text = event.text()
            if text and text.isprintable():
                self._buffer += text
                self.status.setText(f"Receiving... {self._buffer}")
                self.status.setStyleSheet(
                    f"color:{theme.WARNING}; font-weight:800;")
                return True
        return super().eventFilter(watched, event)

    def _submit(self, code: str) -> None:
        code = code.strip()
        self.status.setText("READY - waiting for a scan")
        self.status.setStyleSheet(f"color:{theme.SUCCESS}; font-weight:800;")
        if not code:
            return
        self.code_label.setText(f"Last barcode:  {code}")
        self.time_label.setText(f"Time:  {datetime.now().strftime('%H:%M:%S')}")
        product = (self.ctx.catalog.find_by_barcode(code)
                   or self.ctx.catalog.find_by_sku(code))
        if product:
            self.result_label.setText(
                f"Product:  {product['name']}  •  stock "
                f"{float(product.get('stock', 0)):g}  •  "
                f"{format_minor(product['selling_price'], self.ctx.settings.currency)}")
            self.result_label.setStyleSheet(f"color:{theme.SUCCESS};")
        else:
            self.result_label.setText(
                "Product:  not found (the scanner read it correctly, the barcode "
                "just is not in the catalogue yet)")
            self.result_label.setStyleSheet(f"color:{theme.WARNING};")

    def _clear(self) -> None:
        self._buffer = ""
        self.code_label.setText("Last barcode:  -")
        self.time_label.setText("Time:  -")
        self.result_label.setText("Product:  -")
        self.result_label.setStyleSheet("")


class SettingsPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.can_edit = ctx.can("settings.edit")
        self._logo_path = ctx.settings.get("shop.logo") or ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = widgets.PageHeader(
            "Settings",
            "Everything a shop owner needs to configure - no code, no database tools")
        if self.can_edit:
            change = QPushButton("Change my password")
            change.setIcon(icons.icon("key", "primary", 16))
            change.clicked.connect(self.change_password)
            header.add_action(change)
        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._shop_tab(), "Shop")
        self.tabs.addTab(self._receipt_tab(), "Receipt")
        self.tabs.addTab(self._pos_tab(), "POS")
        self.tabs.addTab(self._hardware_tab(), "Hardware")
        self.tabs.addTab(self._database_tab(), "Database")
        self.tabs.addTab(self._audit_tab(), "Audit log")
        self.tabs.addTab(self._about_tab(), "About")
        self.tabs.currentChanged.connect(lambda *_: self._on_tab_changed())
        root.addWidget(self.tabs, 1)

        if not self.can_edit:
            # configuration tabs become read-only; viewers keep the hardware test,
            # the backup tools and the audit log usable within their own rights
            for index in (0, 1, 2):
                page = self.tabs.widget(index)
                for widget in page.findChildren(
                        (QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox,
                         QCheckBox)):
                    if isinstance(widget, widgets.SearchBox):
                        continue
                    widget.setEnabled(False)
            notice = widgets.hint(
                "You are signed in with view-only access to the settings. "
                "Ask an administrator to change them.")
            notice.setStyleSheet(f"color:{theme.WARNING}; font-weight:600;")
            root.insertWidget(1, notice)

    # ------------------------------------------------------------------ shop
    def _section(self, title: str) -> tuple[QWidget, QFormLayout]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(10)
        outer.addWidget(widgets.section_title(title))
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)
        outer.addLayout(form, 1)
        page._form = form      # type: ignore[attr-defined]
        page._outer = outer    # type: ignore[attr-defined]
        return page, form

    def _add_save(self, page: QWidget, handler) -> QPushButton:
        row = QHBoxLayout()
        row.addStretch(1)
        save = QPushButton("Save changes")
        save.setProperty("variant", "primary")
        save.setIcon(icons.icon("save", "primary", 16))
        save.setEnabled(self.can_edit)
        save.clicked.connect(handler)
        row.addWidget(save)
        page._outer.addLayout(row)   # type: ignore[attr-defined]
        return save

    def _shop_tab(self) -> QWidget:
        page, form = self._section("Shop identity - shown on receipts and reports")
        settings = self.ctx.settings
        self.shop_name = QLineEdit(settings.get("shop.name"))
        self.shop_address = QPlainTextEdit(settings.get("shop.address"))
        self.shop_address.setFixedHeight(70)
        self.shop_phone = QLineEdit(settings.get("shop.phone"))
        self.shop_email = QLineEdit(settings.get("shop.email"))
        self.currency_combo = QComboBox()
        self.currency_combo.setEditable(True)
        self.currency_combo.addItems(list(CURRENCIES))
        self.currency_combo.setCurrentText(settings.get("currency", "PKR"))
        self.invoice_prefix = QLineEdit(settings.get("invoice.prefix", "ALS"))
        self.invoice_padding = QDoubleSpinBox()
        self.invoice_padding.setRange(3, 12)
        self.invoice_padding.setDecimals(0)
        self.invoice_padding.setValue(settings.get_int("invoice.padding", 6))
        self.return_prefix = QLineEdit(settings.get("return.prefix", "RET"))
        self.purchase_prefix = QLineEdit(settings.get("purchase.prefix", "PUR"))

        logo_row = QHBoxLayout()
        self.logo_preview = QLabel()
        self.logo_preview.setFixedSize(64, 64)
        self.logo_preview.setStyleSheet(
            f"background:{theme.BG}; border:1px solid {theme.BORDER}; "
            "border-radius:8px;")
        self.logo_preview.setAlignment(Qt.AlignCenter)
        logo_path_label = QLineEdit(self._logo_path or "(no logo selected)")
        logo_path_label.setReadOnly(True)
        choose = QPushButton("Choose logo...")
        choose.setIcon(icons.icon("photo", "primary", 15))
        choose.clicked.connect(lambda: self._choose_logo(logo_path_label))
        clear = QPushButton("Clear")
        clear.setProperty("variant", "flat")
        clear.clicked.connect(lambda: self._clear_logo(logo_path_label))
        logo_row.addWidget(self.logo_preview)
        logo_row.addWidget(logo_path_label, 1)
        choose.setEnabled(self.can_edit)
        clear.setEnabled(self.can_edit)
        logo_row.addWidget(choose)
        logo_row.addWidget(clear)

        form.addRow("Shop name *", self.shop_name)
        form.addRow("Address", self.shop_address)
        form.addRow("Phone", self.shop_phone)
        form.addRow("Email", self.shop_email)
        form.addRow("Currency", self.currency_combo)
        form.addRow("Invoice prefix", self.invoice_prefix)
        form.addRow("Invoice digits", self.invoice_padding)
        form.addRow("Return prefix", self.return_prefix)
        form.addRow("Purchase prefix", self.purchase_prefix)
        form.addRow("Logo", logo_row)
        self._refresh_logo(self.logo_preview)
        self._add_save(page, self._save_shop)
        return page

    def _choose_logo(self, path_label: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the shop logo", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        try:
            shutil.copy2(path, config.SHOP_LOGO_PATH)
        except OSError as exc:
            widgets.error_box(self, exc, "Logo could not be copied")
            return
        self._logo_path = str(config.SHOP_LOGO_PATH)
        path_label.setText(self._logo_path)
        self._refresh_logo(self.logo_preview)

    def _clear_logo(self, path_label: QLineEdit) -> None:
        self._logo_path = ""
        path_label.setText("(no logo selected)")
        self.logo_preview.clear()

    def _refresh_logo(self, target: QLabel) -> None:
        source = self._logo_path or str(config.SHOP_LOGO_PATH)
        if Path(source).exists():
            pixmap = QPixmap(source)
            if not pixmap.isNull():
                target.setPixmap(pixmap.scaled(
                    target.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        target.setText("LOGO")

    def _save_shop(self) -> None:
        if not self.shop_name.text().strip():
            widgets.notify(self, "Shop name is required.", "error")
            return
        values = {
            "shop.name": self.shop_name.text().strip(),
            "shop.address": self.shop_address.toPlainText().strip(),
            "shop.phone": self.shop_phone.text().strip(),
            "shop.email": self.shop_email.text().strip(),
            "shop.logo": self._logo_path,
            "currency": self.currency_combo.currentText().strip().upper() or "PKR",
            "invoice.prefix": self.invoice_prefix.text().strip().upper() or "ALS",
            "invoice.padding": str(int(self.invoice_padding.value())),
            "return.prefix": self.return_prefix.text().strip().upper() or "RET",
            "purchase.prefix": self.purchase_prefix.text().strip().upper() or "PUR",
        }
        try:
            self.ctx.settings.set_many(values, session=self.ctx.session)
        except AppError as exc:
            widgets.error_box(self, exc)
            return
        widgets.notify(self, "Shop settings saved", "success")

    # -------------------------------------------------------------- receipt
    def _receipt_tab(self) -> QWidget:
        page, form = self._section("Receipt printing - 58 mm and 80 mm thermal paper")
        settings = self.ctx.settings
        printer_row = QHBoxLayout()
        self.printer_combo = QComboBox()
        self.printer_combo.addItem("(Windows default printer)", "")
        try:
            for printer in self.ctx.receipts.available_printers():
                self.printer_combo.addItem(printer, printer)
        except Exception:  # pragma: no cover - printer spooler quirks
            pass
        saved_printer = settings.get("receipt.printer", "")
        index = self.printer_combo.findData(saved_printer)
        if index >= 0:
            self.printer_combo.setCurrentIndex(index)
        refresh = QPushButton("Refresh")
        refresh.setIcon(icons.icon("refresh", "primary", 15))
        refresh.clicked.connect(self._refresh_printers)
        test = QPushButton("Print test receipt")
        test.setIcon(icons.icon("print", "primary", 15))
        test.clicked.connect(self._test_receipt)
        preview = QPushButton("Preview")
        preview.clicked.connect(self._preview_receipt)
        for widget in (refresh, test, preview):
            printer_row.addWidget(widget)
        printer_row.addStretch(1)

        self.width_combo = QComboBox()
        for width in config.SUPPORTED_RECEIPT_WIDTHS_MM:
            self.width_combo.addItem(f"{width} mm", width)
        self.width_combo.setCurrentIndex(max(
            0, config.SUPPORTED_RECEIPT_WIDTHS_MM.index(
                settings.get_int("receipt.width_mm", 80))
            if settings.get_int("receipt.width_mm", 80)
            in config.SUPPORTED_RECEIPT_WIDTHS_MM else 1))
        self.header_edit = QLineEdit(settings.get("receipt.header"))
        self.header_edit.setPlaceholderText("Optional extra line at the top")
        self.footer_edit = QPlainTextEdit(settings.get("receipt.footer"))
        self.footer_edit.setFixedHeight(64)

        self.check_boxes: dict[str, QCheckBox] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for index, (key, label) in enumerate(BOOL_SETTINGS.items()):
            if not key.startswith("receipt."):
                continue
            box = QCheckBox(label)
            box.setChecked(settings.get_bool(key, True))
            self.check_boxes[key] = box
            grid.addWidget(box, index // 2, index % 2)

        form.addRow("Printer", printer_row)
        form.addRow("Paper width", self.width_combo)
        form.addRow("Extra header line", self.header_edit)
        form.addRow("Footer", self.footer_edit)
        form.addRow("Include", grid)
        self._add_save(page, self._save_receipt)
        return page

    def _refresh_printers(self) -> None:
        current = self.printer_combo.currentData()
        self.printer_combo.clear()
        self.printer_combo.addItem("(Windows default printer)", "")
        try:
            for printer in self.ctx.receipts.available_printers():
                self.printer_combo.addItem(printer, printer)
        except Exception as exc:  # pragma: no cover
            widgets.notify(self, f"Could not read printers: {exc}", "warning")
            return
        index = self.printer_combo.findData(current)
        if index >= 0:
            self.printer_combo.setCurrentIndex(index)
        widgets.notify(self, "Printer list refreshed", "success")

    def _save_receipt(self) -> None:
        values = {
            "receipt.printer": self.printer_combo.currentData() or "",
            "receipt.width_mm": str(self.width_combo.currentData() or 80),
            "receipt.header": self.header_edit.text().strip(),
            "receipt.footer": self.footer_edit.toPlainText().strip(),
        }
        for key, box in self.check_boxes.items():
            values[key] = "1" if box.isChecked() else "0"
        try:
            self.ctx.settings.set_many(values, session=self.ctx.session)
        except AppError as exc:
            widgets.error_box(self, exc)
            return
        widgets.notify(self, "Receipt settings saved", "success")

    def _test_receipt(self) -> None:
        try:
            html_text = self.ctx.receipts.test_receipt_html()
            self.ctx.receipts.print_html(
                html_text, width_mm=self.width_combo.currentData() or 80,
                printer_name=self.printer_combo.currentData() or "")
        except Exception as exc:  # pragma: no cover
            from ...core.logging_setup import get_logger, log_exception
            log_exception(get_logger("settings"), "Test print failed", exc)
            widgets.notify(self,
                           "Test print failed. Check that the printer is switched "
                           "on, connected and selected above.", "error")
            return
        widgets.notify(self, "Test receipt sent to the printer", "success")

    def _preview_receipt(self) -> None:
        try:
            html_text = self.ctx.receipts.test_receipt_html()
            self.ctx.receipts.preview(self, html_text,
                                      width_mm=self.width_combo.currentData() or 80,
                                      title="Receipt preview")
        except Exception as exc:  # pragma: no cover
            widgets.error_box(self, exc, "Preview failed")

    # ------------------------------------------------------------------ POS
    def _pos_tab(self) -> QWidget:
        page, form = self._section("POS screen behaviour")
        settings = self.ctx.settings
        self.pay_method_combo = QComboBox()
        self.pay_method_combo.addItems(list(config.PAYMENT_METHODS))
        self.pay_method_combo.setCurrentText(
            settings.get("pos.default_payment_method", "Cash"))
        self.discount_pct = QDoubleSpinBox()
        self.discount_pct.setRange(0, 100)
        self.discount_pct.setDecimals(0)
        self.discount_pct.setSuffix(" %")
        self.discount_pct.setValue(settings.get_int("pos.discount_threshold_percent", 10))
        self.discount_amount = QDoubleSpinBox()
        self.discount_amount.setRange(0, 100_000_000)
        self.discount_amount.setDecimals(0)
        self.discount_amount.setValue(
            settings.get_int("pos.discount_threshold_amount", 1000))

        self.pos_check_boxes: dict[str, QCheckBox] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        row = 0
        for key, label in BOOL_SETTINGS.items():
            if key.startswith("receipt."):
                continue
            box = QCheckBox(label)
            box.setChecked(settings.get_bool(key, key in
                                             ("pos.auto_focus_barcode",
                                              "pos.beep_on_scan",
                                              "pos.show_product_images")))
            self.pos_check_boxes[key] = box
            grid.addWidget(box, row // 2, row % 2)
            row += 1

        form.addRow("Default payment method", self.pay_method_combo)
        form.addRow("Discount approval above", self.discount_pct)
        form.addRow("Discount approval above (amount)", self.discount_amount)
        form.addRow("Behaviour", grid)
        form.addRow("", widgets.hint(
            "High value discounts above these limits need a supervisor password "
            "at the till."))
        self._add_save(page, self._save_pos)
        return page

    def _save_pos(self) -> None:
        values = {
            "pos.default_payment_method": self.pay_method_combo.currentText(),
            "pos.discount_threshold_percent": str(int(self.discount_pct.value())),
            "pos.discount_threshold_amount": str(int(self.discount_amount.value())),
        }
        for key, box in self.pos_check_boxes.items():
            values[key] = "1" if box.isChecked() else "0"
        try:
            self.ctx.settings.set_many(values, session=self.ctx.session)
        except AppError as exc:
            widgets.error_box(self, exc)
            return
        widgets.notify(self, "POS settings saved", "success")

    # ------------------------------------------------------------- hardware
    def _hardware_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(12)
        outer.addWidget(widgets.section_title(
            "Hardware - barcode scanner and receipt printer"))
        outer.addWidget(widgets.hint(
            "USB barcode scanners (HID type) need no driver: they type the barcode "
            "and press Enter. If nothing appears below, try another USB port or "
            "check that the scanner is configured to append Enter (CR suffix)."))
        self.scanner_panel = ScannerTestPanel(self.ctx)
        outer.addWidget(self.scanner_panel)

        printer_card = widgets.card()
        printer_layout = QFormLayout()
        printer_card.layout().addLayout(printer_layout)
        self.printer_info = QLabel()
        self.printer_info.setWordWrap(True)
        printer_layout.addRow("Receipt printer", self.printer_info)
        buttons = QHBoxLayout()
        test = QPushButton("Print test receipt")
        test.setIcon(icons.icon("print", "primary", 15))
        test.clicked.connect(self._test_receipt)
        preview = QPushButton("Preview receipt")
        preview.clicked.connect(self._preview_receipt)
        open_backups = QPushButton("Open backup folder")
        open_backups.setIcon(icons.icon("folder", "primary", 15))
        open_backups.clicked.connect(self._open_backup_folder)
        buttons.addWidget(test)
        buttons.addWidget(preview)
        buttons.addWidget(open_backups)
        buttons.addStretch(1)
        printer_layout.addRow("", buttons)
        outer.addWidget(printer_card)
        outer.addStretch(1)
        self._update_printer_info()
        return page

    def _update_printer_info(self) -> None:
        printer = self.ctx.settings.get("receipt.printer", "") or \
            "(Windows default printer)"
        width = self.ctx.settings.get_int("receipt.width_mm", 80)
        self.printer_info.setText(f"{printer}  •  {width} mm paper")

    # ------------------------------------------------------------- database
    def _database_tab(self) -> QWidget:
        page, form = self._section("Database, backups and restore")
        settings = self.ctx.settings

        self.db_info = QLabel()
        self.db_info.setWordWrap(True)
        self.db_info.setObjectName("MutedLabel")

        self.backup_mode = QComboBox()
        self.backup_mode.addItems(["manual", "daily", "weekly"])
        self.backup_mode.setCurrentText(settings.get("backup.mode", "manual"))
        self.backup_retention = QDoubleSpinBox()
        self.backup_retention.setRange(1, 365)
        self.backup_retention.setDecimals(0)
        self.backup_retention.setValue(settings.get_int("backup.retention", 7))

        backup_buttons = QHBoxLayout()
        backup_now = QPushButton("Back up now")
        backup_now.setIcon(icons.icon("save", "primary", 15))
        backup_now.clicked.connect(self._backup_now)
        backup_elsewhere = QPushButton("Back up to a folder...")
        backup_elsewhere.setIcon(icons.icon("folder", "primary", 15))
        backup_elsewhere.clicked.connect(self._backup_to_folder)
        integrity = QPushButton("Check database")
        integrity.setIcon(icons.icon("shield", "primary", 15))
        integrity.clicked.connect(self._integrity_check)
        can_backup = self.ctx.can("database.backup")
        for button in (backup_now, backup_elsewhere, integrity):
            button.setEnabled(can_backup)
            backup_buttons.addWidget(button)
        backup_buttons.addStretch(1)

        restore_row = QHBoxLayout()
        restore_button = QPushButton("Restore from a backup file...")
        restore_button.setIcon(icons.icon("import", "primary", 15))
        restore_button.clicked.connect(self._restore_backup)
        restore_button.setEnabled(ctx_can(self.ctx, "database.restore"))
        restore_row.addWidget(restore_button)
        restore_row.addStretch(1)

        form.addRow("Database", self.db_info)
        form.addRow("Automatic backups", self.backup_mode)
        form.addRow("Keep auto backups", self.backup_retention)
        form.addRow("Maintenance", backup_buttons)
        form.addRow("Restore", restore_row)
        form.addRow("", widgets.hint(
            "Restoring always writes a safety backup first and validates the file "
            "before it replaces your data."))

        form.addRow(widgets.section_title("Backup history"))
        columns = [
            widgets.Column("filename", "File", 260),
            widgets.Column("created_at", "Created", 160),
            widgets.Column("kind", "Type", 110, "center"),
            widgets.Column("created_by", "By", 120),
            widgets.Column("size_mb", "Size (MB)", 100, "right"),
            widgets.Column("status", "Status", 90, "center"),
        ]
        self.backups_table, self.backups_model = widgets.make_table(columns, [])
        form.addRow(self.backups_table)
        self._add_save(page, self._save_backup_settings)
        self._refresh_database_tab()
        return page

    def _refresh_database_tab(self) -> None:
        info = self.ctx.backups.database_info()
        counts = info["counts"]
        self.db_info.setText(
            f"{info['path']}  •  {info['size_mb']} MB  •  "
            f"schema v{info['schema_version']}\n"
            f"Products {counts['products']}  •  Sales {counts['sales']}  •  "
            f"Customers {counts['customers']}  •  Suppliers {counts['suppliers']}  •  "
            f"Purchases {counts['purchases']}  •  Users {counts['users']}  •  "
            f"Audit entries {counts['audit_entries']}\n"
            f"Backups: mode {info['mode']}  •  keep {info['retention']}  •  "
            f"last run {info['last_run']}")
        records = self.ctx.backups.list_backups()
        for record in records:
            record["status"] = "ok" if record["exists"] else "missing"
        self.backups_model.set_rows(records)
        self.backups_table.resizeColumnsToContents()

    def _save_backup_settings(self) -> None:
        try:
            self.ctx.settings.set_many({
                "backup.mode": self.backup_mode.currentText(),
                "backup.retention": str(int(self.backup_retention.value())),
            }, session=self.ctx.session)
        except AppError as exc:
            widgets.error_box(self, exc)
            return
        widgets.notify(self, "Backup settings saved", "success")

    def _backup_now(self) -> None:
        try:
            path = self.ctx.backups.create_backup(
                kind="manual", user=self.ctx.username, note="Manual backup")
        except AppError as exc:
            widgets.error_box(self, exc, "Backup failed")
            return
        self._refresh_database_tab()
        widgets.notify(self, f"Backup created: {path.name}", "success")

    def _backup_to_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a backup folder")
        if not folder:
            return
        try:
            path = self.ctx.backups.create_backup(
                folder, kind="manual", user=self.ctx.username,
                note="Manual backup to a custom folder")
        except AppError as exc:
            widgets.error_box(self, exc, "Backup failed")
            return
        self._refresh_database_tab()
        widgets.notify(self, f"Backup written to {path}", "success")

    def _integrity_check(self) -> None:
        try:
            ok = self.ctx.db.integrity_check()
        except Exception as exc:  # pragma: no cover
            widgets.error_box(self, exc, "Check failed")
            return
        if ok:
            widgets.info_box(self, "The database passed the integrity check.",
                             "Database healthy")
        else:
            widgets.info_box(self,
                             "The database reported problems. Restore the most "
                             "recent backup from the backup history below.",
                             "Database problem")

    def _restore_backup(self) -> None:
        record = widgets.selected_row(self.backups_table)
        path = ""
        if record and record.get("exists"):
            path = record["path"]
        else:
            path = widgets.file_open_dialog(
                self, "Choose a backup file",
                "Alshan POS backups (*.db);;All files (*.*)") or ""
        if not path:
            return
        try:
            info = self.ctx.backups.validate_backup(path)
        except AppError as exc:
            widgets.error_box(self, exc, "Invalid backup")
            return
        counts = info["counts"]
        if not widgets.confirm(
                self,
                f"Restore this backup?\n\nFile: {Path(path).name}\n"
                f"Shop: {info.get('shop_name') or '-'}\n"
                f"Products: {counts['products']}  •  Sales: {counts['sales']}  •  "
                f"Customers: {counts['customers']}\n\n"
                "Your current data will be replaced. A safety backup is created "
                "automatically first.", "Confirm restore"):
            return
        try:
            result = self.ctx.backups.restore(path, session=self.ctx.session)
        except AppError as exc:
            widgets.error_box(self, exc, "Restore failed")
            return
        self._refresh_database_tab()
        widgets.info_box(
            self,
            f"Database restored from {Path(result['restored']).name}.\n"
            f"Safety backup: {Path(result['safety_backup']).name}\n\n"
            "Screens will reload to pick up the restored data.",
            "Restore complete")
        window = self.window()
        if hasattr(window, "refresh_current"):
            window.refresh_current()

    def _open_backup_folder(self) -> None:
        import os
        config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(config.BACKUP_DIR))  # noqa: S606 - Windows shell
        except OSError:
            widgets.info_box(self, str(config.BACKUP_DIR), "Backup folder")

    # ---------------------------------------------------------------- audit
    def _audit_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(10)
        outer.addWidget(widgets.section_title(
            "Audit log - who did what, when (never editable, never deletable)"))
        controls = QHBoxLayout()
        self.audit_search = widgets.SearchBox("Search action, user or description")
        self.audit_search.changed.connect(lambda _t: self._refresh_audit())
        controls.addWidget(self.audit_search, 1)
        refresh = QPushButton("Refresh")
        refresh.setIcon(icons.icon("refresh", "primary", 15))
        refresh.clicked.connect(self._refresh_audit)
        controls.addWidget(refresh)
        outer.addLayout(controls)
        columns = [
            widgets.Column("created_at", "When", 160),
            widgets.Column("username", "User", 120),
            widgets.Column("action", "Action", 130),
            widgets.Column("entity", "Entity", 110),
            widgets.Column("entity_id", "ID", 70, "center"),
            widgets.Column("description", "Details", 320),
        ]
        self.audit_table, self.audit_model = widgets.make_table(columns, [])
        outer.addWidget(self.audit_table, 1)
        self.audit_status = widgets.hint("")
        outer.addWidget(self.audit_status)
        return page

    def _refresh_audit(self) -> None:
        term = self.audit_search.text().strip()
        sql = ("SELECT created_at, username, action, entity, entity_id, "
               "description, details FROM audit_logs")
        params: tuple = ()
        if term:
            sql += (" WHERE action LIKE ? OR username LIKE ? OR entity LIKE ? "
                    "OR description LIKE ?")
            params = (f"%{term}%",) * 4
        sql += " ORDER BY id DESC LIMIT 1000"
        try:
            with self.ctx.db.read() as conn:
                records = db_rows(conn, sql, params)
        except Exception as exc:  # pragma: no cover
            widgets.error_box(self, exc, "Could not read the audit log")
            return
        for record in records:
            if record.get("details") and not record.get("description"):
                record["description"] = record["details"]
            elif record.get("details"):
                record["description"] = f"{record['description']} ({record['details']})"
        self.audit_model.set_rows(records)
        self.audit_status.setText(f"{len(records)} entry(ies)")
        self.audit_table.resizeColumnsToContents()

    # ---------------------------------------------------------------- about
    def _about_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(10)
        outer.addWidget(widgets.section_title("About"))

        logo = QLabel()
        logo.setPixmap(theme.logo_icon(96).pixmap(96, 96))
        logo.setAlignment(Qt.AlignCenter)
        outer.addWidget(logo)

        title = QLabel(config.APP_NAME)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:18pt; font-weight:800;")
        outer.addWidget(title)
        version = QLabel(f"Version {config.APP_VERSION}  •  {config.APP_VENDOR}")
        version.setAlignment(Qt.AlignCenter)
        version.setObjectName("MutedLabel")
        outer.addWidget(version)

        import PySide6
        details = QLabel(
            f"Python {config.__dict__.get('__version__', '')}"
            f"{'.'.join(str(p) for p in __import__('sys').version_info[:3])}  •  "
            f"PySide6 {PySide6.__version__}  •  SQLite\n"
            f"Database: {config.DB_PATH}\n"
            f"Backups: {config.BACKUP_DIR}\n"
            f"Logs: {config.LOG_DIR}\n\n"
            f"{config.APP_COPYRIGHT}")
        details.setAlignment(Qt.AlignCenter)
        details.setObjectName("MutedLabel")
        details.setWordWrap(True)
        outer.addWidget(details)

        outer.addWidget(widgets.section_title("Keyboard shortcuts"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        for index, (key, description) in enumerate(config.SHORTCUTS.items()):
            key_label = QLabel(key)
            key_label.setStyleSheet(
                f"font-weight:800; color:{theme.PRIMARY}; background:{theme.BG};"
                f" border:1px solid {theme.BORDER}; border-radius:4px;"
                " padding:2px 8px;")
            key_label.setAlignment(Qt.AlignCenter)
            grid.addWidget(key_label, index // 4, (index % 4) * 2)
            grid.addWidget(QLabel(description), index // 4, (index % 4) * 2 + 1)
        outer.addLayout(grid)
        outer.addStretch(1)
        return page

    # --------------------------------------------------------------- actions
    def on_show(self) -> None:
        if self.tabs.currentWidget() is not None:
            self._on_tab_changed()

    def _on_tab_changed(self) -> None:
        label = self.tabs.tabText(self.tabs.currentIndex())
        if label == "Database":
            self._refresh_database_tab()
        elif label == "Audit log":
            self._refresh_audit()
        elif label == "Hardware":
            self._update_printer_info()
            QTimer.singleShot(0, self.scanner_panel.setFocus)

    def change_password(self) -> None:
        dialog = widgets.FormDialog(self, "Change my password", "Update password")
        current = QLineEdit()
        current.setEchoMode(QLineEdit.Password)
        new = QLineEdit()
        new.setEchoMode(QLineEdit.Password)
        confirm = QLineEdit()
        confirm.setEchoMode(QLineEdit.Password)
        dialog.add_field("Current password", current)
        dialog.add_field("New password", new)
        dialog.add_field("Confirm new password", confirm)

        def check() -> str:
            if len(new.text()) < config.MIN_PASSWORD_LENGTH:
                return (f"Password must be at least {config.MIN_PASSWORD_LENGTH} "
                        "characters long.")
            if new.text() != confirm.text():
                return "The passwords do not match."
            return ""

        def accept() -> None:
            error = check()
            if error:
                dialog.set_error(error)
                return
            try:
                self.ctx.auth.change_own_password(current.text(), new.text())
            except AppError as exc:
                dialog.set_error(exc.message)
                return
            dialog.accept()

        dialog.validate = check            # type: ignore[method-assign]
        dialog.accept = accept             # type: ignore[method-assign]
        if dialog.exec() == QDialog.Accepted:
            widgets.notify(self, "Password updated", "success")


def ctx_can(ctx, permission: str) -> bool:
    return bool(ctx and ctx.can(permission))


def create(ctx, parent=None) -> SettingsPage:
    return SettingsPage(ctx, parent)
