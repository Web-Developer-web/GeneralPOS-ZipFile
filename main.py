import sys

from PySide6.QtWidgets import QApplication, QStyleFactory

from app import config, licensing
from app.backup import ensure_daily_backup
from app.branding import build_app_icon
from app.database import Database
from app.theme import theme_manager, build_stylesheet, build_qpalette
from app.windows.auth_window import AuthWindow
from app.windows.license_window import LicenseLockedWindow
from app.windows.main_window import MainWindow

if sys.platform == "win32":
    # Without an explicit AppUserModelID, Windows associates the running
    # process with python.exe's own identity - which is exactly what makes
    # the taskbar/Alt+Tab fall back to showing the Python logo instead of
    # our window icon. Setting our own ID before any window is created
    # fixes that association.
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "HotelPOS.HotelPOS.POS.1"
        )
    except Exception:
        pass


class Application:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName(config.APP_NAME)
        self.app.setOrganizationName(config.ORG_NAME)
        self.app_icon = build_app_icon()
        self.app.setWindowIcon(self.app_icon)

        # Force the fully Qt-drawn Fusion style instead of the native Windows
        # style. The native style pulls some chrome (combobox popups, spin
        # buttons, calendar, scrollbars) straight from the OS theme, which is
        # what made light mode unreadable on machines with Windows dark mode
        # enabled - Fusion always renders strictly from our own QPalette.
        self.app.setStyle(QStyleFactory.create("Fusion"))

        self.db = Database()
        ensure_daily_backup(self.db.conn)

        theme_manager.theme = self.db.get_settings()["theme"]
        self.app.setPalette(build_qpalette(theme_manager.theme))
        self.app.setStyleSheet(build_stylesheet(theme_manager.theme))

        self.main_window = None
        self.auth_window = None
        self.license_window = None

        self.check_license()

    def check_license(self):
        status = licensing.get_status(self.db)
        if status["state"] in ("expired", "invalid"):
            self.license_window = LicenseLockedWindow(self.db, status)
            self.license_window.setWindowIcon(self.app_icon)
            self.license_window.activated.connect(self._on_license_activated)
            self.license_window.show()
        else:
            self.show_auth_window()

    def _on_license_activated(self):
        self.license_window.close()
        self.license_window = None
        self.show_auth_window()

    def show_auth_window(self):
        if self.main_window:
            self.main_window.close()
            self.main_window = None

        self.auth_window = AuthWindow(self.db)
        self.auth_window.setWindowIcon(self.app_icon)
        self.auth_window.authenticated.connect(self.on_authenticated)
        self.auth_window.show()

    def on_authenticated(self, user):
        self.auth_window.close()
        self.auth_window = None

        self.main_window = MainWindow(self.db, user, self.app)
        self.main_window.setWindowIcon(self.app_icon)
        self.main_window.logout_requested.connect(self.on_logout)
        self.main_window.show()

    def on_logout(self):
        self.show_auth_window()

    def run(self):
        exit_code = self.app.exec()
        self.db.close()
        sys.exit(exit_code)


def main():
    application = Application()
    application.run()


if __name__ == "__main__":
    main()
