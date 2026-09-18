"""Live digital clock card - Dashboard-only.

Same visual language as the "Developed By" credit badge (see
app.widgets.credit_label): a translucent dark-glass card with a faint
light border and a fixed, static drop shadow - no animated glow, no
per-open random entrance variant. The card's one idle motion is the
credit badge's light sweep: a soft highlight glides once across the card
every few seconds, then pauses before the next pass. On first appearing
it fades and rises into place once, exactly like the credit badge.

The whole card - background, shadow, sweep, and text - is drawn directly
in paintEvent rather than via child QLabels/QGraphicsEffect, for the same
reason the credit badge does it that way: it lets the card and its text
fade in together in one pass. The shadow itself is hand-painted (layered
translucent rounded rects) rather than a QGraphicsDropShadowEffect,
because this card lives inside the Dashboard's hero banner, which already
has its own drop-shadow effect - nesting a second QGraphicsEffect on a
descendant of an already-shadowed widget is what caused a rendering bug
previously (see project memory), so this widget never uses one at all.
"""
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QFont, QFontMetricsF
from PySide6.QtWidgets import QWidget

_ENTRANCE_RISE_PX = 16
_ENTRANCE_MS = 520

_TICK_MS = 30

# The light sweep: glides across the card, pauses, then repeats. Same
# timing/shape as the credit badge's sweep.
_SWEEP_PERIOD_MS = 3200
_SWEEP_ACTIVE_FRACTION = 0.5
_SWEEP_BAND_WIDTH_FRAC = 0.55
_SWEEP_PEAK_ALPHA = 95

# Hand-painted shadow: a handful of layered, progressively larger and
# fainter rounded rects behind the card approximate a soft blur without
# needing a real QGraphicsEffect (see module docstring for why).
_SHADOW_LAYERS = 6
_SHADOW_MAX_GROW = 16.0
_SHADOW_OFFSET_Y = 4.0
_SHADOW_PEAK_ALPHA = 70

_CARD_RADIUS = 20
_PAD_TOP, _PAD_BOTTOM = 16, 18
_LINE_SPACING = 4
# Extra transparent margin around the drawn card so the entrance rise and
# the hand-painted shadow both have room to play without being clipped.
_MARGIN = 12 + round(_SHADOW_MAX_GROW)

_MIN_WIDTH, _MAX_WIDTH = 330, 400


class DigitalClockWidget(QWidget):
    def __init__(self, parent=None, glow_color: str = "#2563eb"):
        super().__init__(parent)
        self.setObjectName("digitalClock")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._glow_color = glow_color
        self._colon_visible = True

        self._time_font = QFont("Consolas", 22)
        self._time_font.setFamilies(["Consolas", "Courier New"])
        self._time_font.setWeight(QFont.Weight.Bold)
        self._time_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)

        self._date_font = QFont("Segoe UI", 12)
        self._date_font.setWeight(QFont.Weight.DemiBold)
        self._date_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.7)

        self._time_metrics = QFontMetricsF(self._time_font)
        self._date_metrics = QFontMetricsF(self._date_font)

        content_h = self._time_metrics.height() + _LINE_SPACING + self._date_metrics.height()
        self._card_h = _PAD_TOP + content_h + _PAD_BOTTOM
        self.setFixedHeight(round(self._card_h) + _MARGIN * 2)
        self.setMinimumWidth(_MIN_WIDTH)
        self.setMaximumWidth(_MAX_WIDTH)

        self._time_text = ""
        self._date_text = ""
        self._update_text()

        self._paint_alpha = 0.0     # entrance fade, 0..1
        self._entrance_ready = False    # True once the deferred entrance has actually begun
        self._entrance_running = False
        self._entrance_start = 0
        self._rise = 0.0
        self._sweep_elapsed = 0
        self._blink_elapsed = 0
        self._started = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _glow_qcolor(self, alpha: int) -> QColor:
        c = QColor(self._glow_color)
        c.setAlpha(alpha)
        return c

    def _update_text(self):
        now = datetime.now()
        sep = ":" if self._colon_visible else " "
        self._time_text = now.strftime(f"%I{sep}%M{sep}%S %p")
        self._date_text = now.strftime("%A  •  %d %B %Y")

    # -- lifecycle ---------------------------------------------------- #
    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._update_text()
            self._timer.start(_TICK_MS)
        if not self._started:
            self._started = True
            QTimer.singleShot(150, self._play_entrance)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()
        self._started = False

    # -- entrance ------------------------------------------------------ #
    def _play_entrance(self):
        self._paint_alpha = 0.0
        self._entrance_start = 0
        self._entrance_running = True
        self._entrance_ready = True

    # -- the single tick that drives everything ------------------------ #
    def _tick(self):
        # Entrance: a short, smooth fade + rise, eased with a simple
        # power-curve ramp - identical to the credit badge's entrance.
        self._rise = 0.0
        if not self._entrance_ready:
            self._paint_alpha = 0.0
        elif self._entrance_running:
            self._entrance_start += _TICK_MS
            t = min(1.0, self._entrance_start / _ENTRANCE_MS)
            eased = 1 - (1 - t) ** 3  # ease-out cubic
            self._paint_alpha = eased
            self._rise = (1 - eased) * _ENTRANCE_RISE_PX
            if t >= 1.0:
                self._entrance_running = False
        else:
            self._paint_alpha = 1.0

        # The idle motion: advance the light-sweep clock, same as the
        # credit badge's _sweep_progress().
        self._sweep_elapsed = (self._sweep_elapsed + _TICK_MS) % _SWEEP_PERIOD_MS

        # The clock's own functionality: blink the colon twice a second and
        # keep the displayed time/date current.
        self._blink_elapsed += _TICK_MS
        if self._blink_elapsed >= 500:
            self._blink_elapsed = 0
            self._colon_visible = not self._colon_visible
        self._update_text()

        self.update()

    def _sweep_progress(self):
        """Returns None while paused, or 0..1 while the light is gliding
        across the card (eased, so it drifts rather than moves linearly)."""
        active_span = _SWEEP_PERIOD_MS * _SWEEP_ACTIVE_FRACTION
        if self._sweep_elapsed >= active_span:
            return None
        t = self._sweep_elapsed / active_span
        return t * t * (3 - 2 * t)  # smoothstep ease

    # -- paint: the rounded translucent glass card + its text ---------- #
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setOpacity(self._paint_alpha)

        w, h = self.width() - _MARGIN * 2, self._card_h
        cx, cy = self.width() / 2, self.height() / 2
        painter.translate(cx, cy + self._rise)
        painter.translate(-w / 2, -h / 2)

        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), _CARD_RADIUS, _CARD_RADIUS)

        # A hand-painted soft shadow behind the card - see module docstring
        # for why this isn't a QGraphicsDropShadowEffect.
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(_SHADOW_LAYERS, 0, -1):
            t = i / _SHADOW_LAYERS
            grow = _SHADOW_MAX_GROW * t
            alpha = int(_SHADOW_PEAK_ALPHA * (1 - t) ** 1.5)
            if alpha <= 0:
                continue
            layer_rect = QRectF(-grow, _SHADOW_OFFSET_Y - grow, w + grow * 2, h + grow * 2)
            layer_path = QPainterPath()
            layer_path.addRoundedRect(layer_rect, _CARD_RADIUS + grow, _CARD_RADIUS + grow)
            painter.fillPath(layer_path, self._glow_qcolor(alpha))

        # The same frosted dark-glass fill as the credit badge.
        painter.fillPath(path, QColor(15, 23, 42, 168))

        # The same faint light top-edge border as the credit badge.
        painter.setPen(QColor(255, 255, 255, 60))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setFont(self._time_font)
        painter.setPen(QColor(255, 255, 255, 235))
        time_w = self._time_metrics.horizontalAdvance(self._time_text)
        time_baseline_y = _PAD_TOP + self._time_metrics.ascent()
        painter.drawText(QPointF((w - time_w) / 2, time_baseline_y), self._time_text)

        painter.setFont(self._date_font)
        painter.setPen(QColor(255, 255, 255, 224))
        date_w = self._date_metrics.horizontalAdvance(self._date_text)
        date_top = _PAD_TOP + self._time_metrics.height() + _LINE_SPACING
        date_baseline_y = date_top + self._date_metrics.ascent()
        painter.drawText(QPointF((w - date_w) / 2, date_baseline_y), self._date_text)

        # The light sweep itself: a soft vertical highlight band glides
        # left-to-right over everything drawn so far, clipped to the
        # card's own rounded shape - drawn last (on top) exactly like the
        # credit badge's sweep.
        progress = self._sweep_progress()
        if progress is not None:
            band_w = w * _SWEEP_BAND_WIDTH_FRAC
            band_center = -band_w / 2 + progress * (w + band_w)
            gradient = QLinearGradient(band_center - band_w / 2, 0, band_center + band_w / 2, 0)
            gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
            gradient.setColorAt(0.5, QColor(255, 255, 255, _SWEEP_PEAK_ALPHA))
            gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.save()
            painter.setClipPath(path)
            painter.fillRect(QRectF(0, 0, w, h), gradient)
            painter.restore()

        painter.end()
