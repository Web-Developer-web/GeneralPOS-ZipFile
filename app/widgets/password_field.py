"""GlowLineEdit with an eye icon to toggle password visibility, plus a
leading lock icon - shares the focus glow and error-state affordances with
the other premium form fields instead of duplicating them."""
import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QToolButton

from app.theme import theme_manager
from app.widgets.glow_input import GlowLineEdit


class PasswordField(GlowLineEdit):
    def __init__(self, placeholder: str = "Password", parent=None):
        super().__init__(placeholder=placeholder, icon_name="fa5s.lock", parent=parent)
        self.setEchoMode(QLineEdit.EchoMode.Password)

        self._toggle_btn = QToolButton(self)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet("border: none; background: transparent;")
        self._toggle_btn.clicked.connect(self._toggle_visibility)
        self.setTextMargins(0, 0, 30, 0)
        self._refresh_toggle_icon()
        theme_manager.subscribe(lambda _t: self._refresh_toggle_icon())

    def _refresh_toggle_icon(self):
        name = "fa5s.eye" if self.echoMode() == QLineEdit.EchoMode.Password else "fa5s.eye-slash"
        self._toggle_btn.setIcon(qta.icon(name, color=theme_manager.icon_color_muted()))

    def _toggle_visibility(self):
        if self.echoMode() == QLineEdit.EchoMode.Password:
            self.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.setEchoMode(QLineEdit.EchoMode.Password)
        self._refresh_toggle_icon()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        size = 22
        x = self.rect().right() - size - 6
        y = (self.rect().height() - size) // 2
        self._toggle_btn.setGeometry(x, y, size, size)
