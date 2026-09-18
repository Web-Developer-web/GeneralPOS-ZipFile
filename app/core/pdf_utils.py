"""HTML -> PDF / printer export helpers built on Qt's own print pipeline
(no extra dependencies beyond PySide6). Includes thermal-receipt support
for 80mm / 58mm POS printers with auto-fit page height.

Three Qt rich-text quirks this module works around:

1. Never manually force a QTextDocument's textWidth/pageSize to a printer's
   raw high-DPI DevicePixel count. Qt's HTML/CSS "pt" sizes map 1:1 onto
   QTextDocument's internal layout unit (i.e. that unit already IS a
   point, 1/72 inch) - not a 96dpi pixel. Feeding it a huge DevicePixel
   number computed from the printer's real hardware DPI creates a document
   many times "wider" than its point-sized text expects, so everything
   renders as a tiny fraction of that canvas, crammed into one corner.
   Point-based widths (see POINTS_PER_MM below) avoid that entirely.

2. An HTML "font-family" set on an outer <table> does not reliably
   inherit into cells of tables nested inside it, so deeply nested layout
   tables can silently fall back to Qt's default font resolution and
   render as boxes/garbage glyphs. The fix is to set a concrete
   QTextDocument.setDefaultFont() in code rather than depend on that CSS
   inheritance - see _new_document() below.

3. For a *custom* (non-standard) QPageSize - which is what a thermal
   receipt's narrow page is - QTextDocument.print_() does not reliably
   auto-match its wrapping width to the page the way it does for a
   standard size like A4. So for the thermal path we explicitly set
   document.setTextWidth() to the page's printable width in points
   before printing, using the same conversion the height estimate uses.

4. Never preview receipt/report HTML in a live QTextEdit on Windows. Its
   native ClearType text rendering applies real RGB sub-pixel colour
   fringing at glyph edges - invisible to the eye on a matching LCD panel,
   but it shows up as stray red/blue/orange tinges the moment that widget
   is captured (grab(), a screenshot, a remote session). QTextDocument's
   own QPainter.drawContents() - the exact path PDF export already uses -
   is plain greyscale antialiasing with zero colour fringing. So on-screen
   previews render through render_html_to_pixmap() below instead of a
   QTextEdit, guaranteeing the preview looks exactly like the PDF/print
   output and never shows a stray colour.

5. Any HTML text left without an explicit "color" - and a bare <hr> always,
   regardless of styling - silently falls back to the *application's*
   QPalette (Text/WindowText) instead of black. That palette changes with
   the user's light/dark theme choice, which is exactly why numbers and
   separators could render tinted blue or light grey depending on which
   theme happened to be active. _new_document() below sets a default
   stylesheet forcing plain dark text app-wide for these documents, and
   every HTML generator replaces <hr> with a CSS-bordered <div> so
   separator lines aren't exempt from that rule either.
"""
from PySide6.QtCore import Qt, QMarginsF, QSizeF
from PySide6.QtGui import QFont, QImage, QPainter, QPixmap, QTextDocument, QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

MM_PER_INCH = 25.4
POINTS_PER_INCH = 72.0
POINTS_PER_MM = POINTS_PER_INCH / MM_PER_INCH
DOCUMENT_FONT_FAMILY = "Segoe UI"
DOCUMENT_FONT_POINT_SIZE = 10
THERMAL_MARGIN_MM = 3.0


DOCUMENT_TEXT_COLOR = "#111111"


def _new_document(html: str) -> QTextDocument:
    document = QTextDocument()
    document.setDefaultFont(QFont(DOCUMENT_FONT_FAMILY, DOCUMENT_FONT_POINT_SIZE))
    # Forces a fixed dark text color regardless of the app's current
    # light/dark QPalette - see point 5 above.
    document.setDefaultStyleSheet(f"* {{ color: {DOCUMENT_TEXT_COLOR}; }}")
    document.setHtml(html)
    return document


def list_available_printers() -> list[str]:
    """Names of all printers currently installed on this machine."""
    return [p.printerName() for p in QPrinterInfo.availablePrinters()]


def default_printer_name() -> str:
    info = QPrinterInfo.defaultPrinter()
    return "" if info.isNull() else info.printerName()


def _printable_width_points(width_mm: float) -> float:
    return (width_mm - 2 * THERMAL_MARGIN_MM) * POINTS_PER_MM


def _estimate_content_height_mm(html: str, width_mm: float) -> float:
    """Content-height estimate (in mm) at a fixed physical printable width,
    used to pick a sensible custom page length for a thermal receipt."""
    probe = _new_document(html)
    probe.setTextWidth(_printable_width_points(width_mm))
    return probe.size().height() / POINTS_PER_MM


def _make_thermal_printer(printer_info: QPrinterInfo = None) -> QPrinter:
    return (
        QPrinter(printer_info, QPrinter.PrinterMode.HighResolution)
        if printer_info is not None
        else QPrinter(QPrinter.PrinterMode.HighResolution)
    )


def _configure_thermal_page(printer: QPrinter, width_mm: float, height_mm: float):
    """Sets the custom thermal page size/margins - must run AFTER
    printer.setOutputFormat() (e.g. PdfFormat), not before: switching
    output format swaps QPrinter's underlying print engine, which silently
    resets page geometry set on the previous engine, so a margin/fullPage
    call made before that switch would otherwise just vanish."""
    # A small, flat safety pad against font-metric rounding between the
    # estimate pass and the final print pass - just enough to avoid
    # clipping the last line onto a second page, without the excess this
    # used to have. The previous 50%+25mm buffer was the actual cause of
    # thermal receipts feeding a long stretch of blank paper after the
    # printed content: on a real roll printer, "extra height on the page"
    # means "extra paper fed and wasted", not harmless margin the way it
    # would be on a fixed A4 sheet. Measured against a real 16-item receipt,
    # the old formula wasted ~168mm of blank paper per receipt; this pads
    # by a flat 15mm instead - proportionally small on a long receipt,
    # still a real cushion on a short one.
    page_height = max(height_mm + 15, 40)
    printer.setPageSize(QPageSize(QSizeF(width_mm, page_height), QPageSize.Unit.Millimeter))
    # setFullPage(True) makes Qt measure the page from the true physical
    # paper edge instead of whatever default printable-area inset the
    # printer driver itself bakes in - without it, a 0mm top margin here
    # can still leave a visible gap because the driver's own margin wins.
    # Paired with a literal 0 top margin, this is what makes the receipt
    # start printing right at the top of the page on both a real thermal
    # printer and a normal page printer that substitutes its own paper
    # size for our custom one.
    printer.setFullPage(True)
    printer.setPageMargins(
        QMarginsF(THERMAL_MARGIN_MM, 0, THERMAL_MARGIN_MM, THERMAL_MARGIN_MM),
        QPageLayout.Unit.Millimeter,
    )


def _print_thermal_document(html: str, printer: QPrinter, width_mm: float):
    document = _new_document(html)
    document.setTextWidth(_printable_width_points(width_mm))
    document.print_(printer)


def export_receipt_to_pdf(html: str, file_path: str, width_mm: float = 80):
    """Save a receipt as a narrow, thermal-style PDF sized to fit its content."""
    height_mm = _estimate_content_height_mm(html, width_mm)
    printer = _make_thermal_printer()
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(file_path)
    _configure_thermal_page(printer, width_mm, height_mm)
    _print_thermal_document(html, printer, width_mm)


def print_receipt(html: str, width_mm: float = 80, printer_name: str = "") -> bool:
    """Send a receipt straight to a thermal/POS printer (no print dialog).

    Returns False if the requested printer (or, with none configured, the
    system default) could not be found - callers should fall back to the
    printer-choice dialog in that case.
    """
    printer_info = None
    if printer_name:
        printer_info = QPrinterInfo.printerInfo(printer_name)
        if printer_info.isNull():
            return False
    else:
        printer_info = QPrinterInfo.defaultPrinter()
        if printer_info.isNull():
            return False

    height_mm = _estimate_content_height_mm(html, width_mm)
    printer = _make_thermal_printer(printer_info)
    _configure_thermal_page(printer, width_mm, height_mm)
    _print_thermal_document(html, printer, width_mm)
    return True


def export_html_to_pdf(html: str, file_path: str, page_size=QPageSize.PageSizeId.A4):
    """Full-page (A4) export used for daily/overall reports. Standard page
    sizes like A4 don't need the manual textWidth override - Qt's print_()
    already matches the document's wrapping width to a standard page."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(file_path)
    printer.setPageSize(QPageSize(page_size))
    printer.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter)

    document = _new_document(html)
    document.print_(printer)


def render_report_on_printer(html: str, printer: QPrinter):
    """Render report HTML onto an already-configured QPrinter - used both by
    the PDF export path and by the print-preview dialog so both show
    identical, correctly page-fitted output."""
    document = _new_document(html)
    document.print_(printer)


def render_html_to_pixmap(html: str, width_mm: float = 80, scale: float = 2.0) -> QPixmap:
    """Render HTML to a crisp, colour-fringe-free QPixmap for on-screen
    preview - see point 4 above for why this replaces a live QTextEdit.

    width_mm sizes the preview in the SAME unit space document.setTextWidth
    expects (points - see point 1 above), so a 58mm receipt genuinely
    previews narrower than an 80mm one instead of both being force-fit into
    an arbitrary fixed pixel width (which is what previously made long
    lines overflow past the visible preview area instead of wrapping).

    Renders onto a QImage rather than a QPixmap: on Windows a QPixmap is a
    native, GPU/DirectWrite-backed surface and still applies ClearType
    sub-pixel colour fringing to text even when painted on directly and
    off-screen. QImage always goes through Qt's own software raster paint
    engine, which is plain, fringe-free greyscale antialiasing - the exact
    path PDF/print export already uses. The QImage is converted to a
    QPixmap only at the very end, for QLabel to display."""
    document = _new_document(html)
    width_pt = width_mm * POINTS_PER_MM
    document.setTextWidth(width_pt)
    logical_size = document.size()

    image = QImage(
        int(logical_size.width() * scale), int(logical_size.height() * scale),
        QImage.Format.Format_ARGB32,
    )
    image.setDevicePixelRatio(scale)
    image.fill(Qt.GlobalColor.white)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    document.drawContents(painter)
    painter.end()
    return QPixmap.fromImage(image)
