"""Domain exceptions.

Every exception carries a message that is safe to show to an end user.
Technical details are written to the application log instead.
"""
from __future__ import annotations


class AppError(Exception):
    """Base class for expected, user-facing application errors."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class ValidationError(AppError):
    """Input failed validation."""


class AuthenticationError(AppError):
    """Login failed."""


class PermissionDenied(AppError):
    """The current role is not allowed to perform the operation."""


class NotFoundError(AppError):
    """Requested record does not exist."""


class StockError(AppError):
    """Inventory rule violated (e.g. insufficient stock)."""


class ConflictError(AppError):
    """Unique constraint / duplicate business identifier."""


class DatabaseError(AppError):
    """Database operation failed - the transaction was rolled back."""

    DEFAULT_MESSAGE = (
        "Unable to complete this operation. Your data has not been changed."
    )

    def __init__(self, detail: str = "", message: str = DEFAULT_MESSAGE):
        super().__init__(message, detail)


class BackupError(AppError):
    """Backup / restore failure."""


class PrintError(AppError):
    """Printing failure."""
