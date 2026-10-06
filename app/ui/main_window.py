"""Main application window: sidebar navigation, top bar, page stack."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QPushButton, QScrollArea,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import config
from . import icons, theme, widgets

# (key, label, icon, permission)
NAVIGATION = [
    ("dashboard", "Dashboard", "home", "dashboard.view"),
    ("pos", "POS Billing", "pos", "sales.create"),
    ("products", "Products", "tag", "products.view"),
    ("inventory", "Inventory", "inventory", "inventory.view"),
    ("purchases", "Purchases", "truck", "purchases.view"),
    ("customers", "Customers", "user", "customers.view"),
    ("suppliers", "Suppliers", "users", "suppliers.view"),
    ("sales", "Sales History", "receipt", "sales.view"),
    ("returns", "Returns", "return", "sales.view"),
    ("expenses", "Expenses", "money", "expenses.view"),
    ("reports", "Reports", "chart", "reports.view"),
    ("users", "Users & Roles", "users", "users.view"),
    ("settings", "Settings", "settings", "settings.view"),
]


class MainWindow(QMainWindow):
    """Shell that hosts every module of ALSHAN POS SYSTEM."""

    def __init__(self, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.pages: dict[str, QWidget] = {}
        self._current_key = ""
        self.setWindowTitle(f"{config.APP_NAME}")
        self.setWindowIcon(theme.logo_icon(48))
        self.resize(1366, 768)
        self.setMinimumSize(1100, 660)

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self.setCentralWidget(central)

        # ---------------------------------------------------------- sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 12, 0, 14)
        sidebar_layout.setSpacing(2)

        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(16, 4, 12, 10)
        brand_layout.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(theme.logo_icon(38).pixmap(38, 38))
        brand_layout.addWidget(logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_title = QLabel("ALSHAN")
        brand_title.setObjectName("BrandTitle")
        brand_title.setStyleSheet("font-size:16pt; color:#FFFFFF; font-weight:800;")
        brand_sub = QLabel("POS SYSTEM")
        brand_sub.setObjectName("BrandSub")
        brand_text.addWidget(brand_title)
        brand_text.addWidget(brand_sub)
        brand_layout.addLayout(brand_text, 1)
        sidebar_layout.addWidget(brand)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}

        from ..core.schema import CASHIER_PERMISSIONS  # noqa: F401  (documentation)
        for key, label, glyph_name, permission in NAVIGATION:
            if permission and not ctx.can(permission):
                continue
            button = QPushButton("  " + label.replace("&", "&&"))
            button.setProperty("nav", True)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setIcon(icons.icon(glyph_name, "muted", 17))
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(lambda _c, k=key: self.show_page(k))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            sidebar_layout.addWidget(button)

        sidebar_layout.addStretch(1)

        # quick action buttons at the bottom of the sidebar
        if ctx.can("sales.create"):
            new_sale = QPushButton("  New sale  (F1)")
            new_sale.setProperty("sidebarBtn", True)
            new_sale.setIcon(icons.icon("plus", "muted", 16))
            new_sale.clicked.connect(lambda: self.show_page("pos"))
            sidebar_layout.addWidget(new_sale)

        user_block = QFrame()
        user_block.setStyleSheet("background:transparent;")
        user_layout = QVBoxLayout(user_block)
        user_layout.setContentsMargins(16, 8, 16, 0)
        user_layout.setSpacing(1)
        session = ctx.session
        user_name = QLabel(session.full_name if session else "")
        user_name.setObjectName("UserBadge")
        user_name.setWordWrap(True)
        user_role = QLabel(f"{session.role_name}  •  {session.username}" if session else "")
        user_role.setObjectName("UserRole")
        logout = QPushButton("  Sign out")
        logout.setProperty("sidebarBtn", True)
        logout.setIcon(icons.icon("logout", "muted", 16))
        logout.clicked.connect(self.request_logout)
        user_layout.addWidget(user_name)
        user_layout.addWidget(user_role)
        user_layout.addWidget(logout)
        sidebar_layout.addWidget(user_block)
        central_layout.addWidget(self.sidebar)

        # ------------------------------------------------------- main column
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(64)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(22, 8, 18, 8)
        top_layout.setSpacing(14)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        self.page_title = QLabel("")
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel("")
        self.page_subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(self.page_title)
        title_box.addWidget(self.page_subtitle)
        top_layout.addLayout(title_box, 1)

        self.clock = QLabel(datetime.now().strftime("%A, %d %B %Y  %H:%M"))
        self.clock.setStyleSheet(f"color:{theme.MUTED}; font-size:9.5pt;")
        top_layout.addWidget(self.clock)

        self.session_chip = QLabel(f"  {ctx.session.role_name}  ")
        self.session_chip.setObjectName("SessionChip")
        top_layout.addWidget(self.session_chip)

        self.settings_button = QPushButton()
        self.settings_button.setProperty("variant", "flat")
        self.settings_button.setIcon(icons.icon("settings", "muted", 18))
        self.settings_button.setFixedSize(36, 36)
        self.settings_button.setToolTip("Settings")
        if ctx.can("settings.view"):
            self.settings_button.clicked.connect(lambda: self.show_page("settings"))
            top_layout.addWidget(self.settings_button)
        self.logout_button = QPushButton()
        self.logout_button.setProperty("variant", "flat")
        self.logout_button.setIcon(icons.icon("logout", "muted", 18))
        self.logout_button.setFixedSize(36, 36)
        self.logout_button.setToolTip("Sign out")
        self.logout_button.clicked.connect(self.request_logout)
        top_layout.addWidget(self.logout_button)
        column_layout.addWidget(top_bar)

        # ---------------------------------------------------------- content
        content = QFrame()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 14, 18, 12)
        content_layout.setSpacing(0)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)
        column_layout.addWidget(content, 1)
        central_layout.addWidget(column, 1)

        # ------------------------------------------------------------- toast
        self.toast = widgets.Toast(self)

        # --------------------------------------------------------- statusbar
        self.statusBar().showMessage(
            f"{config.APP_NAME} {config.APP_VERSION}  |  Database: {config.DB_PATH}")
        self.statusBar().setFixedHeight(26)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(
            lambda: self.clock.setText(datetime.now().strftime("%A, %d %B %Y  %H:%M")))
        self._clock_timer.start(30_000)

        self.logout_requested = False
        self._install_shortcuts()
        first = next(iter(self.nav_buttons), None)
        if first:
            self.show_page(first)
        else:  # pragma: no cover - role with no navigation
            self.show_page("dashboard")

    # ------------------------------------------------------------- helpers
    def _install_shortcuts(self) -> None:
        actions = [
            (QKeySequence("F1"), self._shortcut_new_sale),
            (QKeySequence("Escape"), self._shortcut_escape),
        ]
        for sequence, handler in actions:
            from PySide6.QtGui import QShortcut
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(handler)

    def _shortcut_new_sale(self) -> None:
        if "pos" in self.nav_buttons:
            self.show_page("pos")

    def _shortcut_escape(self) -> None:
        page = self.stack.currentWidget()
        handler = getattr(page, "handle_escape", None)
        if callable(handler):
            handler()

    def current_page(self) -> QWidget | None:
        return self.stack.currentWidget()

    def show_page(self, key: str) -> None:
        if key not in self.nav_buttons and key not in self.pages:
            return
        page = self.pages.get(key)
        if page is None:
            page = self._build_page(key)
            if page is None:
                return
            self.pages[key] = page
            self.stack.addWidget(page)
        index = self.stack.indexOf(page)
        if index >= 0:
            self.stack.setCurrentWidget(page)
        button = self.nav_buttons.get(key)
        if button:
            button.setChecked(True)
        meta = next((n for n in NAVIGATION if n[0] == key), None)
        if meta:
            self.page_title.setText(meta[1])
        self._current_key = key
        on_show = getattr(page, "on_show", None)
        if callable(on_show):
            on_show()

    def _build_page(self, key: str) -> QWidget | None:
        from .pages import build_page
        try:
            return build_page(key, self.ctx, self)
        except Exception as exc:  # pragma: no cover - defensive
            from ..core.logging_setup import get_logger, log_exception
            log_exception(get_logger("ui"), f"Failed to build page {key}", exc)
            return widgets.empty_state(f"This module could not be opened ({key}).")

    # ----------------------------------------------------------- behaviours
    def show_toast(self, message: str, kind: str = "info",
                   duration: int = 3000) -> None:
        self.toast.show_message(message, kind, duration)

    def refresh_current(self) -> None:
        page = self.stack.currentWidget()
        on_show = getattr(page, "on_show", None)
        if callable(on_show):
            on_show()

    def refresh_page(self, key: str) -> None:
        page = self.pages.get(key)
        on_show = getattr(page, "on_show", None) if page else None
        if callable(on_show):
            on_show()

    def request_logout(self) -> None:
        if widgets.confirm(self, "Sign out of ALSHAN POS SYSTEM?", "Sign out",
                           "Any unsaved screen content will be discarded."):
            self.logout_requested = True
            self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.logout_requested and not getattr(self, "_force_close", False):
            if not widgets.confirm(self, "Exit ALSHAN POS SYSTEM?", "Exit",
                                   "Make sure your data is saved before closing."):
                event.ignore()
                return
        event.accept()

