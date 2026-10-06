"""Returns / refunds - historical sale rows are never edited destructively."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from ..core import audit
from ..core.db import now_str, row, rows, scalar
from ..core.exceptions import NotFoundError, PermissionDenied, ValidationError
from ..core.money import to_minor
from ..core.security import Session
from .inventory_service import InventoryService


def _prorate(value: int, part: float, whole: float) -> int:
    if whole <= 0:
        return 0
    amount = (Decimal(int(value)) * Decimal(str(part)) / Decimal(str(whole))).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(amount)


class ReturnService:
    def __init__(self, db, settings, inventory: InventoryService | None = None,
                 session: Session | None = None):
        self.db = db
        self.settings = settings
        self.inventory = inventory or InventoryService(db, settings, session)
        self.session = session

    # ------------------------------------------------------------- create
    def create_return(self, sale_id: int, lines: list[dict], reason: str = "",
                      refund_method: str = "Cash",
                      session: Session | None = None) -> dict:
        session = session or self.session
        if not session:
            raise PermissionDenied("Please log in first.")
        if not session.can("returns.process"):
            raise PermissionDenied("You do not have permission to process returns.")
        if not lines:
            raise ValidationError("Select at least one item to return.")

        with self.db.transaction() as conn:
            sale = row(conn, "SELECT * FROM sales WHERE id = ?", (sale_id,))
            if not sale:
                raise NotFoundError("Invoice not found.")
            if sale["status"] == "voided":
                raise ValidationError("Voided invoices cannot be returned.")

            prepared = []
            for line in lines:
                sale_item_id = line.get("sale_item_id")
                qty = float(line.get("quantity") or 0)
                item = row(conn, "SELECT * FROM sale_items WHERE id = ? AND sale_id = ?",
                           (sale_item_id, sale_id))
                if not item:
                    raise ValidationError("An item on this invoice no longer exists.")
                if qty <= 0:
                    raise ValidationError(
                        f"Return quantity for '{item['product_name']}' must be greater than zero."
                    )
                already = float(item["returned_qty"] or 0)
                if qty - already > float(item["quantity"]) + 1e-9:
                    raise ValidationError(
                        f"Cannot return {qty:g} of '{item['product_name']}' - "
                        f"only {float(item['quantity']) - already:g} available to return."
                    )
                prepared.append((item, qty))

            # prorate the bill discount across the returned lines
            goods_total = max(1, int(sale["subtotal"]) - int(sale["item_discount"]))
            return_no = self.db.next_number(
                conn, "return", self.settings.get("return.prefix", "RET"), 6
            )
            cur = conn.execute(
                "INSERT INTO returns(return_no, sale_id, customer_id, user_id, reason, "
                "refund_method, subtotal, total, status) VALUES (?,?,?,?,?,?,?,?, 'completed')",
                (return_no, sale_id, sale["customer_id"], session.user_id,
                 (reason or "").strip(), refund_method, 0, 0),
            )
            return_id = int(cur.lastrowid)
            refund_total = 0
            subtotal_total = 0
            for item, qty in prepared:
                line_refund = _prorate(int(item["line_total"]), qty, float(item["quantity"]))
                bill_share = _prorate(int(sale["bill_discount"]), line_refund, goods_total)
                refund = max(0, line_refund - bill_share)
                conn.execute(
                    "INSERT INTO return_items(return_id, sale_item_id, product_id, "
                    "product_name, quantity, unit_price, discount_amount, refund_amount, reason) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (return_id, item["id"], item["product_id"], item["product_name"],
                     qty, item["unit_price"], bill_share, refund, (reason or "").strip()),
                )
                conn.execute(
                    "UPDATE sale_items SET returned_qty = returned_qty + ? WHERE id = ?",
                    (qty, item["id"]),
                )
                if item["product_id"]:
                    self.inventory.increase(
                        conn, item["product_id"], qty, "return", "return", return_id,
                        f"Return {return_no} from {sale['invoice_no']}", session,
                    )
                refund_total += refund
                subtotal_total += line_refund
            conn.execute("UPDATE returns SET subtotal = ?, total = ? WHERE id = ?",
                         (subtotal_total, refund_total, return_id))
            conn.execute(
                "INSERT INTO payments(return_id, direction, method, amount, user_id, reference) "
                "VALUES (?,?,?,?,?,?)",
                (return_id, "OUT", refund_method, refund_total, session.user_id, return_no),
            )
            # update the sale status without touching the original numbers
            remaining = scalar(
                conn,
                "SELECT COALESCE(SUM(quantity - returned_qty),0) FROM sale_items "
                "WHERE sale_id = ?",
                (sale_id,), 0,
            )
            any_returned = scalar(
                conn, "SELECT COALESCE(SUM(returned_qty),0) FROM sale_items WHERE sale_id = ?",
                (sale_id,), 0,
            )
            new_status = "returned" if float(remaining) <= 1e-9 else "partially_returned"
            conn.execute("UPDATE sales SET status = ? WHERE id = ? AND status != 'voided'",
                         (new_status, sale_id))
            audit.log(conn, session, audit.RETURN, entity="returns", entity_id=return_id,
                      description=f"Return {return_no} processed for {sale['invoice_no']}",
                      details=f"refund={refund_total}; reason={reason}")
            return {
                "return_id": return_id,
                "return_no": return_no,
                "total": refund_total,
                "items": len(prepared),
                "sale_status": new_status,
                "fully_returned": float(any_returned) > 0 and float(remaining) <= 1e-9,
            }

    # --------------------------------------------------------------- read
    def list_returns(self, date_from: str = "", date_to: str = "", term: str = "",
                     limit: int = 500) -> list[dict]:
        where, params = [], []
        if date_from:
            where.append("date(r.created_at) >= date(?)")
            params.append(date_from)
        if date_to:
            where.append("date(r.created_at) <= date(?)")
            params.append(date_to)
        if term:
            like = f"%{term.strip()}%"
            where.append("(r.return_no LIKE ? OR s.invoice_no LIKE ? OR cu.name LIKE ?)")
            params.extend([like, like, like])
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        sql = """
        SELECT r.*, s.invoice_no, COALESCE(cu.name,'Walk-in Customer') AS customer,
               u.username AS processed_by,
               (SELECT COUNT(*) FROM return_items ri WHERE ri.return_id = r.id) AS item_count
        FROM returns r
        JOIN sales s ON s.id = r.sale_id
        LEFT JOIN customers cu ON cu.id = r.customer_id
        LEFT JOIN users u ON u.id = r.user_id
        """ + clause + " ORDER BY r.id DESC LIMIT ?"
        with self.db.read() as conn:
            return rows(conn, sql, tuple(params))

    def get_return(self, return_id: int) -> dict:
        with self.db.read() as conn:
            record = row(
                conn,
                "SELECT r.*, s.invoice_no FROM returns r JOIN sales s ON s.id = r.sale_id "
                "WHERE r.id = ?",
                (return_id,),
            )
            if not record:
                raise NotFoundError("Return not found.")
            record["items"] = rows(conn,
                                   "SELECT * FROM return_items WHERE return_id = ? ORDER BY id",
                                   (return_id,))
            return record

    def returnable_items(self, sale_id: int) -> list[dict]:
        """Sale lines with the quantity still available to return."""
        with self.db.read() as conn:
            items = rows(
                conn,
                "SELECT si.id AS sale_item_id, si.product_name, si.sku, si.quantity, "
                "si.returned_qty, si.unit_price, si.line_total, si.discount_amount, "
                "si.product_id FROM sale_items si WHERE si.sale_id = ? ORDER BY si.id",
                (sale_id,),
            )
        for item in items:
            item["returnable"] = round(float(item["quantity"]) - float(item["returned_qty"]), 3)
        return [i for i in items if i["returnable"] > 1e-9]
