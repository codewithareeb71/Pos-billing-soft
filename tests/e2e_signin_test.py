"""End-to-end regression test for the reported sign-in failure.

Scenario: fresh install -> setup wizard creates the administrator ->
sign-in page with correct credentials -> main window must open.

Regression covered: with PySide6 6.11 `login.Accepted` (instance attribute)
no longer exists, so a *successful* sign-in crashed in app/main.py and no
page ever opened.

Run:  python tests/e2e_signin_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="alshan_e2e_"))
os.environ["ALSHAN_DATA_DIR"] = str(TMP)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QWizard  # noqa: E402

from app import config  # noqa: E402
from app.context import AppContext  # noqa: E402
from app.ui import theme  # noqa: E402

checks: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    checks.append((name, bool(condition), detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}"
          + (f"  [{detail}]" if detail else ""))


USERNAME = "shopowner"
PASSWORD = "till2026"


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(config.APP_SHORT_NAME)
    theme.apply_theme(app)

    ctx = AppContext()
    check("fresh database created", ctx.needs_setup or ctx.needs_user)

    # ---------------------------------------------------- setup wizard
    from app.ui.setup_wizard import SetupWizard

    wizard = SetupWizard(ctx)
    wizard.shop_page.name.setText("Alshan General Store")
    wizard.shop_page.phone.setText("0300-0000000")
    wizard.admin_page.username.setText(USERNAME)
    wizard.admin_page.password.setText(PASSWORD)
    wizard.admin_page.confirm.setText(PASSWORD)
    check("wizard admin page validates", wizard.admin_page.validate())
    wizard.accept()                      # the exact code the Finish button runs
    check("wizard completed", not ctx.needs_setup)
    check("administrator exists", ctx.auth.has_user())

    # ------------------------------------------------------- sign-in page
    from app.ui.login_page import LoginDialog

    dialog = LoginDialog(ctx)
    dialog.username.setText(USERNAME)
    dialog.password.setText(PASSWORD)
    dialog.attempt_login()

    # this is the exact comparison app/main.py performs
    check("main.py comparison sees an accepted sign-in",
          dialog.result() == QDialog.DialogCode.Accepted,
          f"result={dialog.result()}")
    check("sign-in dialog accepted (no crash, no error label)",
          dialog.error.isHidden() and dialog.login_button.isEnabled())

    session = ctx.session
    check("session attached to the context",
          session is not None and session.username == USERNAME
          and session.is_admin, session.username if session else "None")

    # ---------------------------------------------------------- main window
    from app.ui.main_window import MainWindow

    window = MainWindow(ctx)
    window.show()
    app.processEvents()
    check("main window opens after sign-in", window.isVisible())
    window.show_page("dashboard")
    app.processEvents()
    check("dashboard loads", "dashboard" in window.pages)
    window.show_page("pos")
    app.processEvents()
    check("pos loads", "pos" in window.pages)
    window._force_close = True        # skip the modal "Exit?" confirmation
    window.close()

    # wizard enum used by run_setup must also be present
    check("QWizard dialog code available",
          QWizard.DialogCode.Accepted == QDialog.DialogCode.Accepted)

    passed = sum(1 for _n, ok, _d in checks if ok)
    total = len(checks)
    print("\n" + "=" * 60)
    print(f"E2E SIGN-IN TEST: {passed}/{total} checks passed")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
