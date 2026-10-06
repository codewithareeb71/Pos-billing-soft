# ALSHAN POS SYSTEM

Offline desktop **Point of Sale, Billing and Inventory** software for retail shops.
Python + PySide6 (Qt) + SQLite - no cloud, no subscription, no internet required
after installation.

---

## 1. What is included

| Area | Highlights |
| --- | --- |
| **POS billing** | USB barcode scanner workflow, fast product search, quantities & discounts, bill discount, hold/recall sales (F9), cash tendering with change, receipt printing |
| **Catalogue** | Products, categories, brands, units, EAN-13/UPC/Code-128 barcode generation, barcode **label printing**, CSV import/export |
| **Inventory** | Live stock, low/out-of-stock alerts, stock value, manual adjustments with reasons, full movement history |
| **Purchases** | Supplier purchase orders that increase stock and record payments/balances |
| **Sales** | Invoice history, reprint, **returns** (partial or full, stock restored), **voids** with reason, audit trail |
| **Partners** | Customers (purchase history, lifetime value) and suppliers (purchases, outstanding balance, payments) |
| **Expenses** | Categorised expenses that feed into net profit |
| **Reports** | 14 reports: daily/weekly/monthly sales, invoices, product sales, profit, purchases, inventory, low stock, out of stock, customers, suppliers, expenses, cashier performance - all printable and exportable |
| **Security** | Roles & permission matrix, PBKDF2 password hashing, login lockout, audit log of every critical action |
| **Backup** | Manual + automatic backups (daily/weekly) with retention, validated restore with automatic safety backup |
| **Setup** | First-run wizard (shop, receipt, administrator), Settings screen for everything else |

**Keyboard shortcuts**

| Key | Action | Key | Action |
| --- | --- | --- | --- |
| `F1` | New sale | `F6` | Focus the barcode field |
| `F2` | Product search | `F8` | Complete sale |
| `F4` | Select customer | `F9` | Hold sale |
| `ESC` | Cancel / close | `Enter` | Scan / confirm |

---

## 2. Running the application (developer)

```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py          (or double-click run.bat)
```

Requirements: **Python 3.11+**, `PySide6`, `python-barcode`.

### First launch

1. The **setup wizard** opens automatically - shop name, receipt settings and the
   first administrator account.
2. From then on you sign in with your own username and password.
3. An `admin / admin` account only exists when the installer creates it; the
   wizard is the normal path.

---

## 3. Tests

```bat
python tests\smoke_test.py       :: business layer  (50 checks)
python tests\ui_smoke_test.py    :: every screen, off-screen Qt (26 checks)
```

Both suites write to a temporary data folder (`ALSHAN_DATA_DIR`) and never touch
your real database.

---

## 4. Building the installer

```bat
pip install pyinstaller
build\build.bat
```

The script runs the tests, generates the icon, builds

```
dist\ALSHAN_POS_SYSTEM\ALSHAN_POS_SYSTEM.exe     <- portable folder
build\Setup_ALSHAN_POS_SYSTEM_v1.0.0.exe         <- installer (needs Inno Setup 6)
```

The installer is per-user (`%LOCALAPPDATA%\Programs\AlshanPOS`), needs **no
administrator rights**, no Python, no SQLite, and installs desktop/start-menu
shortcuts. Uninstalling keeps the shop's database.

---

## 5. Where the data lives

| What | Location |
| --- | --- |
| Database | `%LOCALAPPDATA%\AlshanPOS\alshan_pos.db` |
| Backups | `%LOCALAPPDATA%\AlshanPOS\backups\` |
| Logs | `%LOCALAPPDATA%\AlshanPOS\logs\` |
| Product images / logo | `%LOCALAPPDATA%\AlshanPOS\assets\` |

Everything is created automatically on first run. Copy the whole `AlshanPOS`
folder to move the shop to another computer.

**Money is stored as integers (paisa)** - no floating point is ever used for
amounts, so totals are exact to the last paisa.

---

## 6. Hardware notes

**Barcode scanner (USB, keyboard-emulating)**
* No driver needed: the scanner types the code and presses `Enter`.
* Scan on the POS screen - the field refocuses automatically after every scan.
* Test it in **Settings → Hardware → Barcode scanner test**.
* If nothing appears, configure the scanner's *CR* (Enter) suffix or try another
  USB port.

**Receipt printer**
* Settings → Receipt: choose the printer, 58 mm or 80 mm paper, header/footer,
  optional logo/barcode/address/cashier lines, and a *Print test receipt* button.
* Any Windows printer works (thermal, inkjet, or "Microsoft Print to PDF" for
  testing).

**Barcode labels**
* Products → *Print barcodes*: pick size (default 50 × 30 mm), preview, print.

---

## 7. Project layout

```
app\
  config.py            paths, constants, shortcut table
  context.py           AppContext - single composition root (services + session)
  main.py              start-up: theme -> context -> setup -> login -> window
  core\                db, schema, money, security, audit, logging, exceptions
  services\            settings, auth, catalog, inventory, sale, purchase,
                       return, customer, supplier, expense, report, dashboard,
                       backup, csv, receipt
  ui\                  theme, icons, widgets, login, setup wizard, main window
  ui\pages\            dashboard, pos, products, inventory, purchases,
                       customers, suppliers, sales, returns, expenses,
                       reports, users, settings
tests\                 smoke_test.py, ui_smoke_test.py
build\                 build.bat, alshan_pos.iss (Inno Setup)
assets\                generate_icon.py -> alshan_pos.ico / .png
```

---

## 8. Licence

MIT - see `LICENSE`.
