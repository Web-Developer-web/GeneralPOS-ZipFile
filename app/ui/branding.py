"""HotelPOS application icon - drawn entirely in code (no external image
assets to manage). A rounded blue badge with a bed glyph (hotel) and a
small gold receipt badge (point-of-sale) layered on top, rendered crisply
at every size Windows actually asks for (title bar, taskbar, Alt+Tab)."""
import qtawesome as qta
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QLinearGradient, QColor, QPainterPath

BG_START = "#2563eb"
BG_END = "#1e3a8a"
BADGE_COLOR = "#f59e0b"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def _draw_icon(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Rounded-square badge background.
    radius = size * 0.22
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0, QColor(BG_START))
    gradient.setColorAt(1, QColor(BG_END))
    painter.fillPath(path, gradient)

    # Hotel glyph (bed), white, centered with a slight upward offset so the
    # POS badge has room in the bottom-right corner.
    bed_size = max(int(size * 0.56), 8)
    bed_pixmap = qta.icon("fa5s.bed", color="white").pixmap(bed_size, bed_size)
    bx = (size - bed_size) / 2 - size * 0.02
    by = (size - bed_size) / 2 - size * 0.06
    painter.drawPixmap(int(bx), int(by), bed_pixmap)

    # Small gold "receipt" badge bottom-right, signalling POS/billing -
    # only at sizes where it stays legible rather than muddying the icon.
    if size >= 28:
        badge_d = size * 0.44
        badge_rect = QRectF(size - badge_d - size * 0.02, size - badge_d - size * 0.02, badge_d, badge_d)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BG_END))
        painter.drawEllipse(badge_rect.adjusted(-size * 0.02, -size * 0.02, size * 0.02, size * 0.02))
        painter.setBrush(QColor(BADGE_COLOR))
        painter.drawEllipse(badge_rect)

        glyph_size = max(int(badge_d * 0.6), 6)
        glyph_pixmap = qta.icon("fa5s.receipt", color="white").pixmap(glyph_size, glyph_size)
        gx = badge_rect.center().x() - glyph_size / 2
        gy = badge_rect.center().y() - glyph_size / 2
        painter.drawPixmap(int(gx), int(gy), glyph_pixmap)

    painter.end()
    return pixmap


def build_app_icon() -> QIcon:
    """A crisp multi-resolution HotelPOS QIcon, generated fresh every launch."""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(_draw_icon(size))
    return icon
