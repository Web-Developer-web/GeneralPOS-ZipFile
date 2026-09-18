"""Login + Signup window (split-panel modern UI)."""
import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication,
    QFrame, QStackedWidget, QCheckBox, QSizePolicy, QSpacerItem, QComboBox,
)

from app import config, licensing
from app.database import Database
from app.security import is_valid_email, is_valid_phone
from app.widgets.password_field import PasswordField
from app.widgets.glow_input import GlowLineEdit
from app.widgets.password_strength import PasswordStrengthMeter
from app.widgets.loading_button import set_button_loading
from app.widgets.message_box import AppMessageBox
from app.widgets.credit_label import AnimatedCreditLabel
from app.widgets.wavy_background import WavyGradientBackground
from app.widgets.animations import crossfade_stack, fade_slide_in
from app.widgets.remember_me import save_credentials, load_credentials, clear_credentials


class BrandPanel(WavyGradientBackground):
    def __init__(self, hotel_name: str, parent=None):
        super().__init__(
            colors=["#1d4ed8", "#1e3a8a", "#4338ca"], wave_color="#ffffff", parent=parent,
        )
        self.setFixedWidth(380)
        self._entered = False

        from app.theme import apply_card_shadow
        # A soft, diffuse shadow along the panel's right edge is what gives
        # it that "floating above the page" neumorphic separation from the
        # sign-in form next to it, instead of the two panels just abutting.
        apply_card_shadow(self, blur=48, y_offset=0, alpha=55)

        # No fixed top/bottom padding - the whole content block is centred
        # vertically via the stretches around it, so the coloured panel
        # itself always fills the full window height edge to edge with
        # nothing holding it back from top or bottom.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 0, 40, 0)
        layout.setSpacing(18)
        layout.addStretch(1)

        from app.branding import build_app_icon
        self.icon_label = QLabel()
        self.icon_label.setPixmap(build_app_icon().pixmap(64, 64))
        layout.addWidget(self.icon_label)

        self.title_label = QLabel(hotel_name)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("color: white; font-size: 26px; font-weight: 700; border: none;")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(f"{config.APP_NAME} — Complete (Point of Sale)\nSystem for hotels")
        self.subtitle_label.setStyleSheet("color: #dbeafe; font-size: 13px; border: none;")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)

        layout.addSpacerItem(QSpacerItem(20, 30, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # A frosted-glass card behind the feature checklist - a translucent
        # fill plus a faint light border - gives the panel a touch of
        # genuine glassmorphism instead of text floating directly on the
        # gradient.
        self.features_container = QWidget()
        self.features_container.setStyleSheet(
            "background-color: rgba(255, 255, 255, 22);"
            "border: 1px solid rgba(255, 255, 255, 45);"
            "border-radius: 14px;"
        )
        features_layout = QVBoxLayout(self.features_container)
        features_layout.setContentsMargins(16, 14, 16, 14)
        features_layout.setSpacing(10)
        for icon, text in [
            ("fa5s.check-circle", "Fast & simple billing"),
            ("fa5s.check-circle", "Daily & overall PDF reports"),
            ("fa5s.check-circle", "Secure role-based access"),
        ]:
            row = QHBoxLayout()
            ic = QLabel()
            ic.setPixmap(qta.icon(icon, color="#93c5fd").pixmap(16, 16))
            ic.setStyleSheet("background: transparent; border: none;")
            row.addWidget(ic)
            lbl = QLabel(text)
            lbl.setStyleSheet("color: white; font-size: 12px; border: none; background: transparent;")
            row.addWidget(lbl)
            row.addStretch()
            features_layout.addLayout(row)
        layout.addWidget(self.features_container)

        layout.addStretch(2)

        # The version badge gets a translucent pill background, bold text
        # and an icon so it reads clearly against the panel instead of
        # disappearing as a thin, low-contrast caption.
        self.version_row_widget = QWidget()
        self.version_row_widget.setStyleSheet("background: transparent;")
        vr_layout = QHBoxLayout(self.version_row_widget)
        vr_layout.setContentsMargins(0, 0, 0, 0)

        version_pill = QWidget()
        version_pill.setStyleSheet(
            "background-color: rgba(255, 255, 255, 38); border-radius: 13px;"
        )
        pill_layout = QHBoxLayout(version_pill)
        pill_layout.setContentsMargins(12, 6, 14, 6)
        pill_layout.setSpacing(8)
        self.version_badge = QLabel()
        self.version_badge.setPixmap(qta.icon("fa5s.tag", color="white").pixmap(12, 12))
        pill_layout.addWidget(self.version_badge)
        version_text = QLabel(f"{config.APP_NAME}  •  v{config.APP_VERSION}")
        version_text.setStyleSheet("color: white; font-size: 13px; font-weight: 700; border: none;")
        pill_layout.addWidget(version_text)

        vr_layout.addWidget(version_pill)
        vr_layout.addStretch()
        layout.addWidget(self.version_row_widget)

        layout.addStretch(1)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._entered:
            self._entered = True
            widgets = [
                self.icon_label, self.title_label, self.subtitle_label,
                self.features_container, self.version_row_widget,
            ]
            for i, w in enumerate(widgets):
                fade_slide_in(w, delay=150 + i * 110)


class LoginPage(QWidget):
    login_successful = Signal(object)
    go_to_signup = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 70, 60, 60)
        layout.setSpacing(10)

        title = QLabel("Welcome back")
        title.setProperty("role", "pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Sign in to continue to your dashboard")
        subtitle.setProperty("role", "subtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(20)

        layout.addWidget(QLabel("Username"))
        self.username_input = GlowLineEdit("Enter your username", icon_name="fa5s.user")
        layout.addWidget(self.username_input)
        self.username_input.textChanged.connect(lambda: self.username_input.clear_error())

        layout.addSpacing(6)
        layout.addWidget(QLabel("Password"))
        self.password_input = PasswordField("Enter your password")
        layout.addWidget(self.password_input)
        self.password_input.textChanged.connect(lambda: self.password_input.clear_error())

        layout.addSpacing(10)
        self.remember_checkbox = QCheckBox("Remember Me")
        self.remember_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.remember_checkbox)

        layout.addSpacing(14)
        self.login_btn = QPushButton("  Sign In")
        self.login_btn.setProperty("variant", "primary")
        self.login_btn.setMinimumHeight(42)
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setIcon(qta.icon("fa5s.sign-in-alt", color="white"))
        self.login_btn.clicked.connect(self._attempt_login)
        layout.addWidget(self.login_btn)

        self.password_input.returnPressed.connect(self._attempt_login)
        self.username_input.returnPressed.connect(self._attempt_login)

        layout.addSpacing(14)
        switch_row = QHBoxLayout()
        switch_row.addStretch()
        self.switch_label = QLabel("Don't have an account?")
        self.switch_label.setProperty("role", "subtitle")
        switch_row.addWidget(self.switch_label)
        self.switch_btn = QPushButton("Sign Up")
        self.switch_btn.setProperty("variant", "ghost")
        self.switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_btn.setStyleSheet("color: #2563eb; font-weight: 600;")
        self.switch_btn.clicked.connect(self.go_to_signup.emit)
        switch_row.addWidget(self.switch_btn)
        switch_row.addStretch()
        layout.addLayout(switch_row)

        layout.addStretch()

        self.load_remembered()
        self.update_signup_availability()

    def update_signup_availability(self):
        """Sign Up is a one-time bootstrap step for creating the very
        first (Admin) account - once any account exists, every further
        user is created by an Admin from Settings -> User Management, so
        the public "Sign Up" link has nothing left to do and is hidden."""
        available = self.db.count_users() == 0
        self.switch_label.setVisible(available)
        self.switch_btn.setVisible(available)

    def load_remembered(self):
        """Fill in and check "Remember Me" from previously saved credentials,
        or clear the form when none are stored."""
        self.username_input.clear_error()
        self.password_input.clear_error()
        creds = load_credentials()
        if creds:
            username, password = creds
            self.username_input.setText(username)
            self.password_input.setText(password)
            self.remember_checkbox.setChecked(True)
        else:
            self.username_input.clear()
            self.password_input.clear()
            self.remember_checkbox.setChecked(False)

    def _attempt_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()

        self.username_input.clear_error()
        self.password_input.clear_error()

        if not username or not password:
            if not username:
                self.username_input.set_error(True)
            if not password:
                self.password_input.set_error(True)
            AppMessageBox.warning(self, "Missing Information", "Please enter both username and password.")
            return

        # A brief, real "checking your credentials" beat on the button
        # (disabled + spinner) rather than an instant flash straight to
        # success/failure - the actual verification below is unchanged.
        set_button_loading(self.login_btn, True, busy_text="Signing in...")
        QTimer.singleShot(350, lambda: self._verify_login(username, password))

    def _verify_login(self, username: str, password: str):
        set_button_loading(self.login_btn, False)

        user = self.db.get_user_by_username(username)
        from app.security import verify_password

        if not user or not verify_password(password, user["password_hash"], user["password_salt"]):
            self.username_input.set_error(True)
            self.password_input.set_error(True)
            AppMessageBox.error(self, "Login Failed", "Invalid username or password.")
            return

        if not user["is_active"]:
            AppMessageBox.error(self, "Account Disabled", "This account has been disabled. Contact an administrator.")
            return

        if self.remember_checkbox.isChecked():
            save_credentials(username, password)
        else:
            clear_credentials()

        self.password_input.clear()
        AppMessageBox.success(self, "Login Successful", f"Welcome back, {user['full_name']}!")
        self.login_successful.emit(user)

    def clear_fields(self):
        self.load_remembered()


class SignupPage(QWidget):
    signup_successful = Signal(object)
    go_to_login = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        outer = QVBoxLayout(self)
        outer.setContentsMargins(60, 40, 60, 30)
        outer.setSpacing(8)

        title = QLabel("Create your Admin account")
        title.setProperty("role", "pageTitle")
        outer.addWidget(title)
        subtitle = QLabel(
            "One-time setup: this creates the Admin account for your hotel's POS system. "
            "Cashier accounts are added later from Settings -> User Management."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        outer.addSpacing(14)

        row1 = QHBoxLayout()
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Full Name"))
        self.full_name_input = GlowLineEdit("e.g. Ahmed Khan", icon_name="fa5s.id-card")
        col1.addWidget(self.full_name_input)
        col2 = QVBoxLayout()
        col2.addWidget(QLabel("Username"))
        self.username_input = GlowLineEdit("Choose a username", icon_name="fa5s.user")
        col2.addWidget(self.username_input)
        row1.addLayout(col1)
        row1.addLayout(col2)
        outer.addLayout(row1)

        row2 = QHBoxLayout()
        col3 = QVBoxLayout()
        col3.addWidget(QLabel("Email"))
        self.email_input = GlowLineEdit("name@example.com", icon_name="fa5s.envelope")
        col3.addWidget(self.email_input)
        col4 = QVBoxLayout()
        col4.addWidget(QLabel("Phone (optional)"))
        self.phone_input = GlowLineEdit("03XXXXXXXXX", icon_name="fa5s.phone")
        col4.addWidget(self.phone_input)
        row2.addLayout(col3)
        row2.addLayout(col4)
        outer.addLayout(row2)

        row3 = QHBoxLayout()
        col5 = QVBoxLayout()
        col5.addWidget(QLabel("Password"))
        self.password_input = PasswordField("Create a password")
        col5.addWidget(self.password_input)
        self.strength_meter = PasswordStrengthMeter()
        self.strength_meter.setVisible(False)
        col5.addWidget(self.strength_meter)
        self.password_input.textChanged.connect(self.strength_meter.update_password)
        col6 = QVBoxLayout()
        col6.addWidget(QLabel("Confirm Password"))
        self.confirm_input = PasswordField("Re-enter password")
        col6.addWidget(self.confirm_input)
        row3.addLayout(col5)
        row3.addLayout(col6)
        outer.addLayout(row3)

        for field in (
            self.full_name_input, self.username_input, self.email_input,
            self.phone_input, self.password_input, self.confirm_input,
        ):
            field.textChanged.connect(lambda _t, f=field: f.clear_error())

        outer.addSpacing(8)
        outer.addWidget(QLabel("Choose your plan"))
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("1 Week Trial — Free", licensing.TIER_TRIAL_1WEEK)
        self.plan_combo.addItem("15 Day Trial — Free", licensing.TIER_TRIAL_15DAY)
        self.plan_combo.addItem("1 Month Trial — Free", licensing.TIER_TRIAL_1MONTH)
        self.plan_combo.addItem("Lifetime — Requires License Key", licensing.TIER_LIFETIME)
        self.plan_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.plan_combo.currentIndexChanged.connect(self._on_plan_changed)
        outer.addWidget(self.plan_combo)

        self.lifetime_box = QWidget()
        lifetime_layout = QVBoxLayout(self.lifetime_box)
        lifetime_layout.setContentsMargins(0, 8, 0, 0)
        lifetime_layout.setSpacing(6)

        machine_row = QHBoxLayout()
        machine_caption = QLabel("Your Machine ID:")
        machine_row.addWidget(machine_caption)
        self.machine_id_label = QLabel(licensing.format_id(licensing.get_machine_id()))
        self.machine_id_label.setStyleSheet("font-weight: 700; letter-spacing: 1px;")
        machine_row.addWidget(self.machine_id_label)
        copy_id_btn = QPushButton()
        copy_id_btn.setIcon(qta.icon("fa5s.copy"))
        copy_id_btn.setToolTip("Copy Machine ID")
        copy_id_btn.setFixedSize(28, 28)
        copy_id_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_id_btn.clicked.connect(self._copy_machine_id)
        machine_row.addWidget(copy_id_btn)
        machine_row.addStretch()
        lifetime_layout.addLayout(machine_row)

        lifetime_hint = QLabel("Send this Machine ID to your vendor to receive a Lifetime License Key.")
        lifetime_hint.setProperty("role", "subtitle")
        lifetime_hint.setWordWrap(True)
        lifetime_layout.addWidget(lifetime_hint)

        lifetime_layout.addWidget(QLabel("License Key"))
        self.license_key_input = GlowLineEdit("XXXX-XXXX-XXXX-XXXX-XXXX", icon_name="fa5s.key")
        self.license_key_input.textChanged.connect(lambda: self.license_key_input.clear_error())
        lifetime_layout.addWidget(self.license_key_input)

        outer.addWidget(self.lifetime_box)
        self.lifetime_box.setVisible(False)

        outer.addSpacing(8)
        self.remember_checkbox = QCheckBox("Remember my password for next sign in")
        self.remember_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        outer.addWidget(self.remember_checkbox)

        outer.addSpacing(10)
        self.signup_btn = QPushButton("  Create Account")
        self.signup_btn.setProperty("variant", "primary")
        self.signup_btn.setMinimumHeight(42)
        self.signup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.signup_btn.setIcon(qta.icon("fa5s.user-plus", color="white"))
        self.signup_btn.clicked.connect(self._attempt_signup)
        outer.addWidget(self.signup_btn)

        outer.addSpacing(10)
        switch_row = QHBoxLayout()
        switch_row.addStretch()
        lbl = QLabel("Already have an account?")
        lbl.setProperty("role", "subtitle")
        switch_row.addWidget(lbl)
        switch_btn = QPushButton("Sign In")
        switch_btn.setProperty("variant", "ghost")
        switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        switch_btn.setStyleSheet("color: #2563eb; font-weight: 600;")
        switch_btn.clicked.connect(self.go_to_login.emit)
        switch_row.addWidget(switch_btn)
        switch_row.addStretch()
        outer.addLayout(switch_row)
        outer.addStretch()

    def _on_plan_changed(self):
        self.lifetime_box.setVisible(self.plan_combo.currentData() == licensing.TIER_LIFETIME)
        self.license_key_input.clear_error()

    def _copy_machine_id(self):
        QApplication.clipboard().setText(licensing.get_machine_id())

    def _attempt_signup(self):
        full_name = self.full_name_input.text().strip()
        username = self.username_input.text().strip()
        email = self.email_input.text().strip()
        phone = self.phone_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_input.text()

        required_fields = (
            (self.full_name_input, full_name), (self.username_input, username),
            (self.email_input, email), (self.password_input, password),
            (self.confirm_input, confirm),
        )
        for field, _value in required_fields:
            field.clear_error()

        if not full_name or not username or not email or not password or not confirm:
            for field, value in required_fields:
                if not value:
                    field.set_error(True)
            AppMessageBox.warning(self, "Missing Information", "Please fill in all required fields.")
            return
        if len(username) < 3:
            self.username_input.set_error(True)
            AppMessageBox.warning(self, "Invalid Username", "Username must be at least 3 characters.")
            return
        if not is_valid_email(email):
            self.email_input.set_error(True)
            AppMessageBox.warning(self, "Invalid Email", "Please enter a valid email address.")
            return
        if not is_valid_phone(phone):
            self.phone_input.set_error(True)
            AppMessageBox.warning(self, "Invalid Phone", "Please enter a valid phone number (e.g. 03001234567).")
            return
        if len(password) < config.PASSWORD_MIN_LENGTH:
            self.password_input.set_error(True)
            AppMessageBox.warning(
                self, "Weak Password",
                f"Password must be at least {config.PASSWORD_MIN_LENGTH} characters.",
            )
            return
        if password != confirm:
            self.password_input.set_error(True)
            self.confirm_input.set_error(True)
            AppMessageBox.warning(self, "Password Mismatch", "Passwords do not match.")
            return

        plan_tier = self.plan_combo.currentData()
        license_key = self.license_key_input.text().strip()
        if plan_tier == licensing.TIER_LIFETIME:
            if not license_key:
                self.license_key_input.set_error(True)
                AppMessageBox.warning(self, "License Key Required", "Please enter your Lifetime license key.")
                return
            if not licensing.verify_lifetime_key(licensing.get_machine_id(), license_key):
                self.license_key_input.set_error(True)
                AppMessageBox.error(
                    self, "Invalid License Key",
                    "This license key is not valid for this computer. Please check the key "
                    "or contact your vendor with your Machine ID.",
                )
                return

        # The remaining checks touch the database - show a brief, real
        # "creating your account" beat on the button rather than jumping
        # straight from click to result.
        set_button_loading(self.signup_btn, True, busy_text="Creating account...")
        QTimer.singleShot(
            350,
            lambda: self._finish_signup(full_name, username, email, phone, password, plan_tier, license_key),
        )

    def _finish_signup(self, full_name: str, username: str, email: str, phone: str, password: str,
                        plan_tier: str, license_key: str):
        set_button_loading(self.signup_btn, False)

        # Sign Up only ever creates the one bootstrap Admin account - the
        # button that reaches this page is already hidden once any user
        # exists, but this guards the same rule directly in case it's ever
        # reached another way.
        if self.db.count_users() > 0:
            AppMessageBox.error(
                self, "Sign Up Unavailable",
                "An account already exists. Please sign in, or ask an Admin "
                "to create your account from Settings -> User Management.",
            )
            return

        if self.db.username_exists(username):
            self.username_input.set_error(True)
            AppMessageBox.error(self, "Username Taken", "This username is already registered.")
            return
        if self.db.email_exists(email):
            self.email_input.set_error(True)
            AppMessageBox.error(self, "Email Taken", "This email is already registered.")
            return

        user_id = self.db.create_user(full_name, username, email, phone, password, config.ROLE_ADMIN)
        user = self.db.get_user(user_id)

        if plan_tier == licensing.TIER_LIFETIME:
            licensing.activate_lifetime(self.db, license_key)
        else:
            licensing.activate_trial(self.db, plan_tier)

        if self.remember_checkbox.isChecked():
            save_credentials(username, password)
        else:
            clear_credentials()

        AppMessageBox.success(self, "Account Created", "Your account has been created successfully. Please sign in.")
        self.clear_fields()
        self.signup_successful.emit(user)

    def clear_fields(self):
        for field in [
            self.full_name_input, self.username_input, self.email_input,
            self.phone_input, self.password_input, self.confirm_input,
            self.license_key_input,
        ]:
            field.clear()
        self.remember_checkbox.setChecked(False)
        self.plan_combo.setCurrentIndex(0)


class AuthWindow(QWidget):
    authenticated = Signal(object)

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        hotel_name = self.db.get_settings()["hotel_name"]
        self.setObjectName("authWindow")
        self.setWindowTitle(f"{hotel_name} — Sign In")
        self.resize(980, 620)
        self.setMinimumSize(860, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)
        top_row.addWidget(BrandPanel(hotel_name))

        self.stack = QStackedWidget()
        self.login_page = LoginPage(db)
        self.signup_page = SignupPage(db)
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.signup_page)
        top_row.addWidget(self.stack, 1)
        root.addLayout(top_row, 1)

        # A page-wide footer band with a dim, slowly-drifting cloudy
        # background - spans the full window width (under both the brand
        # panel and the form) so the colour reads as continuing all the way
        # to the bottom edge instead of stopping short and leaving a bare
        # margin under the panel. The premium glass credit badge sits
        # fixed at the bottom centre of this band.
        footer_bar = WavyGradientBackground(
            colors=["#0f172a", "#1e293b", "#334155"], parent=None,
            style="clouds", speed=0.015,
        )
        footer_bar.setFixedHeight(64)
        footer_layout = QHBoxLayout(footer_bar)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch()
        footer_layout.addWidget(AnimatedCreditLabel("Developed By: Abdul Wahid Khan", font_size=12))
        footer_layout.addStretch()
        root.addWidget(footer_bar)

        self.login_page.login_successful.connect(self.authenticated.emit)
        self.login_page.go_to_signup.connect(lambda: crossfade_stack(self.stack, self.signup_page))
        self.signup_page.go_to_login.connect(self._go_to_login_after_signup)
        self.signup_page.signup_successful.connect(self._after_signup)

        # If there are no users yet, start on the signup page so onboarding is obvious.
        if self.db.count_users() == 0:
            self.stack.setCurrentWidget(self.signup_page)

    def _go_to_login_after_signup(self):
        crossfade_stack(self.stack, self.login_page)

    def _after_signup(self, _user):
        # Pick up whatever the signup page just remembered (or cleared) so
        # the login form reflects it immediately on arrival, and hide the
        # now one-time-only Sign Up link since an account exists.
        self.login_page.load_remembered()
        self.login_page.update_signup_availability()
        crossfade_stack(self.stack, self.login_page)

    def reset(self):
        self.login_page.clear_fields()
        crossfade_stack(self.stack, self.login_page)
