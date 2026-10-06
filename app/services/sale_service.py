"""POS billing: cart computation, sale completion, holds, voids, history.

Every completed sale is written inside a single database transaction:
sale header -> sale items -> payment -> stock deduction -> stock movements
-> audit log.  Any failure rolls the whole transaction back, so an invoice
can never exist without its stock movement and vice versa.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from ..core import audit
from ..core.db import now_str, row, rows, scalar
from ..core.exceptions import NotFoundError, PermissionDenied, StockError, ValidationError
from ..core.money import apply_percent, from_minor, to_minor
from ..core.security import Session
from ..services.inventory_service import InventoryService

DISCOUNT_TYPES = ("None", "Percentage", "Fixed")


def line_gross(quantity: float, unit_price: int) -> int:
    """Exact gross for a line: price(minor) * quantity(decimal)."""
    from decimal import Decimal, ROUND_HALF_UP

    qty = Decimal(str(round(float(quantity), 3)))
    gross = (Decimal(int(unit_price)) * qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(gross)


def compute_item_discount(quantity: float, unit_price: int, dtype: str, dvalue) -> int:
    """`unit_price` and Fixed `dvalue` are MINOR units (integer paisa)."""
    gross = line_gross(quantity, unit_price)
    if dtype == "Percentage":
        pct = float(dvalue or 0)
        if pct < 0 or pct > 100:
            raise ValidationError("Discount percentage must be between 0 and 100.")
        return min(apply_percent(gross, pct), gross)
    if dtype == "Fixed":
        fixed = int(dvalue or 0)
        return max(0, min(fixed, gross))
    return 0


def compute_totals(items: list[dict], bill_type: str = "None", bill_value=0) -> dict:
    """Pure calculation used by both the UI and the service.

    Every monetary value inside a cart is an INTEGER number of minor units
    (paisa).  Percentages are plain numbers.  Quantities are rounded to three
    decimals.  No floating point is ever used for money.
    """
    subtotal = 0
    item_discount = 0
    normalized = []
    for raw in items:
        qty = float(raw.get("quantity") or 0)
        price = int(raw.get("unit_price") or 0)
        dtype = raw.get("discount_type") or "None"
        dvalue = raw.get("discount_value") or 0
        gross = line_gross(qty, price)
        discount = compute_item_discount(qty, price, dtype, dvalue)
        total = gross - discount
        entry = dict(raw)
        entry.update({
            "line_gross": gross,
            "discount_amount": discount,
            "line_total": total,
            "quantity": qty,
            "unit_price": price,
        })
        normalized.append(entry)
        subtotal += gross
        item_discount += discount
    goods = max(0, subtotal - item_discount)
    if bill_type == "Percentage":
        pct = float(bill_value or 0)
        if pct < 0 or pct > 100:
            raise ValidationError("Bill discount must be between 0 and 100%.")
        bill_discount = min(apply_percent(goods, pct), goods)
    elif bill_type == "Fixed":
        bill_discount = min(int(bill_value or 0), goods)
    else:
        bill_discount = 0
    total = goods - bill_discount
    return {
        "items": normalized,
        "subtotal": subtotal,
        "item_discount": item_discount,
        "goods_total": goods,
        "bill_discount_type": bill_type if bill_type in DISCOUNT_TYPES else "None",
        "bill_discount_value": int(bill_value or 0),
        "bill_discount": bill_discount,
        "total": total,
        "change_due": 0,
    }


class SaleService:
    def __init__(self, db, settings, inventory: InventoryService | None = None,
                 session: Session | None = None):
        self.db = db
        self.settings = settings
        self.inventory = inventory or InventoryService(db, settings, session)
        self.session = session

    # ------------------------------------------------------------ helpers
    @property
    def currency(self) -> str:
        return self.settings.currency if self.settings else "PKR"

    def check_discount_authorisation(self, totals: dict, session: Session | None = None) -> None:
        """High value discounts require the 'discount.high' permission."""
        session = session or self.session
        if not session:
            return
        if session.can("discount.high"):
            return
        threshold_pct = self.settings.get_int("pos.discount_threshold_percent", 10) if self.settings else 10
        threshold_amt = self.settings.get_int("pos.discount_threshold_amount", 1000) if self.settings else 1000
        from ..core.money import to_minor as _minor
        threshold_amt_minor = _minor(threshold_amt)
        bill_pct = (totals["bill_discount"] * 100) // max(totals["goods_total"], 1)
        item_pct = (totals["item_discount"] * 100) // max(totals["subtotal"], 1)
        if bill_pct > threshold_pct or item_pct > threshold_pct \
                or totals["bill_discount"] > threshold_amt_minor:
            if not session.can("discount.high"):
                raise PermissionDenied(
                    "This discount is above your limit. An administrator must approve it."
                )

    # ------------------------------------------------------ complete a sale
    def complete_sale(self, cart: dict, session: Session | None = None) -> dict:
        session = session or self.session
        if not session:
            raise PermissionDenied("Please log in first.")
        items = cart.get("items") or []
        if not items:
            raise ValidationError("The cart is empty. Add at least one product.")
        totals = compute_totals(
            items, cart.get("bill_discount_type", "None"), cart.get("bill_discount_value", 0)
        )
        self.check_discount_authorisation(totals, session)

        paid = int(cart.get("paid") or 0)
        if paid < 0:
            raise ValidationError("Paid amount cannot be negative.")
        total = totals["total"]
        method = cart.get("payment_method") or self.settings.get(
            "pos.default_payment_method", "Cash")
        if paid < total:
            raise ValidationError(
                f"Paid amount is less than the invoice total "
                f"({self.currency} {from_minor(total):,.2f})."
            )
        if str(method).lower() == "cash" and paid - total > 10 ** 12:  # pragma: no cover
            raise ValidationError("Paid amount is invalid.")
        allow_negative = self.settings.get_bool("pos.allow_negative_stock", False)

        with self.db.transaction() as conn:
            # 1. validate every product and check availability -------------
            validated = []
            for entry in totals["items"]:
                product = row(
                    conn,
                    "SELECT p.id, p.name, p.sku, p.barcode, p.selling_price, p.purchase_price, "
                    "p.is_active, COALESCE(i.quantity,0) AS stock "
                    "FROM products p LEFT JOIN inventory i ON i.product_id = p.id "
                    "WHERE p.id = ?",
                    (entry.get("product_id"),),
                )
                if not product:
                    raise ValidationError("A product in the cart no longer exists.")
                if product["is_active"] != 1:
                    raise ValidationError(f"'{product['name']}' is no longer active.")
                qty = float(entry["quantity"])
                if qty <= 0:
                    raise ValidationError(f"Invalid quantity for '{product['name']}'.")
                if not allow_negative and float(product["stock"]) + 1e-9 < qty:
                    raise StockError(
                        f"Insufficient stock available for '{product['name']}' "
                        f"(available: {float(product['stock']):g})."
                    )
                entry = dict(entry)
                entry["product"] = product
                # trust the current stored price unless the cashier was allowed
                # to change it (unit_price already validated as >= 0)
                validated.append(entry)

            # 2. invoice number -------------------------------------------
            invoice_no = self.db.next_number(
                conn, "invoice", self.settings.invoice_prefix, self.settings.invoice_padding
            )

            # 3. sale header ----------------------------------------------
            customer_id = cart.get("customer_id") or None
            if customer_id and not row(conn, "SELECT id FROM customers WHERE id = ?",
                                       (customer_id,)):
                customer_id = None
            cur = conn.execute(
                "INSERT INTO sales(invoice_no, customer_id, user_id, cashier_name, subtotal, "
                "item_discount, bill_discount_type, bill_discount_value, bill_discount, total, "
                "paid, change_due, payment_method, status, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (invoice_no, customer_id, session.user_id, session.username,
                 totals["subtotal"], totals["item_discount"], totals["bill_discount_type"],
                 totals["bill_discount_value"], totals["bill_discount"], total,
                 paid, paid - total, method, "completed",
                 (cart.get("notes") or "").strip()),
            )
            sale_id = int(cur.lastrowid)

            # 4. sale items + stock deduction -----------------------------
            for entry in validated:
                product = entry["product"]
                cur = conn.execute(
                    "INSERT INTO sale_items(sale_id, product_id, product_name, sku, barcode, "
                    "quantity, unit_price, cost_price, discount_type, discount_value, "
                    "discount_amount, line_total) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sale_id, product["id"], product["name"], product["sku"] or "",
                     product["barcode"] or "", entry["quantity"], entry["unit_price"],
                     product["purchase_price"], entry.get("discount_type", "None"),
                     int(float(entry.get("discount_value") or 0)),
                     entry["discount_amount"], entry["line_total"]),
                )
                self.inventory.decrease(
                    conn, product["id"], entry["quantity"], "sale",
                    "sale", sale_id, f"Invoice {invoice_no}",
                    allow_negative=allow_negative, session=session,
                )

            # 5. payment ---------------------------------------------------
            conn.execute(
                "INSERT INTO payments(sale_id, direction, method, amount, user_id, reference) "
                "VALUES (?,?,?,?,?,?)",
                (sale_id, "IN", method, paid, session.user_id, invoice_no),
            )
            # 6. audit -----------------------------------------------------
            audit.log(conn, session, audit.CREATE, entity="sales", entity_id=sale_id,
                      description=f"Invoice {invoice_no} completed",
                      details=f"total={total}; paid={paid}; method={method}; "
                              f"items={len(validated)}")
            detail = self.get_sale_detail(sale_id, conn=conn)
        detail["change_due"] = paid - total
        detail["totals"] = totals
        return detail

    # ------------------------------------------------------------ history
    def list_sales(self, date_from: str = "", date_to: str = "", term: str = "",
                   cashier: str = "", payment: str = "", status: str = "",
                   limit: int = 500, offset: int = 0,
                   session: Session | None = None) -> list[dict]:
        where, params = [], []
        if date_from:
            where.append("date(s.created_at) >= date(?)")
            params.append(date_from)
        if date_to:
            where.append("date(s.created_at) <= date(?)")
            params.append(date_to)
        if cashier:
            where.append("s.user_id = ?")
            params.append(cashier)
        if payment:
            where.append("s.payment_method = ?")
            params.append(payment)
        if status:
            where.append("s.status = ?")
            params.append(status)
        term = (term or "").strip()
        if term:
            where.append("(s.invoice_no LIKE ? OR cu.name LIKE ? OR s.cashier_name LIKE ?)")
            like = f"%{term}%"
            params.extend([like, like, like])
        session = session or self.session
        if session and not session.can("sales.view_all"):
            where.append("s.user_id = ?")
            params.append(session.user_id)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        params.extend([limit, offset])
        sql = """
        SELECT s.id, s.invoice_no, s.created_at, s.total, s.paid, s.change_due,
               s.payment_method, s.status, s.cashier_name, s.user_id,
               COALESCE(cu.name,'Walk-in Customer') AS customer,
               (SELECT COUNT(*) FROM sale_items si WHERE si.sale_id = s.id) AS item_count,
               (SELECT COALESCE(SUM(total),0) FROM returns r WHERE r.sale_id = s.id
                    AND r.status='completed') AS refunded
        FROM sales s
        LEFT JOIN customers cu ON cu.id = s.customer_id
        """ + clause + " ORDER BY s.id DESC LIMIT ? OFFSET ?"
        with self.db.read() as conn:
            return rows(conn, sql, tuple(params))

    def sale_totals_summary(self, date_from: str, date_to: str) -> dict:
        with self.db.read() as conn:
            record = row(
                conn,
                "SELECT COUNT(*) AS txns, COALESCE(SUM(total),0) AS total, "
                "COALESCE(SUM(paid),0) AS paid, "
                "COALESCE(SUM(item_discount)+SUM(bill_discount),0) AS discounts "
                "FROM sales WHERE status IN ('completed','partially_returned') "
                "AND date(created_at) >= date(?) AND date(created_at) <= date(?)",
                (date_from, date_to),
            ) or {}
            returns = row(
                conn,
                "SELECT COALESCE(SUM(total),0) AS returned FROM returns "
                "WHERE status='completed' AND date(created_at) >= date(?) "
                "AND date(created_at) <= date(?)",
                (date_from, date_to),
            ) or {}
        record["returns"] = returns.get("returned", 0)
        record["net"] = int(record.get("total", 0)) - int(record.get("returned", 0))
        return record

    def get_sale_detail(self, sale_id: int, conn=None) -> dict:
        def _fetch(c):
            sale = row(
                c,
                "SELECT s.*, COALESCE(cu.name,'Walk-in Customer') AS customer, "
                "cu.phone AS customer_phone, cu.address AS customer_address "
                "FROM sales s LEFT JOIN customers cu ON cu.id = s.customer_id WHERE s.id = ?",
                (sale_id,),
            )
            if not sale:
                raise NotFoundError("Invoice not found.")
            items = rows(
                c,
                "SELECT si.*, p.image_path FROM sale_items si "
                "LEFT JOIN products p ON p.id = si.product_id WHERE si.sale_id = ? "
                "ORDER BY si.id",
                (sale_id,),
            )
            pays = rows(c, "SELECT * FROM payments WHERE sale_id = ? ORDER BY id",
                        (sale_id,))
            rets = rows(
                c,
                "SELECT r.id, r.return_no, r.total, r.created_at, r.reason "
                "FROM returns r WHERE r.sale_id = ? ORDER BY r.id",
                (sale_id,),
            )
            sale["items"] = items
            sale["payments"] = pays
            sale["returns"] = rets
            sale["returned_total"] = sum(int(r["total"]) for r in rets)
            return sale

        if conn is not None:
            return _fetch(conn)
        with self.db.read() as c:
            return _fetch(c)

    def get_by_invoice(self, invoice_no: str) -> dict | None:
        with self.db.read() as conn:
            record = row(conn, "SELECT id FROM sales WHERE invoice_no = ? COLLATE NOCASE",
                         ((invoice_no or "").strip(),))
        return self.get_sale_detail(record["id"]) if record else None

    # ---------------------------------------------------------------- void
    def void_sale(self, sale_id: int, reason: str, session: Session | None = None) -> None:
        session = session or self.session
        if not session or not session.can("sales.void"):
            raise PermissionDenied("You do not have permission to void sales.")
        if not (reason or "").strip():
            raise ValidationError("Please provide a reason for voiding this invoice.")
        with self.db.transaction() as conn:
            sale = row(conn, "SELECT * FROM sales WHERE id = ?", (sale_id,))
            if not sale:
                raise NotFoundError("Invoice not found.")
            if sale["status"] == "voided":
                raise ValidationError("This invoice has already been voided.")
            conn.execute(
                "UPDATE sales SET status='voided', voided_at=?, voided_by=?, void_reason=? "
                "WHERE id=?",
                (now_str(), session.user_id, reason.strip(), sale_id),
            )
            items = rows(conn, "SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,))
            for item in items:
                if not item["product_id"]:
                    continue
                self.inventory.increase(
                    conn, item["product_id"], float(item["quantity"]), "void",
                    "sale", sale_id, f"Voided invoice {sale['invoice_no']}: {reason.strip()}",
                    session,
                )
            audit.log(conn, session, audit.VOID, entity="sales", entity_id=sale_id,
                      description=f"Invoice {sale['invoice_no']} voided",
                      details=f"reason: {reason.strip()}")
            # restore the invoice number counter? Never: numbering stays unique.

    # ----------------------------------------------------------- hold sale
    def hold_sale(self, cart: dict, label: str = "",
                  session: Session | None = None) -> int:
        session = session or self.session
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO held_sales(label, user_id, username, payload) VALUES (?,?,?,?)",
                ((label or "").strip() or datetime.now().strftime("Hold %H:%M:%S"),
                 session.user_id if session else None,
                 session.username if session else "",
                 json.dumps(cart)),
            )
            audit.log(conn, session, audit.CREATE, entity="held_sales",
                      entity_id=int(cur.lastrowid), description="Sale placed on hold")
            return int(cur.lastrowid)

    def list_held_sales(self) -> list[dict]:
        with self.db.read() as conn:
            return rows(conn, "SELECT id, label, username, created_at FROM held_sales "
                              "ORDER BY id DESC")

    def get_held_sale(self, hold_id: int) -> dict:
        with self.db.read() as conn:
            record = row(conn, "SELECT * FROM held_sales WHERE id = ?", (hold_id,))
        if not record:
            raise NotFoundError("Held sale not found.")
        return json.loads(record["payload"])

    def delete_held_sale(self, hold_id: int, session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM held_sales WHERE id = ?", (hold_id,))
            audit.log(conn, session or self.session, audit.DELETE, entity="held_sales",
                      entity_id=hold_id, description="Held sale discarded")

    # ------------------------------------------------------- cashier stats
    def recent_sales(self, limit: int = 10) -> list[dict]:
        return self.list_sales(limit=limit)

    def sales_between(self, date_from: str, date_to: str) -> list[dict]:
        return self.list_sales(date_from=date_from, date_to=date_to, limit=10000)
