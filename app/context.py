"""Application context: wires the database, services and the user session."""
from __future__ import annotations

from pathlib import Path

from . import config
from .core.db import Database
from .core.logging_setup import get_logger, setup_logging
from .core.security import Session
from .services.auth_service import AuthService
from .services.backup_service import BackupService
from .services.catalog_service import CatalogService
from .services.customer_service import CustomerService
from .services.csv_service import CsvService
from .services.dashboard_service import DashboardService
from .services.expense_service import ExpenseService
from .services.inventory_service import InventoryService
from .services.purchase_service import PurchaseService
from .services.receipt_service import ReceiptService
from .services.report_service import ReportService
from .services.return_service import ReturnService
from .services.sale_service import SaleService
from .services.settings_service import SettingsService
from .services.supplier_service import SupplierService

log = get_logger("context")


class AppContext:
    """Single composition root shared by every screen."""

    def __init__(self, db_path: Path | str | None = None):
        setup_logging()
        self.db = Database(db_path)
        self.db.initialize()
        self.settings = SettingsService(self.db)
        self.auth = AuthService(self.db, self.settings)
        self.session: Session | None = None

        # services (session is attached after login)
        self.customers = CustomerService(self.db)
        self.suppliers = SupplierService(self.db)
        self.catalog = CatalogService(self.db, self.settings)
        self.inventory = InventoryService(self.db, self.settings)
        self.expenses = ExpenseService(self.db)
        self.sales = SaleService(self.db, self.settings, self.inventory)
        self.purchases = PurchaseService(self.db, self.settings, self.inventory)
        self.returns = ReturnService(self.db, self.settings, self.inventory)
        self.reports = ReportService(self.db, self.settings, self.expenses, self.purchases)
        self.dashboard = DashboardService(self.db, self.settings, self.reports,
                                          self.inventory, self.expenses)
        self.csv = CsvService(self.db, self.catalog, self.inventory, self.settings)
        self.receipts = ReceiptService(self.db, self.settings)
        self.backups = BackupService(self.db, self.settings)
        self._session_services = (
            self.customers, self.suppliers, self.catalog, self.inventory,
            self.expenses, self.sales, self.purchases, self.returns, self.csv,
            self.backups,
        )

    # ---------------------------------------------------------------- session
    def login(self, username: str, password: str) -> Session:
        session = self.auth.login(username, password)
        self.session = session
        for service in self._session_services:
            service.session = session
        return session

    def logout(self) -> None:
        self.auth.logout()
        self.session = None
        for service in self._session_services:
            service.session = None

    def can(self, permission: str) -> bool:
        return bool(self.session and self.session.can(permission))

    def any(self, *permissions: str) -> bool:
        return bool(self.session and self.session.any(*permissions))

    @property
    def username(self) -> str:
        return self.session.username if self.session else ""

    # --------------------------------------------------------------- startup
    def run_startup_tasks(self) -> None:
        """Automatic backup scheduling and configuration sanity checks."""
        try:
            made = self.backups.auto_backup_if_due()
            if made:
                log.info("Automatic backup created: %s", made)
        except Exception as exc:  # never block start-up on a backup failure
            log.error("Automatic backup failed: %s", exc)

    @property
    def needs_setup(self) -> bool:
        return not self.settings.setup_completed

    @property
    def needs_user(self) -> bool:
        return not self.auth.has_user()

    def currency(self) -> str:
        return self.settings.currency
