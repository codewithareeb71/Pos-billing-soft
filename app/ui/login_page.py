"""Professional login screen."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

from .. import config
from ..core.exceptions import AppError
from . import icons, theme, widgets


class LoginDialog(QDialog):
    def __init__(self, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"{config.APP_NAME} - Sign in")
        self.setWindowIcon(theme.logo_icon(32))
        self.setFixedWidth(430)
        self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background:{theme.CARD}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ------------------------------------------------------------ header
        header = QWidget()
        header.setStyleSheet(f"background:{theme.PRIMARY};")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(30, 30, 30, 26)
        header_layout.setSpacing(6)
        logo_row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(theme.logo_icon(56).pixmap(56, 56))
        logo_row.addWidget(logo)
        logo_row.addStretch(1)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        brand = QLabel(config.APP_NAME)
        brand.setStyleSheet("color:#FFFFFF; font-size:19pt; font-weight:700;")
        tagline = QLabel("Offline Retail POS  |  Billing  |  Inventory")
        tagline.setStyleSheet("color:#9FC2DC; font-size:9pt; letter-spacing:1px;")
        title_box.addWidget(brand)
        title_box.addWidget(tagline)
        logo_row.addLayout(title_box, 1)
        logo_row.setAlignment(Qt.AlignVCenter)
        header_layout.addLayout(logo_row)
        root.addWidget(header)

        # -------------------------------------------------------------- body
        body = QWidget()
        body.setStyleSheet(f"background:{theme.CARD};")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(34, 26, 34, 26)
        layout.setSpacing(12)

        shop = ctx.settings.shop_name
        if shop and shop != config.APP_NAME:
            shop_label = QLabel(shop)
            shop_label.setStyleSheet(f"color:{theme.MUTED}; font-size:9pt;")
            layout.addWidget(shop_label)

        heading = QLabel("Sign in to continue")
        heading.setStyleSheet("font-size:13pt; font-weight:700;")
        layout.addWidget(heading)

        self.username = QLineEdit()
        self.username.setPlaceholderText("Username")
        self.username.setClearButtonEnabled(True)
        layout.addWidget(self.username)

        password_row = QWidget()
        password_layout = QHBoxLayout(password_row)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(6)
        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.Password)
        self.show_password = QPushButton()
        self.show_password.setProperty("variant", "flat")
        self.show_password.setIcon(icons.icon("user", "muted", 16))
        self.show_password.setFixedWidth(40)
        self.show_password.setToolTip("Show / hide password")
        self.show_password.setCheckable(True)
        self.show_password.toggled.connect(self._toggle_password)
        password_layout.addWidget(self.password, 1)
        password_layout.addWidget(self.show_password)
        layout.addWidget(password_row)

        options = QHBoxLayout()
        self.remember = QCheckBox("Keep me signed in on this computer")
        self.remember.setChecked(True)
        options.addWidget(self.remember)
        options.addStretch(1)
        layout.addLayout(options)

        self.error = QLabel()
        self.error.setObjectName("ErrorLabel")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)

        self.login_button = QPushButton("Sign in")
        self.login_button.setProperty("variant", "primary")
        self.login_button.setStyleSheet(
            "QPushButton { font-size:12pt; font-weight:700; padding:12px; "
            "border-radius:8px; }")
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.clicked.connect(self.attempt_login)
        layout.addWidget(self.login_button)

        footer = QLabel(f"{config.APP_VERSION}  •  Local database  •  Works offline")
        footer.setObjectName("HintLabel")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)
        root.addWidget(body, 1)

        self.password.returnPressed.connect(self.attempt_login)
        self.username.returnPressed.connect(self.password.setFocus)
        self.setTabOrder(self.username, self.password)

    # -----------------------------------------------------------------
    def _toggle_password(self, checked: bool) -> None:
        self.password.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self.password.setFocus()

    def show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
        self.password.selectAll()
        self.password.setFocus()

    def attempt_login(self) -> None:
        self.error.hide()
        username = self.username.text().strip()
        password = self.password.text()
        if not username or not password:
            self.show_error("Enter your username and password.")
            return
        self.login_button.setEnabled(False)
        self.login_button.setText("Signing in...")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            session = self.ctx.login(username, password)
        except AppError as exc:
            self.show_error(exc.message)
            self._reset_button()
            return
        except Exception as exc:  # pragma: no cover - defensive
            from ..core.logging_setup import get_logger, log_exception
            log_exception(get_logger("login"), "Login failure", exc)
            self.show_error("Unable to sign in right now. Please try again.")
            self._reset_button()
            return
        self._session = session
        self.accept()

    def _reset_button(self) -> None:
        self.login_button.setEnabled(True)
        self.login_button.setText("Sign in")
