"""Expense tracking."""
from __future__ import annotations

from ..core import audit
from ..core.db import now_str, row, rows, scalar
from ..core.exceptions import NotFoundError, ValidationError
from ..core.money import to_minor
from ..core.security import Session

EXPENSE_CATEGORIES = [
    "General", "Rent", "Utilities", "Salaries", "Transport", "Maintenance",
    "Packaging", "Marketing", "Taxes", "Licences", "Other",
]


class ExpenseService:
    def __init__(self, db, session: Session | None = None):
        self.db = db
        self.session = session

    def create(self, data: dict, session: Session | None = None) -> int:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValidationError("Expense title is required.")
        amount = to_minor(data.get("amount") or 0)
        if amount <= 0:
            raise ValidationError("Expense amount must be greater than zero.")
        expense_date = (data.get("expense_date") or "").strip() or now_str()[:10]
        session = session or self.session
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO expenses(title, category, amount, expense_date, payment_method, "
                "notes, user_id) VALUES (?,?,?,?,?,?,?)",
                (title, (data.get("category") or "General").strip(), amount, expense_date,
                 (data.get("payment_method") or "Cash").strip(),
                 (data.get("notes") or "").strip(), session.user_id if session else None),
            )
            expense_id = int(cur.lastrowid)
            audit.log(conn, session, audit.CREATE, entity="expenses", entity_id=expense_id,
                      description=f"Expense '{title}' recorded",
                      details=f"amount={amount}; date={expense_date}")
            return expense_id

    def update(self, expense_id: int, data: dict, session: Session | None = None) -> None:
        title = (data.get("title") or "").strip()
        amount = to_minor(data.get("amount") or 0)
        if not title:
            raise ValidationError("Expense title is required.")
        if amount <= 0:
            raise ValidationError("Expense amount must be greater than zero.")
        session = session or self.session
        with self.db.transaction() as conn:
            if not row(conn, "SELECT id FROM expenses WHERE id = ?", (expense_id,)):
                raise NotFoundError("Expense not found.")
            conn.execute(
                "UPDATE expenses SET title=?, category=?, amount=?, expense_date=?, "
                "payment_method=?, notes=? WHERE id=?",
                (title, (data.get("category") or "General").strip(), amount,
                 (data.get("expense_date") or now_str()[:10]).strip(),
                 (data.get("payment_method") or "Cash").strip(),
                 (data.get("notes") or "").strip(), expense_id),
            )
            audit.log(conn, session, audit.UPDATE, entity="expenses", entity_id=expense_id,
                      description=f"Expense '{title}' updated", details=f"amount={amount}")

    def delete(self, expense_id: int, session: Session | None = None) -> None:
        session = session or self.session
        with self.db.transaction() as conn:
            record = row(conn, "SELECT title FROM expenses WHERE id = ?", (expense_id,))
            if not record:
                raise NotFoundError("Expense not found.")
            conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            audit.log(conn, session, audit.DELETE, entity="expenses", entity_id=expense_id,
                      description=f"Expense '{record['title']}' deleted")

    def list(self, date_from: str = "", date_to: str = "", term: str = "",
             category: str = "", limit: int = 1000) -> list[dict]:
        where, params = [], []
        if date_from:
            where.append("date(e.expense_date) >= date(?)")
            params.append(date_from)
        if date_to:
            where.append("date(e.expense_date) <= date(?)")
            params.append(date_to)
        if category:
            where.append("e.category = ?")
            params.append(category)
        if term:
            like = f"%{term.strip()}%"
            where.append("(e.title LIKE ? OR e.notes LIKE ? OR e.category LIKE ?)")
            params.extend([like, like, like])
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        sql = """
        SELECT e.*, u.username AS created_by FROM expenses e
        LEFT JOIN users u ON u.id = e.user_id
        """ + clause + " ORDER BY e.expense_date DESC, e.id DESC LIMIT ?"
        with self.db.read() as conn:
            return rows(conn, sql, tuple(params))

    def total_between(self, date_from: str, date_to: str) -> int:
        with self.db.read() as conn:
            return int(scalar(
                conn,
                "SELECT COALESCE(SUM(amount),0) FROM expenses "
                "WHERE date(expense_date) >= date(?) AND date(expense_date) <= date(?)",
                (date_from, date_to), 0,
            ))

    def by_category(self, date_from: str, date_to: str) -> list[dict]:
        with self.db.read() as conn:
            return rows(
                conn,
                "SELECT category, COUNT(*) AS count, SUM(amount) AS total FROM expenses "
                "WHERE date(expense_date) >= date(?) AND date(expense_date) <= date(?) "
                "GROUP BY category ORDER BY total DESC",
                (date_from, date_to),
            )
