"""Sidebar navigation widget for the main application window."""
import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup,
    QFrame,
)

from app.widgets.message_box import AppMessageBox
from app.widgets.nav_button import NavButton

NAV_ITEMS = [
    # (key, label, icon, accent) - each section gets its own signature glow
    # color instead of a single flat blue, so the active item reads as more
    # vibrant and the sections feel visually distinct at a glance.
    ("dashboard", "Dashboard", "fa5s.th-large", "#2563eb"),
    ("items", "Item Management", "fa5s.box-open", "#d97706"),
    ("billing", "Billing", "fa5s.cash-register", "#16a34a"),
    ("reports", "Reports", "fa5s.chart-line", "#7c3aed"),
    ("backup", "Backup", "fa5s.database", "#0891b2"),
    ("settings", "Settings", "fa5s.cog", "#db2777"),
]


class Sidebar(QWidget):
    navigate = Signal(str)
    logout_requested = Signal()

    def __init__(self, hotel_name: str, user_full_name: str, role: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        # QWidget (unlike QFrame or a top-level window) does not paint its
        # own stylesheet background unless this attribute is set - without
        # it the "#sidebar { background-color: ... }" rule below is silently
        # ignored, and the page's own background shows through instead. In
        # dark theme that happened to look close enough to pass unnoticed,
        # but in light theme it left the sidebar's white text/icons sitting
        # on a near-white background, unreadable.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(252)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(6)

        brand_row = QHBoxLayout()
        self.brand_icon = QLabel()
        from app.branding import build_app_icon
        self.brand_icon.setPixmap(build_app_icon().pixmap(28, 28))
        brand_row.addWidget(self.brand_icon)
        self.brand_label = QLabel(hotel_name)
        self.brand_label.setStyleSheet("font-size: 16px; font-weight: 700; color: white;")
        self.brand_label.setWordWrap(True)
        brand_row.addWidget(self.brand_label, 1)
        layout.addLayout(brand_row)
        layout.addSpacing(20)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self._buttons = {}
        self._icons = {}

        for key, label, icon, accent in NAV_ITEMS:
            btn = NavButton(f"   {label}", accent=accent)
            btn.setProperty("nav", "true")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(42)
            btn.setIcon(qta.icon(icon, color="#9ca3af"))
            btn.clicked.connect(lambda _c=False, k=key: self._on_nav_clicked(k))
            self.button_group.addButton(btn)
            self._buttons[key] = btn
            self._icons[key] = icon
            layout.addWidget(btn)

        layout.addStretch()

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #1f2937;")
        layout.addWidget(divider)
        layout.addSpacing(8)

        user_row = QHBoxLayout()
        avatar = QLabel()
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            "background-color: #2563eb; border-radius: 18px; color: white; font-weight: 700;"
        )
        initials = "".join([p[0].upper() for p in user_full_name.split()[:2]]) or "U"
        avatar.setText(initials)
        user_row.addWidget(avatar)

        name_col = QVBoxLayout()
        name_col.setSpacing(0)
        name_label = QLabel(user_full_name)
        name_label.setStyleSheet("color: white; font-weight: 600; font-size: 12px;")
        role_label = QLabel(role)
        role_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        name_col.addWidget(name_label)
        name_col.addWidget(role_label)
        user_row.addLayout(name_col)
        user_row.addStretch()
        layout.addLayout(user_row)

        logout_btn = QPushButton("   Logout")
        logout_btn.setProperty("nav", "true")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setIcon(qta.icon("fa5s.sign-out-alt", color="#f87171"))
        logout_btn.setMinimumHeight(40)
        logout_btn.clicked.connect(self._on_logout_clicked)
        layout.addSpacing(8)
        layout.addWidget(logout_btn)

    def _on_logout_clicked(self):
        confirmed = AppMessageBox.question(
            self, "Confirm Logout", "Are you sure you want to logout?",
            yes_text="Logout", no_text="Cancel",
        )
        if confirmed:
            AppMessageBox.success(self, "Logged Out", "You have been logged out successfully.")
            self.logout_requested.emit()

    def _on_nav_clicked(self, key: str):
        self.set_active(key)
        self.navigate.emit(key)

    def set_active(self, key: str):
        btn = self._buttons.get(key)
        if btn:
            btn.setChecked(True)
        for k, b in self._buttons.items():
            color = "white" if k == key else "#9ca3af"
            b.setIcon(qta.icon(self._icons[k], color=color))

    def set_nav_visible(self, key: str, visible: bool):
        btn = self._buttons.get(key)
        if btn:
            btn.setVisible(visible)

    def set_hotel_name(self, name: str):
        self.brand_label.setText(name)
