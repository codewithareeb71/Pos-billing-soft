"""Application configuration, paths and constants.

Everything the application needs at runtime lives inside a per-user
application-data directory so that the database survives restarts,
updates and Windows reinstalls of the program files.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ALSHAN POS SYSTEM"
APP_SHORT_NAME = "AlshanPOS"
APP_VENDOR = "Alshan Software"
APP_VERSION = "1.0.0"
APP_COPYRIGHT = f"Copyright (c) 2026 {APP_VENDOR}"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _data_dir() -> Path:
    override = os.environ.get("ALSHAN_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        base = base / APP_SHORT_NAME
    else:  # pragma: no cover - development on non Windows platforms
        base = Path.home() / ".alshan_pos"
    base.mkdir(parents=True, exist_ok=True)
    return base


DATA_DIR: Path = _data_dir()
DB_PATH: Path = DATA_DIR / "alshan_pos.db"
LOG_DIR: Path = DATA_DIR / "logs"
BACKUP_DIR: Path = DATA_DIR / "backups"
ASSET_DIR: Path = DATA_DIR / "assets"
PRODUCT_IMAGE_DIR: Path = ASSET_DIR / "products"
SHOP_LOGO_PATH: Path = ASSET_DIR / "shop_logo.png"
APP_ICON_PATH: Path = ASSET_DIR / "alshan_pos.ico"

for _d in (LOG_DIR, BACKUP_DIR, PRODUCT_IMAGE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DB_FILENAME = "alshan_pos.db"

# ---------------------------------------------------------------------------
# Security / authentication
# ---------------------------------------------------------------------------
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 390_000
MIN_PASSWORD_LENGTH = 5
MAX_LOGIN_ATTEMPTS = 8
LOGIN_LOCKOUT_MINUTES = 5

# ---------------------------------------------------------------------------
# Business defaults
# ---------------------------------------------------------------------------
DEFAULT_CURRENCY = "PKR"
DEFAULT_INVOICE_PREFIX = "ALS"
DEFAULT_INVOICE_PADDING = 6
DEFAULT_RECEIPT_WIDTH_MM = 80
SUPPORTED_RECEIPT_WIDTHS_MM = (58, 80, 72)

PAYMENT_METHODS = ("Cash", "Card", "Bank Transfer", "Other")
PAYMENT_METHOD_DEFAULT = "Cash"

STOCK_ADJUST_REASONS = (
    "Damaged",
    "Lost",
    "Found",
    "Manual correction",
    "Opening stock",
    "Expired",
    "Returned to supplier",
)

MOVERS = ("sale", "purchase", "return", "adjustment", "void", "import", "initial")

# Shortcuts exposed on the POS screen
SHORTCUTS = {
    "F1": "New sale",
    "F2": "Product search",
    "F4": "Select customer",
    "F6": "Focus barcode",
    "F8": "Complete sale",
    "F9": "Hold sale",
    "ESC": "Cancel / close",
}

IS_FROZEN = getattr(sys, "frozen", False)


def resource_path(relative: str) -> Path:
    """Return path to bundled resource (works with PyInstaller onefile/onefolder)."""
    if IS_FROZEN:  # pragma: no cover - packaging environment
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative
