"""Animated gradient backgrounds.

Two flavours, both painted directly with QPainter (no images/assets) and
driven by a single QTimer so they stay cheap even on modest hardware:

- "waves": a continuously-moving gradient with translucent sine-wave layers
  along the bottom edge - used behind large areas (the login brand panel,
  the dashboard hero banner).
- "shimmer": the same moving gradient plus a soft diagonal light band that
  sweeps across on a loop - a subtler, more "premium badge" animation used
  behind small elements (the digital clock, the credit pill) where a full
  wave silhouette wouldn't read at that size.
- "clouds": a dim, muted base tone with a handful of large, soft, blurred
  blobs that drift slowly across it like haze/clouds - used behind quiet
  footer bands where the effect should read as ambient atmosphere rather
  than an active accent.
"""
import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QRadialGradient
from PySide6.QtWidgets import QWidget


class WavyGradientBackground(QWidget):
    def __init__(self, colors=None, wave_color: str = None, parent=None,
                 interval_ms: int = 60, speed: float = 0.02,
                 radius: int = 0, style: str = "waves"):
        super().__init__(parent)
        self._colors = colors or ["#1d4ed8", "#4f46e5", "#7c3aed"]
        self._wave_color = wave_color
        self._phase = 0.0
        self._speed = speed
        self._interval = interval_ms
        self._radius = radius
        self._style = style

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start(self._interval)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self):
        self._phase += self._speed
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        if self._radius > 0:
            clip = QPainterPath()
            clip.addRoundedRect(0, 0, w, h, self._radius, self._radius)
            painter.setClipPath(clip)

        # The gradient's end point drifts slowly back and forth, which reads
        # as a gentle, perpetual "breathing" of colour across the panel.
        drift = (math.sin(self._phase) + 1) / 2  # 0..1
        grad = QLinearGradient(0, 0, w * (0.35 + 0.65 * drift), h)
        n = len(self._colors)
        for i, c in enumerate(self._colors):
            grad.setColorAt(0.0 if n == 1 else i / (n - 1), QColor(c))
        painter.fillRect(self.rect(), grad)

        if self._style == "waves" and self._wave_color:
            self._paint_waves(painter, w, h)
        elif self._style == "shimmer":
            self._paint_shimmer(painter, w, h)
        elif self._style == "clouds":
            self._paint_clouds(painter, w, h)

        painter.end()

    def _paint_waves(self, painter, w, h):
        painter.setPen(Qt.PenStyle.NoPen)
        base_color = QColor(self._wave_color)
        step = 16
        for layer in range(2):
            path = QPainterPath()
            base_y = h * (0.74 + layer * 0.1)
            amp = 10 + layer * 7
            path.moveTo(0, h)
            path.lineTo(0, base_y)
            x = 0.0
            while x <= w:
                y = base_y + amp * math.sin(self._phase * (1.4 + layer * 0.5) + x / 70.0)
                path.lineTo(x, y)
                x += step
            path.lineTo(w, h)
            path.closeSubpath()
            base_color.setAlphaF(0.16 + layer * 0.10)
            painter.setBrush(base_color)
            painter.drawPath(path)

    def _paint_shimmer(self, painter, w, h):
        # A soft light band that sweeps left-to-right on a loop, independent
        # of the base gradient drift - a subtler "premium badge" glint
        # rather than the wave silhouette used on bigger panels.
        band_w = max(24.0, w * 0.5)
        total = w + band_w
        sweep_x = ((self._phase * 26.0) % total) - band_w

        grad = QLinearGradient(sweep_x, 0, sweep_x + band_w, 0)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.5, QColor(255, 255, 255, 60))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawRect(0, 0, w, h)

    def _paint_clouds(self, painter, w, h):
        # A handful of large, soft, low-opacity radial blobs drifting slowly
        # at different speeds/heights - reads as dim haze rather than a
        # distinct animated shape, so it stays calm behind footer content.
        painter.setPen(Qt.PenStyle.NoPen)
        blobs = [
            (0.33, 0.9, 0.55, 0.42),
            (-0.22, 0.5, 0.75, 0.32),
            (0.55, -0.35, 0.6, 0.28),
            (-0.6, -0.15, 0.65, 0.24),
        ]
        for speed_mul, y_frac, size_frac, alpha in blobs:
            span = w + w * size_frac * 2
            cx = ((self._phase * 14.0 * speed_mul) % span) - w * size_frac
            cy = h * y_frac
            r = w * size_frac
            grad = QRadialGradient(cx, cy, r)
            grad.setColorAt(0.0, QColor(255, 255, 255, int(255 * alpha * 0.16)))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(grad)
            painter.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
