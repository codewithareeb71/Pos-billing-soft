"""Page factory for the main window."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from PySide6.QtWidgets import QWidget

    from ..context import AppContext

_MODULES = {
    "dashboard": "dashboard",
    "pos": "pos_page",
    "products": "products_page",
    "inventory": "inventory_page",
    "purchases": "purchases_page",
    "customers": "customers_page",
    "suppliers": "suppliers_page",
    "sales": "sales_page",
    "returns": "returns_page",
    "expenses": "expenses_page",
    "reports": "reports_page",
    "users": "users_page",
    "settings": "settings_page",
}


def build_page(key: str, ctx: "AppContext", parent=None):
    """Import and build the requested page (lazy loading keeps start-up fast)."""
    import importlib

    module_name = _MODULES.get(key)
    if not module_name:
        raise KeyError(f"Unknown page: {key}")
    module = importlib.import_module(f"{__name__}.{module_name}")
    return module.create(ctx, parent)
