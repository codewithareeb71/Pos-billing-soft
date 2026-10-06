"""Purchase (stock-in) management - automatically increases inventory."""
from __future__ import annotations

from ..core import audit
from ..core.db import now_str, row, rows, scalar
from ..core.exceptions import NotFoundError, ValidationError
from ..core.money import to_minor
from ..core.security import Session
from .inventory_service import InventoryService
from .sale_service import line_gross


class PurchaseService:
    def __init__(self, db, settings, inventory: InventoryService | None = None,
                 session: Session | None = None):
        self.db = db
        self.settings = settings
        self.inventory = inventory or InventoryService(db, settings, session)
        self.session = session

    # ------------------------------------------------------------- create
    def create_purchase(self, supplier_id: int | None, items: list[dict],
                        paid=0, discount=0, purchase_date: str = "",
                        notes: str = "", update_prices: bool = True,
                        session: Session | None = None) -> dict:
        session = session or self.session
        if not items:
            raise ValidationError("Add at least one product to the purchase.")
        subtotal = 0
        clean_items = []
        for entry in items:
            qty = float(entry.get("quantity") or 0)
            price = to_minor(entry.get("unit_price") or 0)
            if qty <= 0:
                raise ValidationError("Purchase quantities must be greater than zero.")
            if price < 0:
                raise ValidationError("Purchase prices cannot be negative.")
            product_id = entry.get("product_id")
            total = line_gross(qty, price)
            subtotal += total
            clean_items.append({"product_id": product_id, "quantity": qty,
                                "unit_price": price, "line_total": total,
                                "name": entry.get("name", "")})
        discount_minor = to_minor(discount)
        if discount_minor > subtotal:
            raise ValidationError("Discount cannot exceed the purchase total.")
        total = subtotal - discount_minor
        paid_minor = to_minor(paid)
        if paid_minor < 0:
            raise ValidationError("Paid amount cannot be negative.")
        if paid_minor > total:
            raise ValidationError("Paid amount cannot exceed the purchase total.")
        balance = total - paid_minor

        with self.db.transaction() as conn:
            if supplier_id and not row(conn, "SELECT id FROM suppliers WHERE id = ?",
                                       (supplier_id,)):
                raise NotFoundError("Supplier not found.")
            for entry in clean_items:
                product = row(conn, "SELECT id, name FROM products WHERE id = ? AND is_active = 1",
                              (entry["product_id"],))
                if not product:
                    raise ValidationError("A product in this purchase no longer exists.")
            purchase_no = self.db.next_number(
                conn, "purchase", self.settings.get("purchase.prefix", "PUR"), 6
            )
            cur = conn.execute(
                "INSERT INTO purchases(purchase_no, supplier_id, user_id, purchase_date, "
                "subtotal, discount, total, paid, balance, status, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (purchase_no, supplier_id, session.user_id,
                 purchase_date or now_str()[:10], subtotal, discount_minor, total,
                 paid_minor, balance, "received", notes.strip()),
            )
            purchase_id = int(cur.lastrowid)
            for entry in clean_items:
                conn.execute(
                    "INSERT INTO purchase_items(purchase_id, product_id, product_name, "
                    "quantity, unit_price, line_total) VALUES (?,?,?,?,?,?)",
                    (purchase_id, entry["product_id"], entry["name"], entry["quantity"],
                     entry["unit_price"], entry["line_total"]),
                )
                self.inventory.increase(
                    conn, entry["product_id"], entry["quantity"], "purchase",
                    "purchase", purchase_id, f"Purchase {purchase_no}", session,
                )
                if update_prices:
                    conn.execute(
                        "UPDATE products SET purchase_price = ?, updated_at = ? WHERE id = ?",
                        (entry["unit_price"], now_str(), entry["product_id"]),
                    )
            if paid_minor > 0:
                conn.execute(
                    "INSERT INTO payments(purchase_id, direction, method, amount, user_id, reference) "
                    "VALUES (?,?,?,?,?,?)",
                    (purchase_id, "OUT", self.settings.get("pos.default_payment_method", "Cash"),
                     paid_minor, session.user_id, purchase_no),
                )
            if supplier_id:
                conn.execute("UPDATE suppliers SET updated_at = ? WHERE id = ?",
                             (now_str(), supplier_id))
            audit.log(conn, session, audit.CREATE, entity="purchases", entity_id=purchase_id,
                      description=f"Purchase {purchase_no} recorded",
                      details=f"total={total}; paid={paid_minor}; items={len(clean_items)}")
            return self.get_purchase(purchase_id, conn=conn)

    # --------------------------------------------------------------- read
    def list_purchases(self, date_from: str = "", date_to: str = "", term: str = "",
                       supplier_id: int | None = None, limit: int = 500) -> list[dict]:
        where, params = [], []
        if date_from:
            where.append("date(p.purchase_date) >= date(?)")
            params.append(date_from)
        if date_to:
            where.append("date(p.purchase_date) <= date(?)")
            params.append(date_to)
        if supplier_id:
            where.append("p.supplier_id = ?")
            params.append(supplier_id)
        if term:
            like = f"%{term.strip()}%"
            where.append("(p.purchase_no LIKE ? OR s.name LIKE ?)")
            params.extend([like, like])
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        sql = """
        SELECT p.*, COALESCE(s.name,'(No supplier)') AS supplier,
               u.username AS created_by,
               (SELECT COUNT(*) FROM purchase_items pi WHERE pi.purchase_id = p.id) AS item_count
        FROM purchases p
        LEFT JOIN suppliers s ON s.id = p.supplier_id
        LEFT JOIN users u ON u.id = p.user_id
        """ + clause + " ORDER BY p.id DESC LIMIT ?"
        with self.db.read() as conn:
            return rows(conn, sql, tuple(params))

    def get_purchase(self, purchase_id: int, conn=None) -> dict:
        def _fetch(c):
            record = row(
                c,
                "SELECT p.*, COALESCE(s.name,'(No supplier)') AS supplier, "
                "COALESCE(s.phone,'') AS supplier_phone "
                "FROM purchases p LEFT JOIN suppliers s ON s.id = p.supplier_id "
                "WHERE p.id = ?",
                (purchase_id,),
            )
            if not record:
                raise NotFoundError("Purchase not found.")
            record["items"] = rows(
                c,
                "SELECT pi.*, p.sku, p.barcode FROM purchase_items pi "
                "LEFT JOIN products p ON p.id = pi.product_id "
                "WHERE pi.purchase_id = ? ORDER BY pi.id",
                (purchase_id,),
            )
            record["payments"] = rows(c, "SELECT * FROM payments WHERE purchase_id = ? "
                                         "ORDER BY id", (purchase_id,))
            return record

        if conn is not None:
            return _fetch(conn)
        with self.db.read() as c:
            return _fetch(c)

    def totals_between(self, date_from: str, date_to: str) -> dict:
        with self.db.read() as conn:
            record = row(
                conn,
                "SELECT COUNT(*) AS count, COALESCE(SUM(total),0) AS total, "
                "COALESCE(SUM(paid),0) AS paid, COALESCE(SUM(balance),0) AS balance "
                "FROM purchases WHERE status='received' AND date(purchase_date) >= date(?) "
                "AND date(purchase_date) <= date(?)",
                (date_from, date_to),
            ) or {}
            record.setdefault("count", 0)
            for key in ("total", "paid", "balance"):
                record[key] = int(record.get(key) or 0)
            return record
