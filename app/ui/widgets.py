"""Reusable widgets: tables, cards, dialogs, search boxes, toasts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from PySide6.QtCore import (QAbstractTableModel, QEvent, QModelIndex, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QSizePolicy, QSpacerItem, QTableView,
                               QVBoxLayout, QWidget)

from . import icons, theme


# ===========================================================================
# Notifications
# ===========================================================================
class Toast(QLabel):
    """Lightweight non-modal notification pinned to the top of a window."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, message: str, kind: str = "info", duration: int = 3000) -> None:
        palette = {
            "info": (theme.INFO, "#FFFFFF"),
            "success": (theme.SUCCESS, "#FFFFFF"),
            "error": (theme.DANGER, "#FFFFFF"),
            "warning": (theme.WARNING, "#FFFFFF"),
        }
        background, foreground = palette.get(kind, palette["info"])
        self.setText(message)
        self.setStyleSheet(
            f"background:{background}; color:{foreground}; padding:10px 16px;"
            f"border-radius:6px; font-weight:600; font-size:10pt;"
        )
        width = min(self.parent().width() - 60, 720)
        self.setFixedWidth(max(280, width))
        self.adjustSize()
        self.setFixedHeight(max(38, self.height()))
        self.move(int((self.parent().width() - self.width()) / 2), 14)
        self.raise_()
        self.show()
        self._timer.start(duration)


def notify(parent, message: str, kind: str = "info") -> None:
    """Show a toast when the parent window supports it, else a message box."""
    window = parent
    while window is not None and not hasattr(window, "show_toast"):
        window = window.parentWidget() if hasattr(window, "parentWidget") else None
    if window is not None:
        window.show_toast(message, kind)
    else:
        QMessageBox.information(parent, theme.APP_NAME, message)


# ===========================================================================
# Message boxes
# ===========================================================================
def error_box(parent, exc: BaseException, title: str = "Operation failed") -> None:
    """Show a safe error message. Stack traces never reach the user."""
    from ..core.exceptions import AppError

    if isinstance(exc, AppError):
        message = exc.message
        detail = exc.detail
        title = "Attention"
    else:  # pragma: no cover - defensive
        from ..core.logging_setup import log_exception, get_logger
        log_exception(get_logger("ui"), "Unhandled error", exc)
        message = ("Something went wrong while completing this action. "
                   "Please try again.")
        detail = ""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    if detail:
        box.setDetailedText(detail)
    box.setStandardButtons(QMessageBox.Ok)
    box.exec()


def info_box(parent, message: str, title: str = theme.APP_NAME) -> None:
    QMessageBox.information(parent, title, message)


def confirm(parent, message: str, title: str = "Please confirm",
            detail: str = "") -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(title)
    box.setText(message)
    if detail:
        box.setInformativeText(detail)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes


def ask_text(parent, title: str, label: str, default: str = "") -> str | None:
    from PySide6.QtWidgets import QInputDialog

    text, ok = QInputDialog.getText(parent, title, label, QLineEdit.Normal, default)
    return text if ok else None


# ===========================================================================
# Layout helpers
# ===========================================================================
def card(widget: QWidget | None = None, hover: bool = False) -> QFrame | QWidget:
    frame = QFrame()
    frame.setProperty("card", True)
    if hover:
        frame.setProperty("hover", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    if widget is not None:
        layout.addWidget(widget)
    return frame


def hbox(*widgets, spacing: int = 8, stretch_last: bool = False) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for item in widgets:
        if item is None:
            layout.addStretch(1)
        elif isinstance(item, int):
            layout.addStretch(item)
        else:
            layout.addWidget(item)
    if stretch_last:
        layout.addStretch(1)
    return container


def vbox(*widgets, spacing: int = 8) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for item in widgets:
        if item is None:
            layout.addStretch(1)
        elif isinstance(item, int):
            layout.addStretch(item)
        else:
            layout.addWidget(item)
    return container


class PageHeader(QWidget):
    """Title + subtitle + trailing actions."""

    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(10)
        text = QVBoxLayout()
        text.setSpacing(0)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        text.addWidget(heading)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        if subtitle:
            text.addWidget(self.subtitle)
        layout.addLayout(text)
        layout.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)

    def add_action(self, button: QPushButton) -> QPushButton:
        self.actions.addWidget(button)
        return button

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))


class StatCard(QFrame):
    """Dashboard KPI card."""

    def __init__(self, label: str, value: str = "0", glyph_name: str = "chart",
                 accent: str = "primary"):
        super().__init__()
        self.setProperty("card", True)
        self.setProperty("hover", True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        badge = QLabel()
        badge.setPixmap(icons.pixmap(glyph_name, 26, accent))
        badge.setFixedSize(44, 44)
        badge.setStyleSheet(
            f"background:{theme.qcolor(accent).lighter(160).name()};"
            f"border-radius:8px; padding:8px;"
        )
        badge.setAlignment(Qt.AlignCenter)
        layout.addWidget(badge)
        column = QVBoxLayout()
        column.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        column.addWidget(self.value_label)
        self.name_label = QLabel(label)
        self.name_label.setObjectName("StatLabel")
        column.addWidget(self.name_label)
        layout.addLayout(column, 1)
        layout.setAlignment(badge, Qt.AlignVCenter)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("MutedLabel")
    label.setWordWrap(True)
    return label


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("HintLabel")
    label.setWordWrap(True)
    return label


def empty_state(text: str, glyph_name: str = "list") -> QWidget:
    box = QVBoxLayout()
    box.setSpacing(8)
    box.setAlignment(Qt.AlignCenter)
    icon_label = QLabel()
    icon_label.setPixmap(icons.pixmap(glyph_name, 40, "muted"))
    icon_label.setAlignment(Qt.AlignCenter)
    message = QLabel(text)
    message.setObjectName("MutedLabel")
    message.setAlignment(Qt.AlignCenter)
    message.setWordWrap(True)
    box.addWidget(icon_label)
    box.addWidget(message)
    container = QWidget()
    container.setLayout(box)
    container.setMinimumHeight(160)
    return container


def tool_button(text: str, glyph_name: str = "", variant: str = "",
                slot: Callable | None = None, tooltip: str = "",
                shortcut: str = "") -> QPushButton:
    button = QPushButton(text)
    if glyph_name:
        button.setIcon(icons.icon(glyph_name, "primary" if not variant else
                                  ("primary" if variant == "primary" else "muted")))
    if variant:
        button.setProperty("variant", variant)
    if tooltip:
        button.setToolTip(tooltip)
    if shortcut:
        button.setShortcut(QKeySequence(shortcut))
    if slot is not None:
        button.clicked.connect(slot)
    return button


# ===========================================================================
# Search field with debounce
# ===========================================================================
class SearchBox(QLineEdit):
    changed = Signal(str)

    def __init__(self, placeholder: str = "Search...", debounce_ms: int = 220):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setProperty("search", True)
        self.setClearButtonEnabled(True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(lambda: self.changed.emit(self.text().strip()))
        self.textChanged.connect(lambda _t: self._timer.start())

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._timer.stop()
            self.changed.emit(self.text().strip())
            return
        super().keyPressEvent(event)


class BarcodeInput(QLineEdit):
    """Dedicated scanner field: Enter submits, focus is never lost for long."""

    submitted = Signal(str)

    def __init__(self, placeholder: str = "Scan barcode or type it and press Enter"):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setProperty("barcode", True)
        self.setClearButtonEnabled(False)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            text = self.text().strip()
            if text:
                self.submitted.emit(text)
                self.clear()
            return
        super().keyPressEvent(event)


# ===========================================================================
# Tables
# ===========================================================================
@dataclass
class Column:
    key: str
    title: str
    width: int | None = 140
    align: str = "left"          # left | right | center
    format: Callable[[Any], str] | None = None   # noqa: A003
    visible: bool = True


# Database status values -> what the shop owner reads on screen
STATUS_LABELS = {
    "completed": "Completed",
    "partially_returned": "Partially returned",
    "returned": "Returned",
    "voided": "Voided",
    "on_hold": "On hold",
    "received": "Received",
    "cancelled": "Cancelled",
    "ok": "OK",
    "missing": "Missing",
    "manual": "Manual",
    "auto": "Automatic",
    "daily": "Daily",
    "weekly": "Weekly",
    "restore-safety": "Restore safety",
}


def status_label(value: Any) -> str:
    """Human readable status text (unknown values pass through unchanged)."""
    text = str(value or "")
    return STATUS_LABELS.get(text.lower(), text)


class TableModel(QAbstractTableModel):
    def __init__(self, columns: Sequence[Column], rows: Iterable[dict] | None = None):
        super().__init__()
        self.columns = list(columns)
        self.rows: list[dict] = list(rows or [])

    # -- Qt model API ---------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(self.columns)

    def data(self, index, role=Qt.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        column = self.columns[index.column()]
        value = row.get(column.key)
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            if column.format:
                return column.format(value)
            if value is None:
                return ""
            if column.key == "status":
                return status_label(value)
            if isinstance(value, float):
                return f"{value:g}"
            return str(value)
        if role == Qt.TextAlignmentRole:
            return {"right": int(Qt.AlignRight | Qt.AlignVCenter),
                    "center": int(Qt.AlignCenter),
                    "left": int(Qt.AlignLeft | Qt.AlignVCenter)}[column.align]
        if role == Qt.UserRole:
            return value
        if role == Qt.ForegroundRole:
            status = status_label(row.get("status", ""))
            if status in ("Out of stock", "Disabled", "Voided"):
                return QColor(theme.DANGER)
            if status in ("Low stock", "Partially returned", "On hold"):
                return QColor(theme.WARNING)
            if status in ("In stock", "Completed", "Active"):
                return QColor(theme.SUCCESS)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section].title
        if role == Qt.TextAlignmentRole and orientation == Qt.Horizontal:
            return int(Qt.AlignCenter)
        if role == Qt.FontRole and orientation == Qt.Horizontal:
            font = QFont()
            font.setBold(True)
            return font
        return None

    # -- helpers --------------------------------------------------------
    def set_rows(self, rows: Iterable[dict]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def append(self, row: dict) -> None:
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows))
        self.rows.append(row)
        self.endInsertRows()

    def row_at(self, index: QModelIndex) -> dict | None:
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        return self.rows[index.row()]


def make_table(columns: Sequence[Column], rows: Iterable[dict] | None = None,
               stretch_last: bool = True, select_rows: bool = True,
               alternating: bool = True) -> tuple[QTableView, TableModel]:
    model = TableModel(columns, rows)
    view = QTableView()
    view.setModel(model)
    view.setAlternatingRowColors(alternating)
    view.setSelectionBehavior(QAbstractItemView.SelectRows)
    view.setSelectionMode(QAbstractItemView.SingleSelection if select_rows
                          else QAbstractItemView.NoSelection)
    view.setEditTriggers(QAbstractItemView.NoEditTriggers)
    view.setSortingEnabled(False)
    view.setShowGrid(False)
    view.verticalHeader().setVisible(False)
    view.verticalHeader().setDefaultSectionSize(32)
    view.verticalHeader().sectionResized.connect(lambda *_: None)
    header = view.horizontalHeader()
    header.setStretchLastSection(stretch_last)
    header.setMinimumSectionSize(56)
    for index, column in enumerate(columns):
        mode = QHeaderView.Stretch if (column.width is None and stretch_last) \
            else QHeaderView.Interactive
        header.setSectionResizeMode(index, mode)
        if column.width:
            header.resizeSection(index, column.width)
    view.setFocusPolicy(Qt.StrongFocus)
    return view, model


def selected_row(view: QTableView) -> dict | None:
    model: TableModel = view.model()  # type: ignore[assignment]
    indexes = view.selectionModel().selectedRows() if view.selectionModel() else []
    if not indexes:
        return None
    return model.row_at(indexes[0])


# ===========================================================================
# Dialogs
# ===========================================================================
class FormDialog(QDialog):
    """Base dialog: form fields + OK/Cancel with a validation hook."""

    def __init__(self, parent: QWidget | None, title: str, submit_text: str = "Save"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 18, 20, 16)
        self.root.setSpacing(12)
        self.form = QFormLayout()
        self.form.setSpacing(10)
        self.form.setLabelAlignment(Qt.AlignRight)
        self.root.addLayout(self.form)
        self.error_label = QLabel()
        self.error_label.setObjectName("ErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.root.addWidget(self.error_label)
        self.buttons = QDialogButtonBox()
        self.submit_button = self.buttons.addButton(
            submit_text, QDialogButtonBox.AcceptRole)
        self.submit_button.setProperty("variant", "primary")
        self.buttons.addButton(QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        self.root.addWidget(self.buttons)

    def add_field(self, label: str, widget: QWidget) -> QWidget:
        self.form.addRow(label, widget)
        return widget

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))

    def validate(self) -> str:
        """Return an error message (empty when valid)."""
        return ""

    def _on_accept(self) -> None:
        error = self.validate()
        if error:
            self.set_error(error)
            return
        self.set_error("")
        self.accept()


class LineEdit(QLineEdit):
    def __init__(self, placeholder: str = "", value: str = ""):
        super().__init__()
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setText(value)

    def value(self) -> str:
        return self.text().strip()


def file_save_dialog(parent, title: str, filter_str: str,
                     default_name: str) -> str | None:
    path, _ = QFileDialog.getSaveFileName(parent, title, default_name, filter_str)
    return path or None


def file_open_dialog(parent, title: str, filter_str: str) -> str | None:
    path, _ = QFileDialog.getOpenFileName(parent, title, "", filter_str)
    return path or None


def busy_cursor(active: bool = True) -> None:
    from PySide6.QtGui import QCursor
    from PySide6.QtCore import Qt as _Qt
    QApplication.setOverrideCursor(QCursor(_Qt.WaitCursor)) if active \
        else QApplication.restoreOverrideCursor()
