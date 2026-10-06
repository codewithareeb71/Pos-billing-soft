"""Supplier records, purchases and outstanding balances."""
from __future__ import annotations

from ..core import audit
from ..core.db import now_str, row, rows, scalar
from ..core.exceptions import NotFoundError, ValidationError
from ..core.money import to_minor
from ..core.security import Session

FIELDS = ("name", "company", "phone", "whatsapp", "address", "email", "notes")


class SupplierService:
    def __init__(self, db, session: Session | None = None):
        self.db = db
        self.session = session

    def search(self, term: str = "", limit: int = 200) -> list[dict]:
        term = (term or "").strip()
        sql = """
        SELECT s.*,
               COALESCE((SELECT SUM(total) FROM purchases p WHERE p.supplier_id = s.id),0) AS total_purchased,
               COALESCE((SELECT SUM(balance) FROM purchases p WHERE p.supplier_id = s.id
                         AND p.status='received'),0) AS outstanding,
               (SELECT COUNT(*) FROM purchases p WHERE p.supplier_id = s.id) AS purchase_count,
               (SELECT MAX(purchase_date) FROM purchases p WHERE p.supplier_id = s.id) AS last_purchase
        FROM suppliers s
        """
        params: tuple = ()
        if term:
            like = f"%{term}%"
            sql += " WHERE s.name LIKE ? OR s.company LIKE ? OR s.phone LIKE ?"
            params = (like, like, like)
        sql += " ORDER BY s.name LIMIT ?"
        params += (limit,)
        with self.db.read() as conn:
            return rows(conn, sql, params)

    def get(self, supplier_id: int) -> dict:
        with self.db.read() as conn:
            record = row(conn, "SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
        if not record:
            raise NotFoundError("Supplier not found.")
        return record

    @staticmethod
    def _validate(data: dict) -> dict:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValidationError("Supplier name is required.")
        return {f: (data.get(f) or "").strip() for f in FIELDS} | {"name": name}

    def create(self, data: dict, session: Session | None = None) -> int:
        clean = self._validate(data)
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO suppliers(name, company, phone, whatsapp, address, email, notes) "
                "VALUES (?,?,?,?,?,?,?)",
                (clean["name"], clean["company"], clean["phone"], clean["whatsapp"],
                 clean["address"], clean["email"], clean["notes"]),
            )
            supplier_id = int(cur.lastrowid)
            audit.log(conn, session or self.session, audit.CREATE, entity="suppliers",
                      entity_id=supplier_id,
                      description=f"Supplier '{clean['name']}' created")
            return supplier_id

    def update(self, supplier_id: int, data: dict, session: Session | None = None) -> None:
        clean = self._validate(data)
        with self.db.transaction() as conn:
            if not row(conn, "SELECT id FROM suppliers WHERE id = ?", (supplier_id,)):
                raise NotFoundError("Supplier not found.")
            conn.execute(
                "UPDATE suppliers SET name=?, company=?, phone=?, whatsapp=?, address=?, "
                "email=?, notes=?, updated_at=? WHERE id=?",
                (clean["name"], clean["company"], clean["phone"], clean["whatsapp"],
                 clean["address"], clean["email"], clean["notes"], now_str(), supplier_id),
            )
            audit.log(conn, session or self.session, audit.UPDATE, entity="suppliers",
                      entity_id=supplier_id,
                      description=f"Supplier '{clean['name']}' updated")

    def deactivate(self, supplier_id: int, active: bool,
                   session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE suppliers SET active = ?, updated_at = ? WHERE id = ?",
                         (1 if active else 0, now_str(), supplier_id))

    def purchases(self, supplier_id: int, limit: int = 200) -> list[dict]:
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT p.*, u.username AS created_by FROM purchases p "
                "LEFT JOIN users u ON u.id = p.user_id WHERE p.supplier_id = ? "
                "ORDER BY p.id DESC LIMIT ?",
                (supplier_id, limit),
            )

    def payment_history(self, supplier_id: int, limit: int = 200) -> list[dict]:
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT pay.* FROM payments pay "
                "JOIN purchases p ON p.id = pay.purchase_id "
                "WHERE p.supplier_id = ? ORDER BY pay.id DESC LIMIT ?",
                (supplier_id, limit),
            )

    def record_payment(self, supplier_id: int, amount, method: str, note: str = "",
                       session: Session | None = None) -> dict:
        """Pay off outstanding supplier balance (oldest purchase first)."""
        amount_minor = to_minor(amount)
        if amount_minor <= 0:
            raise ValidationError("Payment amount must be greater than zero.")
        session = session or self.session
        with self.db.transaction() as conn:
            supplier = row(conn, "SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
            if not supplier:
                raise NotFoundError("Supplier not found.")
            open_purchases = rows(
                conn,
                "SELECT id, balance FROM purchases WHERE supplier_id = ? AND status='received' "
                "AND balance > 0 ORDER BY id",
                (supplier_id,),
            )
            remaining = amount_minor
            for purchase in open_purchases:
                if remaining <= 0:
                    break
                share = min(remaining, int(purchase["balance"]))
                conn.execute("UPDATE purchases SET balance = balance - ? WHERE id = ?",
                             (share, purchase["id"]))
                conn.execute(
                    "INSERT INTO payments(purchase_id, direction, method, amount, user_id, note) "
                    "VALUES (?,?,?,?,?,?)",
                    (purchase["id"], "OUT", method, share, session.user_id, note.strip()),
                )
                remaining -= share
            conn.execute("UPDATE suppliers SET updated_at = ? WHERE id = ?",
                         (now_str(), supplier_id))
            audit.log(conn, session, audit.UPDATE, entity="suppliers", entity_id=supplier_id,
                      description=f"Payment of {amount_minor/100:.2f} recorded for "
                                  f"'{supplier['name']}'",
                      details=f"method={method}; unallocated={remaining}")
            return {"allocated": amount_minor - remaining, "unallocated": remaining}

    def outstanding_total(self) -> int:
        with self.db.read() as conn:
            return int(scalar(
                conn,
                "SELECT COALESCE(SUM(balance),0) FROM purchases WHERE status='received'",
                (), 0,
            ))

    def count(self) -> int:
        with self.db.read() as conn:
            return int(scalar(conn, "SELECT COUNT(*) FROM suppliers WHERE active = 1", (), 0))
