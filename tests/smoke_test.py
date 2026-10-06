"""End-to-end smoke test of the business layer (no UI).

Run:  python tests/smoke_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="alshan_test_"))
os.environ["ALSHAN_DATA_DIR"] = str(TMP)

from app import config  # noqa: E402
from app.core.db import Database  # noqa: E402
from app.services.settings_service import SettingsService  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.services.catalog_service import CatalogService  # noqa: E402
from app.services.inventory_service import InventoryService  # noqa: E402
from app.services.sale_service import SaleService, compute_totals  # noqa: E402
from app.services.purchase_service import PurchaseService  # noqa: E402
from app.services.return_service import ReturnService  # noqa: E402
from app.services.customer_service import CustomerService  # noqa: E402
from app.services.supplier_service import SupplierService  # noqa: E402
from app.services.expense_service import ExpenseService  # noqa: E402
from app.services.report_service import ReportService  # noqa: E402
from app.services.dashboard_service import DashboardService  # noqa: E402
from app.services.backup_service import BackupService  # noqa: E402
from app.services.csv_service import CsvService  # noqa: E402
from app.services.receipt_service import ReceiptService  # noqa: E402
from app.core.exceptions import AppError, StockError, ValidationError  # noqa: E402

checks: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    checks.append((name, bool(condition), detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def main() -> int:
    db = Database(config.DB_PATH)
    db.initialize(create_default_admin=True)
    check("database created", config.DB_PATH.exists(), str(config.DB_PATH))

    settings = SettingsService(db)
    settings.set_many({"shop.name": "Alshan General Store",
                       "currency": "PKR",
                       "setup_completed": "1"})
    check("settings seeded", settings.currency == "PKR")

    auth = AuthService(db, settings)
    session = auth.login("admin", "admin")
    check("default admin login", session.role_name == "Administrator")

    catalog = CatalogService(db, settings, session)
    inventory = InventoryService(db, settings, session)
    customers = CustomerService(db, session)
    suppliers = SupplierService(db, session)
    expenses = ExpenseService(db, session)
    sales = SaleService(db, settings, inventory, session)
    purchases = PurchaseService(db, settings, inventory, session)
    returns = ReturnService(db, settings, inventory, session)
    reports = ReportService(db, settings, expenses, purchases)
    dashboard = DashboardService(db, settings, reports, inventory, expenses)
    backup = BackupService(db, settings, session)
    csvs = CsvService(db, catalog, inventory, settings, session)
    receipts = ReceiptService(db, settings)

    # --- categories / suppliers / customers -----------------------------
    cat_id = catalog.save_category("Grocery", session=session)
    sup_id = suppliers.create({"name": "Metro Distributors", "phone": "0300-1234567"},
                              session)
    cust_id = customers.create({"name": "Ali Khan", "phone": "0321-9999999"}, session)
    check("reference records created", bool(cat_id and sup_id and cust_id))

    # --- products --------------------------------------------------------
    p1 = catalog.create({
        "name": "Milk 1L", "sku": "MILK-1L", "barcode": "8901234567890",
        "category_id": cat_id, "supplier_id": sup_id,
        "purchase_price": 180, "selling_price": 220,
        "min_stock": 10, "opening_stock": 24,
    }, session)
    p2 = catalog.create({
        "name": "Sugar 1kg", "sku": "SUG-1K", "barcode": "8901234567891",
        "category_id": cat_id, "purchase_price": 120, "selling_price": 150,
        "min_stock": 5, "opening_stock": 3,
    }, session)
    check("products created", p1 > 0 and p2 > 0)

    found = catalog.find_by_barcode("8901234567890")
    check("barcode lookup", found is not None and found["name"] == "Milk 1L")
    check("unknown barcode returns None", catalog.find_by_barcode("0000000000000") is None)
    check("initial stock", inventory.stock_of(p1) == 24)

    # --- sale ------------------------------------------------------------
    cart = {
        "customer_id": cust_id,
        "payment_method": "Cash",
        "paid": 100000,          # minor units = PKR 1,000.00
        "bill_discount_type": "Percentage",
        "bill_discount_value": 5,
        "items": [
            {"product_id": p1, "quantity": 2, "unit_price": 22000,
             "discount_type": "None", "discount_value": 0},
            {"product_id": p2, "quantity": 1, "unit_price": 15000,
             "discount_type": "Fixed", "discount_value": 1000},
        ],
    }
    totals = compute_totals(cart["items"], cart["bill_discount_type"],
                            cart["bill_discount_value"])
    expected_total = (2 * 22000 + 15000 - 1000) - int((2 * 22000 + 15000 - 1000) * 0.05)
    check("totals computed", totals["total"] == expected_total,
          f"{totals['total']} vs {expected_total}")

    detail = sales.complete_sale(cart, session)
    check("sale completed", detail["invoice_no"].startswith("ALS-"), detail["invoice_no"])
    check("stock deducted", inventory.stock_of(p1) == 22 and inventory.stock_of(p2) == 2)
    check("change calculated", detail["change_due"] == 100000 - expected_total)
    check("payment recorded", len(detail["payments"]) == 1)

    # insufficient stock must fail and roll back
    try:
        sales.complete_sale({"payment_method": "Cash", "paid": 10000000,
                             "items": [{"product_id": p2, "quantity": 99,
                                        "unit_price": 15000, "discount_type": "None",
                                        "discount_value": 0}]}, session)
        check("insufficient stock rejected", False)
    except StockError:
        check("insufficient stock rejected", True)

    try:
        sales.complete_sale({"payment_method": "Cash", "paid": 1,
                             "items": [{"product_id": p1, "quantity": 1,
                                        "unit_price": 22000, "discount_type": "None",
                                        "discount_value": 0}]}, session)
        check("underpayment rejected", False)
    except ValidationError:
        check("underpayment rejected", True)

    check("failed sale did not change stock", inventory.stock_of(p2) == 2)

    # --- invoice uniqueness ---------------------------------------------
    numbers = [detail["invoice_no"]]
    for _ in range(3):
        numbers.append(sales.complete_sale(
            {"payment_method": "Cash", "paid": 22000,
             "items": [{"product_id": p1, "quantity": 1, "unit_price": 22000,
                        "discount_type": "None", "discount_value": 0}]},
            session)["invoice_no"])
    check("invoice numbers unique", len(set(numbers)) == len(numbers), ",".join(numbers))

    # --- return ----------------------------------------------------------
    sale_full = sales.get_sale_detail(detail["id"])
    ret = returns.create_return(detail["id"],
                                [{"sale_item_id": sale_full["items"][0]["id"],
                                  "quantity": 1}],
                                reason="Damaged pack", session=session)
    check("return processed", ret["return_no"].startswith("RET"))
    check("stock restored by return", inventory.stock_of(p1) == 20,
          str(inventory.stock_of(p1)))
    updated = sales.get_sale_detail(detail["id"])
    check("sale marked partially returned", updated["status"] == "partially_returned")

    # --- purchase --------------------------------------------------------
    purchase = purchases.create_purchase(
        sup_id,
        [{"product_id": p1, "quantity": 48, "unit_price": 185}],
        paid=4000, discount=0, notes="Weekly order", session=session)
    check("purchase recorded", purchase["purchase_no"].startswith("PUR"))
    check("purchase increased stock", inventory.stock_of(p1) == 68,
          str(inventory.stock_of(p1)))
    check("purchase balance", purchase["balance"] == 48 * 18500 - 400000,
          str(purchase["balance"]))

    # --- stock adjustment ------------------------------------------------
    inventory.adjust(p2, 10, "Manual correction", session, note="Recount")
    check("stock adjustment", inventory.stock_of(p2) == 10)
    check("movement history", len(inventory.movements(p2)) >= 2)

    # --- product update / price change audit ----------------------------
    sugar = catalog.get(p2)
    sugar["selling_price"] = 160
    catalog.update(p2, sugar, session)
    check("product updated", catalog.get(p2)["selling_price"] == 16000)

    # --- expense ---------------------------------------------------------
    expense_id = expenses.create({"title": "Shop rent", "category": "Rent",
                                  "amount": 25000, "expense_date": "2026-10-01"},
                                 session)
    check("expense recorded", expense_id > 0)

    # --- reports ---------------------------------------------------------
    summary = reports.sales_summary("2026-01-01", "2026-12-31")
    check("sales report", summary["transactions"] >= 4 and summary["total"] > 0,
          f"txns={summary['transactions']} total={summary['total']}")
    profit = reports.profit_report("2026-01-01", "2026-12-31")
    check("gross profit computed", isinstance(profit["gross_profit"], int))
    check("net profit includes expenses",
          profit["net_profit"] == profit["gross_profit"] - profit["expenses"])
    check("product report", len(reports.product_sales("2026-01-01", "2026-12-31")) >= 2)
    check("cashier report", len(reports.cashier_performance("2026-01-01", "2026-12-31")) >= 1)
    check("inventory report", len(reports.inventory_report()) == 2)

    stats = dashboard.stats()
    check("dashboard figures", stats["today_transactions"] >= 4 and
          stats["products_total"] == 2, str(stats["today_transactions"]))

    # --- void ------------------------------------------------------------
    void_id = sales.get_by_invoice(numbers[-1])["id"]
    sales.void_sale(void_id, "Wrong items", session)
    voided = sales.get_sale_detail(void_id)
    check("sale voided", voided["status"] == "voided")

    # --- users / permissions --------------------------------------------
    auth.create_user("cashier1", "cashier123", "Nadia", 2, session)
    cashier = auth.login("cashier1", "cashier123")
    check("cashier login", cashier.role_name == "Cashier" and not cashier.is_admin)
    check("cashier permission set", cashier.can("sales.create") and
          not cashier.can("database.restore"))
    try:
        sales.void_sale(detail["id"], "nope", cashier)
        check("cashier cannot void", False)
    except AppError:
        check("cashier cannot void", True)

    # --- backup / restore ------------------------------------------------
    target = backup.create_backup(TMP / "backups", kind="manual")
    check("backup created", target.exists() and target.stat().st_size > 0)
    info = backup.validate_backup(target)
    check("backup validated", info["ok"] and info["counts"]["products"] == 2)
    result = backup.restore(target, session)
    check("restore completed", Path(result["restored"]).exists())
    check("db still queryable after restore", dashboard.stats()["products_total"] == 2)

    # --- csv -------------------------------------------------------------
    csv_path = csvs.export_products(TMP / "products.csv")
    check("csv export", csv_path.exists() and csv_path.stat().st_size > 0)
    csv_path.write_text("Product Name,Selling Price\nNew Item,99.50\n,Broken\n",
                        encoding="utf-8")
    preview = csvs.preview_import(csv_path)
    check("csv preview validates", preview["total"] == 2 and len(preview["valid"]) == 1)
    imported = csvs.commit_import(preview, session)
    check("csv import commits", imported["created"] == 1)
    check("imported product searchable",
          catalog.search("New Item")[0]["name"] == "New Item")

    # --- receipt ---------------------------------------------------------
    html_text = receipts.receipt_html(sales.get_sale_detail(detail["id"]))
    check("receipt html built", "ALS-" in html_text and "TOTAL" in html_text)
    check("test receipt built", "ALS-TEST-0001" in receipts.test_receipt_html())

    # --- audit -----------------------------------------------------------
    from app.core.db import rows
    with db.read() as conn:
        logs = rows(conn, "SELECT * FROM audit_logs ORDER BY id")
    actions = {r["action"] for r in logs}
    check("audit log populated", {"LOGIN", "CREATE", "UPDATE", "VOID", "RETURN"} <= actions,
          ",".join(sorted(actions)))

    # --- settings survive reopen ----------------------------------------
    settings2 = SettingsService(db)
    check("settings persist", settings2.get("shop.name") == "Alshan General Store")

    failed = [c for c in checks if not c[1]]
    print("\n" + "=" * 60)
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed")
    if failed:
        for name, _, detail in failed:
            print(f"  FAILED: {name} {detail}")
    print(f"Data directory: {TMP}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
