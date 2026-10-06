"""Password hashing and permission checks.

Passwords are never stored or logged in plain text.  The format is:

    pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from .. import config
from .exceptions import ValidationError

SALT_BYTES = 16
DIGEST = hashlib.sha256


def hash_password(password: str, iterations: int | None = None) -> tuple[str, str]:
    """Return (stored_hash, plain_password) - the plain value is only for
    bootstrap flows such as creating a default account; it is never persisted."""
    if not isinstance(password, str) or len(password) < config.MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {config.MIN_PASSWORD_LENGTH} characters long."
        )
    iterations = iterations or config.PASSWORD_HASH_ITERATIONS
    salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(DIGEST().name, password.encode("utf-8"), salt, iterations)
    stored = (
        f"{config.PASSWORD_HASH_ALGORITHM}${iterations}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )
    return stored, password


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of a password against the stored hash."""
    if not password or not stored:
        return False
    try:
        algorithm, iterations, salt_b64, hash_b64 = stored.split("$", 3)
    except ValueError:
        return False
    if algorithm != config.PASSWORD_HASH_ALGORITHM:
        return False
    try:
        iterations_i = int(iterations)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac(DIGEST().name, password.encode("utf-8"), salt, iterations_i)
    return hmac.compare_digest(dk, expected)


def needs_rehash(stored: str) -> bool:
    """True when the stored hash uses fewer iterations than the current policy."""
    try:
        _, iterations, _, _ = stored.split("$", 3)
        return int(iterations) < config.PASSWORD_HASH_ITERATIONS
    except (ValueError, AttributeError):
        return True


def validate_password_strength(password: str) -> None:
    if not password or len(password) < config.MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {config.MIN_PASSWORD_LENGTH} characters long."
        )
    if password.strip() != password:
        raise ValidationError("Password cannot start or end with spaces.")


@dataclass
class Session:
    """Authenticated user context passed to every service."""

    user_id: int
    username: str
    full_name: str
    role_id: int
    role_name: str
    permissions: set[str] = field(default_factory=set)

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def any(self, *permissions: str) -> bool:
        return any(p in self.permissions for p in permissions)

    @property
    def is_admin(self) -> bool:
        return self.role_name.lower() == "administrator"


ANONYMOUS = Session(0, "", "", 0, "", set())


def permission_denied(permission: str):
    from .exceptions import PermissionDenied

    return PermissionDenied(f"You do not have permission to do this ({permission}).")
