"""Product catalogue: categories, brands, units and products."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from .. import config
from ..core import audit
from ..core.db import now_str, row, rows, scalar
from ..core.exceptions import ConflictError, NotFoundError, ValidationError
from ..core.money import to_minor
from ..core.security import Session

PRODUCT_SELECT = """
SELECT p.id, p.name, p.sku, p.barcode, p.purchase_price, p.selling_price,
       p.discount_type, p.discount_value, p.min_stock, p.max_stock, p.allow_decimal,
       p.description, p.image_path, p.is_active, p.created_at, p.updated_at,
       p.category_id, p.brand_id, p.unit_id, p.supplier_id,
       COALESCE(c.name,'') AS category, COALESCE(b.name,'') AS brand,
       COALESCE(u.name,'') AS unit, COALESCE(u.short_code,'') AS unit_short,
       COALESCE(s.name,'') AS supplier,
       COALESCE(i.quantity, 0) AS stock
FROM products p
LEFT JOIN categories c ON c.id = p.category_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN units u ON u.id = p.unit_id
LEFT JOIN suppliers s ON s.id = p.supplier_id
LEFT JOIN inventory i ON i.product_id = p.id
"""


class CatalogService:
    def __init__(self, db, settings=None, session: Session | None = None):
        self.db = db
        self.settings = settings
        self.session = session

    # ------------------------------------------------------------ lookups
    def _require(self, conn, product_id: int) -> dict:
        record = row(conn, PRODUCT_SELECT + "WHERE p.id = ?", (product_id,))
        if not record:
            raise NotFoundError("Product not found.")
        return record

    def get(self, product_id: int) -> dict:
        with self.db.read() as conn:
            return self._require(conn, product_id)

    def find_by_barcode(self, barcode: str) -> dict | None:
        """Indexed exact lookup used by the USB barcode scanner."""
        barcode = (barcode or "").strip()
        if not barcode:
            return None
        with self.db.read() as conn:
            return row(conn, PRODUCT_SELECT + "WHERE p.barcode = ? AND p.is_active = 1",
                       (barcode,))

    def find_by_sku(self, sku: str) -> dict | None:
        with self.db.read() as conn:
            return row(conn, PRODUCT_SELECT + "WHERE p.sku = ? COLLATE NOCASE AND p.is_active = 1",
                       ((sku or "").strip(),))

    def barcode_exists(self, barcode: str, exclude_id: int | None = None) -> bool:
        with self.db.read() as conn:
            sql = "SELECT 1 FROM products WHERE barcode = ? COLLATE NOCASE"
            params: list = [barcode.strip()]
            if exclude_id:
                sql += " AND id != ?"
                params.append(exclude_id)
            return row(conn, sql, tuple(params)) is not None

    # ------------------------------------------------------------- search
    def search(self, term: str = "", category_id: int | None = None,
               brand_id: int | None = None, supplier_id: int | None = None,
               active_only: bool = True, stock_status: str = "",
               limit: int = 200, offset: int = 0) -> list[dict]:
        where: list[str] = []
        params: list = []
        if active_only:
            where.append("p.is_active = 1")
        if category_id:
            where.append("p.category_id = ?")
            params.append(category_id)
        if brand_id:
            where.append("p.brand_id = ?")
            params.append(brand_id)
        if supplier_id:
            where.append("p.supplier_id = ?")
            params.append(supplier_id)
        term = (term or "").strip()
        if term:
            like = f"%{term}%"
            where.append(
                "(p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ? OR c.name LIKE ? "
                "OR b.name LIKE ?)"
            )
            params.extend([like] * 5)
        if stock_status == "low":
            where.append("COALESCE(i.quantity,0) > 0 AND COALESCE(i.quantity,0) <= p.min_stock")
        elif stock_status == "out":
            where.append("COALESCE(i.quantity,0) <= 0")
        elif stock_status == "in":
            where.append("COALESCE(i.quantity,0) > p.min_stock")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        params.extend([limit, offset])
        with self.db.read() as conn:
            return rows(
                conn,
                PRODUCT_SELECT + clause + " ORDER BY p.name LIMIT ? OFFSET ?",
                tuple(params),
            )

    def count(self, active_only: bool = True) -> int:
        with self.db.read() as conn:
            sql = "SELECT COUNT(*) FROM products"
            if active_only:
                sql += " WHERE is_active = 1"
            return int(scalar(conn, sql, (), 0))

    def all_for_export(self) -> list[dict]:
        with self.db.read() as conn:
            return rows(conn, PRODUCT_SELECT + " ORDER BY p.name")

    # --------------------------------------------------------------- CRUD
    @staticmethod
    def _validate(data: dict) -> dict:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValidationError("Product name is required.")
        if len(name) > 120:
            raise ValidationError("Product name is too long (max 120 characters).")
        purchase = to_minor(data.get("purchase_price", 0))
        selling = to_minor(data.get("selling_price", 0))
        if selling < 0 or purchase < 0:
            raise ValidationError("Prices cannot be negative.")
        if data.get("min_stock", 0) is None:
            data["min_stock"] = 0
        return {
            "name": name,
            "sku": (data.get("sku") or "").strip() or None,
            "barcode": (data.get("barcode") or "").strip() or None,
            "category_id": data.get("category_id") or None,
            "brand_id": data.get("brand_id") or None,
            "unit_id": data.get("unit_id") or None,
            "supplier_id": data.get("supplier_id") or None,
            "purchase_price": purchase,
            "selling_price": selling,
            "discount_type": data.get("discount_type") or "None",
            "discount_value": to_minor(data.get("discount_value", 0))
            if (data.get("discount_type") or "None") == "Fixed"
            else int(float(data.get("discount_value") or 0)),
            "min_stock": float(data.get("min_stock") or 0),
            "max_stock": float(data.get("max_stock") or 0),
            "allow_decimal": 1 if data.get("allow_decimal") else 0,
            "description": (data.get("description") or "").strip(),
            "image_path": (data.get("image_path") or "").strip(),
        }

    def _check_duplicates(self, data: dict, exclude_id: int | None = None) -> None:
        with self.db.read() as conn:
            if data["barcode"] and self.barcode_exists(data["barcode"], exclude_id):
                raise ConflictError(
                    f"Another product already uses barcode {data['barcode']}."
                )
            if data["sku"]:
                sql = "SELECT 1 FROM products WHERE sku = ? COLLATE NOCASE"
                params: list = [data["sku"]]
                if exclude_id:
                    sql += " AND id != ?"
                    params.append(exclude_id)
                if row(conn, sql, tuple(params)):
                    raise ConflictError(f"Another product already uses SKU {data['sku']}.")

    def create(self, data: dict, session: Session | None = None) -> int:
        clean = self._validate(data)
        self._check_duplicates(clean)
        opening = float(data.get("opening_stock") or 0)
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO products(name, sku, barcode, category_id, brand_id, unit_id, "
                "supplier_id, purchase_price, selling_price, discount_type, discount_value, "
                "min_stock, max_stock, allow_decimal, description, image_path) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (clean["name"], clean["sku"], clean["barcode"], clean["category_id"],
                 clean["brand_id"], clean["unit_id"], clean["supplier_id"],
                 clean["purchase_price"], clean["selling_price"], clean["discount_type"],
                 clean["discount_value"], clean["min_stock"], clean["max_stock"],
                 clean["allow_decimal"], clean["description"], clean["image_path"]),
            )
            product_id = int(cur.lastrowid)
            conn.execute("INSERT INTO inventory(product_id, quantity) VALUES (?,?)",
                         (product_id, opening))
            if opening:
                self._movement(conn, product_id, "initial", opening, opening,
                               session, "Opening stock")
            audit.log(conn, session or self.session, audit.CREATE, entity="products",
                      entity_id=product_id,
                      description=f"Product '{clean['name']}' created",
                      details=f"price={clean['selling_price']}")
            return product_id

    def update(self, product_id: int, data: dict, session: Session | None = None) -> None:
        clean = self._validate(data)
        self._check_duplicates(clean, exclude_id=product_id)
        with self.db.transaction() as conn:
            before = self._require(conn, product_id)
            conn.execute(
                "UPDATE products SET name=?, sku=?, barcode=?, category_id=?, brand_id=?, "
                "unit_id=?, supplier_id=?, purchase_price=?, selling_price=?, discount_type=?, "
                "discount_value=?, min_stock=?, max_stock=?, allow_decimal=?, description=?, "
                "image_path=?, updated_at=? WHERE id=?",
                (clean["name"], clean["sku"], clean["barcode"], clean["category_id"],
                 clean["brand_id"], clean["unit_id"], clean["supplier_id"],
                 clean["purchase_price"], clean["selling_price"], clean["discount_type"],
                 clean["discount_value"], clean["min_stock"], clean["max_stock"],
                 clean["allow_decimal"], clean["description"], clean["image_path"],
                 now_str(), product_id),
            )
            details = []
            if before["selling_price"] != clean["selling_price"]:
                details.append(f"selling price {before['selling_price']} -> {clean['selling_price']}")
            if before["purchase_price"] != clean["purchase_price"]:
                details.append(f"purchase price {before['purchase_price']} -> {clean['purchase_price']}")
            audit.log(conn, session or self.session, audit.UPDATE, entity="products",
                      entity_id=product_id,
                      description=f"Product '{clean['name']}' updated",
                      details="; ".join(details))

    def set_active(self, product_id: int, active: bool,
                   session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            record = self._require(conn, product_id)
            conn.execute("UPDATE products SET is_active = ?, updated_at = ? WHERE id = ?",
                         (1 if active else 0, now_str(), product_id))
            audit.log(conn, session or self.session,
                      audit.DELETE if not active else audit.UPDATE,
                      entity="products", entity_id=product_id,
                      description=f"Product '{record['name']}' "
                                  f"{'deactivated' if not active else 'reactivated'}")

    def delete(self, product_id: int, session: Session | None = None) -> None:
        """Soft delete: products referenced by sales are never hard-deleted."""
        self.set_active(product_id, False, session)

    # ------------------------------------------------------------ barcode
    @staticmethod
    def ean13_check_digit(first12: str) -> int:
        total = sum((int(d) if i % 2 == 0 else int(d) * 3) for i, d in enumerate(first12))
        return (10 - (total % 10)) % 10

    def generate_barcode(self, product_id: int, session: Session | None = None) -> str:
        """Assign an in-house EAN-13 style barcode only when none exists."""
        with self.db.transaction() as conn:
            record = self._require(conn, product_id)
            if record["barcode"]:
                return record["barcode"]
            base = f"20{product_id:011d}"[:12]
            barcode = base + str(self.ean13_check_digit(base))
            while self.barcode_exists(barcode, exclude_id=product_id):
                digits = str(int(barcode[:12]) + 1).zfill(12)
                barcode = digits + str(self.ean13_check_digit(digits))
            sku = record["sku"] or f"SKU-{product_id:06d}"
            conn.execute("UPDATE products SET barcode = ?, sku = ?, updated_at = ? "
                         "WHERE id = ?", (barcode, sku, now_str(), product_id))
            audit.log(conn, session or self.session, audit.UPDATE, entity="products",
                      entity_id=product_id,
                      description=f"Barcode {barcode} generated for '{record['name']}'")
            return barcode

    # ------------------------------------------------------------ images
    @staticmethod
    def store_image(source: str) -> str:
        src = Path(source)
        if not src.exists():
            raise ValidationError("The selected product image could not be found.")
        config.PRODUCT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        target = config.PRODUCT_IMAGE_DIR / f"{uuid.uuid4().hex}{src.suffix.lower()}"
        shutil.copy2(src, target)
        return str(target)

    # --------------------------------------------- reference data (CRUD)
    def categories(self, include_inactive: bool = False) -> list[dict]:
        with self.db.read() as conn:
            sql = ("SELECT c.*, (SELECT COUNT(*) FROM products WHERE category_id = c.id) AS product_count "
                   "FROM categories c")
            if not include_inactive:
                sql += " WHERE c.active = 1"
            return rows(conn, sql + " ORDER BY c.name")

    def save_category(self, name: str, category_id: int | None = None,
                      description: str = "", active: bool = True,
                      session: Session | None = None) -> int:
        name = name.strip()
        if not name:
            raise ValidationError("Category name is required.")
        with self.db.transaction() as conn:
            if row(conn, "SELECT id FROM categories WHERE name = ? COLLATE NOCASE "
                         "AND id != ?", (name, category_id or -1)):
                raise ConflictError(f"Category '{name}' already exists.")
            if category_id:
                conn.execute("UPDATE categories SET name=?, description=?, active=? "
                             "WHERE id=?",
                             (name, description.strip(), 1 if active else 0, category_id))
                audit.log(conn, session or self.session, audit.UPDATE, entity="categories",
                          entity_id=category_id, description=f"Category '{name}' updated")
                return category_id
            cur = conn.execute("INSERT INTO categories(name, description, active) VALUES (?,?,?)",
                               (name, description.strip(), 1 if active else 0))
            cat_id = int(cur.lastrowid)
            audit.log(conn, session or self.session, audit.CREATE, entity="categories",
                      entity_id=cat_id, description=f"Category '{name}' created")
            return cat_id

    def delete_category(self, category_id: int, session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            used = scalar(conn, "SELECT COUNT(*) FROM products WHERE category_id = ?",
                          (category_id,), 0)
            if used:
                raise ConflictError(
                    "This category is used by products. Reassign the products first."
                )
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            audit.log(conn, session or self.session, audit.DELETE, entity="categories",
                      entity_id=category_id, description="Category deleted")

    def brands(self, include_inactive: bool = False) -> list[dict]:
        with self.db.read() as conn:
            sql = "SELECT * FROM brands"
            if not include_inactive:
                sql += " WHERE active = 1"
            return rows(conn, sql + " ORDER BY name")

    def save_brand(self, name: str, brand_id: int | None = None,
                   session: Session | None = None) -> int:
        name = name.strip()
        if not name:
            raise ValidationError("Brand name is required.")
        with self.db.transaction() as conn:
            if row(conn, "SELECT id FROM brands WHERE name = ? COLLATE NOCASE AND id != ?",
                   (name, brand_id or -1)):
                raise ConflictError(f"Brand '{name}' already exists.")
            if brand_id:
                conn.execute("UPDATE brands SET name = ? WHERE id = ?", (name, brand_id))
                return brand_id
            return int(conn.execute("INSERT INTO brands(name) VALUES (?)",
                                    (name,)).lastrowid)

    def delete_brand(self, brand_id: int, session: Session | None = None) -> None:
        with self.db.transaction() as conn:
            used = scalar(conn, "SELECT COUNT(*) FROM products WHERE brand_id = ?",
                          (brand_id,), 0)
            if used:
                raise ConflictError("This brand is used by products.")
            conn.execute("DELETE FROM brands WHERE id = ?", (brand_id,))

    def units(self) -> list[dict]:
        with self.db.read() as conn:
            return rows(conn, "SELECT * FROM units ORDER BY name")

    def save_unit(self, name: str, short_code: str = "", unit_id: int | None = None) -> int:
        name = name.strip()
        if not name:
            raise ValidationError("Unit name is required.")
        with self.db.transaction() as conn:
            if row(conn, "SELECT id FROM units WHERE name = ? COLLATE NOCASE AND id != ?",
                   (name, unit_id or -1)):
                raise ConflictError(f"Unit '{name}' already exists.")
            if unit_id:
                conn.execute("UPDATE units SET name = ?, short_code = ? WHERE id = ?",
                             (name, short_code.strip(), unit_id))
                return unit_id
            return int(conn.execute("INSERT INTO units(name, short_code) VALUES (?,?)",
                                    (name, short_code.strip())).lastrowid)

    # -------------------------------------------------------------- shared
    @staticmethod
    def _movement(conn, product_id: int, movement: str, change: float, after: float,
                  session: Session | None, note: str = "") -> None:
        conn.execute(
            "INSERT INTO stock_movements(product_id, movement, quantity_change, "
            "quantity_after, user_id, username, note) VALUES (?,?,?,?,?,?,?)",
            (product_id, movement, change, after,
             session.user_id if session else None,
             session.username if session else "", note),
        )
