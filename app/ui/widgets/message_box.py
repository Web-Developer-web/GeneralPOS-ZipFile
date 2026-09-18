"""Modern replacement for QMessageBox: a colored header bar + icon + themed body."""
import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QWidget,
)

from app.ui.theme import ACCENT, DANGER, SUCCESS, WARNING, PURPLE, apply_card_shadow, theme_manager


class AppMessageBox(QDialog):
    _KIND_STYLE = {
        "info": ("fa5s.info-circle", ACCENT, "Information"),
        "success": ("fa5s.check-circle", SUCCESS, "Success"),
        "warning": ("fa5s.exclamation-triangle", WARNING, "Warning"),
        "error": ("fa5s.times-circle", DANGER, "Error"),
        "question": ("fa5s.question-circle", PURPLE, "Please Confirm"),
    }

    def __init__(self, parent, kind: str, title: str, message: str,
                 primary_text="OK", secondary_text=None):
        super().__init__(parent)
        self._confirmed = False
        icon_name, color, default_title = self._KIND_STYLE.get(kind, self._KIND_STYLE["info"])

        self.setWindowTitle(title or default_title)
        self.setMinimumWidth(400)
        self.setMaximumWidth(460)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None

        surface_color = theme_manager.palette()["surface"]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(0)

        header = QFrame()
        header.setCursor(Qt.CursorShape.SizeAllCursor)
        header.setStyleSheet(
            f"background-color: {color}; border-top-left-radius: 18px; border-top-right-radius: 18px;"
        )
        header.setFixedHeight(64)
        header.mousePressEvent = self._header_mouse_press
        header.mouseMoveEvent = self._header_mouse_move
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 12, 20, 12)
        header_layout.setSpacing(14)

        badge = QLabel()
        badge.setFixedSize(36, 36)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            "background-color: rgba(255, 255, 255, 45); border-radius: 18px; border: none;"
        )
        badge.setPixmap(qta.icon(icon_name, color="white").pixmap(20, 20))
        header_layout.addWidget(badge)

        title_label = QLabel(title or default_title)
        title_label.setStyleSheet(
            "color: white; font-size: 16px; font-weight: 700; border: none; background: transparent;"
        )
        header_layout.addWidget(title_label, 1)
        outer.addWidget(header)

        body = QFrame()
        body.setStyleSheet(
            f"background-color: {surface_color}; border-bottom-left-radius: 18px; border-bottom-right-radius: 18px;"
        )
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 20)
        body_layout.setSpacing(20)

        # Color set explicitly (not left to inherit from the app
        # stylesheet) - this dialog is frameless + translucent, and that
        # combination has previously let a widget's text color fall back
        # to the OS palette instead of ours, turning invisible if Windows
        # itself is in dark mode while this app is in light mode.
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet(f"font-size: 13px; color: {theme_manager.palette()['text']};")
        body_layout.addWidget(message_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        if secondary_text:
            self.secondary_btn = QPushButton(secondary_text)
            self.secondary_btn.setMinimumHeight(38)
            self.secondary_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.secondary_btn.setStyleSheet(
                f"background-color: {surface_color}; color: {theme_manager.palette()['text']}; "
                f"border: 1px solid {theme_manager.palette()['border']}; border-radius: 10px; "
                f"padding: 8px 18px; font-weight: 600;"
            )
            self.secondary_btn.clicked.connect(self.reject)
            btn_row.addWidget(self.secondary_btn)

        self.primary_btn = QPushButton(f"  {primary_text}")
        self.primary_btn.setIcon(qta.icon("fa5s.check", color="white"))
        self.primary_btn.setMinimumHeight(38)
        self.primary_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_btn.setStyleSheet(
            f"background-color: {color}; color: white; border: none; border-radius: 10px; padding: 8px 18px; font-weight: 600;"
        )
        self.primary_btn.clicked.connect(self._on_primary)
        btn_row.addWidget(self.primary_btn)

        body_layout.addLayout(btn_row)
        outer.addWidget(body)
        apply_card_shadow(self, blur=32, y_offset=8, alpha=60)

    def _on_primary(self):
        self._confirmed = True
        self.accept()

    def _header_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _header_mouse_move(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    # ------------------------------------------------------------------ #
    @staticmethod
    def info(parent, title, message, ok_text="OK"):
        AppMessageBox(parent, "info", title, message, primary_text=ok_text).exec()

    @staticmethod
    def success(parent, title, message, ok_text="Great"):
        AppMessageBox(parent, "success", title, message, primary_text=ok_text).exec()

    @staticmethod
    def warning(parent, title, message, ok_text="OK"):
        AppMessageBox(parent, "warning", title, message, primary_text=ok_text).exec()

    @staticmethod
    def error(parent, title, message, ok_text="OK"):
        AppMessageBox(parent, "error", title, message, primary_text=ok_text).exec()

    @staticmethod
    def question(parent, title, message, yes_text="Yes", no_text="Cancel") -> bool:
        box = AppMessageBox(parent, "question", title, message,
                             primary_text=yes_text, secondary_text=no_text)
        box.exec()
        return box._confirmed
