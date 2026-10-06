"""Application logging (technical troubleshooting only - no secrets)."""
from __future__ import annotations

import logging
import traceback
from logging.handlers import RotatingFileHandler

from .. import config

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configured = False


def setup_logging() -> logging.Logger:
    global _configured
    root = logging.getLogger("alshan")
    if _configured:
        return root
    root.setLevel(logging.DEBUG)
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        config.LOG_DIR / "app.log",
        maxBytes=1_500_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.setLevel(logging.DEBUG)
    root.addHandler(handler)
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)
    _configured = True
    root.info("ALSHAN POS SYSTEM %s started", config.APP_VERSION)
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"alshan.{name}")


def log_exception(logger: logging.Logger, message: str, exc: BaseException) -> None:
    """Log an unexpected exception with stack trace (never shown to users)."""
    logger.error("%s: %s\n%s", message, exc, traceback.format_exc())
