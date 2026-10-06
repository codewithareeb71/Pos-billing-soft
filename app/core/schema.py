"""Database schema (DDL) and seed data.

The schema is idempotent: it is executed with `IF NOT EXISTS` guards on
every launch, which doubles as automatic migration for fresh installs and
upgrades.
"""
from __future__ import annotations

SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- ------------------------------------------------------------------ security
CREATE TABLE IF NOT EXISTS roles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT NOT NULL DEFAULT '',
    is_system   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS permissions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    module      TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    username             TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash        TEXT NOT NULL,
    full_name            TEXT NOT NULL DEFAULT '',
    role_id              INTEGER NOT NULL REFERENCES roles(id),
    email                TEXT NOT NULL DEFAULT '',
    phone                TEXT NOT NULL DEFAULT '',
    active               INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    last_login           TEXT
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL,
    succeeded  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_login_attempts_user ON login_attempts(username, created_at);

-- ---------------------------------------------------------------- catalogue
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT NOT NULL DEFAULT '',
    parent_id   INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS brands (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS units (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    short_code TEXT NOT NULL DEFAULT '' UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS suppliers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL COLLATE NOCASE,
    company    TEXT NOT NULL DEFAULT '',
    phone      TEXT NOT NULL DEFAULT '',
    whatsapp   TEXT NOT NULL DEFAULT '',
    address    TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT '',
    notes      TEXT NOT NULL DEFAULT '',
    balance    INTEGER NOT NULL DEFAULT 0,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_suppliers_name ON suppliers(name);

CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL COLLATE NOCASE,
    phone       TEXT NOT NULL DEFAULT '',
    whatsapp    TEXT NOT NULL DEFAULT '',
    address     TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    is_walkin   INTEGER NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_customers_name ON customers(name);
CREATE INDEX IF NOT EXISTS ix_customers_phone ON customers(phone);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    sku             TEXT UNIQUE COLLATE NOCASE,
    barcode         TEXT UNIQUE COLLATE NOCASE,
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    brand_id        INTEGER REFERENCES brands(id) ON DELETE SET NULL,
    unit_id         INTEGER REFERENCES units(id) ON DELETE SET NULL,
    supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    purchase_price  INTEGER NOT NULL DEFAULT 0,
    selling_price   INTEGER NOT NULL DEFAULT 0,
    discount_type   TEXT NOT NULL DEFAULT 'None',
    discount_value  INTEGER NOT NULL DEFAULT 0,
    min_stock       REAL NOT NULL DEFAULT 0,
    max_stock       REAL NOT NULL DEFAULT 0,
    allow_decimal   INTEGER NOT NULL DEFAULT 0,
    description     TEXT NOT NULL DEFAULT '',
    image_path      TEXT NOT NULL DEFAULT '',
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_products_name ON products(name);
CREATE INDEX IF NOT EXISTS ix_products_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS ix_products_sku ON products(sku);
CREATE INDEX IF NOT EXISTS ix_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS ix_products_brand ON products(brand_id);
CREATE INDEX IF NOT EXISTS ix_products_active ON products(is_active);

CREATE TABLE IF NOT EXISTS inventory (
    product_id INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    quantity   REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_inventory_qty ON inventory(quantity);

CREATE TABLE IF NOT EXISTS stock_movements (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    movement       TEXT NOT NULL,
    quantity_change REAL NOT NULL,
    quantity_after REAL NOT NULL,
    reference_type TEXT NOT NULL DEFAULT '',
    reference_id   INTEGER,
    user_id        INTEGER,
    username       TEXT NOT NULL DEFAULT '',
    note           TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_stock_movements_product ON stock_movements(product_id, created_at);
CREATE INDEX IF NOT EXISTS ix_stock_movements_ref ON stock_movements(reference_type, reference_id);

-- ----------------------------------------------------------------- trading
CREATE TABLE IF NOT EXISTS sales (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no        TEXT NOT NULL UNIQUE,
    customer_id       INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    user_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    cashier_name      TEXT NOT NULL DEFAULT '',
    subtotal          INTEGER NOT NULL DEFAULT 0,
    item_discount     INTEGER NOT NULL DEFAULT 0,
    bill_discount_type TEXT NOT NULL DEFAULT 'None',
    bill_discount_value INTEGER NOT NULL DEFAULT 0,
    bill_discount     INTEGER NOT NULL DEFAULT 0,
    total             INTEGER NOT NULL DEFAULT 0,
    paid              INTEGER NOT NULL DEFAULT 0,
    change_due        INTEGER NOT NULL DEFAULT 0,
    payment_method    TEXT NOT NULL DEFAULT 'Cash',
    status            TEXT NOT NULL DEFAULT 'completed',
    notes             TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    voided_at         TEXT,
    voided_by         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    void_reason       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_sales_created ON sales(created_at);
CREATE INDEX IF NOT EXISTS ix_sales_customer ON sales(customer_id);
CREATE INDEX IF NOT EXISTS ix_sales_user ON sales(user_id);
CREATE INDEX IF NOT EXISTS ix_sales_status ON sales(status);

CREATE TABLE IF NOT EXISTS sale_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id           INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id        INTEGER REFERENCES products(id) ON DELETE SET NULL,
    product_name      TEXT NOT NULL,
    sku               TEXT NOT NULL DEFAULT '',
    barcode           TEXT NOT NULL DEFAULT '',
    quantity          REAL NOT NULL DEFAULT 1,
    unit_price        INTEGER NOT NULL DEFAULT 0,
    cost_price        INTEGER NOT NULL DEFAULT 0,
    discount_type     TEXT NOT NULL DEFAULT 'None',
    discount_value    INTEGER NOT NULL DEFAULT 0,
    discount_amount   INTEGER NOT NULL DEFAULT 0,
    line_total        INTEGER NOT NULL DEFAULT 0,
    returned_qty      REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_sale_items_sale ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS ix_sale_items_product ON sale_items(product_id);

CREATE TABLE IF NOT EXISTS payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id     INTEGER REFERENCES sales(id) ON DELETE CASCADE,
    purchase_id INTEGER REFERENCES purchases(id) ON DELETE CASCADE,
    return_id   INTEGER REFERENCES returns(id) ON DELETE CASCADE,
    direction   TEXT NOT NULL DEFAULT 'IN',
    method      TEXT NOT NULL DEFAULT 'Cash',
    amount      INTEGER NOT NULL DEFAULT 0,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reference   TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_payments_sale ON payments(sale_id);
CREATE INDEX IF NOT EXISTS ix_payments_created ON payments(created_at);

CREATE TABLE IF NOT EXISTS purchases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_no   TEXT NOT NULL UNIQUE,
    supplier_id   INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    user_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    purchase_date TEXT NOT NULL DEFAULT (date('now','localtime')),
    subtotal      INTEGER NOT NULL DEFAULT 0,
    discount      INTEGER NOT NULL DEFAULT 0,
    total         INTEGER NOT NULL DEFAULT 0,
    paid          INTEGER NOT NULL DEFAULT 0,
    balance       INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'received',
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_purchases_date ON purchases(purchase_date);
CREATE INDEX IF NOT EXISTS ix_purchases_supplier ON purchases(supplier_id);

CREATE TABLE IF NOT EXISTS purchase_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id  INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    product_id   INTEGER REFERENCES products(id) ON DELETE SET NULL,
    product_name TEXT NOT NULL,
    quantity     REAL NOT NULL DEFAULT 1,
    unit_price   INTEGER NOT NULL DEFAULT 0,
    line_total   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_purchase_items_purchase ON purchase_items(purchase_id);
CREATE INDEX IF NOT EXISTS ix_purchase_items_product ON purchase_items(product_id);

CREATE TABLE IF NOT EXISTS returns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    return_no     TEXT NOT NULL UNIQUE,
    sale_id       INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    customer_id   INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    user_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reason        TEXT NOT NULL DEFAULT '',
    refund_method TEXT NOT NULL DEFAULT 'Cash',
    subtotal      INTEGER NOT NULL DEFAULT 0,
    total         INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'completed',
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_returns_sale ON returns(sale_id);
CREATE INDEX IF NOT EXISTS ix_returns_created ON returns(created_at);

CREATE TABLE IF NOT EXISTS return_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id      INTEGER NOT NULL REFERENCES returns(id) ON DELETE CASCADE,
    sale_item_id   INTEGER NOT NULL REFERENCES sale_items(id) ON DELETE CASCADE,
    product_id     INTEGER REFERENCES products(id) ON DELETE SET NULL,
    product_name   TEXT NOT NULL,
    quantity       REAL NOT NULL DEFAULT 1,
    unit_price     INTEGER NOT NULL DEFAULT 0,
    discount_amount INTEGER NOT NULL DEFAULT 0,
    refund_amount  INTEGER NOT NULL DEFAULT 0,
    reason         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_return_items_return ON return_items(return_id);

CREATE TABLE IF NOT EXISTS expenses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    category       TEXT NOT NULL DEFAULT 'General',
    amount         INTEGER NOT NULL DEFAULT 0,
    expense_date   TEXT NOT NULL DEFAULT (date('now','localtime')),
    payment_method TEXT NOT NULL DEFAULT 'Cash',
    notes          TEXT NOT NULL DEFAULT '',
    user_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_expenses_date ON expenses(expense_date);
CREATE INDEX IF NOT EXISTS ix_expenses_category ON expenses(category);

-- --------------------------------------------------------- system / support
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_by TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    username    TEXT NOT NULL DEFAULT '',
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL DEFAULT '',
    entity_id   TEXT,
    description TEXT NOT NULL DEFAULT '',
    details     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS ix_audit_user ON audit_logs(username);

CREATE TABLE IF NOT EXISTS backups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT NOT NULL,
    filename   TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    kind       TEXT NOT NULL DEFAULT 'manual',
    status     TEXT NOT NULL DEFAULT 'ok',
    note       TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS held_sales (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    label      TEXT NOT NULL DEFAULT '',
    user_id    INTEGER,
    username   TEXT NOT NULL DEFAULT '',
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS counters (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------
PERMISSIONS = [
    # code, module, description
    ("dashboard.view", "Dashboard", "View the dashboard"),
    ("sales.create", "Sales", "Create new sales at the POS"),
    ("sales.view", "Sales", "View own sales history"),
    ("sales.view_all", "Sales", "View all cashiers' sales"),
    ("sales.reprint", "Sales", "Reprint receipts"),
    ("sales.void", "Sales", "Void / cancel a sale"),
    ("returns.process", "Returns", "Process product returns"),
    ("products.view", "Products", "View products"),
    ("products.create", "Products", "Add products"),
    ("products.edit", "Products", "Edit products"),
    ("products.deactivate", "Products", "Deactivate / delete products"),
    ("products.import", "Products", "Import products from CSV"),
    ("products.export", "Products", "Export products to CSV"),
    ("products.barcode", "Products", "Generate and print barcodes"),
    ("inventory.view", "Inventory", "View inventory"),
    ("inventory.adjust", "Inventory", "Adjust stock levels"),
    ("purchases.view", "Purchases", "View purchases"),
    ("purchases.create", "Purchases", "Record purchases"),
    ("customers.view", "Customers", "View customers"),
    ("customers.manage", "Customers", "Add / edit customers"),
    ("suppliers.view", "Suppliers", "View suppliers"),
    ("suppliers.manage", "Suppliers", "Add / edit suppliers"),
    ("expenses.view", "Expenses", "View expenses"),
    ("expenses.manage", "Expenses", "Record / edit expenses"),
    ("reports.view", "Reports", "View operational reports"),
    ("reports.financial", "Reports", "View profit and financial reports"),
    ("reports.export", "Reports", "Export reports"),
    ("discount.standard", "Sales", "Apply standard discounts"),
    ("discount.high", "Sales", "Apply high value discounts"),
    ("users.view", "Users", "View users"),
    ("users.manage", "Users", "Manage users, roles and permissions"),
    ("settings.view", "Settings", "View settings"),
    ("settings.edit", "Settings", "Change settings"),
    ("database.backup", "Database", "Create backups"),
    ("database.restore", "Database", "Restore the database"),
    ("audit.view", "Audit", "View the audit log"),
]

ADMIN_PERMISSIONS = [p[0] for p in PERMISSIONS]

CASHIER_PERMISSIONS = [
    "dashboard.view",
    "sales.create",
    "sales.view",
    "sales.reprint",
    "returns.process",
    "products.view",
    "customers.view",
    "customers.manage",
    "expenses.view",
    "reports.view",
    "discount.standard",
]

DEFAULT_UNITS = [
    ("Piece", "pcs"),
    ("Box", "box"),
    ("Pack", "pack"),
    ("Kilogram", "kg"),
    ("Litre", "ltr"),
    ("Dozen", "dzn"),
]

DEFAULT_SETTINGS = {
    "setup_completed": "0",
    "shop.name": "",
    "shop.address": "",
    "shop.phone": "",
    "shop.email": "",
    "shop.logo": "",
    "currency": "PKR",
    "invoice.prefix": "ALS",
    "invoice.padding": "6",
    "return.prefix": "RET",
    "purchase.prefix": "PUR",
    "receipt.width_mm": "80",
    "receipt.printer": "",
    "receipt.header": "",
    "receipt.footer": "Thank you for shopping with us.",
    "receipt.show_logo": "1",
    "receipt.show_barcode": "1",
    "receipt.show_address": "1",
    "receipt.show_phone": "1",
    "receipt.show_cashier": "1",
    "receipt.show_customer": "1",
    "receipt.show_sku": "0",
    "pos.auto_focus_barcode": "1",
    "pos.default_payment_method": "Cash",
    "pos.allow_negative_stock": "0",
    "pos.require_customer": "0",
    "pos.beep_on_scan": "1",
    "pos.show_product_images": "1",
    "pos.discount_threshold_percent": "10",
    "pos.discount_threshold_amount": "1000",
    "inventory.low_stock_alert": "1",
    "backup.mode": "manual",
    "backup.retention": "7",
    "backup.last_run": "",
    "backup.auto_time": "02:00",
    "security.lockout_attempts": "8",
    "security.lockout_minutes": "5",
}
