"""First-launch setup wizard: shop identity, receipt and administrator."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QWizard, QWizardPage, QVBoxLayout, QWidget)

from .. import config
from ..core.exceptions import AppError
from . import icons, theme, widgets


def _brand_header(title: str, subtitle: str) -> QWidget:
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)
    logo = QLabel()
    logo.setPixmap(theme.logo_icon(64).pixmap(64, 64))
    layout.addWidget(logo)
    text = QVBoxLayout()
    text.setSpacing(2)
    heading = QLabel(title)
    heading.setObjectName("PageTitle")
    heading.setStyleSheet(f"font-size:16pt; color:{theme.PRIMARY}; font-weight:700;")
    sub = QLabel(subtitle)
    sub.setObjectName("PageSubtitle")
    sub.setWordWrap(True)
    text.addWidget(heading)
    text.addWidget(sub)
    layout.addLayout(text, 1)
    layout.setAlignment(Qt.AlignVCenter)
    return box


class _BasePage(QWizardPage):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        self.setTitle(title)
        self.setSubTitle(subtitle)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(12)
        self.layout.setContentsMargins(20, 16, 20, 12)

    def add(self, widget: QWidget) -> QWidget:
        self.layout.addWidget(widget)
        return widget

    def field_row(self, label: str, widget: QWidget) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        caption = QLabel(label)
        caption.setFixedWidth(150)
        caption.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(caption)
        layout.addWidget(widget, 1)
        self.layout.addWidget(row)
        return widget


class WelcomePage(_BasePage):
    def __init__(self):
        super().__init__("Welcome", "A few quick steps and your shop is ready to trade.")
        self.add(_brand_header(config.APP_NAME,
                               "Professional Offline Retail POS, Billing & "
                               "Inventory Management"))
        body = QLabel(
            "This setup wizard creates your shop profile, receipt preferences and the "
            "first administrator account.\n\n"
            "•  All data is stored locally on this computer - no internet required\n"
            "•  Your database is created automatically\n"
            "•  You can change every setting later under Settings\n"
            "•  A backup is recommended after your first day of trading"
        )
        body.setWordWrap(True)
        body.setObjectName("MutedLabel")
        self.add(body)
        self.add(widgets.hint(
            f"Database location: {config.DB_PATH}"))
        self.layout.addStretch(1)


class ShopPage(_BasePage):
    def __init__(self, settings):
        super().__init__("Your shop", "Details printed on receipts and reports.")
        self.settings = settings
        self.add(_brand_header("Shop details", "These details appear on every receipt."))
        self.name = QLineEdit(settings.get("shop.name"))
        self.name.setPlaceholderText("e.g. Alshan General Store")
        self.address = QLineEdit(settings.get("shop.address"))
        self.address.setPlaceholderText("Street, area, city")
        self.phone = QLineEdit(settings.get("shop.phone"))
        self.phone.setPlaceholderText("0300-0000000")
        self.email = QLineEdit(settings.get("shop.email"))
        self.email.setPlaceholderText("shop@example.com")
        self.currency = QComboBox()
        self.currency.setEditable(True)
        for code in ("PKR", "USD", "EUR", "GBP", "AED", "SAR", "INR", "BDT", "AFN"):
            self.currency.addItem(code)
        self.currency.setCurrentText(settings.get("currency", "PKR"))
        self.field_row("Shop name *", self.name)
        self.field_row("Address", self.address)
        self.field_row("Phone", self.phone)
        self.field_row("Email", self.email)
        self.field_row("Currency", self.currency)
        self.layout.addStretch(1)

    def validatePage(self) -> bool:  # noqa: N802 - Qt hook
        return self.validate()

    def validate(self) -> bool:
        if not self.name.text().strip():
            self.name.setProperty("invalid", True)
            self.name.style().unpolish(self.name)
            self.name.style().polish(self.name)
            self.name.setFocus()
            return False
        return True


class ReceiptPage(_BasePage):
    def __init__(self, settings):
        super().__init__("Receipt printing",
                         "Thermal printer preferences - any Windows printer works.")
        self.settings = settings
        self.add(_brand_header("Receipt setup",
                               "Choose the width of your receipt paper and default printer."))
        self.width_box = QComboBox()
        for mm in config.SUPPORTED_RECEIPT_WIDTHS_MM:
            self.width_box.addItem(f"{mm} mm", mm)
        current = settings.get_int("receipt.width_mm", 80)
        index = self.width_box.findData(current)
        self.width_box.setCurrentIndex(index if index >= 0 else 1)

        from PySide6.QtPrintSupport import QPrinterInfo
        self.printer_box = QComboBox()
        printers = [p.printerName() for p in QPrinterInfo.availablePrinters()]
        self.printer_box.addItem("(Windows default printer)")
        self.printer_box.addItems(printers)
        saved = settings.get("receipt.printer", "")
        if saved in printers:
            self.printer_box.setCurrentText(saved)

        self.footer = QPlainTextEdit(settings.get("receipt.footer"))
        self.footer.setFixedHeight(70)
        self.footer.setPlaceholderText("Footer message, e.g. Thank you for shopping with us.")
        self.show_logo = QCheckBox("Print the shop logo on receipts")
        self.show_logo.setChecked(settings.get_bool("receipt.show_logo", True))
        self.show_barcode = QCheckBox("Print an invoice barcode on receipts")
        self.show_barcode.setChecked(settings.get_bool("receipt.show_barcode", True))

        self.field_row("Paper width", self.width_box)
        self.field_row("Receipt printer", self.printer_box)
        self.layout.addWidget(self.footer)
        self.layout.addWidget(self.show_logo)
        self.layout.addWidget(self.show_barcode)
        if not printers:
            self.layout.addWidget(widgets.hint(
                "No printers were detected. You can install or configure a printer "
                "later - Windows printer support is used."))
        self.layout.addStretch(1)

    def values(self) -> dict:
        return {
            "receipt.width_mm": self.width_box.currentData() or 80,
            "receipt.printer": ("" if self.printer_box.currentIndex() == 0
                                else self.printer_box.currentText()),
            "receipt.footer": self.footer.toPlainText().strip(),
            "receipt.show_logo": "1" if self.show_logo.isChecked() else "0",
            "receipt.show_barcode": "1" if self.show_barcode.isChecked() else "0",
        }


class AdminPage(_BasePage):
    def __init__(self):
        super().__init__("Administrator account",
                         "This account has full access to ALSHAN POS SYSTEM.")
        self.add(_brand_header("Create the administrator",
                               "You can add cashiers and more roles after setup."))
        self.full_name = QLineEdit()
        self.full_name.setPlaceholderText("Optional")
        self.username = QLineEdit()
        self.username.setPlaceholderText("At least 3 characters")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText(f"At least {config.MIN_PASSWORD_LENGTH} characters")
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.Password)
        self.field_row("Full name", self.full_name)
        self.field_row("Username *", self.username)
        self.field_row("Password *", self.password)
        self.field_row("Confirm password *", self.confirm)
        self.error = QLabel()
        self.error.setObjectName("ErrorLabel")
        self.error.setWordWrap(True)
        self.layout.addWidget(self.error)
        self.layout.addStretch(1)

    def validatePage(self) -> bool:  # noqa: N802 - Qt hook
        return self.validate()

    def validate(self) -> bool:
        def fail(message: str) -> bool:
            self.error.setText(message)
            return False

        if len(self.username.text().strip()) < 3:
            return fail("Username must be at least 3 characters long.")
        if len(self.password.text()) < config.MIN_PASSWORD_LENGTH:
            return fail(f"Password must be at least {config.MIN_PASSWORD_LENGTH} "
                        "characters long.")
        if self.password.text() != self.confirm.text():
            return fail("The passwords do not match.")
        self.error.setText("")
        return True


class SetupWizard(QWizard):
    """Collects shop details and creates the first administrator account."""

    def __init__(self, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"{config.APP_NAME} - First time setup")
        self.setWindowIcon(theme.logo_icon(32))
        self.setFixedSize(720, 540)
        self.setWizardStyle(QWizard.ClassicStyle)
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
        self.setButtonText(QWizard.NextButton, "Next")
        self.setButtonText(QWizard.BackButton, "Back")
        self.setButtonText(QWizard.FinishButton, "Finish setup")
        self.setButtonText(QWizard.CancelButton, "Cancel")

        self.shop_page = ShopPage(ctx.settings)
        self.receipt_page = ReceiptPage(ctx.settings)
        self.admin_page = AdminPage()
        self.addPage(WelcomePage())
        self.addPage(self.shop_page)
        self.addPage(self.receipt_page)
        self.has_existing_user = ctx.auth.has_user()
        if not self.has_existing_user:
            self.addPage(self.admin_page)

    def accept(self) -> None:
        try:
            settings_values = {
                "shop.name": self.shop_page.name.text().strip(),
                "shop.address": self.shop_page.address.text().strip(),
                "shop.phone": self.shop_page.phone.text().strip(),
                "shop.email": self.shop_page.email.text().strip(),
                "currency": self.shop_page.currency.currentText().strip() or "PKR",
                **self.receipt_page.values(),
                "setup_completed": "1",
            }
            self.ctx.settings.set_many(settings_values, session=None)
            if not self.has_existing_user:
                username = self.admin_page.username.text().strip()
                password = self.admin_page.password.text()
                role = next((r for r in self.ctx.auth.list_roles()
                             if r["name"].lower() == "administrator"), None)
                self.ctx.auth.create_user(
                    username, password,
                    self.admin_page.full_name.text().strip() or "Administrator",
                    role["id"] if role else 1,
                )
            from ..core import audit
            audit.log_always(self.ctx.db, None, audit.SETTINGS, entity="setup",
                             description="First-time setup completed",
                             details=f"shop={settings_values['shop.name']}")
        except AppError as exc:
            widgets.error_box(self, exc, "Setup could not be completed")
            return
        except Exception as exc:  # pragma: no cover
            widgets.error_box(self, exc)
            return
        super().accept()


def run_setup(ctx, parent=None) -> bool:
    from PySide6.QtWidgets import QDialog

    wizard = SetupWizard(ctx, parent)
    return wizard.exec() == QDialog.DialogCode.Accepted
