"""Inventory: stock levels, adjustments and movement history."""
from __future__ import annotations

from ..core import audit
from ..core.db import now_str, row, rows, scalar
from ..core.exceptions import NotFoundError, StockError, ValidationError
from ..core.security import Session

MOVEMENT_SQL = """
SELECT m.id, m.movement, m.quantity_change, m.quantity_after, m.reference_type,
       m.reference_id, m.username, m.note, m.created_at,
       p.name AS product_name, p.sku, p.barcode
FROM stock_movements m
JOIN products p ON p.id = m.product_id
"""

LOW_STOCK_SQL = """
SELECT p.id, p.name, p.sku, p.barcode, p.min_stock, p.purchase_price, p.selling_price,
       COALESCE(i.quantity,0) AS stock, c.name AS category, s.name AS supplier,
       p.unit_id, u.short_code AS unit_short
FROM products p
LEFT JOIN inventory i ON i.product_id = p.id
LEFT JOIN categories c ON c.id = p.category_id
LEFT JOIN suppliers s ON s.id = p.supplier_id
LEFT JOIN units u ON u.id = p.unit_id
WHERE p.is_active = 1
"""


class InventoryService:
    def __init__(self, db, settings=None, session: Session | None = None):
        self.db = db
        self.settings = settings
        self.session = session

    # --------------------------------------------------------------- reads
    def stock_of(self, product_id: int) -> float:
        with self.db.read() as conn:
            value = row(conn, "SELECT quantity FROM inventory WHERE product_id = ?",
                        (product_id,))
            return float(value["quantity"]) if value else 0.0

    def list_inventory(self, term: str = "", category_id: int | None = None,
                       supplier_id: int | None = None, status: str = "",
                       limit: int = 500) -> list[dict]:
        where = ["p.is_active = 1"]
        params: list = []
        term = (term or "").strip()
        if term:
            like = f"%{term}%"
            where.append("(p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ?)")
            params.extend([like, like, like])
        if category_id:
            where.append("p.category_id = ?")
            params.append(category_id)
        if supplier_id:
            where.append("p.supplier_id = ?")
            params.append(supplier_id)
        if status == "low":
            where.append("COALESCE(i.quantity,0) > 0 AND COALESCE(i.quantity,0) <= p.min_stock")
        elif status == "out":
            where.append("COALESCE(i.quantity,0) <= 0")
        elif status == "ok":
            where.append("COALESCE(i.quantity,0) > p.min_stock")
        params.append(limit)
        sql = """
        SELECT p.id, p.name, p.sku, p.barcode, p.min_stock, p.max_stock,
               p.purchase_price, p.selling_price, p.is_active,
               COALESCE(i.quantity,0) AS stock, c.name AS category,
               b.name AS brand, s.name AS supplier, u.short_code AS unit_short,
               u.name AS unit
        FROM products p
        LEFT JOIN inventory i ON i.product_id = p.id
        LEFT JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        LEFT JOIN suppliers s ON s.id = p.supplier_id
        LEFT JOIN units u ON u.id = p.unit_id
        WHERE """ + " AND ".join(where) + " ORDER BY p.name LIMIT ?"
        with self.db.read() as conn:
            result = rows(conn, sql, tuple(params))
        for record in result:
            stock = float(record["stock"])
            if stock <= 0:
                record["status"] = "Out of stock"
            elif stock <= float(record["min_stock"]):
                record["status"] = "Low stock"
            else:
                record["status"] = "In stock"
            record["stock_value"] = int(round(stock * int(record["purchase_price"])))
        return result

    def low_stock(self) -> list[dict]:
        with self.db.read() as conn:
            return rows(conn, LOW_STOCK_SQL +
                        " AND COALESCE(i.quantity,0) > 0 AND COALESCE(i.quantity,0) <= p.min_stock "
                        "ORDER BY (p.min_stock - COALESCE(i.quantity,0)) DESC")

    def out_of_stock(self) -> list[dict]:
        with self.db.read() as conn:
            return rows(conn, LOW_STOCK_SQL + " AND COALESCE(i.quantity,0) <= 0 ORDER BY p.name")

    def stock_alerts(self) -> dict:
        with self.db.read() as conn:
            low = scalar(conn,
                         "SELECT COUNT(*) FROM products p LEFT JOIN inventory i "
                         "ON i.product_id = p.id WHERE p.is_active = 1 AND "
                         "COALESCE(i.quantity,0) > 0 AND COALESCE(i.quantity,0) <= p.min_stock",
                         (), 0)
            out = scalar(conn,
                         "SELECT COUNT(*) FROM products p LEFT JOIN inventory i "
                         "ON i.product_id = p.id WHERE p.is_active = 1 AND "
                         "COALESCE(i.quantity,0) <= 0", (), 0)
            return {"low": int(low), "out": int(out)}

    def stock_value(self) -> int:
        with self.db.read() as conn:
            total = scalar(
                conn,
                "SELECT COALESCE(SUM(COALESCE(i.quantity,0) * p.purchase_price),0) "
                "FROM products p LEFT JOIN inventory i ON i.product_id = p.id "
                "WHERE p.is_active = 1",
                (), 0,
            )
            return int(total)

    def movements(self, product_id: int | None = None, limit: int = 200,
                  offset: int = 0) -> list[dict]:
        where, params = [], []
        if product_id:
            where.append("m.product_id = ?")
            params.append(product_id)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        params.extend([limit, offset])
        with self.db.read() as conn:
            return rows(conn, MOVEMENT_SQL + clause +
                        " ORDER BY m.id DESC LIMIT ? OFFSET ?", tuple(params))

    # -------------------------------------------------------------- writes
    def _set_stock(self, conn, product_id: int, quantity: float) -> float:
        conn.execute(
            "INSERT INTO inventory(product_id, quantity, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(product_id) DO UPDATE SET quantity = excluded.quantity, "
            "updated_at = excluded.updated_at",
            (product_id, quantity, now_str()),
        )
        return quantity

    def _movement_row(self, conn, product_id: int, movement: str, change: float,
                      after: float, reference_type: str = "", reference_id=None,
                      note: str = "", session: Session | None = None) -> None:
        session = session or self.session
        conn.execute(
            "INSERT INTO stock_movements(product_id, movement, quantity_change, "
            "quantity_after, reference_type, reference_id, user_id, username, note) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (product_id, movement, change, after, reference_type, reference_id,
             session.user_id if session else None,
             session.username if session else "", note),
        )

    def increase(self, conn, product_id: int, quantity: float, movement: str,
                 reference_type: str = "", reference_id=None, note: str = "",
                 session: Session | None = None) -> float:
        """Add stock inside the caller's transaction (purchases, returns)."""
        current = self._current(conn, product_id)
        new_qty = round(current + float(quantity), 3)
        self._set_stock(conn, product_id, new_qty)
        self._movement_row(conn, product_id, movement, float(quantity), new_qty,
                           reference_type, reference_id, note, session)
        return new_qty

    def decrease(self, conn, product_id: int, quantity: float, movement: str,
                 reference_type: str = "", reference_id=None, note: str = "",
                 allow_negative: bool = False,
                 session: Session | None = None) -> float:
        """Remove stock inside the caller's transaction (sales)."""
        current = self._current(conn, product_id)
        qty = float(quantity)
        if not allow_negative and current - qty < -1e-9:
            raise StockError("Insufficient stock available.")
        new_qty = round(current - qty, 3)
        self._set_stock(conn, product_id, new_qty)
        self._movement_row(conn, product_id, movement, -qty, new_qty,
                           reference_type, reference_id, note, session)
        return new_qty

    def _current(self, conn, product_id: int) -> float:
        record = row(conn, "SELECT quantity FROM inventory WHERE product_id = ?",
                     (product_id,))
        if record is None:
            product = row(conn, "SELECT id FROM products WHERE id = ?", (product_id,))
            if not product:
                raise NotFoundError("Product not found.")
            self._set_stock(conn, product_id, 0)
            return 0.0
        return float(record["quantity"])

    def adjust(self, product_id: int, new_quantity: float, reason: str,
               session: Session | None = None, note: str = "") -> dict:
        """Manual stock adjustment with reason - always audited."""
        if not reason.strip():
            raise ValidationError("Please provide a reason for the adjustment.")
        if new_quantity < 0:
            raise ValidationError("Stock quantity cannot be negative.")
        session = session or self.session
        with self.db.transaction() as conn:
            product = row(conn, "SELECT name FROM products WHERE id = ?", (product_id,))
            if not product:
                raise NotFoundError("Product not found.")
            current = self._current(conn, product_id)
            change = round(float(new_quantity) - current, 3)
            self._set_stock(conn, product_id, float(new_quantity))
            self._movement_row(conn, product_id, "adjustment", change,
                               float(new_quantity), "adjustment", None,
                               f"{reason}. {note}".strip(), session)
            audit.log(conn, session, audit.ADJUST, entity="products", entity_id=product_id,
                      description=f"Stock adjusted for '{product['name']}'",
                      details=f"{current} -> {new_quantity}; reason: {reason}")
            return {"product_id": product_id, "before": current,
                    "after": float(new_quantity), "change": change, "reason": reason}

    def set_initial_stock(self, product_id: int, quantity: float,
                          session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            current = self._current(conn, product_id)
            if current == quantity:
                return
            self._set_stock(conn, product_id, float(quantity))
            self._movement_row(conn, product_id, "initial",
                               round(float(quantity) - current, 3), float(quantity),
                               "product", product_id, "Opening stock",
                               session or self.session)

    def transfer(self, product_id: int, quantity: float, movement: str,
                 reference_type: str = "", reference_id=None, note: str = "",
                 allow_negative: bool = False,
                 session: Session | None = None) -> float:
        return self.decrease(conn, product_id, quantity, movement, reference_type,
                             reference_id, note, allow_negative, session)
