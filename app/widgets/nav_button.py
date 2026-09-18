"""Sidebar nav button with an animated glow + shimmer background when active."""
from PySide6.QtCore import (
    Qt, QVariantAnimation, QPropertyAnimation, QSequentialAnimationGroup, QEasingCurve,
)
from PySide6.QtGui import QPainter, QLinearGradient, QBrush, QColor
from PySide6.QtWidgets import QPushButton, QGraphicsDropShadowEffect

from app.theme import ACCENT


class NavButton(QPushButton):
    """A checkable sidebar button that, while active, sweeps a soft shimmer
    across its rounded background and pulses a matching glow shadow - a
    little bit of motion so the current section reads as "alive" instead of
    a flat, static highlight."""

    def __init__(self, text: str, accent: str = ACCENT, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self._accent = accent
        self._phase = 0.0
        self._wave_anim = None
        self._glow_group = None
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool):
        if checked:
            self._start_animations()
        else:
            self._stop_animations()
        self.update()

    def _start_animations(self):
        if self._wave_anim is None:
            self._wave_anim = QVariantAnimation(self)
            self._wave_anim.setStartValue(0.0)
            self._wave_anim.setEndValue(1.0)
            self._wave_anim.setDuration(1800)
            self._wave_anim.setLoopCount(-1)
            self._wave_anim.valueChanged.connect(self._on_wave_value)
        self._wave_anim.start()

        effect = QGraphicsDropShadowEffect(self)
        effect.setOffset(0, 0)
        effect.setColor(QColor(self._accent))
        effect.setBlurRadius(16)
        self.setGraphicsEffect(effect)

        # Breathing glow: blur radius grows/shrinks in a smooth, endless loop.
        self._glow_group = QSequentialAnimationGroup(self)
        grow = QPropertyAnimation(effect, b"blurRadius")
        grow.setStartValue(14)
        grow.setEndValue(30)
        grow.setDuration(900)
        grow.setEasingCurve(QEasingCurve.Type.InOutSine)
        shrink = QPropertyAnimation(effect, b"blurRadius")
        shrink.setStartValue(30)
        shrink.setEndValue(14)
        shrink.setDuration(900)
        shrink.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._glow_group.addAnimation(grow)
        self._glow_group.addAnimation(shrink)
        self._glow_group.setLoopCount(-1)
        self._glow_group.start()

    def _stop_animations(self):
        if self._wave_anim:
            self._wave_anim.stop()
        if self._glow_group:
            self._glow_group.stop()
            self._glow_group = None
        self.setGraphicsEffect(None)

    def _on_wave_value(self, value):
        self._phase = value
        self.update()

    def paintEvent(self, event):
        if not self.isChecked():
            super().paintEvent(event)
            return

        # Hand-paint the active background before letting the normal style
        # draw the icon/text on top - the stylesheet keeps this button's
        # background transparent while checked precisely so this custom
        # fill shows through instead of being covered. Two layers give it
        # depth: a diagonal two-tone base in the section's own accent color,
        # then a soft white shimmer band swept across it for motion.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)

        base = QColor(self._accent)
        base_gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base_gradient.setColorAt(0.0, base.lighter(120))
        base_gradient.setColorAt(1.0, base.darker(115))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(base_gradient))
        painter.drawRoundedRect(rect, 12, 12)

        band = 0.35
        center = self._phase
        left = max(0.0, center - band)
        right = min(1.0, center + band)
        transparent = QColor(255, 255, 255, 0)
        shimmer_peak = QColor(255, 255, 255, 130)

        shimmer = QLinearGradient(rect.topLeft(), rect.topRight())
        shimmer.setColorAt(0.0, transparent)
        if left > 0.0:
            shimmer.setColorAt(left, transparent)
        shimmer.setColorAt(center, shimmer_peak)
        if right < 1.0:
            shimmer.setColorAt(right, transparent)
        shimmer.setColorAt(1.0, transparent)

        painter.setBrush(QBrush(shimmer))
        painter.drawRoundedRect(rect, 12, 12)
        painter.end()

        super().paintEvent(event)
