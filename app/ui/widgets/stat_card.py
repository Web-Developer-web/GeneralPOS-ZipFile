"""Dashboard stat card widget."""
import re

import qtawesome as qta
from PySide6.QtCore import Qt, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QGraphicsDropShadowEffect

_NUMBER_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")


class StatCard(QFrame):
    def __init__(self, title: str, icon_name: str, accent: str, parent=None):
        super().__init__(parent)
        self.setProperty("card", "true")
        self.setMinimumHeight(110)
        self._icon_name = icon_name
        self._accent = accent
        self._current_numeric = 0.0
        self._value_anim = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(16)

        self.icon_frame = QFrame()
        self.icon_frame.setFixedSize(54, 54)
        self.icon_frame.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f" stop:0 {accent}33, stop:1 {accent}15); border-radius: 16px; border: none;"
        )
        icon_layout = QVBoxLayout(self.icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(qta.icon(icon_name, color=accent).pixmap(26, 26))
        icon_layout.addWidget(self.icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        self.value_label = QLabel("0")
        self.value_label.setStyleSheet("font-size: 24px; font-weight: 700; border: none;")
        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "subtitle")
        text_layout.addWidget(self.value_label)
        text_layout.addWidget(self.title_label)

        outer.addWidget(self.icon_frame)
        outer.addLayout(text_layout)
        outer.addStretch()

    def enterEvent(self, event):
        super().enterEvent(event)
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setBlurRadius(58)
            effect.setOffset(0, 18)
            tint = QColor(self._accent)
            tint.setAlpha(70)
            effect.setColor(tint)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setBlurRadius(42)
            effect.setOffset(0, 10)
            effect.setColor(QColor(0, 0, 0, 24))

    def set_value(self, value: str, animate: bool = True):
        match = _NUMBER_RE.search(value)
        if not match or not animate:
            self.value_label.setText(value)
            if match:
                self._current_numeric = float(match.group().replace(",", ""))
            return

        prefix, suffix = value[:match.start()], value[match.end():]
        number_str = match.group()
        decimals = len(number_str.split(".")[1]) if "." in number_str else 0
        target = float(number_str.replace(",", ""))
        start = self._current_numeric
        self._current_numeric = target

        if self._value_anim is not None:
            # DeleteWhenStopped means a previous animation that already
            # finished on its own has had its underlying C++ object freed -
            # the Python reference is then stale and .stop() would raise.
            try:
                self._value_anim.stop()
            except RuntimeError:
                pass

        anim = QVariantAnimation(self)
        anim.setDuration(700)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _on_value(v, decimals=decimals, prefix=prefix, suffix=suffix):
            text = f"{v:,.{decimals}f}" if decimals else f"{int(round(v)):,}"
            self.value_label.setText(f"{prefix}{text}{suffix}")

        anim.valueChanged.connect(_on_value)
        self._value_anim = anim
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
