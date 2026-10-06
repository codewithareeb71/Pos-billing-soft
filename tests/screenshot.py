"""Dev tool: capture screenshots of the main screens (off-screen).

Run:  python tests/screenshot.py [output_folder]
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="alshan_shots_"))
os.environ["ALSHAN_DATA_DIR"] = str(TMP)
# Capture with the native platform so real fonts are used; export
# QT_QPA_PLATFORM=offscreen manually when running on a headless machine.

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import config  # noqa: E402
from app.context import AppContext  # noqa: E402
from app.ui import theme  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "screenshots"
    out.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    theme.apply_theme(app)

    ctx = AppContext()
    ctx.db.initialize(create_default_admin=True)
    ctx.settings.set_many({
        "shop.name": "Alshan General Store",
        "shop.address": "Main Bazaar, Rawalpindi",
        "shop.phone": "051-4567890",
        "setup_completed": "1",
    })
    ctx.login("admin", "admin")

    supplier = ctx.suppliers.create({"name": "Karachi Traders", "phone": "03001112223"})
    customer = ctx.customers.create({"name": "Bilal Ahmed", "phone": "03001234567",
                                     "address": "Street 4"})
    products = [
        ("Green Tea 250g", 450, 360, 40, 10),
        ("Milk 1L", 220, 190, 25, 12),
        ("Sugar 1kg", 160, 140, 60, 20),
        ("Basmati Rice 5kg", 2450, 2200, 18, 5),
        ("Dish Wash 500ml", 320, 250, 30, 8),
    ]
    ids = []
    beverages = ctx.catalog.save_category("Beverages")
    grocery = ctx.catalog.save_category("Grocery")
    for index, (name, price, cost, stock, minimum) in enumerate(products):
        ids.append(ctx.catalog.create({
            "name": name,
            "barcode": f"629100000{index:04d}",
            "purchase_price": cost,
            "selling_price": price,
            "opening_stock": stock,
            "min_stock": minimum,
            "supplier_id": supplier,
            "category_id": beverages if index < 3 else grocery,
        }))

    cart = {"items": [{"product_id": ids[0], "quantity": 2,
                       "unit_price": ctx.catalog.get(ids[0])["selling_price"]}],
            "bill_discount_type": "Percentage", "bill_discount_value": 5,
            "customer_id": customer, "payment_method": "Cash", "paid": 100000}
    ctx.sales.complete_sale(cart)
    cart["items"] = [{"product_id": ids[3], "quantity": 1,
                      "unit_price": ctx.catalog.get(ids[3])["selling_price"]}]
    cart["paid"] = 300000
    ctx.sales.complete_sale(cart)
    ctx.purchases.create_purchase(supplier,
                                  [{"product_id": ids[1], "quantity": 48,
                                    "unit_price": 190}], paid=4000)
    ctx.expenses.create({"title": "Shop rent October", "category": "Rent",
                         "amount": 25000, "expense_date": "2026-10-01"})

    from app.ui.main_window import MainWindow

    window = MainWindow(ctx)
    window.resize(1366, 768)
    window.show()

    # put a couple of lines into the POS cart for the screenshot
    window.show_page("pos")
    pos = window.pages["pos"]
    pos.refresh_categories()
    pos.refresh_products()
    pos.refresh_customers()
    pos.scan(ctx.catalog.get(ids[0])["barcode"])
    pos.scan(ctx.catalog.get(ids[1])["barcode"])
    pos.cart_table.selectRow(0)

    captured = []
    for key in ("dashboard", "pos", "products", "inventory", "reports",
                "sales", "settings"):
        window.show_page(key)
        app.processEvents()
        window.toast.hide()
        app.processEvents()
        path = out / f"{key}.png"
        window.grab().save(str(path))
        captured.append(path)

    for path in captured:
        print(f"OK  {path}")

    # ------------------------------------------------------ dialogs (extra)
    from app.ui.login_page import LoginDialog
    from app.ui.setup_wizard import SetupWizard

    login = LoginDialog(ctx)
    login.grab().save(str(out / "login.png"))
    wizard = SetupWizard(ctx)
    wizard.show()
    app.processEvents()
    wizard.grab().save(str(out / "wizard.png"))
    wizard.close()
    print(f"OK  {out / 'login.png'}")
    print(f"OK  {out / 'wizard.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
