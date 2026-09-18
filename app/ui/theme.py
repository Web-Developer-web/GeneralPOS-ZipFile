"""Centralised theming: QSS stylesheets + palette tokens for light/dark modes."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QGraphicsDropShadowEffect

ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
DANGER = "#dc2626"
DANGER_HOVER = "#b91c1c"
SUCCESS = "#16a34a"
SUCCESS_HOVER = "#15803d"
WARNING = "#d97706"
PURPLE = "#7c3aed"

PALETTES = {
    "light": {
        "bg": "#f3f4f6",
        "surface": "#ffffff",
        "surface_alt": "#f3f4f6",
        "border": "#dde1e6",
        "text": "#000000",
        "text_muted": "#4b5563",
        "sidebar_bg": "#111827",
        "sidebar_text": "#d1d5db",
        "sidebar_active": "#2563eb",
        "sidebar_hover": "#1f2937",
        "icon": "#374151",
        "icon_muted": "#6b7280",
        "input_bg": "#ffffff",
    },
    "dark": {
        "bg": "#0f172a",
        "surface": "#1e293b",
        "surface_alt": "#172033",
        "border": "#334155",
        "text": "#f1f5f9",
        "text_muted": "#94a3b8",
        "sidebar_bg": "#0b1220",
        "sidebar_text": "#cbd5e1",
        "sidebar_active": "#2563eb",
        "sidebar_hover": "#1e293b",
        "icon": "#e2e8f0",
        "icon_muted": "#64748b",
        "input_bg": "#111827",
    },
}


def palette(theme: str) -> dict:
    return PALETTES.get(theme, PALETTES["light"])


def apply_card_shadow(widget, blur=42, y_offset=10, alpha=24):
    """Attach a soft, wide drop shadow to give cards/dialogs a modern,
    neumorphic "floating" look - a larger blur with lower opacity reads as
    a gentle ambient shadow rather than a hard drop shadow."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


def _shade(hex_color: str, amount: float) -> str:
    """Lighten (amount > 0) or darken (amount < 0) a hex color in HSL space -
    used to build the subtle gradients behind neumorphic cards/buttons."""
    c = QColor(hex_color)
    h, s, l, a = c.getHslF()
    l = max(0.0, min(1.0, l + amount))
    c.setHslF(h, s, l, a)
    return c.name()


def build_qpalette(theme: str) -> QPalette:
    """Force a matching QPalette so native-rendered controls (calendar popup,
    spin box arrows, combobox frames) never fall back to the OS palette -
    that mismatch is what makes text disappear in light mode when Windows
    itself is set to dark mode."""
    p = palette(theme)
    pal = QPalette()

    window = QColor(p["bg"])
    surface = QColor(p["surface"])
    base = QColor(p["input_bg"])
    alt_base = QColor(p["surface_alt"])
    text = QColor(p["text"])
    muted = QColor(p["text_muted"])
    accent = QColor(ACCENT)

    pal.setColor(QPalette.ColorRole.Window, window)
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Base, base)
    pal.setColor(QPalette.ColorRole.AlternateBase, alt_base)
    pal.setColor(QPalette.ColorRole.ToolTipBase, surface)
    pal.setColor(QPalette.ColorRole.ToolTipText, text)
    pal.setColor(QPalette.ColorRole.Text, text)
    pal.setColor(QPalette.ColorRole.Button, surface)
    pal.setColor(QPalette.ColorRole.ButtonText, text)
    pal.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Highlight, accent)
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Link, accent)
    pal.setColor(QPalette.ColorRole.PlaceholderText, muted)

    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, muted)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, muted)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, muted)
    return pal


def build_stylesheet(theme: str) -> str:
    p = palette(theme)
    # A faint diagonal sheen (lighter in light mode, a touch lighter still
    # in dark mode) behind cards/buttons is what reads as "soft UI" instead
    # of a flat fill - paired with the wide, low-alpha apply_card_shadow
    # above, it gives the embossed, pillowy look without needing the dual
    # light/dark shadow pair real neumorphism relies on (Qt only supports
    # one QGraphicsDropShadowEffect per widget).
    card_sheen = _shade(p["surface"], 0.04 if theme == "light" else 0.02)
    return f"""
    QWidget {{
        background-color: {p['bg']};
        color: {p['text']};
        font-family: 'Segoe UI';
        font-size: 13px;
    }}

    QMainWindow, #authWindow {{
        background-color: {p['bg']};
    }}

    QLabel {{
        background: transparent;
    }}

    QLabel[role="pageTitle"] {{
        font-size: 22px;
        font-weight: 600;
        color: {p['text']};
    }}

    QLabel[role="subtitle"] {{
        color: {p['text_muted']};
        font-size: 13px;
    }}

    QFrame[card="true"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {card_sheen}, stop:1 {p['surface']});
        border: 1px solid {p['border']};
        border-radius: 18px;
    }}

    QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {p['input_bg']};
        border: 1px solid {p['border']};
        border-radius: 10px;
        padding: 8px 10px;
        color: {p['text']};
        selection-background-color: {ACCENT};
        selection-color: white;
    }}

    QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {ACCENT};
    }}

    /* Inline validation state (e.g. an invalid discount or insufficient
       cash amount on the billing screen) - kept generic so any plain
       QLineEdit can opt in via the dynamic "error" property. */
    QLineEdit[error="true"], QLineEdit[error="true"]:focus {{
        border: 1.5px solid {DANGER};
    }}

    /* Premium auth-screen fields (GlowLineEdit / PasswordField) - a
       slightly larger radius and roomier padding than the app's regular
       compact inputs, scoped to this object name only so the rest of the
       app (billing, items, settings) keeps its existing field sizing. */
    QLineEdit#glowInput {{
        border-radius: 13px;
        padding: 10px 14px;
        font-size: 13px;
    }}
    QLineEdit#glowInput:focus {{
        border: 1.5px solid {ACCENT};
    }}
    QLineEdit#glowInput[error="true"], QLineEdit#glowInput[error="true"]:focus {{
        border: 1.5px solid {DANGER};
    }}

    QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QPushButton:disabled {{
        color: {p['text_muted']};
        background-color: {p['surface_alt']};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 26px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {p['surface']};
        color: {p['text']};
        border: 1px solid {p['border']};
        selection-background-color: {ACCENT};
        selection-color: white;
        outline: none;
        padding: 4px;
    }}

    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 20px;
        border-left: 1px solid {p['border']};
        border-top-right-radius: 8px;
        background-color: {p['surface_alt']};
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 20px;
        border-left: 1px solid {p['border']};
        border-bottom-right-radius: 8px;
        background-color: {p['surface_alt']};
    }}

    QCalendarWidget {{
        background-color: {p['surface']};
    }}
    QCalendarWidget QWidget {{
        background-color: {p['surface']};
        color: {p['text']};
        alternate-background-color: {p['surface_alt']};
    }}
    QCalendarWidget QToolButton {{
        color: {p['text']};
        background: transparent;
        border-radius: 6px;
        padding: 4px 8px;
        font-weight: 600;
    }}
    QCalendarWidget QToolButton:hover {{
        background-color: {p['surface_alt']};
    }}
    QCalendarWidget QMenu {{
        background-color: {p['surface']};
        color: {p['text']};
    }}
    QCalendarWidget QAbstractItemView:enabled {{
        color: {p['text']};
        background-color: {p['surface']};
        selection-background-color: {ACCENT};
        selection-color: white;
    }}
    QCalendarWidget QAbstractItemView:disabled {{
        color: {p['text_muted']};
    }}
    QCalendarWidget #qt_calendar_navigationbar {{
        background-color: {p['surface_alt']};
    }}

    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {card_sheen}, stop:1 {p['surface']});
        border: 1px solid {p['border']};
        border-radius: 10px;
        padding: 9px 16px;
        color: {p['text']};
        font-weight: 500;
    }}

    QPushButton:hover {{
        background-color: {p['surface_alt']};
    }}
    QPushButton:pressed {{
        background-color: {p['border']};
    }}

    QPushButton[variant="primary"] {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_shade(ACCENT, 0.06)}, stop:1 {ACCENT});
        color: white;
        border: none;
    }}
    QPushButton[variant="primary"]:hover {{
        background-color: {ACCENT_HOVER};
    }}
    QPushButton[variant="primary"]:pressed {{
        background-color: #1e40af;
    }}
    QPushButton[variant="primary"]:disabled {{
        background-color: {p['border']};
        color: {p['text_muted']};
    }}

    QPushButton[variant="success"] {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_shade(SUCCESS, 0.06)}, stop:1 {SUCCESS});
        color: white;
        border: none;
    }}
    QPushButton[variant="success"]:hover {{
        background-color: {SUCCESS_HOVER};
    }}
    QPushButton[variant="success"]:pressed {{
        background-color: #14532d;
    }}

    QPushButton[variant="danger"] {{
        background-color: transparent;
        color: {DANGER};
        border: 1px solid {DANGER};
    }}
    QPushButton[variant="danger"]:hover {{
        background-color: {DANGER};
        color: white;
    }}
    QPushButton[variant="danger"]:pressed {{
        background-color: {DANGER_HOVER};
        color: white;
    }}

    QPushButton[variant="ghost"] {{
        background-color: transparent;
        border: none;
        color: {p['text_muted']};
    }}
    QPushButton[variant="ghost"]:hover {{
        background-color: {p['surface_alt']};
        color: {p['text']};
    }}

    QPushButton[flat="true"] {{
        border: none;
        background: transparent;
    }}

    QPushButton[variant="icon"] {{
        background-color: {p['surface_alt']};
        border: 1px solid {p['border']};
        border-radius: 10px;
        padding: 4px;
    }}
    QPushButton[variant="icon"]:hover {{
        background-color: {ACCENT};
        border: 1px solid {ACCENT};
    }}
    QPushButton[variant="icon"]:pressed {{
        background-color: {ACCENT_HOVER};
        border: 1px solid {ACCENT_HOVER};
    }}

    QPushButton[variant="qty"] {{
        background-color: {p['surface_alt']};
        border: 1px solid {p['border']};
        border-radius: 12px;
        padding: 0;
        font-weight: 700;
        color: {p['text']};
    }}
    QPushButton[variant="qty"]:hover {{
        background-color: {ACCENT};
        color: white;
        border: 1px solid {ACCENT};
    }}
    QPushButton[variant="qty"]:pressed {{
        background-color: {ACCENT_HOVER};
        color: white;
    }}

    #sidebar {{
        background-color: {p['sidebar_bg']};
    }}

    #sidebar QLabel {{
        color: {p['sidebar_text']};
    }}

    QPushButton[nav="true"] {{
        background-color: transparent;
        border: none;
        border-radius: 12px;
        color: {p['sidebar_text']};
        text-align: left;
        padding: 11px 8px;
        font-weight: 500;
    }}
    QPushButton[nav="true"]:hover:!checked {{
        background-color: {p['sidebar_hover']};
    }}
    QPushButton[nav="true"]:checked {{
        background-color: transparent;
        color: white;
    }}

    QTableWidget {{
        background-color: {p['surface']};
        alternate-background-color: {p['surface_alt']};
        gridline-color: {p['border']};
        border: 1px solid {p['border']};
        border-radius: 14px;
        selection-background-color: {ACCENT};
        selection-color: white;
        color: {p['text']};
    }}

    QHeaderView::section {{
        background-color: {p['surface_alt']};
        color: {p['text_muted']};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {p['border']};
        font-weight: 600;
    }}

    QTableWidget::item {{
        padding: 6px;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {p['border']};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
    }}
    QScrollBar::handle:horizontal {{
        background: {p['border']};
        border-radius: 5px;
        min-width: 24px;
    }}

    QTabWidget::pane {{
        border: 1px solid {p['border']};
        border-radius: 14px;
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {p['text_muted']};
        padding: 9px 18px;
        font-weight: 500;
    }}
    QTabBar::tab:selected {{
        color: {ACCENT};
        border-bottom: 2px solid {ACCENT};
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {p['border']};
        background: {p['input_bg']};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border: 1px solid {ACCENT};
    }}

    QToolTip {{
        background-color: {p['surface']};
        color: {p['text']};
        border: 1px solid {p['border']};
        padding: 4px 8px;
        border-radius: 6px;
    }}

    QMessageBox {{
        background-color: {p['surface']};
    }}
    """


class ThemeManager:
    """Small pub/sub so widgets can react to a theme change at runtime."""

    def __init__(self, theme: str = "light"):
        self.theme = theme
        self._listeners = []

    def palette(self) -> dict:
        return palette(self.theme)

    def icon_color(self) -> str:
        return self.palette()["icon"]

    def icon_color_muted(self) -> str:
        return self.palette()["icon_muted"]

    def subscribe(self, callback):
        self._listeners.append(callback)

    def set_theme(self, theme: str, app):
        self.theme = theme
        app.setPalette(build_qpalette(theme))
        app.setStyleSheet(build_stylesheet(theme))
        for cb in list(self._listeners):
            cb(theme)

    def stylesheet(self) -> str:
        return build_stylesheet(self.theme)


theme_manager = ThemeManager()
