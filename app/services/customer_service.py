"""Customer records and purchase history."""
from __future__ import annotations

from ..core import audit
from ..core.db import now_str, row, rows, scalar
from ..core.exceptions import ConflictError, NotFoundError, ValidationError
from ..core.security import Session

FIELDS = ("name", "phone", "whatsapp", "address", "email", "notes")


class CustomerService:
    def __init__(self, db, session: Session | None = None):
        self.db = db
        self.session = session

    def walk_in(self) -> dict | None:
        with self.db.read() as conn:
            return row(conn, "SELECT * FROM customers WHERE is_walkin = 1 LIMIT 1")

    def search(self, term: str = "", limit: int = 200) -> list[dict]:
        term = (term or "").strip()
        sql = """
        SELECT c.*,
               COALESCE((SELECT SUM(total) FROM sales s WHERE s.customer_id = c.id
                         AND s.status != 'voided'), 0) AS total_spent,
               (SELECT COUNT(*) FROM sales s WHERE s.customer_id = c.id
                    AND s.status != 'voided') AS visit_count,
               (SELECT MAX(created_at) FROM sales s WHERE s.customer_id = c.id) AS last_visit
        FROM customers c
        """
        params: tuple = ()
        if term:
            like = f"%{term}%"
            sql += (" WHERE c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ? "
                    "OR c.address LIKE ?")
            params = (like, like, like, like)
        sql += " ORDER BY c.is_walkin DESC, c.name LIMIT ?"
        params += (limit,)
        with self.db.read() as conn:
            return rows(conn, sql, params)

    def get(self, customer_id: int) -> dict:
        with self.db.read() as conn:
            record = row(conn, "SELECT * FROM customers WHERE id = ?", (customer_id,))
        if not record:
            raise NotFoundError("Customer not found.")
        return record

    @staticmethod
    def _validate(data: dict) -> dict:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValidationError("Customer name is required.")
        email = (data.get("email") or "").strip()
        if email and "@" not in email:
            raise ValidationError("Please enter a valid email address.")
        return {f: (data.get(f) or "").strip() for f in FIELDS} | {"name": name}

    def create(self, data: dict, session: Session | None = None) -> int:
        clean = self._validate(data)
        with self.db.transaction() as conn:
            if clean["phone"] and row(
                conn, "SELECT id FROM customers WHERE phone = ? AND phone != ''",
                (clean["phone"],),
            ):
                raise ConflictError(f"A customer with phone {clean['phone']} already exists.")
            cur = conn.execute(
                "INSERT INTO customers(name, phone, whatsapp, address, email, notes) "
                "VALUES (?,?,?,?,?,?)",
                (clean["name"], clean["phone"], clean["whatsapp"], clean["address"],
                 clean["email"], clean["notes"]),
            )
            customer_id = int(cur.lastrowid)
            audit.log(conn, session or self.session, audit.CREATE, entity="customers",
                      entity_id=customer_id,
                      description=f"Customer '{clean['name']}' created")
            return customer_id

    def update(self, customer_id: int, data: dict, session: Session | None = None) -> None:
        clean = self._validate(data)
        with self.db.transaction() as conn:
            current = row(conn, "SELECT * FROM customers WHERE id = ?", (customer_id,))
            if not current:
                raise NotFoundError("Customer not found.")
            if clean["phone"] and row(
                conn, "SELECT id FROM customers WHERE phone = ? AND id != ?",
                (clean["phone"], customer_id),
            ):
                raise ConflictError(f"A customer with phone {clean['phone']} already exists.")
            conn.execute(
                "UPDATE customers SET name=?, phone=?, whatsapp=?, address=?, email=?, "
                "notes=?, updated_at=? WHERE id=?",
                (clean["name"], clean["phone"], clean["whatsapp"], clean["address"],
                 clean["email"], clean["notes"], now_str(), customer_id),
            )
            audit.log(conn, session or self.session, audit.UPDATE, entity="customers",
                      entity_id=customer_id,
                      description=f"Customer '{clean['name']}' updated")

    def history(self, customer_id: int, limit: int = 200) -> list[dict]:
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT s.id, s.invoice_no, s.created_at, s.total, s.payment_method, "
                "s.status, s.cashier_name FROM sales s WHERE s.customer_id = ? "
                "ORDER BY s.id DESC LIMIT ?",
                (customer_id, limit),
            )

    def deactivate(self, customer_id: int, active: bool,
                   session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE customers SET active = ?, updated_at = ? WHERE id = ?",
                         (1 if active else 0, now_str(), customer_id))
            audit.log(conn, session or self.session, audit.UPDATE, entity="customers",
                      entity_id=customer_id,
                      description=f"Customer {'activated' if active else 'deactivated'}")

    def count(self) -> int:
        with self.db.read() as conn:
            return int(scalar(conn, "SELECT COUNT(*) FROM customers WHERE active = 1", (), 0))
