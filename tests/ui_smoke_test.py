"""UI smoke test: every screen of ALSHAN POS SYSTEM is built off-screen.

Run:  python tests/ui_smoke_test.py
Uses the Qt offscreen platform so it works on build machines without a display.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="alshan_ui_"))
os.environ["ALSHAN_DATA_DIR"] = str(TMP)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import config  # noqa: E402
from app.context import AppContext  # noqa: E402
from app.ui import theme  # noqa: E402

checks: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    checks.append((name, bool(condition), detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}"
          + (f"  [{detail}]" if detail else ""))


def run(name: str, fn) -> bool:
    """Execute a UI step and record a PASS/FAIL instead of crashing."""
    try:
        fn()
        check(name, True)
        return True
    except Exception as exc:  # noqa: BLE001 - the point of the test
        detail = f"{type(exc).__name__}: {exc}"
        print(f"      {detail}")
        traceback.print_exc()
        check(name, False, detail)
        return False


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(config.APP_SHORT_NAME)
    theme.apply_theme(app)

    # ------------------------------------------------------------- context
    ctx = AppContext()
    ctx.db.initialize(create_default_admin=True)
    ctx.settings.set_many({
        "shop.name": "Alshan General Store",
        "shop.address": "Main Bazaar",
        "shop.phone": "0300-0000000",
        "currency": "PKR",
        "setup_completed": "1",
    })
    session = ctx.login("admin", "admin")
    check("signed in", ctx.session is not None, session.username)

    # ------------------------------------------------- sign-in regression
    # Regression: with PySide6 6.11 a successful sign-in crashed in main.py
    # ('LoginDialog' object has no attribute 'Accepted'), so correct
    # credentials never opened any page.
    def login_dialog_flow():
        from PySide6.QtWidgets import QDialog

        from app.ui.login_page import LoginDialog

        wrong = LoginDialog(ctx)
        wrong.username.setText("admin")
        wrong.password.setText("definitely-wrong-password")
        wrong.attempt_login()
        assert wrong.result() != QDialog.DialogCode.Accepted, \
            "wrong password must not sign in"
        assert not wrong.error.isHidden(), "error message not shown"
        assert "incorrect" in wrong.error.text().lower(), wrong.error.text()

        good = LoginDialog(ctx)
        good.username.setText("ADMIN")       # case-insensitive now
        good.password.setText("admin")
        good.attempt_login()
        assert good.result() == QDialog.DialogCode.Accepted, \
            "correct credentials must accept the login dialog"

    run("login dialog: wrong rejected / correct accepted", login_dialog_flow)

    product_ids = []

    def seed():
        nonlocal product_ids
        for name, price, stock in (
                ("Green Tea 250g", 450, 40),
                ("Milk 1L", 220, 25),
                ("Sugar 1kg", 160, 60)):
            product_ids.append(ctx.catalog.create({
                "name": name,
                "barcode": f"629100{len(product_ids):06d}",
                "purchase_price": int(price * 0.8),
                "selling_price": price,
                "opening_stock": stock,
            }))
        ctx.customers.create({"name": "Test Customer", "phone": "03001234567"})
        ctx.suppliers.create({"name": "Test Supplier", "phone": "03007654321"})

    run("seed catalogue, customer and supplier", seed)
    check("products created", len(product_ids) == 3)

    # -------------------------------------------------------- main window
    from app.ui.main_window import MainWindow
    from app.ui.pages import _MODULES

    window = None

    def open_window():
        nonlocal window
        window = MainWindow(ctx)
        window.show()
        app.processEvents()

    run("main window opens", open_window)
    if window is None:
        return report()

    # -------------------------------------------------------- every page
    for key, module in _MODULES.items():
        def build(k=key, m=module):
            window.show_page(k)
            app.processEvents()
            page = window.pages.get(k)
            assert page is not None, "page was not built"
            assert type(page).__module__.endswith(m), "wrong module"
        run(f"page: {key}", build)

    # --------------------------------------------------------------- POS
    def pos_flow():
        window.show_page("pos")
        app.processEvents()
        page = window.pages["pos"]
        page.refresh_categories()
        page.refresh_products()
        page.refresh_customers()
        assert page.product_model.rowCount() >= 3, "product list empty"
        barcode = page._products[0]["barcode"]
        page.scan(barcode)
        assert len(page.items) == 1, "scan did not add an item"
        page.scan(barcode)          # second scan increments the quantity
        assert float(page.items[0]["quantity"]) == 2, "quantity not incremented"
        page.cart_table.selectRow(0)
        app.processEvents()
        assert page.totals["total"] > 0, "cart totals are zero"
        page._recompute()
        page.build_cart()
        page.reset_sale()
        assert page.items == [], "cart not cleared"

    run("POS scan / cart / reset", pos_flow)

    def pos_unknown_barcode():
        window.show_page("pos")
        page = window.pages["pos"]
        page.scan("0000000000000")
        assert page.items == [], "unknown barcode must not be added"

    run("POS rejects unknown barcode", pos_unknown_barcode)

    # ----------------------------------------------------------- dialogs
    def dialogs():
        from app.ui.pages.products_page import (BarcodeLabelsDialog, ImportDialog,
                                                ProductDialog)
        from app.ui.pages.customers_page import CustomerDialog
        from app.ui.pages.suppliers_page import SupplierDialog
        from app.ui.pages.expenses_page import ExpenseDialog
        from app.ui.pages.users_page import UserDialog, RoleDialog
        from app.ui.pages.inventory_page import AdjustDialog, MovementsDialog

        product = ctx.catalog.get(product_ids[0])
        assert ProductDialog(ctx, None, product) is not None
        assert CustomerDialog(ctx, None, ctx.customers.search()[0]) is not None
        assert SupplierDialog(ctx, None, ctx.suppliers.search()[0]) is not None
        assert ExpenseDialog(ctx, None) is not None
        assert UserDialog(ctx, None, ctx.auth.list_users()[0]) is not None
        assert RoleDialog(ctx, None) is not None
        assert AdjustDialog(ctx, product) is not None
        assert MovementsDialog(ctx, product) is not None
        assert BarcodeLabelsDialog(ctx, [product]) is not None
        assert ImportDialog(ctx) is not None

    run("editor dialogs build", dialogs)

    def pos_dialogs():
        from app.ui.pages.sales_page import InvoiceDialog, ReturnDialog, VoidDialog
        from app.ui.pages.purchases_page import PurchaseDialog, PurchaseDetailDialog

        cart = {
            "items": [{"product_id": product_ids[0], "quantity": 1,
                       "unit_price": ctx.catalog.get(product_ids[0])["selling_price"]}],
            "bill_discount_type": "None", "bill_discount_value": 0,
            "customer_id": None, "payment_method": "Cash",
            "paid": ctx.catalog.get(product_ids[0])["selling_price"] * 2,
        }
        sale = ctx.sales.complete_sale(cart)
        detail = ctx.sales.get_sale_detail(sale["id"])
        assert InvoiceDialog(ctx, sale["id"], None) is not None
        assert ReturnDialog(ctx, detail, None) is not None
        assert VoidDialog(ctx, detail, None) is not None
        assert PurchaseDialog(ctx, None) is not None
        purchase = ctx.purchases.create_purchase(
            None, [{"product_id": product_ids[1], "quantity": 5,
                    "unit_price": 200}], paid=500)
        assert PurchaseDetailDialog(ctx, purchase["id"], None) is not None

    run("sales / purchase dialogs build", pos_dialogs)

    # --------------------------------------------------------- settings
    def settings_tabs():
        window.show_page("settings")
        app.processEvents()
        page = window.pages["settings"]
        for index in range(page.tabs.count()):
            page.tabs.setCurrentIndex(index)
            app.processEvents()
        page.tabs.setCurrentIndex(0)

    run("settings tabs switch", settings_tabs)

    def scanner_panel():
        from app.ui.pages.settings_page import ScannerTestPanel
        panel = ScannerTestPanel(ctx)
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import Qt, QEvent
        code = ctx.catalog.get(product_ids[0])["barcode"]
        for char in code:
            panel.eventFilter(panel, QKeyEvent(
                QEvent.KeyPress, ord(char.upper()), Qt.NoModifier, char))
        panel.eventFilter(panel, QKeyEvent(
            QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, "\r"))
        assert code in panel.code_label.text(), "scanner panel did not capture the code"

    run("barcode scanner test panel", scanner_panel)

    # ------------------------------------------------------------ reports
    def reports():
        window.show_page("reports")
        app.processEvents()
        page = window.pages["reports"]
        for index in range(page.report_combo.count()):
            page.report_combo.setCurrentIndex(index)
            app.processEvents()
            assert page.status.text(), "report produced no status line"
        page.report_combo.setCurrentIndex(0)

    run("all 14 reports run", reports)

    # ------------------------------------------------------- logout flow
    def navigation_guard():
        for key in list(window.pages):
            window.show_page(key)
            app.processEvents()

    run("revisit every open page", navigation_guard)

    def receipts():
        html = ctx.receipts.test_receipt_html()
        assert "ALSHAN" in html.upper() or "Alshan" in html
        labels = ctx.receipts.labels_html(
            [ctx.catalog.get(product_ids[0])], show_price=True, show_name=True)
        assert labels, "label HTML empty"

    run("receipt and label rendering", receipts)

    return report()


def report() -> int:
    passed = sum(1 for _n, ok, _d in checks if ok)
    total = len(checks)
    print("\n" + "=" * 60)
    print(f"UI SMOKE TEST: {passed}/{total} checks passed")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
