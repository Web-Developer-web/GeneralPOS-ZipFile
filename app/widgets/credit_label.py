"""Premium 'Developed By' credit badge.

A small rounded glass-style card - a translucent dark fill with a soft
light border and a fixed, subtle drop shadow - fixed at the bottom centre
of the page. "Abdul Wahid Khan" carries visual emphasis (bold, brighter)
against the softer "Developed By:" label beside it.

On first appearing it fades and rises smoothly into place once. From then
on its only motion is a slow, continuous light sweep: a soft diagonal
highlight glides once across the card every few seconds - like a glint of
light passing over glass - then pauses before the next pass. That's the
card's one animation; there's no float, no breathing glow, and no hover
reaction, so it reads as calm and premium rather than busy.

The whole card - background, sweep highlight, and text - is drawn
directly in paintEvent rather than by resizing/repositioning the widget
itself. That keeps the widget's actual geometry entirely owned by its
parent layout, so it can never drift out of place when a sibling (the
dashboard's live clock, a refreshed table, a window resize) triggers a
later re-layout. Everything is computed on a single lightweight timer, so
it stays cheap even with several instances on screen at once.
"""
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QFont, QFontMetricsF
from PySide6.QtWidgets import QWidget, QGraphicsDropShadowEffect

_ENTRANCE_RISE_PX = 16
_ENTRANCE_MS = 520

_TICK_MS = 30

# The light sweep: glides across the card, pauses, then repeats.
_SWEEP_PERIOD_MS = 3200          # total time for one glide + pause cycle
_SWEEP_ACTIVE_FRACTION = 0.5     # fraction of the period actually spent gliding
_SWEEP_BAND_WIDTH_FRAC = 0.55    # highlight band width, as a fraction of the card width
_SWEEP_PEAK_ALPHA = 95           # brightest point of the highlight (0-255)

_SHADOW_BLUR = 18.0
_SHADOW_ALPHA = 90

_PAD_X, _PAD_Y = 18, 9
_TEXT_SPACING = 6
# Extra transparent margin around the drawn card so the entrance rise has
# room to play without being clipped.
_MARGIN = 12


class AnimatedCreditLabel(QWidget):
    def __init__(self, text: str, parent=None, font_size: int = 11,
                 glow_color: str = "#3b82f6"):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._glow_color = glow_color

        # Split into two runs so "Abdul Wahid Khan" can carry its own
        # bolder, brighter emphasis against the softer "Developed By:"
        # lead-in - both are drawn by hand in paintEvent (see the class
        # docstring for why this isn't a pair of child QLabels).
        prefix, _, name = text.partition(": ")
        self._lead_text = f"{prefix}:" if name else text
        self._name_text = name

        self._lead_font = QFont("Segoe UI", font_size)
        self._lead_font.setWeight(QFont.Weight.Medium)
        self._name_font = QFont("Segoe UI", font_size + 1)
        self._name_font.setWeight(QFont.Weight.Bold)
        self._name_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.3)

        lead_metrics = QFontMetricsF(self._lead_font)
        name_metrics = QFontMetricsF(self._name_font)
        lead_w = lead_metrics.horizontalAdvance(self._lead_text)
        name_w = name_metrics.horizontalAdvance(self._name_text) if self._name_text else 0
        spacing = _TEXT_SPACING if self._name_text else 0
        text_h = max(lead_metrics.height(), name_metrics.height())

        self._lead_metrics = lead_metrics
        self._name_metrics = name_metrics
        # The card's own design size.
        self._card_w = _PAD_X * 2 + lead_w + spacing + name_w
        self._card_h = _PAD_Y * 2 + text_h

        fixed_w = round(self._card_w) + _MARGIN * 2
        fixed_h = round(self._card_h) + _MARGIN * 2
        self.setFixedSize(fixed_w, fixed_h)

        # A fixed, static shadow gives the card its glass depth - no
        # breathing/animation on it any more, that's all in the sweep now.
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setOffset(0, 3)
        shadow.setBlurRadius(_SHADOW_BLUR)
        shadow.setColor(self._glow_qcolor(_SHADOW_ALPHA))
        self.setGraphicsEffect(shadow)

        self._paint_alpha = 0.0     # entrance fade, 0..1
        self._entrance_ready = False    # True once the deferred entrance has actually begun
        self._entrance_running = False
        self._entrance_start = 0
        self._rise = 0.0
        self._sweep_elapsed = 0
        self._started = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _glow_qcolor(self, alpha: int) -> QColor:
        c = QColor(self._glow_color)
        c.setAlpha(alpha)
        return c

    # -- lifecycle ---------------------------------------------------- #
    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start(_TICK_MS)
        if not self._started:
            self._started = True
            QTimer.singleShot(120, self._play_entrance)

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
        # power-curve ramp rather than a discrete animation object. Held
        # fully transparent until the deferred start fires (avoids a
        # one-frame flash at full opacity before that happens).
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

        # The one idle motion: advance the light-sweep clock. It just
        # keeps counting up - _sweep_progress() below turns that into a
        # repeating glide-then-pause position at paint time.
        self._sweep_elapsed = (self._sweep_elapsed + _TICK_MS) % _SWEEP_PERIOD_MS

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

        cx, cy = self.width() / 2, self.height() / 2
        painter.translate(cx, cy + self._rise)
        painter.translate(-self._card_w / 2, -self._card_h / 2)

        w, h = self._card_w, self._card_h
        radius = h / 2.2
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)

        # A frosted dark-glass fill - translucent enough to read as
        # "glass", but with enough body that the bold white text stays
        # readable over any page background (light or dark theme, or the
        # auth screen's own dark footer band) without extra logic.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(path, QColor(15, 23, 42, 168))

        # A faint light top edge is the classic "glass" glint cue.
        painter.setPen(QColor(255, 255, 255, 60))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        baseline_y = h / 2 + (self._lead_metrics.ascent() - self._lead_metrics.descent()) / 2
        x = _PAD_X
        painter.setPen(QColor(255, 255, 255, 209))
        painter.setFont(self._lead_font)
        painter.drawText(QPointF(x, baseline_y), self._lead_text)
        x += self._lead_metrics.horizontalAdvance(self._lead_text)

        if self._name_text:
            x += _TEXT_SPACING
            name_baseline_y = h / 2 + (self._name_metrics.ascent() - self._name_metrics.descent()) / 2
            painter.setPen(QColor(255, 255, 255, 255))
            painter.setFont(self._name_font)
            painter.drawText(QPointF(x, name_baseline_y), self._name_text)

        # The light sweep itself: a soft vertical highlight band glides
        # left-to-right over everything drawn so far, clipped to the
        # card's own rounded shape so it never spills past its edges.
        # Drawn last (on top) so it glints over both the glass and the
        # text, the way a reflection would.
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
