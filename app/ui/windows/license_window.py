"""Full-screen gate shown instead of the login screen once a trial has
expired (or no valid license record survives) - a hard lock, matching the
rest of the app's login/signup visual style, that only lets the user in
after entering a valid Lifetime license key."""
import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from app.core import config, licensing
from app.core.database import Database
from app.ui.widgets.glow_input import GlowLineEdit
from app.ui.widgets.message_box import AppMessageBox
from app.ui.widgets.wavy_background import WavyGradientBackground
from app.ui.widgets.credit_label import AnimatedCreditLabel


class LicenseLockedWindow(QWidget):
    activated = Signal()

    def __init__(self, db: Database, status: dict):
        super().__init__()
        self.db = db
        self.setObjectName("licenseLockedWindow")
        self.setWindowTitle(f"{config.APP_NAME} — License Required")
        self.resize(540, 620)
        self.setMinimumSize(480, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bg = WavyGradientBackground(colors=["#1d4ed8", "#1e3a8a", "#4338ca"], wave_color="#ffffff")
        root.addWidget(bg, 1)

        layout = QVBoxLayout(bg)
        layout.setContentsMargins(56, 40, 56, 24)
        layout.setSpacing(14)
        layout.addStretch(1)

        icon = QLabel()
        icon.setPixmap(qta.icon("fa5s.lock", color="white").pixmap(46, 46))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon)

        if status["state"] == "expired":
            tier_label = licensing.TIER_LABELS.get(status["tier"], "Trial")
            title_text = f"Your {tier_label} has ended"
            body_text = (
                "Your trial period has finished. Enter a Lifetime license key below to "
                "keep using HotelPOS, or contact your vendor to purchase one."
            )
        else:
            title_text = "License Required"
            body_text = (
                "No valid license was found for this installation. Enter a Lifetime "
                "license key to activate, or contact your vendor."
            )

        title = QLabel(title_text)
        title.setStyleSheet("color: white; font-size: 20px; font-weight: 700; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)

        body = QLabel(body_text)
        body.setStyleSheet("color: #dbeafe; font-size: 13px; border: none;")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        layout.addWidget(body)

        layout.addSpacing(12)

        machine_row = QHBoxLayout()
        machine_row.addStretch()
        machine_label = QLabel(f"Machine ID:  {licensing.format_id(licensing.get_machine_id())}")
        machine_label.setStyleSheet("color: white; font-weight: 700; letter-spacing: 1px; border: none;")
        machine_row.addWidget(machine_label)
        machine_row.addStretch()
        layout.addLayout(machine_row)

        layout.addSpacing(10)
        self.key_input = GlowLineEdit("XXXX-XXXX-XXXX-XXXX-XXXX", icon_name="fa5s.key")
        self.key_input.textChanged.connect(lambda: self.key_input.clear_error())
        self.key_input.returnPressed.connect(self._activate)
        layout.addWidget(self.key_input)

        activate_btn = QPushButton("  Activate Lifetime License")
        activate_btn.setProperty("variant", "primary")
        activate_btn.setMinimumHeight(42)
        activate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        activate_btn.setIcon(qta.icon("fa5s.unlock", color="white"))
        activate_btn.clicked.connect(self._activate)
        layout.addWidget(activate_btn)

        exit_btn = QPushButton("Exit")
        exit_btn.setProperty("variant", "ghost")
        exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exit_btn.setStyleSheet("color: white;")
        exit_btn.clicked.connect(self.close)
        layout.addWidget(exit_btn)

        layout.addStretch(2)

        footer_bar = WavyGradientBackground(
            colors=["#0f172a", "#1e293b", "#334155"], parent=None,
            style="clouds", speed=0.015,
        )
        footer_bar.setFixedHeight(56)
        footer_layout = QHBoxLayout(footer_bar)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch()
        footer_layout.addWidget(AnimatedCreditLabel("Developed By: Abdul Wahid Khan", font_size=11))
        footer_layout.addStretch()
        root.addWidget(footer_bar)

    def _activate(self):
        key = self.key_input.text().strip()
        if not key:
            self.key_input.set_error(True)
            AppMessageBox.warning(self, "Missing Key", "Please enter a license key.")
            return

        ok, message = licensing.activate_lifetime(self.db, key)
        if not ok:
            self.key_input.set_error(True)
            AppMessageBox.error(self, "Activation Failed", message)
            return

        AppMessageBox.success(self, "License Activated", "Lifetime license activated successfully.")
        self.activated.emit()
