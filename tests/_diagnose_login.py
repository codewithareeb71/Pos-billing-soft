"""Diagnostic: inspect the live production database after the sign-in failure."""
import os
import sqlite3
from pathlib import Path

db_path = Path(os.environ["LOCALAPPDATA"]) / "AlshanPOS" / "alshan_pos.db"
print("database:", db_path, "exists:", db_path.exists())
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

print("\nusers:")
for r in conn.execute(
        "SELECT id, username, full_name, role_id, active, must_change_password, "
        "created_at, last_login FROM users"):
    print("  ", dict(r))

print("\nsettings (setup/shop):")
for r in conn.execute(
        "SELECT key, value FROM settings "
        "WHERE key IN ('setup_completed', 'shop.name', 'currency')"):
    print("  ", dict(r))

print("\nlogin_attempts rows:", conn.execute(
    "SELECT COUNT(*) FROM login_attempts").fetchone()[0])

print("\naudit_logs (last 10):")
for r in conn.execute(
        "SELECT created_at, username, action, entity, description "
        "FROM audit_logs ORDER BY id DESC LIMIT 10"):
    print("  ", dict(r))

conn.close()
