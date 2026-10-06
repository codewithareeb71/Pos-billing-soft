"""SQLite database engine: connections, transactions, helpers, initialisation."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from .. import config
from . import schema
from .exceptions import DatabaseError
from .logging_setup import get_logger

log = get_logger("db")

LOCAL_NOW = "datetime('now','localtime')"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------


def row_to_dict(row: sqlite3.Row | None) -> Optional[dict]:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rows_to_list(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [row_to_dict(r) for r in rows]


def rows(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[dict]:
    return rows_to_list(conn.execute(sql, params).fetchall())


def row(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> Optional[dict]:
    return row_to_dict(conn.execute(sql, params).fetchone())


def scalar(conn: sqlite3.Connection, sql: str, params: tuple | list = (), default=0):
    value = conn.execute(sql, params).fetchone()
    if value is None or value[0] is None:
        return default
    return value[0]


def insert_returning_id(conn: sqlite3.Connection, sql: str, params: tuple | list) -> int:
    cur = conn.execute(sql, params)
    return int(cur.lastrowid or 0)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class Database:
    """Owns the SQLite file and provides read / write contexts."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else config.DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- plumbing
    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(str(self.path), timeout=20.0, isolation_level=None)
        except sqlite3.Error as exc:  # pragma: no cover - disk level failure
            raise DatabaseError(detail=str(exc)) from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 15000")
        conn.execute("PRAGMA temp_store = MEMORY")
        return conn

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """Read-only style context (auto-committed, always released)."""
        conn = self._connect()
        try:
            yield conn
        except sqlite3.Error as exc:
            log.error("SQL error: %s | %s", exc, str(exc))
            raise DatabaseError(detail=str(exc)) from exc
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Write transaction: BEGIN IMMEDIATE .. COMMIT or ROLLBACK."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:  # pragma: no cover
                pass
            log.error("Transaction rolled back: %s", exc)
            raise DatabaseError(detail=str(exc)) from exc
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:  # pragma: no cover
                pass
            raise
        finally:
            conn.close()

    # ----------------------------------------------------------- operations
    def initialize(self, create_default_admin: bool = False) -> None:
        """Create schema, seed reference data and (optionally) a fallback admin."""
        conn = self._connect()
        try:
            conn.executescript(schema.SCHEMA_SQL)
            self._seed(conn)
            conn.execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION}")
            if create_default_admin:
                self._ensure_default_admin(conn)
        except sqlite3.Error as exc:
            log.error("Database initialisation failed: %s", exc)
            raise DatabaseError(detail=str(exc)) from exc
        finally:
            conn.close()

    def is_initialized(self) -> bool:
        try:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
                )
                return cur.fetchone() is not None
            finally:
                conn.close()
        except sqlite3.Error:
            return False

    @staticmethod
    def _seed(conn: sqlite3.Connection) -> None:
        from ..core import security

        conn.executemany(
            "INSERT OR IGNORE INTO permissions(code, module, description) VALUES (?,?,?)",
            schema.PERMISSIONS,
        )
        for name, description, is_system in (
            ("Administrator", "Full access to every module", 1),
            ("Cashier", "Sales, returns and lookups only", 1),
        ):
            conn.execute(
                "INSERT OR IGNORE INTO roles(name, description, is_system) VALUES (?,?,?)",
                (name, description, is_system),
            )
        # refresh permission grants for the built-in roles
        admin_id = conn.execute(
            "SELECT id FROM roles WHERE name = 'Administrator'"
        ).fetchone()[0]
        cashier_id = conn.execute(
            "SELECT id FROM roles WHERE name = 'Cashier'"
        ).fetchone()[0]
        conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (admin_id,))
        conn.execute(
            "INSERT OR IGNORE INTO role_permissions(role_id, permission_id) "
            "SELECT ?, id FROM permissions",
            (admin_id,),
        )
        conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (cashier_id,))
        conn.execute(
            "INSERT OR IGNORE INTO role_permissions(role_id, permission_id) "
            "SELECT ?, id FROM permissions WHERE code IN (%s)"
            % ",".join("?" * len(schema.CASHIER_PERMISSIONS)),
            (cashier_id, *schema.CASHIER_PERMISSIONS),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO units(name, short_code) VALUES (?,?)",
            schema.DEFAULT_UNITS,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)",
            list(schema.DEFAULT_SETTINGS.items()),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO counters(name, value) VALUES (?,0)",
            [("invoice",), ("return",), ("purchase",)],
        )
        conn.execute(
            "INSERT OR IGNORE INTO customers(name, is_walkin, notes) "
            "VALUES ('Walk-in Customer', 1, 'Default customer')"
        )
        # a couple of scanning-friendly demo categories are NOT created: real
        # data only.  Owners create their own categories in the Products module.

    @staticmethod
    def _ensure_default_admin(conn: sqlite3.Connection) -> None:
        from ..core import security

        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count:
            return
        role_id = conn.execute(
            "SELECT id FROM roles WHERE name = 'Administrator'"
        ).fetchone()[0]
        password_hash, _ = security.hash_password("admin")
        conn.execute(
            "INSERT INTO users(username, password_hash, full_name, role_id, must_change_password) "
            "VALUES (?,?,?,?,1)",
            ("admin", password_hash, "Administrator", role_id),
        )
        log.info("Default administrator account created (username: admin)")

    # -------------------------------------------------------------- backups
    def integrity_check(self) -> bool:
        try:
            with self.read() as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()
                return bool(result) and str(result[0]).lower() == "ok"
        except DatabaseError:
            return False

    def backup_to(self, target: Path | str, kind: str = "manual", user: str = "",
                  note: str = "") -> dict:
        """Create a consistent online backup using the SQLite backup API."""
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        src = self._connect()
        dst = None
        try:
            dst = sqlite3.connect(str(target))
            with dst:
                src.backup(dst)
            size = target.stat().st_size
            with self.transaction() as conn:
                conn.execute(
                    "INSERT INTO backups(path, filename, size_bytes, kind, status, note, created_by) "
                    "VALUES (?,?,?,?, 'ok', ?, ?)",
                    (str(target), target.name, size, kind, note, user),
                )
            log.info("Backup created: %s (%s bytes)", target, size)
            return {"path": str(target), "size": size}
        except (sqlite3.Error, OSError) as exc:
            log.error("Backup failed: %s", exc)
            raise DatabaseError(detail=str(exc)) from exc
        finally:
            src.close()
            if dst is not None:
                dst.close()

    def next_number(self, conn: sqlite3.Connection, counter: str, prefix: str,
                    padding: int) -> str:
        """Atomically reserve the next business number (invoice/return/purchase)."""
        conn.execute(
            "INSERT INTO counters(name, value) VALUES (?, 0) ON CONFLICT(name) DO NOTHING",
            (counter,),
        )
        conn.execute("UPDATE counters SET value = value + 1 WHERE name = ?", (counter,))
        value = conn.execute(
            "SELECT value FROM counters WHERE name = ?", (counter,)
        ).fetchone()[0]
        return f"{prefix}-{int(value):0{padding}d}"


_default_db: Database | None = None


def get_db() -> Database:
    global _default_db
    if _default_db is None:
        _default_db = Database()
    return _default_db
