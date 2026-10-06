"""ALSHAN POS SYSTEM - application entry point.

Start-up order:
    theme -> application context (database + services) -> automatic backup
    -> first-run setup wizard -> sign in -> main window (until sign out).
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

from . import config

# Keeps the process-wide single-instance lock alive (a collected QLockFile
# releases the lock automatically).
_KEEP_ALIVE: dict[str, object] = {}


def _single_instance_guard():
    """Keep one till open per user: a second launch focuses on the first."""
    from PySide6.QtCore import QLockFile

    lock = QLockFile(str(config.DATA_DIR / "alshan_pos.lock"))
    if lock.tryLock(120):
        _KEEP_ALIVE["lock"] = lock   # GC would release the lock otherwise
        return lock, None
    # Another process is holding the lock. If it crashed and left the lock
    # file behind, remove it and try once more before giving up.
    lock_path = Path(config.DATA_DIR / "alshan_pos.lock")
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        age = 0.0
    if age > 120:
        lock.removeStaleLockFile()
        if lock.tryLock(120):
            _KEEP_ALIVE["lock"] = lock
            return lock, None
    return None, (
        "ALSHAN POS SYSTEM is already running on this computer.\n\n"
        "Switch to the open window, or close it first and try again.")


def _install_excepthook():
    """Route unexpected errors to the log, never to a raw traceback window."""
    from .core.logging_setup import get_logger, log_exception

    log = get_logger("app")
    sys.excepthook = lambda exc_type, exc, tb: (  # noqa: E731
        log_exception(log, "Unhandled error", exc),
        traceback.print_exception(exc_type, exc, tb),
        None)[-1]


def main() -> int:
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

    from .core.logging_setup import get_logger, log_exception, setup_logging
    from .ui import theme

    setup_logging()
    log = get_logger("app")
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_SHORT_NAME)
    app.setOrganizationName(config.APP_VENDOR)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setWindowIcon(theme.logo_icon(32))
    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    theme.apply_theme(app)

    lock, message = _single_instance_guard()
    if message:
        QMessageBox.warning(None, config.APP_NAME, message)
        return 1
    _install_excepthook()

    # ---------------------------------------------------------- context
    from .context import AppContext
    from .ui.login_page import LoginDialog
    from .ui.main_window import MainWindow
    from .ui.setup_wizard import run_setup

    try:
        ctx = AppContext()
    except Exception as exc:  # pragma: no cover - corrupt/unwritable data dir
        log_exception(log, "Unable to open the database", exc)
        QMessageBox.critical(
            None, config.APP_NAME,
            "The database could not be opened.\n\n"
            f"Location: {config.DB_PATH}\n\n"
            f"Details: {exc}\n\n"
            "Check that the folder is writable and that no other program is "
            "holding the file, then start ALSHAN POS SYSTEM again.")
        return 2

    try:
        ctx.run_startup_tasks()
    except Exception as exc:  # pragma: no cover - never block start-up
        log_exception(log, "Startup tasks failed", exc)

    # ------------------------------------------------------ first run
    try:
        if ctx.needs_setup or ctx.needs_user:
            if not run_setup(ctx):
                log.info("Setup wizard cancelled - exiting.")
                return 0
    except Exception as exc:  # pragma: no cover
        log_exception(log, "Setup wizard failed", exc)
        QMessageBox.critical(None, config.APP_NAME,
                             f"First-time setup failed: {exc}")
        return 3

    # -------------------------------------------------------- sign in
    while True:
        login = LoginDialog(ctx)
        # QDialog.DialogCode.Accepted - the short form (login.Accepted) was
        # removed for instances in PySide6 6.11 and crashed right after a
        # successful sign-in.
        if login.exec() != QDialog.DialogCode.Accepted:
            log.info("Sign in cancelled - exiting.")
            return 0
        try:
            window = MainWindow(ctx)
        except Exception as exc:  # pragma: no cover
            log_exception(log, "Main window failed to open", exc)
            QMessageBox.critical(
                None, config.APP_NAME,
                "The main window could not be opened.\n\n"
                "Check the log file for details:\n"
                f"{config.LOG_DIR}")
            try:
                ctx.logout()
            except Exception:  # pragma: no cover
                pass
            continue

        window.show()
        app.exec()
        try:
            ctx.logout()
        except Exception as exc:  # pragma: no cover
            log_exception(log, "Sign out failed", exc)
        if not getattr(window, "logout_requested", False):
            return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
