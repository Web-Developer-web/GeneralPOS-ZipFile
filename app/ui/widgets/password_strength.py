"""A small password-strength meter: a thin rounded bar + label that
recompute from the actual password text (length + character variety) -
real feedback, not a decorative placeholder."""
import re

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame

from app.ui.theme import DANGER, WARNING, SUCCESS, ACCENT

_LEVELS = [
    (0, "", "transparent"),
    (1, "Weak", DANGER),
    (2, "Fair", WARNING),
    (3, "Good", ACCENT),
    (4, "Strong", SUCCESS),
]


def _score(password: str) -> int:
    if not password:
        return 0
    score = 0
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if re.search(r"[A-Z]", password) and re.search(r"[a-z]", password):
        score += 1
    if re.search(r"\d", password):
        score += 1
    if re.search(r"[^A-Za-z0-9]", password):
        score += 1
    return min(score, 4)


class PasswordStrengthMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(4)

        track = QFrame()
        track.setFixedHeight(5)
        track.setStyleSheet("background-color: rgba(148, 163, 184, 60); border-radius: 2px;")
        track_layout = QHBoxLayout(track)
        track_layout.setContentsMargins(0, 0, 0, 0)

        self._fill = QFrame(track)
        self._fill.setFixedHeight(5)
        self._fill.setStyleSheet("background-color: transparent; border-radius: 2px;")
        self._fill.setGeometry(0, 0, 0, 5)
        layout.addWidget(track)

        self._label = QLabel("")
        self._label.setStyleSheet("font-size: 11px; font-weight: 600; border: none;")
        layout.addWidget(self._label)

        self._track = track
        self._score = 0
        self._anim = QPropertyAnimation(self._fill, b"geometry", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def update_password(self, password: str):
        self._score = _score(password)
        _, text, color = _LEVELS[self._score]

        self._fill.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
        self._animate_to(self._score)

        self._label.setText(text)
        self._label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {color}; border: none;")
        self.setVisible(bool(password))

    def _animate_to(self, score: int):
        target_w = int(self._track.width() * (score / 4)) if score else 0
        self._anim.stop()
        self._anim.setStartValue(self._fill.geometry())
        self._anim.setEndValue(self._fill.geometry().__class__(0, 0, target_w, 5))
        self._anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep the fill's current fraction correct if the field (and so
        # this meter) is resized by the layout - snap instantly rather
        # than re-animating on every resize tick.
        w = int(self._track.width() * (self._score / 4)) if self._score else 0
        self._fill.setGeometry(0, 0, w, 5)
