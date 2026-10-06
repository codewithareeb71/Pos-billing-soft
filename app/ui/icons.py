"""Vector-style icons rendered from the Segoe MDL2 Assets font (Windows 10+).

A contact sheet can be generated with `python -m app.ui.icons --preview`
which writes `icon_preview.png` for visual verification.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from . import theme

FONT = "Segoe MDL2 Assets"

# name -> glyph code point
GLYPHS = {
    "home": "\uE80F",
    "pos": "\uE7BF",
    "package": "\uE8EC",
    "inventory": "\uE8F1",
    "users": "\uE716",
    "user": "\uE77B",
    "receipt": "\uE8A5",
    "chart": "\uE9D9",
    "settings": "\uE713",
    "database": "\uE801",
    "tag": "\uE8EC",
    "barcode": "\uE8AB",
    "search": "\uE721",
    "add": "\uE710",
    "close": "\uE711",
    "check": "\uE73E",
    "delete": "\uE74C",
    "print": "\uE749",
    "save": "\uE74E",
    "refresh": "\uE72C",
    "history": "\uE81C",
    "lock": "\uE72E",
    "info": "\uE946",
    "warning": "\uE7BA",
    "error": "\uE730",
    "money": "\uE8A1",
    "truck": "\uE806",
    "edit": "\uE90F",
    "folder": "\uE8B7",
    "export": "\uEDE1",
    "import": "\uE896",
    "alert": "\uE7BA",
    "clock": "\uE823",
    "calendar": "\uE787",
    "filter": "\uECB1",
    "list": "\uE8FD",
    "plus": "\uE710",
    "minus": "\uE738",
    "up": "\uE70E",
    "down": "\uE70D",
    "forward": "\uE72A",
    "back": "\uE72B",
    "logout": "\uE896",
    "key": "\uE755",
    "shield": "\uE72E",
    "star": "\uE734",
    "grid": "\uE80A",
    "people": "\uE716",
    "card": "\uE8A1",
    "return": "\uE72C",
    "cart": "\uE7BF",
    "box": "\uE8EC",
    "link": "\uE71B",
    "photo": "\uEB9F",
    "copy": "\uE8C8",
    "play": "\uE768",
    "wrench": "\uE90F",
    "gear": "\uE713",
    "dash": "\uE80F",
}


def glyph(name: str) -> str:
    return GLYPHS.get(name, "\uE946")


# ---------------------------------------------------------------------------
# A few marks are drawn as vectors because the font has no matching glyph.
# ---------------------------------------------------------------------------
def _draw_barcode(painter: QPainter, rect: QRectF, color: str) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(theme.color(color)))
    widths = [0.06, 0.03, 0.09, 0.03, 0.06, 0.03, 0.11, 0.03, 0.06, 0.03, 0.09, 0.03]
    x = rect.left() + rect.width() * 0.06
    top = rect.top() + rect.height() * 0.18
    bottom = rect.bottom() - rect.height() * 0.18
    for factor in widths:
        bar_w = rect.width() * factor
        if factor > 0.05:
            painter.drawRect(QRectF(x, top, bar_w, bottom - top))
        x += bar_w + rect.width() * 0.035
    # quiet zone bars at both ends
    painter.drawRect(QRectF(rect.left() + rect.width() * 0.02, top,
                            rect.width() * 0.02, bottom - top))


def _draw_database(painter: QPainter, rect: QRectF, color: str) -> None:
    pen = QColor(theme.color(color))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(theme.color(color)))
    w = rect.width() * 0.72
    h = rect.height() * 0.26
    x = rect.left() + rect.width() * 0.14
    for index in range(3):
        y = rect.top() + rect.height() * 0.10 + index * rect.height() * 0.26
        painter.drawEllipse(QRectF(x, y, w, h))
        painter.drawRect(QRectF(x, y + h * 0.35, w, h * 0.72))
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(x, rect.top() + rect.height() * 0.10, w, h))


def _draw_logout(painter: QPainter, rect: QRectF, color: str) -> None:
    pen = QColor(theme.color(color))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(theme.color(color)))
    left = rect.left() + rect.width() * 0.10
    painter.drawRect(QRectF(left, rect.top() + rect.height() * 0.16,
                            rect.width() * 0.34, rect.height() * 0.68))
    painter.setBrush(Qt.NoBrush)
    painter.setPen(pen)
    from PySide6.QtGui import QPen
    line_pen = QPen(pen, max(1.4, rect.width() * 0.09))
    line_pen.setCapStyle(Qt.RoundCap)
    painter.setPen(line_pen)
    y = rect.top() + rect.height() * 0.50
    painter.drawLine(int(left + rect.width() * 0.46), int(y),
                     int(rect.right() - rect.width() * 0.16), int(y))
    tip = rect.right() - rect.width() * 0.14
    painter.drawLine(int(tip - rect.width() * 0.14), int(y - rect.height() * 0.16),
                     int(tip), int(y))
    painter.drawLine(int(tip - rect.width() * 0.14), int(y + rect.height() * 0.16),
                     int(tip), int(y))


def _draw_filter(painter: QPainter, rect: QRectF, color: str) -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(theme.color(color)))
    left, right = rect.left() + rect.width() * 0.12, rect.right() - rect.width() * 0.12
    top = rect.top() + rect.height() * 0.18
    mid = rect.top() + rect.height() * 0.58
    points = QPolygonF([
        QPointF(left, top),
        QPointF(right, top),
        QPointF(left + (right - left) * 0.62, mid),
        QPointF(left + (right - left) * 0.62, rect.bottom() - rect.height() * 0.16),
        QPointF(left + (right - left) * 0.38, rect.bottom() - rect.height() * 0.16),
        QPointF(left + (right - left) * 0.38, mid),
    ])
    painter.drawPolygon(points)


def _draw_folder(painter: QPainter, rect: QRectF, color: str) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(theme.color(color)))
    x, y = rect.left() + rect.width() * 0.10, rect.top() + rect.height() * 0.24
    painter.drawRoundedRect(QRectF(x, y, rect.width() * 0.80, rect.height() * 0.56),
                            rect.width() * 0.06, rect.height() * 0.06)
    painter.drawRect(QRectF(x, y - rect.height() * 0.02, rect.width() * 0.34,
                            rect.height() * 0.16))


CUSTOM_DRAW = {
    "barcode": _draw_barcode,
    "database": _draw_database,
    "logout": _draw_logout,
    "filter": _draw_filter,
    "folder": _draw_folder,
}


def pixmap(name: str, size: int = 16, color: str = "primary") -> QPixmap:
    """Render a glyph (or custom vector mark) into a coloured pixmap."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    if name in CUSTOM_DRAW:
        CUSTOM_DRAW[name](painter, QRectF(1, 1, size - 2, size - 2), color)
    else:
        painter.setPen(QColor(theme.color(color)))
        font = QFont(FONT)
        font.setPixelSize(int(size * 1.05))
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, size, size), int(Qt.AlignCenter), glyph(name))
    painter.end()
    return pix


def icon(name: str, color: str = "primary", size: int = 16) -> QIcon:
    return QIcon(pixmap(name, size, color))


def apply(widget, name: str, color: str = "primary", size: int = 16) -> None:
    """Attach a glyph icon to an existing button."""
    widget.setIcon(icon(name, color, size))
    widget.setIconSize(QSize(size, size))


def _preview(path: str = "icon_preview.png") -> None:  # pragma: no cover - dev tool
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    theme.apply_theme(app)
    names = list(GLYPHS)
    per_row = 8
    cell_w, cell_h = 120, 92
    rows = (len(names) + per_row - 1) // per_row
    sheet = QPixmap(cell_w * per_row, cell_h * rows)
    sheet.fill(QColor(theme.BG))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.Antialiasing)
    for index, name in enumerate(names):
        col, row = index % per_row, index // per_row
        x, y = col * cell_w, row * cell_h
        if name in CUSTOM_DRAW:
            pix = pixmap(name, 40, "primary")
            painter.drawPixmap(int(x + (cell_w - 40) / 2), int(y + 12), pix)
        else:
            painter.setPen(QColor(theme.PRIMARY))
            painter.setFont(QFont(FONT, 26))
            painter.drawText(QRectF(x, y + 8, cell_w, 48), int(Qt.AlignCenter), glyph(name))
        painter.setPen(QColor(theme.MUTED))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(x, y + 60, cell_w, 24), int(Qt.AlignCenter), name)
    painter.end()
    sheet.save(path)
    print(f"contact sheet written to {path}")


if __name__ == "__main__":  # pragma: no cover
    _preview()
