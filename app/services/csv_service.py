"""CSV import / export for products, inventory, sales, customers and suppliers."""
from __future__ import annotations

import csv
from pathlib import Path

from ..core import audit
from ..core.db import rows, now_str
from ..core.exceptions import ValidationError
from ..core.money import from_minor, to_minor, to_decimal
from ..core.security import Session

PRODUCT_COLUMNS = [
    "Product Name", "SKU", "Barcode", "Category", "Brand", "Unit",
    "Purchase Price", "Selling Price", "Stock", "Minimum Stock", "Supplier",
    "Description",
]
REQUIRED_COLUMNS = ["Product Name", "Selling Price"]


def _write_csv(path: str | Path, columns: list[str], data: list[dict],
               mapper=None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for record in data:
            if mapper:
                writer.writerow(mapper(record))
            else:
                writer.writerow([record.get(col, "") for col in columns])
    return path


class CsvService:
    def __init__(self, db, catalog, inventory, settings, session: Session | None = None):
        self.db = db
        self.catalog = catalog
        self.inventory = inventory
        self.settings = settings
        self.session = session

    # -------------------------------------------------------------- export
    def export_products(self, path: str | Path) -> Path:
        data = self.catalog.all_for_export()

        def mapper(r):
            return [
                r["name"], r["sku"] or "", r["barcode"] or "", r["category"] or "",
                r["brand"] or "", r["unit"] or "",
                f"{from_minor(r['purchase_price']):.2f}",
                f"{from_minor(r['selling_price']):.2f}",
                f"{float(r['stock']):g}", f"{float(r['min_stock']):g}",
                r["supplier"] or "", r["description"] or "",
            ]

        return _write_csv(path, PRODUCT_COLUMNS, data, mapper)

    def export_inventory(self, path: str | Path) -> Path:
        data = self.inventory.list_inventory(limit=100000)
        columns = ["Product Name", "SKU", "Barcode", "Category", "Stock",
                   "Minimum Stock", "Purchase Price", "Selling Price", "Stock Value",
                   "Status"]

        def mapper(r):
            return [r["name"], r["sku"] or "", r["barcode"] or "", r["category"] or "",
                    f"{float(r['stock']):g}", f"{float(r['min_stock']):g}",
                    f"{from_minor(r['purchase_price']):.2f}",
                    f"{from_minor(r['selling_price']):.2f}",
                    f"{from_minor(r['stock_value']):.2f}", r["status"]]

        return _write_csv(path, columns, data, mapper)

    def export_sales(self, path: str | Path, date_from: str, date_to: str) -> Path:
        with self.db.read() as conn:
            data = rows(
                conn,
                "SELECT s.invoice_no, s.created_at, s.cashier_name, "
                "COALESCE(cu.name,'Walk-in Customer') AS customer, s.subtotal, "
                "s.item_discount, s.bill_discount, s.total, s.paid, s.change_due, "
                "s.payment_method, s.status FROM sales s "
                "LEFT JOIN customers cu ON cu.id = s.customer_id "
                "WHERE date(s.created_at) >= date(?) AND date(s.created_at) <= date(?) "
                "ORDER BY s.id DESC",
                (date_from, date_to),
            )
        columns = ["Invoice", "Date", "Cashier", "Customer", "Subtotal", "Item Discount",
                   "Bill Discount", "Total", "Paid", "Change", "Payment Method", "Status"]

        def mapper(r):
            return [r["invoice_no"], r["created_at"], r["cashier_name"], r["customer"],
                    f"{from_minor(r['subtotal']):.2f}", f"{from_minor(r['item_discount']):.2f}",
                    f"{from_minor(r['bill_discount']):.2f}", f"{from_minor(r['total']):.2f}",
                    f"{from_minor(r['paid']):.2f}", f"{from_minor(r['change_due']):.2f}",
                    r["payment_method"], r["status"]]

        return _write_csv(path, columns, data, mapper)

    def export_customers(self, path: str | Path) -> Path:
        with self.db.read() as conn:
            data = rows(conn, "SELECT name, phone, whatsapp, address, email, notes, "
                              "created_at FROM customers ORDER BY name")
        columns = ["Name", "Phone", "WhatsApp", "Address", "Email", "Notes", "Created"]
        return _write_csv(path, columns, data)

    def export_suppliers(self, path: str | Path) -> Path:
        with self.db.read() as conn:
            data = rows(conn, "SELECT name, company, phone, whatsapp, address, email, notes "
                              "FROM suppliers ORDER BY name")
        columns = ["Name", "Company", "Phone", "WhatsApp", "Address", "Email", "Notes"]
        return _write_csv(path, columns, data)

    def export_rows(self, path: str | Path, columns: list[str], data: list[dict]) -> Path:
        return _write_csv(path, columns, data)

    # -------------------------------------------------------------- import
    def preview_import(self, path: str | Path) -> dict:
        """Validate a product CSV and return a preview - nothing is written."""
        path = Path(path)
        if not path.exists():
            raise ValidationError("The selected CSV file does not exist.")
        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    raise ValidationError("The CSV file has no header row.")
                header = [h.strip() for h in reader.fieldnames if h]
                missing = [c for c in REQUIRED_COLUMNS if c not in header]
                if missing:
                    raise ValidationError(
                        "The CSV is missing required columns: " + ", ".join(missing)
                    )
                raw_rows = [{(k or "").strip(): (v or "").strip()
                             for k, v in r.items() if k} for r in reader]
        except UnicodeDecodeError as exc:
            raise ValidationError("The file is not a valid text (CSV) file.") from exc

        seen_barcodes: set[str] = set()
        valid, errors = [], []
        for index, record in enumerate(raw_rows, start=2):
            problems = []
            name = record.get("Product Name", "").strip()
            if not name:
                problems.append("Product Name is required")
            try:
                selling = to_minor(record.get("Selling Price") or 0)
            except ValidationError:
                selling = -1
            if selling < 0:
                problems.append("Selling Price is not a valid amount")
            try:
                purchase = to_minor(record.get("Purchase Price") or 0)
            except ValidationError:
                purchase = -1
                problems.append("Purchase Price is not a valid amount")
            barcode = record.get("Barcode", "").strip()
            if barcode and barcode.lower() in seen_barcodes:
                problems.append("Duplicate barcode inside the file")
            elif barcode and self.catalog.barcode_exists(barcode):
                problems.append("Barcode already used by an existing product")
            if barcode:
                seen_barcodes.add(barcode.lower())
            try:
                stock = float(record.get("Stock") or 0)
            except ValueError:
                stock = -1
                problems.append("Stock is not a number")
            try:
                min_stock = float(record.get("Minimum Stock") or 0)
            except ValueError:
                min_stock = 0
                problems.append("Minimum Stock is not a number")
            entry = {
                "row": index,
                "name": name,
                "sku": record.get("SKU", "").strip(),
                "barcode": barcode,
                "category": record.get("Category", "").strip(),
                "brand": record.get("Brand", "").strip(),
                "unit": record.get("Unit", "").strip(),
                "purchase_price": purchase,
                "selling_price": selling,
                "stock": max(stock, 0),
                "min_stock": max(min_stock, 0),
                "supplier": record.get("Supplier", "").strip(),
                "description": record.get("Description", "").strip(),
                "problems": problems,
            }
            (errors if problems else valid).append(entry)
        return {"total": len(raw_rows), "valid": valid, "errors": errors,
                "header": header}

    def commit_import(self, preview: dict, session: Session | None = None) -> dict:
        session = session or self.session
        entries = preview.get("valid") or []
        if not entries:
            raise ValidationError("There are no valid rows to import.")
        created = updated = 0
        with self.db.transaction() as conn:
            for entry in entries:
                category_id = self._lookup(conn, "categories", entry["category"])
                brand_id = self._lookup(conn, "brands", entry["brand"])
                unit_id = self._lookup(conn, "units", entry["unit"], "name")
                supplier_id = self._lookup(conn, "suppliers", entry["supplier"])
                existing = None
                if entry["barcode"]:
                    existing = conn.execute(
                        "SELECT id FROM products WHERE barcode = ? COLLATE NOCASE",
                        (entry["barcode"],)).fetchone()
                elif entry["sku"]:
                    existing = conn.execute(
                        "SELECT id FROM products WHERE sku = ? COLLATE NOCASE",
                        (entry["sku"],)).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE products SET name=?, category_id=?, brand_id=?, unit_id=?, "
                        "supplier_id=?, purchase_price=?, selling_price=?, min_stock=?, "
                        "description=?, updated_at=? WHERE id=?",
                        (entry["name"], category_id, brand_id, unit_id, supplier_id,
                         entry["purchase_price"], entry["selling_price"],
                         entry["min_stock"], entry["description"], now_str(),
                         existing["id"]),
                    )
                    updated += 1
                else:
                    cur = conn.execute(
                        "INSERT INTO products(name, sku, barcode, category_id, brand_id, "
                        "unit_id, supplier_id, purchase_price, selling_price, min_stock, "
                        "description) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (entry["name"], entry["sku"] or None, entry["barcode"] or None,
                         category_id, brand_id, unit_id, supplier_id,
                         entry["purchase_price"], entry["selling_price"],
                         entry["min_stock"], entry["description"]),
                    )
                    product_id = int(cur.lastrowid)
                    conn.execute("INSERT INTO inventory(product_id, quantity) VALUES (?,?)",
                                 (product_id, entry["stock"]))
                    if entry["stock"]:
                        conn.execute(
                            "INSERT INTO stock_movements(product_id, movement, "
                            "quantity_change, quantity_after, reference_type, username, note) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (product_id, "import", entry["stock"], entry["stock"],
                             "import", session.username if session else "",
                             "Imported from CSV"),
                        )
                    created += 1
            audit.log(conn, session, audit.IMPORT, entity="products",
                      description=f"CSV import completed: {created} created, "
                                  f"{updated} updated")
        return {"created": created, "updated": updated}

    @staticmethod
    def _lookup(conn, table: str, name: str, column: str = "name") -> int | None:
        name = (name or "").strip()
        if not name:
            return None
        record = conn.execute(
            f"SELECT id FROM {table} WHERE {column} = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if record:
            return int(record[0])
        cur = conn.execute(f"INSERT INTO {table}({column}) VALUES (?)", (name,))
        return int(cur.lastrowid)
