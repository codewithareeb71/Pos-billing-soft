"""ALSHAN POS SYSTEM launcher (development and packaged builds).

Run:  python run.py      (or double-click run.bat)

Also acts as the last line of defence: if anything inside the application
raises after start-up, the error is written to the log and shown in a
message box instead of the windowed build closing without any explanation.
"""
from __future__ import annotations

import sys
import traceback


def _report_fatal(exc: BaseException) -> None:
    """Never let the packaged app die silently - explain what happened."""
    try:
        from app import config
        from app.core.logging_setup import get_logger, log_exception

        log_exception(get_logger("app"), "Fatal error", exc)
        detail = f"{type(exc).__name__}: {exc}"
        log_path = f"{config.LOG_DIR}"
        title = config.APP_NAME
    except Exception:  # pragma: no cover - even logging failed
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        detail = str(exc)
        log_path = "(the log file could not be located)"
        title = "ALSHAN POS SYSTEM"

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(
            None,
            title,
            "ALSHAN POS SYSTEM hit an unexpected problem and had to close.\n\n"
            f"{detail}\n\n"
            "A full report was written to:\n"
            f"{log_path}\n\n"
            "Please share that file when asking for help.",
        )
    except Exception:  # pragma: no cover - no Qt, no console in windowed builds
        traceback.print_exception(type(exc), exc, exc.__traceback__)


def _run() -> int:
    from app.main import main

    return int(main())


if __name__ == "__main__":
    try:
        sys.exit(_run())
    except SystemExit:
        raise
    except BaseException as _fatal:  # noqa: BLE001 - last line of defence
        _report_fatal(_fatal)
        sys.exit(97)
