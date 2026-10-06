"""Application settings (key/value) with an in-memory cache."""
from __future__ import annotations

from ..core import audit
from ..core.db import row, rows, now_str
from ..core.exceptions import NotFoundError
from ..core.security import Session
from .. import config


class SettingsService:
    def __init__(self, db):
        self.db = db
        self._cache: dict[str, str] = {}
        self.reload()

    # ---------------------------------------------------------------- read
    def reload(self) -> None:
        with self.db.read() as conn:
            self._cache = {r["key"]: r["value"] for r in rows(conn, "SELECT key, value FROM settings")}

    def all(self) -> dict[str, str]:
        return dict(self._cache)

    def get(self, key: str, default: str = "") -> str:
        return self._cache.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(float(self._cache.get(key, default) or 0))
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self._cache.get(key, default) or 0)
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self._cache.get(key)
        if value is None:
            return default
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    # --------------------------------------------------------------- write
    def set(self, key: str, value, session: Session | None = None, audit_change: bool = True) -> None:
        text = str(value)
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO settings(key, value, updated_at, updated_by) VALUES (?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                (key, text, now_str(), session.username if session else ""),
            )
            if audit_change:
                audit.log(conn, session, audit.SETTINGS, entity="settings",
                          entity_id=key, description=f"Setting '{key}' changed",
                          details=f"value={text}")
        self._cache[key] = text

    def set_many(self, values: dict, session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            for key, value in values.items():
                text = str(value)
                conn.execute(
                    "INSERT INTO settings(key, value, updated_at, updated_by) VALUES (?,?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                    "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                    (key, text, now_str(), session.username if session else ""),
                )
                self._cache[key] = text
            audit.log(conn, session, audit.SETTINGS, entity="settings",
                      description="Settings updated",
                      details=", ".join(sorted(values.keys())))

    # -------------------------------------------------------- convenience
    @property
    def currency(self) -> str:
        return self.get("currency", config.DEFAULT_CURRENCY) or config.DEFAULT_CURRENCY

    @property
    def shop_name(self) -> str:
        return self.get("shop.name") or config.APP_NAME

    @property
    def setup_completed(self) -> bool:
        return self.get_bool("setup_completed", False)

    @property
    def receipt_width_mm(self) -> int:
        return self.get_int("receipt.width_mm", 80) or 80

    @property
    def invoice_prefix(self) -> str:
        return self.get("invoice.prefix", config.DEFAULT_INVOICE_PREFIX)

    @property
    def invoice_padding(self) -> int:
        return self.get_int("invoice.padding", config.DEFAULT_INVOICE_PADDING)

    def require(self, key: str) -> str:
        value = self.get(key)
        if not value:
            raise NotFoundError(f"Setting '{key}' is not configured.")
        return value
