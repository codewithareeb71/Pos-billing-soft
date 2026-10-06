"""Visual identity: colours, typography and the application stylesheet."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtWidgets import QApplication

APP_NAME = "ALSHAN POS SYSTEM"

# palette -------------------------------------------------------------------
PRIMARY = "#123A5C"        # deep navy - brand
PRIMARY_DARK = "#0D2A44"
PRIMARY_LIGHT = "#1E5F8E"
ACCENT = "#2E86AB"         # bright blue accent
SUCCESS = "#158F5B"
DANGER = "#C0392B"
WARNING = "#D68910"
INFO = "#2E86AB"
BG = "#F2F5F9"
CARD = "#FFFFFF"
BORDER = "#DDE4EC"
TEXT = "#1B2733"
MUTED = "#68788C"
SIDEBAR_BG = "#0E2438"
SIDEBAR_HOVER = "#17374F"
SIDEBAR_ACTIVE = "#1E5F8E"
ROW_ALT = "#F7FAFD"
SELECTED = "#E3EEF8"

GLYPH_FONT = "Segoe MDL2 Assets"

QSS = f"""
* {{ font-family: 'Segoe UI', 'Segoe UI Variable', sans-serif; font-size: 9.5pt; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}
QLabel {{ background: transparent; }}
QToolTip {{
    background: #1B2733; color: #FFFFFF; padding: 5px 8px;
    border: none; border-radius: 3px; font-size: 9pt;
}}

/* ----------------------------------------------------------- side bar */
#Sidebar {{ background: {SIDEBAR_BG}; border: none; }}
#BrandTitle {{ color: #FFFFFF; font-size: 15pt; font-weight: 700; letter-spacing: 1px; }}
#BrandSub {{ color: #8FB3CC; font-size: 8pt; letter-spacing: 1px; }}
#SideSpacer {{ background: transparent; }}
#UserBadge {{ color: #D6E4F0; font-size: 9pt; }}
#UserRole {{ color: #7FA6C4; font-size: 8pt; }}
QPushButton[nav="true"] {{
    background: transparent; color: #C6D6E4; border: none; border-radius: 6px;
    text-align: left; padding: 9px 14px; margin: 1px 8px; font-size: 10pt;
}}
QPushButton[nav="true"]:hover {{ background: {SIDEBAR_HOVER}; color: #FFFFFF; }}
QPushButton[nav="true"]:checked {{ background: {SIDEBAR_ACTIVE}; color: #FFFFFF; font-weight: 600; }}
QPushButton#NavSection {{ color: #6E90AC; font-size: 8pt; padding: 10px 16px 2px 16px;
                          background: transparent; border: none; text-align: left; }}
QPushButton[sidebarBtn="true"] {{
    background: transparent; color: #A9C0D4; border: 1px solid #1E4260; border-radius: 6px;
    padding: 7px; margin: 4px 8px;
}}
QPushButton[sidebarBtn="true"]:hover {{ background: {SIDEBAR_HOVER}; color: #FFFFFF;
                                        border-color: {ACCENT}; }}

/* --------------------------------------------------------------- top bar */
#TopBar {{ background: {CARD}; border-bottom: 1px solid {BORDER}; }}
#PageTitle {{ font-size: 14pt; font-weight: 700; color: {PRIMARY}; }}
#PageSubtitle {{ color: {MUTED}; font-size: 9pt; }}
#SessionChip {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 12px;
                padding: 4px 12px; color: {PRIMARY}; font-size: 9pt; }}

/* --------------------------------------------------------------- cards */
QFrame[card="true"] {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px;
}}
QFrame[card="true"][hover="true"]:hover {{ border-color: {ACCENT}; }}
#CardTitle {{ color: {MUTED}; font-size: 9pt; font-weight: 600;
              text-transform: uppercase; letter-spacing: .5px; }}
#StatValue {{ font-size: 17pt; font-weight: 700; color: {PRIMARY}; }}
#StatLabel {{ color: {MUTED}; font-size: 9pt; }}
#SectionTitle {{ font-size: 11pt; font-weight: 700; color: {PRIMARY}; }}
#MutedLabel {{ color: {MUTED}; font-size: 9pt; }}
#HintLabel {{ color: {MUTED}; font-size: 8.5pt; }}
#ErrorLabel {{ color: {DANGER}; font-size: 9pt; }}
#SuccessLabel {{ color: {SUCCESS}; font-size: 9pt; }}

/* -------------------------------------------------------------- buttons */
QPushButton {{
    background: #EDF1F6; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 7px 14px; font-weight: 500;
}}
QPushButton:hover {{ background: #E2E9F1; border-color: #C9D5E2; }}
QPushButton:pressed {{ background: #D6DFEA; }}
QPushButton:disabled {{ color: #9AA7B5; background: #F3F5F8; border-color: #E6EBF1; }}
QPushButton[variant="primary"] {{
    background: {PRIMARY}; color: #FFFFFF; border: 1px solid {PRIMARY};
}}
QPushButton[variant="primary"]:hover {{ background: {PRIMARY_LIGHT}; border-color: {PRIMARY_LIGHT}; }}
QPushButton[variant="primary"]:pressed {{ background: {PRIMARY_DARK}; }}
QPushButton[variant="success"] {{
    background: {SUCCESS}; color: #FFFFFF; border: 1px solid {SUCCESS};
}}
QPushButton[variant="success"]:hover {{ background: #1AA768; }}
QPushButton[variant="danger"] {{
    background: #FFFFFF; color: {DANGER}; border: 1px solid #E6C2BD;
}}
QPushButton[variant="danger"]:hover {{ background: #FDF1EF; border-color: {DANGER}; }}
QPushButton[variant="flat"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[variant="flat"]:hover {{ background: #E9EFF6; border-color: {BORDER}; }}
QPushButton[variant="big"] {{ font-size: 11pt; padding: 12px 18px; font-weight: 600; }}
QPushButton[shortcut="true"] {{ padding: 10px 12px; font-weight: 600; }}

/* ---------------------------------------------------------- input fields */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit,
QComboBox, QAbstractSpinBox {{
    background: #FFFFFF; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 8px; selection-background-color: {ACCENT}; selection-color: #FFFFFF;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ background: #F4F6F9; color: #94A1B0; }}
QLineEdit[invalid="true"] {{ border: 1px solid {DANGER}; background: #FDF4F3; }}
QLineEdit[search="true"] {{ padding-left: 26px; }}
QLineEdit[barcode="true"] {{ font-size: 13pt; font-weight: 600; letter-spacing: 1px;
                             padding: 10px 12px; border: 2px solid {ACCENT};
                             background: #F7FBFE; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent;
                         border-right: 4px solid transparent; border-top: 5px solid {MUTED};
                         margin-right: 8px; }}
QComboBox QAbstractItemView {{ background: #FFFFFF; border: 1px solid {BORDER};
                               selection-background-color: {SELECTED};
                               selection-color: {TEXT}; padding: 2px; }}

/* ------------------------------------------------------------- grouping */
QGroupBox {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px;
             margin-top: 12px; padding-top: 8px; font-weight: 600; color: {PRIMARY}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; top: -8px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; background: {CARD};
                    top: -1px; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 9px 18px;
                border: 1px solid transparent; border-bottom: none;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
                font-weight: 600; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {CARD}; color: {PRIMARY}; border-color: {BORDER}; }}
QTabBar::tab:hover:!selected {{ color: {PRIMARY}; background: #E9EFF6; }}
QTabBar::tab:disabled {{ color: #A9B4C0; }}

/* ---------------------------------------------------------------- tables */
QTableView, QTreeView, QListView {{
    background: {CARD}; alternate-background-color: {ROW_ALT};
    border: 1px solid {BORDER}; border-radius: 8px; gridline-color: #EDF1F6;
    selection-background-color: {SELECTED}; selection-color: {TEXT};
}}
QTableView::item {{ padding: 6px 8px; border-bottom: 1px solid #F0F3F7; }}
QTableView::item:selected {{ background: {SELECTED}; color: {TEXT}; }}
QHeaderView::section {{
    background: #EEF3F8; color: {PRIMARY}; padding: 7px 8px; border: none;
    border-bottom: 1px solid {BORDER}; border-right: 1px solid #E4EAF1;
    font-weight: 700; font-size: 9pt;
}}
QHeaderView::section:last-child {{ border-right: none; }}
QTableView#BlankTable {{ border: none; background: transparent; }}
QTableView#BlankTable::item {{ border-bottom: 1px solid #F0F3F7; }}

/* ------------------------------------------------------------ scrollbars */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C4CFDB; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #C4CFDB; border-radius: 5px; min-width: 28px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ height: 0; width: 0; }}

/* ------------------------------------------------------------ fragments */
QMenuBar {{ background: {CARD}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item:selected {{ background: {SELECTED}; }}
QMenu {{ background: #FFFFFF; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 26px 6px 14px; border-radius: 4px; }}
QMenu::item:selected {{ background: {SELECTED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
QStatusBar {{ background: {CARD}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QMessageBox {{ background: {CARD}; }}
QDialog {{ background: {BG}; }}
QPushButton:focus {{ outline: none; }}
QLineEdit:focus {{ outline: none; }}
QCheckBox {{ spacing: 6px; }}
QRadioButton {{ spacing: 6px; }}
QProgressBar {{ border: 1px solid {BORDER}; border-radius: 5px; background: #EDF1F6;
                text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QSplitter::handle {{ background: {BORDER}; }}
"""

_COLORS = {
    "primary": PRIMARY,
    "accent": ACCENT,
    "success": SUCCESS,
    "danger": DANGER,
    "warning": WARNING,
    "muted": MUTED,
}


def color(name: str) -> str:
    return _COLORS.get(name, TEXT)


def qcolor(name: str) -> QColor:
    return QColor(color(name))


def apply_theme(app: QApplication) -> None:
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    app.setStyleSheet(QSS)
    _build_palette(app)


def _build_palette(app: QApplication) -> None:
    from PySide6.QtGui import QPalette

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.Base, QColor(CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(ROW_ALT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    app.setPalette(palette)


def logo_icon(size: int = 64, radius_ratio: float = 0.22) -> QIcon:
    """Programmatic Alshan logo: navy rounded square with an 'A' mark."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(0, 0, size, size)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(PRIMARY))
    painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), size * radius_ratio,
                             size * radius_ratio)
    painter.setBrush(QColor(ACCENT))
    painter.drawRoundedRect(QRectF(size * 0.14, size * 0.52, size * 0.72, size * 0.30),
                            size * 0.08, size * 0.08)
    # Vector "A" (no font dependency) - identical to assets/alshan_pos.ico
    painter.setPen(QPen(QColor("#FFFFFF"), max(1, size * 0.11),
                        Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawLine(QPointF(size * 0.30, size * 0.84),
                     QPointF(size * 0.50, size * 0.22))
    painter.drawLine(QPointF(size * 0.50, size * 0.22),
                     QPointF(size * 0.70, size * 0.84))
    painter.drawLine(QPointF(size * 0.385, size * 0.62),
                     QPointF(size * 0.615, size * 0.62))
    painter.end()
    return QIcon(pix)
