"""Safe money handling.

All monetary values are stored in the database as INTEGER minor units
(paisa / cents) - never as floating point numbers - so every SUM, AVG and
report aggregation is exact.  `Decimal` is used for parsing user input.
"""
from __future__ import annotations

import decimal
from decimal import Decimal, ROUND_HALF_UP

from .exceptions import ValidationError

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0")

_PARSE_CLEAN = decimal.Decimal


def to_decimal(value) -> Decimal:
    """Convert str / int / float / Decimal into an exact Decimal."""
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return ZERO
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # floats only arrive from external files: go through repr for safety
        return Decimal(repr(value))
    text = str(value).strip().replace(",", "")
    if not text:
        return ZERO
    try:
        return Decimal(text)
    except decimal.InvalidOperation as exc:
        raise ValidationError("Invalid amount entered.") from exc


def to_minor(value) -> int:
    """Convert any money-like value into integer minor units (x100)."""
    amount = to_decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return int(amount * 100)


def from_minor(minor: int | None) -> Decimal:
    """Convert integer minor units back into Decimal major units."""
    if minor is None:
        return ZERO
    return (Decimal(int(minor)) / 100).quantize(TWO_PLACES)


def parse_input(text: str, field: str = "Amount") -> int:
    """Parse a QLineEdit value into minor units, rejecting garbage input."""
    raw = (text or "").strip()
    if not raw:
        return 0
    cleaned = raw.replace(",", "").replace(" ", "")
    try:
        value = Decimal(cleaned)
    except decimal.InvalidOperation:
        raise ValidationError(f"{field} must be a number.") from None
    if value < 0:
        raise ValidationError(f"{field} cannot be negative.")
    return to_minor(value)


def add_minor(*values) -> int:
    return sum(int(v or 0) for v in values)


def apply_percent(amount_minor: int, percent) -> int:
    """amount * percent / 100 rounded to minor units."""
    pct = to_decimal(percent)
    if pct < 0:
        raise ValidationError("Discount percentage cannot be negative.")
    result = (Decimal(int(amount_minor)) * pct / 100).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(result)


def format_minor(minor: int | None, currency: str = "PKR", with_symbol: bool = True) -> str:
    """Format minor units for display: 'PKR 2,500.00'."""
    amount = from_minor(minor)
    text = f"{amount:,.2f}"
    if with_symbol and currency:
        return f"{currency} {text}"
    return text


def format_number(minor: int | None) -> str:
    """Plain number without currency symbol."""
    return f"{from_minor(minor):,.2f}"


def change_due(total_minor: int, paid_minor: int) -> int:
    return int(paid_minor) - int(total_minor)
