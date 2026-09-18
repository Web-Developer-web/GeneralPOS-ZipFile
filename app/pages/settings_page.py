"""Settings page: hotel profile, appearance, user management, password change."""
import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QTextEdit, QTabWidget, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFormLayout, QDialog,
)

from app import config, licensing
from app.database import Database
from app.security import is_valid_email, is_valid_phone
from app.widgets.password_field import PasswordField
from app.widgets.glow_input import GlowLineEdit
from app.widgets.message_box import AppMessageBox
from app.pdf_utils import print_receipt, list_available_printers
from app.theme import apply_card_shadow


class AddUserDialog(QDialog):
    """Lets an Admin create another account (Cashier or Admin) from inside
    the app - the only way to add a user now that public Sign Up is a
    one-time bootstrap step for the first Admin account."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Add User")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)

        self.full_name_input = QLineEdit()
        self.full_name_input.setPlaceholderText("e.g. Ahmed Khan")
        form.addRow("Full Name", self.full_name_input)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Choose a username")
        form.addRow("Username", self.username_input)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("name@example.com")
        form.addRow("Email", self.email_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("03XXXXXXXXX (optional)")
        form.addRow("Phone", self.phone_input)

        self.role_input = QComboBox()
        self.role_input.addItems(config.ROLES)
        # Default to Cashier, not whatever ROLES happens to list first - a
        # new account left on autopilot should get the lower-privilege
        # role, not silently become an Admin.
        self.role_input.setCurrentText(config.ROLE_CASHIER)
        form.addRow("Role", self.role_input)

        self.password_input = PasswordField("Create a password")
        form.addRow("Password", self.password_input)

        self.confirm_input = PasswordField("Re-enter password")
        form.addRow("Confirm Password", self.confirm_input)

        layout.addLayout(form)
        layout.addSpacing(10)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("  Cancel")
        cancel_btn.setIcon(qta.icon("fa5s.times", color="#6b7280"))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("  Create User")
        save_btn.setIcon(qta.icon("fa5s.user-plus", color="white"))
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self._on_save)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _on_save(self):
        full_name = self.full_name_input.text().strip()
        username = self.username_input.text().strip()
        email = self.email_input.text().strip()
        phone = self.phone_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_input.text()
        role = self.role_input.currentText()

        if not full_name or not username or not email or not password or not confirm:
            AppMessageBox.warning(self, "Missing Information", "Please fill in all required fields.")
            return
        if len(username) < 3:
            AppMessageBox.warning(self, "Invalid Username", "Username must be at least 3 characters.")
            return
        if not is_valid_email(email):
            AppMessageBox.warning(self, "Invalid Email", "Please enter a valid email address.")
            return
        if not is_valid_phone(phone):
            AppMessageBox.warning(
                self, "Invalid Phone", "Please enter a valid phone number (e.g. 03001234567)."
            )
            return
        if len(password) < config.PASSWORD_MIN_LENGTH:
            AppMessageBox.warning(
                self, "Weak Password",
                f"Password must be at least {config.PASSWORD_MIN_LENGTH} characters.",
            )
            return
        if password != confirm:
            AppMessageBox.warning(self, "Password Mismatch", "Passwords do not match.")
            return
        if self.db.username_exists(username):
            AppMessageBox.warning(self, "Username Taken", "This username is already registered.")
            return
        if self.db.email_exists(email):
            AppMessageBox.warning(self, "Email Taken", "This email is already registered.")
            return

        self.db.create_user(full_name, username, email, phone, password, role)
        self.accept()


class HotelProfileTab(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(16)

        card = QFrame()
        card.setProperty("card", "true")
        apply_card_shadow(card)
        form_layout = QVBoxLayout(card)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(12)

        self.hotel_name_input = QLineEdit()
        form.addRow("Hotel / Restaurant Name", self.hotel_name_input)

        self.address_input = QLineEdit()
        form.addRow("Address / Location", self.address_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("03XXXXXXXXX")
        form.addRow("Contact Number", self.phone_input)

        self.currency_input = QLineEdit()
        form.addRow("Currency Symbol", self.currency_input)

        self.footer_input = QTextEdit()
        self.footer_input.setFixedHeight(70)
        form.addRow("Receipt Footer Message", self.footer_input)

        form_layout.addLayout(form)

        save_btn = QPushButton("  Save Changes")
        save_btn.setIcon(qta.icon("fa5s.save", color="white"))
        save_btn.setProperty("variant", "primary")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self.save)
        form_layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(card)
        layout.addStretch()

    def refresh(self):
        s = self.db.get_settings()
        self.hotel_name_input.setText(s["hotel_name"])
        self.address_input.setText(s["address"] or "")
        self.phone_input.setText(s["phone"] or "")
        self.currency_input.setText(s["currency_symbol"])
        self.footer_input.setPlainText(s["footer_message"] or "")

    def save(self):
        if not self.hotel_name_input.text().strip():
            AppMessageBox.warning(self, "Missing Name", "Hotel name cannot be empty.")
            return
        self.db.update_settings(
            hotel_name=self.hotel_name_input.text().strip(),
            address=self.address_input.text().strip(),
            phone=self.phone_input.text().strip(),
            currency_symbol=self.currency_input.text().strip() or "Rs.",
            footer_message=self.footer_input.toPlainText().strip(),
        )
        AppMessageBox.success(self, "Saved", "Hotel profile updated successfully.")
        window = self.window()
        if hasattr(window, "apply_hotel_name"):
            window.apply_hotel_name()


class AppearanceTab(QWidget):
    theme_changed = Signal(str)

    def __init__(self, current_theme: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(16)

        card = QFrame()
        card.setProperty("card", "true")
        apply_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        label = QLabel("Application Theme")
        label.setStyleSheet("font-weight: 600; font-size: 14px;")
        card_layout.addWidget(label)

        desc = QLabel("Choose how HotelPOS looks. Switch anytime — your choice is saved automatically.")
        desc.setProperty("role", "subtitle")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        btn_row = QHBoxLayout()
        self.light_btn = QPushButton("  Light Mode")
        self.light_btn.setIcon(qta.icon("fa5s.sun", color="#d97706"))
        self.light_btn.setCheckable(True)
        self.light_btn.setMinimumHeight(42)
        self.light_btn.clicked.connect(lambda: self._select("light"))

        self.dark_btn = QPushButton("  Dark Mode")
        self.dark_btn.setIcon(qta.icon("fa5s.moon", color="#818cf8"))
        self.dark_btn.setCheckable(True)
        self.dark_btn.setMinimumHeight(42)
        self.dark_btn.clicked.connect(lambda: self._select("dark"))

        btn_row.addWidget(self.light_btn)
        btn_row.addWidget(self.dark_btn)
        card_layout.addLayout(btn_row)

        layout.addWidget(card)
        layout.addStretch()
        self.set_active(current_theme)

    def _select(self, theme):
        self.set_active(theme)
        self.theme_changed.emit(theme)

    def set_active(self, theme):
        self.light_btn.setChecked(theme == "light")
        self.dark_btn.setChecked(theme == "dark")


class UsersTab(QWidget):
    def __init__(self, db: Database, current_user, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_user = current_user

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Cashier and Admin accounts for this hotel."))
        header_row.addStretch()
        add_user_btn = QPushButton("  Add User")
        add_user_btn.setIcon(qta.icon("fa5s.user-plus", color="white"))
        add_user_btn.setProperty("variant", "primary")
        add_user_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_user_btn.clicked.connect(self._add_user)
        header_row.addWidget(add_user_btn)
        layout.addLayout(header_row)

        card = QFrame()
        card.setProperty("card", "true")
        apply_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Full Name", "Username", "Role", "Status", "Actions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(320)
        card_layout.addWidget(self.table)
        layout.addWidget(card, 1)

    def refresh(self):
        users = self.db.list_users()
        self.table.setRowCount(0)
        for row_idx, user in enumerate(users):
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(user["full_name"]))
            self.table.setItem(row_idx, 1, QTableWidgetItem(user["username"]))

            role_combo = QComboBox()
            role_combo.addItems(config.ROLES)
            role_combo.setCurrentText(user["role"])
            is_self = user["id"] == self.current_user["id"]
            role_combo.setEnabled(not is_self)
            role_combo.currentTextChanged.connect(
                lambda text, uid=user["id"]: self.db.update_user_role(uid, text)
            )
            self.table.setCellWidget(row_idx, 2, role_combo)

            status_item = QTableWidgetItem("Active" if user["is_active"] else "Disabled")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 3, status_item)

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)

            is_active = bool(user["is_active"])
            toggle_btn = QPushButton()
            toggle_btn.setIcon(qta.icon("fa5s.toggle-on" if is_active else "fa5s.toggle-off",
                                         color="#16a34a" if is_active else "#9ca3af"))
            toggle_btn.setProperty("variant", "icon")
            toggle_btn.setFixedSize(30, 30)
            toggle_btn.setEnabled(not is_self)
            toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle_btn.setToolTip("Disable" if is_active else "Enable")
            toggle_btn.clicked.connect(
                lambda _c=False, uid=user["id"], a=is_active: self._toggle_user(uid, a)
            )
            actions_layout.addWidget(toggle_btn)

            delete_btn = QPushButton()
            delete_btn.setIcon(qta.icon("fa5s.trash-alt", color="#dc2626"))
            delete_btn.setProperty("variant", "icon")
            delete_btn.setFixedSize(30, 30)
            delete_btn.setEnabled(not is_self)
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.setToolTip("Delete user")
            delete_btn.clicked.connect(lambda _c=False, uid=user["id"]: self._delete_user(uid))
            actions_layout.addWidget(delete_btn)
            actions_layout.addStretch()

            self.table.setCellWidget(row_idx, 4, actions)

    def _add_user(self):
        dialog = AddUserDialog(self.db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            AppMessageBox.success(self, "User Created", "The new account has been created successfully.")

    def _toggle_user(self, user_id, currently_active):
        self.db.set_user_active(user_id, not currently_active)
        self.refresh()

    def _delete_user(self, user_id):
        user = next((u for u in self.db.list_users() if u["id"] == user_id), None)
        user_name = user["full_name"] if user else "this user"
        confirmed = AppMessageBox.question(
            self, "Delete User", f"Are you sure you want to delete '{user_name}'? This cannot be undone.",
            yes_text="Delete", no_text="Cancel",
        )
        if confirmed:
            self.db.delete_user(user_id)
            self.refresh()
            AppMessageBox.success(self, "User Deleted", f"'{user_name}' has been deleted successfully.")


class SecurityTab(QWidget):
    def __init__(self, db: Database, current_user, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_user = current_user

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(16)

        card = QFrame()
        card.setProperty("card", "true")
        # No apply_card_shadow() here, deliberately: a QGraphicsDropShadowEffect
        # on this card, together with each PasswordField's own drop-shadow
        # focus-glow effect nested inside it, corrupts Qt's rendering the
        # first time this tab (initially hidden behind Hotel Profile/
        # Appearance) is switched to - fields paint at the wrong position
        # even though their real, laid-out geometry is correct, and it
        # doesn't self-correct on resize. Removing the outer shadow avoids
        # that nested-effect combination entirely; every other card in the
        # app keeps its shadow since none of them nest a glow-effect field.
        form_layout = QVBoxLayout(card)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(12)

        label = QLabel("Change Password")
        label.setStyleSheet("font-weight: 600; font-size: 14px;")
        form_layout.addWidget(label)

        # Label-above-field, one full-width row per field - the same
        # pattern the Login/Signup screens use for these fields. A
        # QFormLayout's label-beside-field columns don't pair well with
        # PasswordField here: unconstrained it stretches across the whole
        # (fairly wide) settings card, and it visibly mis-renders inside a
        # QFormLayout row on this tab (verified independently of sizing -
        # even width-capped and freshly reconstructed, the glow-shadow
        # widget still paints offset from its real, correctly-computed
        # geometry). Plain vertical stacking avoids the whole combination.
        self.current_password = PasswordField("Current password")
        self.new_password = PasswordField("New password")
        self.confirm_password = PasswordField("Confirm new password")
        for field in (self.current_password, self.new_password, self.confirm_password):
            field.setMaximumWidth(360)

        for row_label, field in (
            ("Current Password", self.current_password),
            ("New Password", self.new_password),
            ("Confirm New Password", self.confirm_password),
        ):
            field_label = QLabel(row_label)
            form_layout.addWidget(field_label)
            form_layout.addWidget(field)

        save_btn = QPushButton("  Update Password")
        save_btn.setIcon(qta.icon("fa5s.key", color="white"))
        save_btn.setProperty("variant", "primary")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self.change_password)
        form_layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(card)
        layout.addStretch()

    def change_password(self):
        from app.security import verify_password

        current = self.current_password.text()
        new = self.new_password.text()
        confirm = self.confirm_password.text()

        if not current or not new or not confirm:
            AppMessageBox.warning(self, "Missing Information", "Please fill in all password fields.")
            return
        if not verify_password(current, self.current_user["password_hash"], self.current_user["password_salt"]):
            AppMessageBox.error(self, "Incorrect Password", "Your current password is incorrect.")
            return
        if len(new) < config.PASSWORD_MIN_LENGTH:
            AppMessageBox.warning(self, "Weak Password", f"New password must be at least {config.PASSWORD_MIN_LENGTH} characters.")
            return
        if new != confirm:
            AppMessageBox.warning(self, "Mismatch", "New passwords do not match.")
            return

        self.db.update_password(self.current_user["id"], new)
        self.current_password.clear()
        self.new_password.clear()
        self.confirm_password.clear()
        AppMessageBox.success(self, "Success", "Your password has been updated.")


class PrinterTab(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(16)

        card = QFrame()
        card.setProperty("card", "true")
        apply_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        label = QLabel("Thermal Receipt Printer")
        label.setStyleSheet("font-weight: 600; font-size: 14px;")
        card_layout.addWidget(label)

        desc = QLabel(
            "Choose the POS/thermal printer and paper width used when printing bill "
            "receipts directly. You can still export a receipt as PDF or pick a "
            "different printer manually at the time of printing."
        )
        desc.setProperty("role", "subtitle")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(12)

        self.printer_combo = QComboBox()
        self.printer_combo.setMinimumHeight(38)
        form.addRow("Printer", self.printer_combo)

        self.width_combo = QComboBox()
        self.width_combo.addItem("80mm (Standard Thermal)", 80)
        self.width_combo.addItem("58mm (Compact Thermal)", 58)
        self.width_combo.setMinimumHeight(38)
        form.addRow("Paper Width", self.width_combo)

        card_layout.addLayout(form)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("  Refresh List")
        refresh_btn.setIcon(qta.icon("fa5s.sync-alt", color="#6b7280"))
        refresh_btn.clicked.connect(self.load_printers)

        test_btn = QPushButton("  Test Print")
        test_btn.setIcon(qta.icon("fa5s.vial", color="#2563eb"))
        test_btn.clicked.connect(self.test_print)

        save_btn = QPushButton("  Save")
        save_btn.setIcon(qta.icon("fa5s.save", color="white"))
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self.save)

        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        card_layout.addLayout(btn_row)

        layout.addWidget(card)
        layout.addStretch()

        self.load_printers()

    def load_printers(self):
        current = self.printer_combo.currentData() if self.printer_combo.count() else None
        self.printer_combo.clear()
        self.printer_combo.addItem("System Default Printer", "")
        for name in list_available_printers():
            self.printer_combo.addItem(name, name)
        if current:
            idx = self.printer_combo.findData(current)
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)

    def refresh(self):
        settings = self.db.get_settings()
        printer_name = settings["printer_name"] if "printer_name" in settings.keys() else ""
        width_mm = settings["paper_width_mm"] if "paper_width_mm" in settings.keys() else 80

        self.load_printers()
        idx = self.printer_combo.findData(printer_name or "")
        if idx >= 0:
            self.printer_combo.setCurrentIndex(idx)
        width_idx = self.width_combo.findData(width_mm)
        if width_idx >= 0:
            self.width_combo.setCurrentIndex(width_idx)

    def save(self):
        printer_name = self.printer_combo.currentData() or None
        width_mm = self.width_combo.currentData()
        self.db.update_settings(printer_name=printer_name, paper_width_mm=width_mm)
        AppMessageBox.success(self, "Saved", "Printer settings have been updated.")

    def test_print(self):
        printer_name = self.printer_combo.currentData() or ""
        width_mm = self.width_combo.currentData()
        settings = self.db.get_settings()
        sample_html = f"""
        <div style="font-family:'Segoe UI',sans-serif; text-align:center; color:#111;">
            <div style="font-size:13pt; font-weight:700; margin-bottom:2pt;">{settings['hotel_name']}</div>
            <div style="font-size:9pt; margin:2pt;">Test Print</div>
            <div style="border-top:1pt solid #333; margin:4pt 0;"></div>
            <div style="font-size:10pt;">If you can read this clearly,<br>your thermal printer is set up correctly.</div>
            <div style="border-top:1pt solid #333; margin:4pt 0;"></div>
            <div style="font-size:9pt;">Developed By: Abdul Wahid Khan</div>
        </div>
        """
        ok = print_receipt(sample_html, width_mm=width_mm, printer_name=printer_name)
        if ok:
            AppMessageBox.success(self, "Test Sent", "A test receipt was sent to the selected printer.")
        else:
            AppMessageBox.warning(self, "No Printer Found", "Could not find that printer. Please check it is connected and try again.")


class LicenseTab(QWidget):
    """Shows the current plan / days remaining and, for a trial, lets the
    Admin key in a Lifetime license to upgrade without reinstalling."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(16)

        # No apply_card_shadow() here - this card holds a GlowLineEdit
        # (license key field), and nesting an outer card shadow with an
        # inner glow-effect field mis-renders (see SecurityTab above).
        card = QFrame()
        card.setProperty("card", "true")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        heading = QLabel("License & Plan")
        heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        card_layout.addWidget(heading)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 13px;")
        card_layout.addWidget(self.status_label)

        self.machine_label = QLabel()
        self.machine_label.setStyleSheet("font-size: 12px; color: #6b7280;")
        card_layout.addWidget(self.machine_label)

        self.upgrade_box = QWidget()
        upgrade_layout = QVBoxLayout(self.upgrade_box)
        upgrade_layout.setContentsMargins(0, 8, 0, 0)
        upgrade_layout.setSpacing(8)
        upgrade_layout.addWidget(QLabel("Upgrade to Lifetime"))
        self.key_input = GlowLineEdit("XXXX-XXXX-XXXX-XXXX-XXXX", icon_name="fa5s.key")
        self.key_input.textChanged.connect(lambda: self.key_input.clear_error())
        upgrade_layout.addWidget(self.key_input)
        activate_btn = QPushButton("  Activate Lifetime License")
        activate_btn.setIcon(qta.icon("fa5s.unlock", color="white"))
        activate_btn.setProperty("variant", "primary")
        activate_btn.setMinimumHeight(40)
        activate_btn.clicked.connect(self._activate)
        upgrade_layout.addWidget(activate_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        card_layout.addWidget(self.upgrade_box)

        layout.addWidget(card)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        status = licensing.get_status(self.db)
        tier_label = licensing.TIER_LABELS.get(status["tier"], "Unknown")

        if status["state"] == "active" and status["tier"] == licensing.TIER_LIFETIME:
            self.status_label.setText(f"Plan: <b>{tier_label}</b> — active, no expiry.")
            self.upgrade_box.setVisible(False)
        elif status["state"] == "active":
            self.status_label.setText(
                f"Plan: <b>{tier_label}</b> — {status['days_left']} day(s) remaining "
                f"(expires {status['expires_at']})."
            )
            self.upgrade_box.setVisible(True)
        else:
            self.status_label.setText(f"Plan: <b>{tier_label}</b> — expired.")
            self.upgrade_box.setVisible(True)

        self.machine_label.setText(f"Machine ID: {licensing.format_id(licensing.get_machine_id())}")

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

        self.key_input.clear()
        AppMessageBox.success(self, "License Activated", "Lifetime license activated successfully.")
        self.refresh()


class SettingsPage(QWidget):
    theme_changed = Signal(str)

    def __init__(self, db: Database, current_user, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_user = current_user

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Settings")
        title.setProperty("role", "pageTitle")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        is_admin = current_user["role"] == config.ROLE_ADMIN

        self.profile_tab = None
        if is_admin:
            self.profile_tab = HotelProfileTab(db)
            self.tabs.addTab(self.profile_tab, "Hotel Profile")

        self.appearance_tab = AppearanceTab(db.get_settings()["theme"])
        self.appearance_tab.theme_changed.connect(self.theme_changed.emit)
        self.tabs.addTab(self.appearance_tab, "Appearance")

        self.printer_tab = PrinterTab(db)
        self.tabs.addTab(self.printer_tab, "Printer")

        self.security_tab = SecurityTab(db, current_user)
        self.tabs.addTab(self.security_tab, "Security")

        if is_admin:
            self.users_tab = UsersTab(db, current_user)
            self.tabs.addTab(self.users_tab, "User Management")
        else:
            self.users_tab = None

        self.license_tab = None
        if is_admin:
            self.license_tab = LicenseTab(db)
            self.tabs.addTab(self.license_tab, "License")

        layout.addWidget(self.tabs, 1)

    def refresh(self):
        if self.profile_tab:
            self.profile_tab.refresh()
        self.printer_tab.refresh()
        if self.users_tab:
            self.users_tab.refresh()
        if self.license_tab:
            self.license_tab.refresh()
