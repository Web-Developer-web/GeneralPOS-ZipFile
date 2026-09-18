"""Main application window: sidebar navigation + stacked pages."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget

from app.core import config
from app.core.database import Database
from app.ui.theme import theme_manager
from app.ui.widgets.sidebar import Sidebar
from app.ui.widgets.animations import crossfade_stack
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.items_page import ItemsPage
from app.ui.pages.billing_page import BillingPage
from app.ui.pages.reports_page import ReportsPage
from app.ui.pages.backup_page import BackupPage
from app.ui.pages.settings_page import SettingsPage


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, db: Database, user, app):
        super().__init__()
        self.db = db
        self.user = user
        self.app = app

        self.setWindowTitle(f"{config.APP_NAME} — {db.get_settings()['hotel_name']}")
        self.resize(1300, 800)
        self.setMinimumSize(1000, 650)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(db.get_settings()["hotel_name"], user["full_name"], user["role"])
        self.sidebar.navigate.connect(self.navigate)
        self.sidebar.logout_requested.connect(self.logout_requested.emit)
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.dashboard_page = DashboardPage(db, user)
        self.items_page = ItemsPage(db)
        self.billing_page = BillingPage(db, user)
        self.reports_page = ReportsPage(db)
        self.backup_page = BackupPage(db)
        self.settings_page = SettingsPage(db, user)
        self.settings_page.theme_changed.connect(self.change_theme)

        self.pages = {
            "dashboard": self.dashboard_page,
            "items": self.items_page,
            "billing": self.billing_page,
            "reports": self.reports_page,
            "backup": self.backup_page,
            "settings": self.settings_page,
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        if user["role"] != config.ROLE_ADMIN:
            self.sidebar.set_nav_visible("items", False)
            self.sidebar.set_nav_visible("backup", False)

        self.sidebar.set_active("dashboard")
        self.navigate("dashboard")

    def navigate(self, key: str):
        page = self.pages.get(key)
        if not page:
            return
        if hasattr(page, "refresh"):
            page.refresh()
        crossfade_stack(self.stack, page)

    def change_theme(self, theme: str):
        theme_manager.set_theme(theme, self.app)
        self.db.update_settings(theme=theme)

    def apply_hotel_name(self):
        name = self.db.get_settings()["hotel_name"]
        self.sidebar.set_hotel_name(name)
        self.setWindowTitle(f"{config.APP_NAME} — {name}")
