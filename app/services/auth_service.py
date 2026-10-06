"""Authentication, users, roles and permissions."""
from __future__ import annotations

from datetime import datetime, timedelta

from .. import config
from ..core import audit, security
from ..core.db import now_str, row, rows, scalar
from ..core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError
from ..core.logging_setup import get_logger
from ..core.security import Session

log = get_logger("auth")


class AuthService:
    def __init__(self, db, settings=None):
        self.db = db
        self.settings = settings
        self.session: Session | None = None

    # ---------------------------------------------------------------- login
    def _load_permissions(self, conn, role_id: int) -> set[str]:
        return {
            r["code"]
            for r in rows(
                conn,
                "SELECT p.code FROM permissions p "
                "JOIN role_permissions rp ON rp.permission_id = p.id "
                "WHERE rp.role_id = ?",
                (role_id,),
            )
        }

    def _lockout_active(self, conn, username: str) -> int:
        """Return remaining locked-out seconds (0 when not locked)."""
        attempts = self.settings.get_int("security.lockout_attempts",
                                         config.MAX_LOGIN_ATTEMPTS) if self.settings else config.MAX_LOGIN_ATTEMPTS
        minutes = self.settings.get_int("security.lockout_minutes",
                                        config.LOGIN_LOCKOUT_MINUTES) if self.settings else config.LOGIN_LOCKOUT_MINUTES
        if attempts <= 0:
            return 0
        since = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        failures = scalar(
            conn,
            "SELECT COUNT(*) FROM login_attempts "
            "WHERE username = ? AND succeeded = 0 AND created_at >= ?",
            (username, since),
            0,
        )
        if failures >= attempts:
            return minutes * 60
        return 0

    def login(self, username: str, password: str) -> Session:
        username = (username or "").strip()
        if not username or not password:
            raise AuthenticationError("Enter your username and password.")
        # Read phase first: the lockout counter and the account lookup do not
        # need a write transaction.
        with self.db.read() as conn:
            locked = self._lockout_active(conn, username)
            record = row(conn,
                         "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                         (username,))
        if locked:
            self._record_attempt(username, succeeded=False)
            raise AuthenticationError(
                "Too many failed attempts. Please wait a few minutes and try again."
            )
        ok = bool(record) and record["active"] == 1 and security.verify_password(
            password, record["password_hash"]
        )
        if not ok:
            # Recorded in its own transaction: raising inside the login
            # transaction would roll the attempt back and silently disable
            # the lockout protection.
            self._record_attempt(username, succeeded=False)
            if record and record["active"] != 1:
                raise AuthenticationError("This account has been disabled.")
            raise AuthenticationError("Incorrect username or password.")
        with self.db.transaction() as conn:
            if security.needs_rehash(record["password_hash"]):
                new_hash, _ = security.hash_password(password)
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                             (new_hash, record["id"]))
            conn.execute("UPDATE users SET last_login = ? WHERE id = ?",
                         (now_str(), record["id"]))
            conn.execute("DELETE FROM login_attempts WHERE username = ?", (username,))
            role = row(conn, "SELECT * FROM roles WHERE id = ?", (record["role_id"],))
            perms = self._load_permissions(conn, record["role_id"])
            session = Session(
                user_id=record["id"],
                username=record["username"],
                full_name=record["full_name"] or record["username"],
                role_id=record["role_id"],
                role_name=role["name"] if role else "",
                permissions=perms,
            )
            audit.log(conn, session, audit.LOGIN, entity="users",
                      entity_id=record["id"], description=f"User '{username}' logged in")
            self.session = session
            return session

    def _record_attempt(self, username: str, succeeded: bool) -> None:
        """Persist a login attempt outside the login transaction."""
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO login_attempts(username, succeeded) VALUES (?, ?)",
                    (username, 1 if succeeded else 0),
                )
        except Exception as exc:  # bookkeeping must never break signing in
            log.error("Could not record a login attempt for '%s': %s", username, exc)

    def logout(self) -> None:
        if self.session:
            audit.log_always(self.db, self.session, audit.LOGOUT, entity="users",
                             entity_id=self.session.user_id,
                             description=f"User '{self.session.username}' logged out")
            self.session = None

    # ---------------------------------------------------------------- users
    def list_users(self) -> list[dict]:
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT u.id, u.username, u.full_name, u.email, u.phone, u.active, "
                "u.created_at, u.last_login, u.must_change_password, r.name AS role, r.id AS role_id "
                "FROM users u JOIN roles r ON r.id = u.role_id ORDER BY u.username",
            )

    def get_user(self, user_id: int) -> dict:
        with self.db.read() as conn:
            record = row(conn, "SELECT u.*, r.name AS role FROM users u "
                               "JOIN roles r ON r.id = u.role_id WHERE u.id = ?", (user_id,))
        if not record:
            raise NotFoundError("User not found.")
        return record

    def create_user(self, username: str, password: str, full_name: str, role_id: int,
                    session: Session | None = None, email: str = "", phone: str = "",
                    must_change_password: bool = False) -> int:
        username = (username or "").strip()
        if len(username) < 3:
            raise ValidationError("Username must be at least 3 characters long.")
        security.validate_password_strength(password)
        with self.db.transaction() as conn:
            exists = row(conn, "SELECT id FROM users WHERE username = ? COLLATE NOCASE",
                         (username,))
            if exists:
                raise ConflictError("A user with this username already exists.")
            if not row(conn, "SELECT id FROM roles WHERE id = ?", (role_id,)):
                raise ValidationError("Please select a valid role.")
            password_hash, _ = security.hash_password(password)
            cur = conn.execute(
                "INSERT INTO users(username, password_hash, full_name, role_id, email, phone, "
                "must_change_password) VALUES (?,?,?,?,?,?,?)",
                (username, password_hash, full_name.strip(), role_id, email.strip(),
                 phone.strip(), 1 if must_change_password else 0),
            )
            user_id = int(cur.lastrowid)
            audit.log(conn, session, audit.CREATE, entity="users", entity_id=user_id,
                      description=f"User '{username}' created")
            return user_id

    def update_user(self, user_id: int, full_name: str, role_id: int, active: bool,
                    email: str = "", phone: str = "", session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            current = row(conn, "SELECT * FROM users WHERE id = ?", (user_id,))
            if not current:
                raise NotFoundError("User not found.")
            if session and session.user_id == user_id and not active:
                raise ValidationError("You cannot disable your own account.")
            conn.execute(
                "UPDATE users SET full_name = ?, role_id = ?, active = ?, email = ?, phone = ?, "
                "updated_at = ? WHERE id = ?",
                (full_name.strip(), role_id, 1 if active else 0, email.strip(),
                 phone.strip(), now_str(), user_id),
            )
            audit.log(conn, session, audit.UPDATE, entity="users", entity_id=user_id,
                      description=f"User '{current['username']}' updated")

    def set_password(self, user_id: int, new_password: str,
                     session: Session | None = None, clear_flag: bool = True) -> None:
        security.validate_password_strength(new_password)
        with self.db.transaction() as conn:
            current = row(conn, "SELECT username FROM users WHERE id = ?", (user_id,))
            if not current:
                raise NotFoundError("User not found.")
            password_hash, _ = security.hash_password(new_password)
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ?, "
                "must_change_password = CASE WHEN ? THEN 0 ELSE must_change_password END "
                "WHERE id = ?",
                (password_hash, now_str(), 1 if clear_flag else 0, user_id),
            )
            audit.log(conn, session, audit.UPDATE, entity="users", entity_id=user_id,
                      description=f"Password changed for '{current['username']}'")

    def change_own_password(self, old_password: str, new_password: str) -> None:
        if not self.session:
            raise AuthenticationError("Please log in first.")
        with self.db.transaction() as conn:
            record = row(conn, "SELECT password_hash FROM users WHERE id = ?",
                         (self.session.user_id,))
            if not record or not security.verify_password(old_password, record["password_hash"]):
                raise ValidationError("Your current password is incorrect.")
            password_hash, _ = security.hash_password(new_password)
            conn.execute("UPDATE users SET password_hash = ?, must_change_password = 0, "
                         "updated_at = ? WHERE id = ?",
                         (password_hash, now_str(), self.session.user_id))
            audit.log(conn, self.session, audit.UPDATE, entity="users",
                      entity_id=self.session.user_id, description="Own password changed")

    def delete_user(self, user_id: int, session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            current = row(conn, "SELECT username FROM users WHERE id = ?", (user_id,))
            if not current:
                raise NotFoundError("User not found.")
            if session and session.user_id == user_id:
                raise ValidationError("You cannot delete your own account.")
            used = scalar(conn, "SELECT COUNT(*) FROM sales WHERE user_id = ?", (user_id,), 0)
            if used:
                # never break historical records: disable instead of deleting
                conn.execute("UPDATE users SET active = 0, updated_at = ? WHERE id = ?",
                             (now_str(), user_id))
                audit.log(conn, session, audit.UPDATE, entity="users", entity_id=user_id,
                          description=f"User '{current['username']}' deactivated (has sales history)")
                return
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            audit.log(conn, session, audit.DELETE, entity="users", entity_id=user_id,
                      description=f"User '{current['username']}' deleted")

    # ----------------------------------------------------------------- roles
    def list_roles(self) -> list[dict]:
        with self.db.read() as conn:
            return rows(conn, "SELECT id, name, description, is_system FROM roles ORDER BY name")

    def list_permissions(self) -> list[dict]:
        with self.db.read() as conn:
            return rows(conn, "SELECT id, code, module, description FROM permissions "
                              "ORDER BY module, code")

    def role_permissions(self, role_id: int) -> set[str]:
        with self.db.read() as conn:
            return self._load_permissions(conn, role_id)

    def set_role_permissions(self, role_id: int, permission_codes: set[str],
                             session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            role = row(conn, "SELECT name FROM roles WHERE id = ?", (role_id,))
            if not role:
                raise NotFoundError("Role not found.")
            conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
            conn.execute(
                "INSERT INTO role_permissions(role_id, permission_id) "
                "SELECT ?, id FROM permissions WHERE code IN (%s)"
                % ",".join("?" * max(len(permission_codes), 1)),
                (role_id, *sorted(permission_codes)) if permission_codes else (role_id,),
            )
            audit.log(conn, session, audit.UPDATE, entity="roles", entity_id=role_id,
                      description=f"Permissions updated for role '{role['name']}'",
                      details=", ".join(sorted(permission_codes)))

    def create_role(self, name: str, description: str = "",
                    copy_from: int | None = None,
                    session: Session | None = None) -> int:
        if not name.strip():
            raise ValidationError("Role name is required.")
        with self.db.transaction() as conn:
            if row(conn, "SELECT id FROM roles WHERE name = ? COLLATE NOCASE", (name.strip(),)):
                raise ConflictError("A role with this name already exists.")
            cur = conn.execute("INSERT INTO roles(name, description) VALUES (?,?)",
                               (name.strip(), description.strip()))
            role_id = int(cur.lastrowid)
            if copy_from:
                conn.execute(
                    "INSERT INTO role_permissions(role_id, permission_id) "
                    "SELECT ?, permission_id FROM role_permissions WHERE role_id = ?",
                    (role_id, copy_from),
                )
            audit.log(conn, session, audit.CREATE, entity="roles", entity_id=role_id,
                      description=f"Role '{name}' created")
            return role_id

    # ----------------------------------------------------------- validation
    def has_user(self) -> bool:
        with self.db.read() as conn:
            return scalar(conn, "SELECT COUNT(*) FROM users", [], 0) > 0
