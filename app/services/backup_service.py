"""Backup, restore and automatic backup retention."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .. import config
from ..core import audit
from ..core.db import now_str, row, rows, scalar
from ..core.exceptions import BackupError, ValidationError
from ..core.security import Session
from .settings_service import SettingsService


class BackupService:
    def __init__(self, db, settings: SettingsService, session: Session | None = None):
        self.db = db
        self.settings = settings
        self.session = session

    # ------------------------------------------------------------ creating
    @staticmethod
    def default_filename(now: datetime | None = None) -> str:
        now = now or datetime.now()
        return f"AlshanPOS_Backup_{now.strftime('%Y-%m-%d_%H-%M-%S')}.db"

    def create_backup(self, target_dir: str | Path | None = None, kind: str = "manual",
                      user: str = "", note: str = "") -> Path:
        directory = Path(target_dir) if target_dir else config.BACKUP_DIR
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / self.default_filename()
        counter = 1
        while target.exists():
            target = directory / f"{self.default_filename().replace('.db', f'_{counter}.db')}"
            counter += 1
        try:
            self.db.backup_to(target, kind=kind, user=user or
                              (self.session.username if self.session else ""),
                              note=note)
        except Exception as exc:
            raise BackupError(f"Backup failed: {exc}") from exc
        return target

    def list_backups(self) -> list[dict]:
        with self.db.read() as conn:
            records = rows(conn, "SELECT * FROM backups ORDER BY id DESC LIMIT 300")
        for record in records:
            path = Path(record["path"])
            record["exists"] = path.exists()
            record["size_mb"] = round(path.stat().st_size / (1024 * 1024), 2) if path.exists() else 0
        return records

    # -------------------------------------------------------------- verify
    @staticmethod
    def validate_backup(path: str | Path) -> dict:
        path = Path(path)
        if not path.exists():
            raise BackupError("The selected backup file does not exist.")
        if path.stat().st_size < 1024:
            raise BackupError("The selected file is not a valid database backup.")
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        except sqlite3.Error as exc:
            raise BackupError(f"Unable to open the backup file: {exc}") from exc
        try:
            header = path.read_bytes()[:16]
            if not header.startswith(b"SQLite format 3"):
                raise BackupError("The selected file is not an Alshan POS database.")
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if str(integrity).lower() != "ok":
                raise BackupError("The backup file is corrupted (integrity check failed).")
            names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"users", "products", "sales", "settings"}
            missing = required - names
            if missing:
                raise BackupError(
                    "The selected file is not a complete Alshan POS backup "
                    f"(missing: {', '.join(sorted(missing))})."
                )
            counts = {
                "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
                "sales": conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                "categories": conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0],
            }
            created = ""
            try:
                created = conn.execute(
                    "SELECT value FROM settings WHERE key='shop.name'").fetchone()[0]
            except sqlite3.Error:
                pass
            return {"ok": True, "path": str(path), "size": path.stat().st_size,
                    "counts": counts, "shop_name": created}
        except sqlite3.Error as exc:
            raise BackupError(f"Unable to read the backup file: {exc}") from exc
        finally:
            conn.close()

    # ------------------------------------------------------------- restore
    def restore(self, path: str | Path, session: Session | None = None) -> dict:
        """Restore with a mandatory safety backup and validation."""
        session = session or self.session
        info = self.validate_backup(path)
        safety = self.create_backup(kind="restore-safety",
                                    user=session.username if session else "",
                                    note="Automatic backup created before restore")
        source = Path(path)
        try:
            # remove stale WAL/SHM files so the restored file is authoritative
            for suffix in ("-wal", "-shm", "-journal"):
                stale = Path(str(self.db.path) + suffix)
                if stale.exists():
                    stale.unlink()
            shutil.copy2(source, self.db.path)
            if not self.db.integrity_check():
                # roll back to the safety copy
                shutil.copy2(safety, self.db.path)
                raise BackupError("Restore failed the integrity check. The previous "
                                  "database was kept.")
        except OSError as exc:
            raise BackupError(f"Unable to restore the database: {exc}") from exc
        self.settings.reload()
        try:
            with self.db.transaction() as conn:
                audit.log(conn, session, audit.RESTORE, entity="database",
                          description=f"Database restored from {source.name}",
                          details=f"safety_backup={safety.name}")
        except Exception:  # pragma: no cover
            pass
        return {"restored": str(source), "safety_backup": str(safety), "info": info}

    # ------------------------------------------------------------- automatic
    def auto_backup_if_due(self) -> Path | None:
        """Called at startup; honours manual / daily / weekly scheduling."""
        mode = self.settings.get("backup.mode", "manual")
        if mode in ("manual", "", "off"):
            return None
        last = self.settings.get("backup.last_run", "")
        now = datetime.now()
        due = True
        if last:
            try:
                last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
                if mode == "daily":
                    due = now - last_dt >= timedelta(days=1)
                elif mode == "weekly":
                    due = now - last_dt >= timedelta(days=7)
            except ValueError:
                due = True
        if not due:
            return None
        target = self.create_backup(config.BACKUP_DIR, kind="auto", user="system",
                                    note=f"Automatic {mode} backup")
        self.settings.set("backup.last_run", now_str(), audit_change=False)
        self._prune()
        return target

    def _prune(self) -> None:
        keep = max(1, self.settings.get_int("backup.retention", 7))
        with self.db.read() as conn:
            records = rows(conn,
                           "SELECT id, path FROM backups WHERE kind='auto' ORDER BY id DESC")
        for record in records[keep:]:
            path = Path(record["path"])
            if path.exists() and str(config.BACKUP_DIR) in str(path):
                try:
                    path.unlink()
                except OSError:
                    continue
            with self.db.transaction() as conn:
                conn.execute("DELETE FROM backups WHERE id = ?", (record["id"],))

    def prune_now(self) -> int:
        before = len(self.list_backups())
        self._prune()
        return before - len(self.list_backups())

    # --------------------------------------------------------------- stats
    def database_info(self) -> dict:
        path = self.db.path
        size = path.stat().st_size if path.exists() else 0
        with self.db.read() as conn:
            version = scalar(conn, "PRAGMA user_version", (), 0)
            counts = {
                "products": scalar(conn, "SELECT COUNT(*) FROM products", (), 0),
                "sales": scalar(conn, "SELECT COUNT(*) FROM sales", (), 0),
                "customers": scalar(conn, "SELECT COUNT(*) FROM customers", (), 0),
                "suppliers": scalar(conn, "SELECT COUNT(*) FROM suppliers", (), 0),
                "purchases": scalar(conn, "SELECT COUNT(*) FROM purchases", (), 0),
                "users": scalar(conn, "SELECT COUNT(*) FROM users", (), 0),
                "audit_entries": scalar(conn, "SELECT COUNT(*) FROM audit_logs", (), 0),
            }
        return {
            "path": str(path),
            "size_mb": round(size / (1024 * 1024), 2),
            "schema_version": version,
            "counts": counts,
            "mode": self.settings.get("backup.mode", "manual"),
            "retention": self.settings.get_int("backup.retention", 7),
            "last_run": self.settings.get("backup.last_run", "Never"),
        }
