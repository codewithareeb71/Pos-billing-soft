"""Audit trail - records who did what and when."""
from __future__ import annotations

from .db import insert_returning_id
from .security import Session

# action constants
LOGIN = "LOGIN"
LOGOUT = "LOGOUT"
CREATE = "CREATE"
UPDATE = "UPDATE"
DELETE = "DELETE"
VOID = "VOID"
RETURN = "RETURN"
ADJUST = "ADJUST"
BACKUP = "BACKUP"
RESTORE = "RESTORE"
SETTINGS = "SETTINGS"
EXPORT = "EXPORT"
IMPORT = "IMPORT"
PRINT = "PRINT"


def log(conn, session: Session | None, action: str, entity: str = "",
        entity_id=None, description: str = "", details: str = "") -> int:
    """Insert an audit row using the caller's open transaction."""
    user_id = session.user_id if session else None
    username = session.username if session else "system"
    return insert_returning_id(
        conn,
        "INSERT INTO audit_logs(user_id, username, action, entity, entity_id, "
        "description, details) VALUES (?,?,?,?,?,?,?)",
        (user_id, username, action, entity,
         str(entity_id) if entity_id is not None else "",
         description, details),
    )


def log_always(db, session: Session | None, action: str, entity: str = "",
               entity_id=None, description: str = "", details: str = "") -> None:
    """Best-effort audit entry with its own transaction (never raises)."""
    try:
        with db.transaction() as conn:
            log(conn, session, action, entity, entity_id, description, details)
    except Exception:  # pragma: no cover - audit must not break the app
        pass
