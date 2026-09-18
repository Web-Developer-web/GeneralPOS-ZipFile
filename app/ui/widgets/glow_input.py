"""A QLineEdit with a leading icon, a soft animated focus glow, and an
inline error state (red border + a small shake) - the shared building
block behind the premium Sign In / Sign Up fields. Plain QLineEdit
elsewhere in the app is untouched; this is opt-in per field.
"""
import qtawesome as qta
from PySide6.QtCore import QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLineEdit, QGraphicsDropShadowEffect

from app.ui.theme import ACCENT, theme_manager

_GLOW_FOCUS_BLUR = 22
_GLOW_COLOR_ALPHA = 130


class GlowLineEdit(QLineEdit):
    def __init__(self, placeholder: str = "", icon_name: str = None, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(46)
        self.setObjectName("glowInput")
        self._error = False
        self._icon_name = icon_name

        if icon_name:
            self._icon_action = self.addAction(
                qta.icon(icon_name, color=theme_manager.icon_color_muted()),
                QLineEdit.ActionPosition.LeadingPosition,
            )
            theme_manager.subscribe(lambda _t: self._refresh_icon())
        else:
            self._icon_action = None

        # Starts invisible (blur 0) and grows into a soft coloured glow on
        # focus - a real animated property, not a static QSS hover state,
        # so it reads as a smooth transition rather than an instant snap.
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setOffset(0, 0)
        self._glow.setColor(QColor(ACCENT))
        self._glow.setBlurRadius(0)
        self.setGraphicsEffect(self._glow)

        self._glow_anim = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._glow_anim.setDuration(220)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._shake_anim = None

    def _refresh_icon(self):
        if self._icon_action:
            self._icon_action.setIcon(qta.icon(self._icon_name, color=theme_manager.icon_color_muted()))

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._animate_glow(_GLOW_FOCUS_BLUR)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._animate_glow(0)

    def _animate_glow(self, target_blur: float):
        color = QColor(ACCENT)
        color.setAlpha(_GLOW_COLOR_ALPHA)
        self._glow.setColor(color)
        self._glow_anim.stop()
        self._glow_anim.setStartValue(self._glow.blurRadius())
        self._glow_anim.setEndValue(target_blur)
        self._glow_anim.start()

    def set_error(self, is_error: bool, shake: bool = True):
        """Toggle the red-border invalid state, optionally with a quick
        shake so a failed field visibly calls for attention."""
        if is_error == self._error:
            return
        self._error = is_error
        self.setProperty("error", is_error)
        self.style().unpolish(self)
        self.style().polish(self)
        if is_error and shake:
            self._shake()

    def clear_error(self):
        self.set_error(False, shake=False)

    def _shake(self):
        rest = self.pos()
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(320)
        offsets = [0, -8, 8, -6, 6, -3, 3, 0]
        for i, dx in enumerate(offsets):
            anim.setKeyValueAt(i / (len(offsets) - 1), QPoint(rest.x() + dx, rest.y()))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._shake_anim = anim
