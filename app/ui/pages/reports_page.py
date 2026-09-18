"""Reports page: daily/monthly/overall report browsers + PDF export."""
import calendar
from datetime import date, datetime

import qtawesome as qta
from PySide6.QtCore import Qt, QDate, QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDateEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QTabWidget,
    QAbstractItemView, QFileDialog, QDialog, QLineEdit, QFormLayout, QSpinBox,
)

from app.core.database import Database
from app.core.pdf_utils import export_html_to_pdf, render_report_on_printer
from app.ui.widgets.message_box import AppMessageBox
from app.ui.theme import apply_card_shadow


class EditBillCustomerDialog(QDialog):
    """Small dialog for editing just the customer/walk-in info recorded
    against a past bill - kept deliberately narrow in scope so editing a
    historical record can never touch its items or totals."""

    def __init__(self, bill, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Bill")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)

        self.customer_input = QLineEdit(bill["customer_name"] or "")
        self.customer_input.setPlaceholderText("Customer name (optional)")
        form.addRow("Customer Name", self.customer_input)

        self.walkin_input = QLineEdit(bill["walkin_no"] or "")
        self.walkin_input.setPlaceholderText("Walk-in / Table No. (optional)")
        form.addRow("Walk-in / Table No.", self.walkin_input)

        layout.addLayout(form)
        layout.addSpacing(10)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("  Cancel")
        cancel_btn.setIcon(qta.icon("fa5s.times", color="#6b7280"))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("  Save")
        save_btn.setIcon(qta.icon("fa5s.save", color="white"))
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def values(self):
        return self.customer_input.text().strip(), self.walkin_input.text().strip()


def _customer_display(bill) -> str:
    name = bill["customer_name"] if "customer_name" in bill.keys() else None
    walkin = bill["walkin_no"] if "walkin_no" in bill.keys() else None
    if name and walkin:
        return f"{name} ({walkin})"
    if name:
        return name
    if walkin:
        return walkin
    return "Walk-in"


def _payment_display(bill) -> str:
    return bill["payment_method"] if "payment_method" in bill.keys() and bill["payment_method"] else "Cash"


def _make_bill_actions_widget(edit_callback, delete_callback) -> QWidget:
    """Edit/Delete icon-button pair used on every bill row in both report
    tabs - matches the Edit/Delete action style already used on the Items
    and User Management pages."""
    widget = QWidget()
    row_layout = QHBoxLayout(widget)
    row_layout.setContentsMargins(4, 2, 4, 2)
    row_layout.setSpacing(6)

    edit_btn = QPushButton()
    edit_btn.setIcon(qta.icon("fa5s.edit", color="#2563eb"))
    edit_btn.setProperty("variant", "icon")
    edit_btn.setFixedSize(30, 30)
    edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    edit_btn.setToolTip("Edit customer / walk-in info")
    edit_btn.clicked.connect(edit_callback)
    row_layout.addWidget(edit_btn)

    delete_btn = QPushButton()
    delete_btn.setIcon(qta.icon("fa5s.trash-alt", color="#dc2626"))
    delete_btn.setProperty("variant", "icon")
    delete_btn.setFixedSize(30, 30)
    delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    delete_btn.setToolTip("Delete this bill")
    delete_btn.clicked.connect(delete_callback)
    row_layout.addWidget(delete_btn)

    row_layout.addStretch()
    return widget


def _build_items_sold_card():
    """A small 'Items Sold' table reused by every report tab - lists every
    active item in the catalog one by one with its quantity sold and
    revenue for that tab's selected period (0 for an item that didn't sell
    at all), so nothing in the software's menu is left out."""
    card = QFrame()
    card.setProperty("card", "true")
    apply_card_shadow(card)
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(14, 14, 14, 14)
    card_layout.setSpacing(8)

    heading = QLabel("Items Sold")
    heading.setStyleSheet("font-size: 14px; font-weight: 600;")
    card_layout.addWidget(heading)

    table = QTableWidget(0, 3)
    table.setHorizontalHeaderLabels(["Item", "Qty Sold", "Revenue"])
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(34)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    table.setMinimumHeight(160)
    card_layout.addWidget(table)
    return card, table


def _populate_items_sold_table(table: QTableWidget, item_sales, currency: str):
    table.setRowCount(0)
    for row_idx, row in enumerate(item_sales):
        table.insertRow(row_idx)
        table.setItem(row_idx, 0, QTableWidgetItem(row["item_name"]))
        qty_item = QTableWidgetItem(str(row["qty_sold"]))
        qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row_idx, 1, qty_item)
        revenue_item = QTableWidgetItem(f"{currency} {row['revenue']:.0f}")
        revenue_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row_idx, 2, revenue_item)


def open_report_preview(parent, html: str):
    """Show a fit-to-page print preview before saving/printing a report."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter)

    preview = QPrintPreviewDialog(printer, parent)
    preview.setWindowTitle("Report Preview")
    preview.paintRequested.connect(lambda p: render_report_on_printer(html, p))
    preview.exec()


class DailyReportTab(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Select date:"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumHeight(36)
        self.date_edit.dateChanged.connect(self.refresh)
        controls.addWidget(self.date_edit)
        controls.addStretch()

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: 600;")
        controls.addWidget(self.summary_label)

        preview_btn = QPushButton("  Preview")
        preview_btn.setIcon(qta.icon("fa5s.eye", color="#6b7280"))
        preview_btn.clicked.connect(self.preview)
        controls.addWidget(preview_btn)

        download_btn = QPushButton("  Download PDF")
        download_btn.setIcon(qta.icon("fa5s.file-download", color="white"))
        download_btn.setProperty("variant", "primary")
        download_btn.clicked.connect(self.download_pdf)
        controls.addWidget(download_btn)
        layout.addLayout(controls)

        card = QFrame()
        card.setProperty("card", "true")
        apply_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["S.No", "Time", "Customer / Walk-in", "Items", "Payment Method", "Grand Total", "Actions"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(320)
        card_layout.addWidget(self.table)
        layout.addWidget(card, 2)

        self.items_card, self.items_table = _build_items_sold_card()
        layout.addWidget(self.items_card, 1)

    def selected_date(self) -> date:
        qd = self.date_edit.date()
        return date(qd.year(), qd.month(), qd.day())

    def refresh(self):
        settings = self.db.get_settings()
        currency = settings["currency_symbol"]
        day = self.selected_date()
        bills = self.db.get_bills_by_date(day)
        self.table.setRowCount(0)
        total = 0
        for row_idx, bill in enumerate(bills):
            self.table.insertRow(row_idx)
            time_str = bill["created_at"].split("T")[1] if "T" in bill["created_at"] else ""
            values = [
                str(row_idx + 1), time_str, _customer_display(bill),
                str(bill["items_count"]), _payment_display(bill), f"{currency} {bill['grand_total']:.0f}",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col, item)

            actions = _make_bill_actions_widget(
                lambda _c=False, bid=bill["id"]: self.edit_bill(bid),
                lambda _c=False, bid=bill["id"]: self.delete_bill(bid),
            )
            self.table.setCellWidget(row_idx, 6, actions)

            total += bill["grand_total"]
        self.summary_label.setText(f"{len(bills)} bills  •  Total: {currency} {total:.0f}")

        item_sales = self.db.get_item_sales_between(day, day)
        _populate_items_sold_table(self.items_table, item_sales, currency)

    def edit_bill(self, bill_id: int):
        bill = self.db.get_bill(bill_id)
        if not bill:
            return
        dialog = EditBillCustomerDialog(bill, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            customer_name, walkin_no = dialog.values()
            self.db.update_bill_customer(bill_id, customer_name, walkin_no)
            self.refresh()
            AppMessageBox.success(self, "Bill Updated", "The bill has been updated successfully.")

    def delete_bill(self, bill_id: int):
        confirmed = AppMessageBox.question(
            self, "Delete Bill", "Permanently delete this bill from the records?",
            yes_text="Delete", no_text="Cancel",
        )
        if confirmed:
            self.db.delete_bill(bill_id)
            self.refresh()
            AppMessageBox.success(self, "Bill Deleted", "The bill has been deleted successfully.")

    def _report_html_or_warn(self):
        day = self.selected_date()
        bills = self.db.get_bills_by_date(day)
        if not bills:
            AppMessageBox.info(self, "No Data", "There are no bills for the selected date.")
            return None, None
        settings = self.db.get_settings()
        item_sales = self.db.get_item_sales_between(day, day)
        html = build_report_html(settings, f"Daily Report — {day.strftime('%d %B %Y')}", bills, item_sales)
        return html, day

    def preview(self):
        html, _ = self._report_html_or_warn()
        if html:
            open_report_preview(self, html)

    def download_pdf(self):
        html, day = self._report_html_or_warn()
        if not html:
            return
        default_name = f"daily_report_{day.isoformat()}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Daily Report", default_name, "PDF Files (*.pdf)")
        if file_path:
            export_html_to_pdf(html, file_path)
            AppMessageBox.success(self, "Saved", f"Report saved to:\n{file_path}")


class MonthlyReportTab(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Select month:"))
        self.month_edit = QDateEdit(QDate.currentDate())
        self.month_edit.setDisplayFormat("MMMM yyyy")
        self.month_edit.setCalendarPopup(True)
        self.month_edit.setMinimumHeight(36)
        self.month_edit.dateChanged.connect(self.refresh)
        controls.addWidget(self.month_edit)
        controls.addStretch()

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: 600;")
        controls.addWidget(self.summary_label)

        preview_btn = QPushButton("  Preview")
        preview_btn.setIcon(qta.icon("fa5s.eye", color="#6b7280"))
        preview_btn.clicked.connect(self.preview)
        controls.addWidget(preview_btn)

        download_btn = QPushButton("  Download PDF")
        download_btn.setIcon(qta.icon("fa5s.file-download", color="white"))
        download_btn.setProperty("variant", "primary")
        download_btn.clicked.connect(self.download_pdf)
        controls.addWidget(download_btn)
        layout.addLayout(controls)

        card = QFrame()
        card.setProperty("card", "true")
        apply_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["S.No", "Date & Time", "Customer / Walk-in", "Items", "Payment Method", "Grand Total", "Actions"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(320)
        card_layout.addWidget(self.table)
        layout.addWidget(card, 2)

        self.items_card, self.items_table = _build_items_sold_card()
        layout.addWidget(self.items_card, 1)

    def range(self):
        qd = self.month_edit.date()
        year, month = qd.year(), qd.month()
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    def refresh(self):
        settings = self.db.get_settings()
        currency = settings["currency_symbol"]
        start, end = self.range()
        bills = self.db.get_bills_between(start, end)
        self.table.setRowCount(0)
        total = 0
        for row_idx, bill in enumerate(bills):
            self.table.insertRow(row_idx)
            values = [
                str(row_idx + 1), bill["created_at"].replace("T", " "), _customer_display(bill),
                str(bill["items_count"]), _payment_display(bill), f"{currency} {bill['grand_total']:.0f}",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col, item)

            actions = _make_bill_actions_widget(
                lambda _c=False, bid=bill["id"]: self.edit_bill(bid),
                lambda _c=False, bid=bill["id"]: self.delete_bill(bid),
            )
            self.table.setCellWidget(row_idx, 6, actions)

            total += bill["grand_total"]
        self.summary_label.setText(f"{len(bills)} bills  •  Total: {currency} {total:.0f}")

        item_sales = self.db.get_item_sales_between(start, end)
        _populate_items_sold_table(self.items_table, item_sales, currency)

    def edit_bill(self, bill_id: int):
        bill = self.db.get_bill(bill_id)
        if not bill:
            return
        dialog = EditBillCustomerDialog(bill, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            customer_name, walkin_no = dialog.values()
            self.db.update_bill_customer(bill_id, customer_name, walkin_no)
            self.refresh()
            AppMessageBox.success(self, "Bill Updated", "The bill has been updated successfully.")

    def delete_bill(self, bill_id: int):
        confirmed = AppMessageBox.question(
            self, "Delete Bill", "Permanently delete this bill from the records?",
            yes_text="Delete", no_text="Cancel",
        )
        if confirmed:
            self.db.delete_bill(bill_id)
            self.refresh()
            AppMessageBox.success(self, "Bill Deleted", "The bill has been deleted successfully.")

    def _report_html_or_warn(self):
        start, end = self.range()
        bills = self.db.get_bills_between(start, end)
        if not bills:
            AppMessageBox.info(self, "No Data", "There are no bills in the selected month.")
            return None, None
        settings = self.db.get_settings()
        title = f"Monthly Report — {start.strftime('%B %Y')}"
        item_sales = self.db.get_item_sales_between(start, end)
        html = build_report_html(settings, title, bills, item_sales)
        return html, start

    def preview(self):
        html, _ = self._report_html_or_warn()
        if html:
            open_report_preview(self, html)

    def download_pdf(self):
        html, start = self._report_html_or_warn()
        if not html:
            return
        default_name = f"monthly_report_{start.strftime('%Y-%m')}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Monthly Report", default_name, "PDF Files (*.pdf)")
        if file_path:
            export_html_to_pdf(html, file_path)
            AppMessageBox.success(self, "Saved", f"Report saved to:\n{file_path}")


class YearlyReportTab(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Select year:"))
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2000, 2100)
        self.year_spin.setValue(QDate.currentDate().year())
        self.year_spin.setMinimumHeight(36)
        self.year_spin.setMinimumWidth(90)
        self.year_spin.valueChanged.connect(self.refresh)
        controls.addWidget(self.year_spin)
        controls.addStretch()

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: 600;")
        controls.addWidget(self.summary_label)

        preview_btn = QPushButton("  Preview")
        preview_btn.setIcon(qta.icon("fa5s.eye", color="#6b7280"))
        preview_btn.clicked.connect(self.preview)
        controls.addWidget(preview_btn)

        download_btn = QPushButton("  Download PDF")
        download_btn.setIcon(qta.icon("fa5s.file-download", color="white"))
        download_btn.setProperty("variant", "primary")
        download_btn.clicked.connect(self.download_pdf)
        controls.addWidget(download_btn)
        layout.addLayout(controls)

        card = QFrame()
        card.setProperty("card", "true")
        apply_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["S.No", "Date & Time", "Customer / Walk-in", "Items", "Payment Method", "Grand Total", "Actions"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(320)
        card_layout.addWidget(self.table)
        layout.addWidget(card, 2)

        self.items_card, self.items_table = _build_items_sold_card()
        layout.addWidget(self.items_card, 1)

    def range(self):
        year = self.year_spin.value()
        return date(year, 1, 1), date(year, 12, 31)

    def refresh(self):
        settings = self.db.get_settings()
        currency = settings["currency_symbol"]
        start, end = self.range()
        bills = self.db.get_bills_between(start, end)
        self.table.setRowCount(0)
        total = 0
        for row_idx, bill in enumerate(bills):
            self.table.insertRow(row_idx)
            values = [
                str(row_idx + 1), bill["created_at"].replace("T", " "), _customer_display(bill),
                str(bill["items_count"]), _payment_display(bill), f"{currency} {bill['grand_total']:.0f}",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col, item)

            actions = _make_bill_actions_widget(
                lambda _c=False, bid=bill["id"]: self.edit_bill(bid),
                lambda _c=False, bid=bill["id"]: self.delete_bill(bid),
            )
            self.table.setCellWidget(row_idx, 6, actions)

            total += bill["grand_total"]
        self.summary_label.setText(f"{len(bills)} bills  •  Total: {currency} {total:.0f}")

        item_sales = self.db.get_item_sales_between(start, end)
        _populate_items_sold_table(self.items_table, item_sales, currency)

    def edit_bill(self, bill_id: int):
        bill = self.db.get_bill(bill_id)
        if not bill:
            return
        dialog = EditBillCustomerDialog(bill, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            customer_name, walkin_no = dialog.values()
            self.db.update_bill_customer(bill_id, customer_name, walkin_no)
            self.refresh()
            AppMessageBox.success(self, "Bill Updated", "The bill has been updated successfully.")

    def delete_bill(self, bill_id: int):
        confirmed = AppMessageBox.question(
            self, "Delete Bill", "Permanently delete this bill from the records?",
            yes_text="Delete", no_text="Cancel",
        )
        if confirmed:
            self.db.delete_bill(bill_id)
            self.refresh()
            AppMessageBox.success(self, "Bill Deleted", "The bill has been deleted successfully.")

    def _report_html_or_warn(self):
        start, end = self.range()
        bills = self.db.get_bills_between(start, end)
        if not bills:
            AppMessageBox.info(self, "No Data", "There are no bills for the selected year.")
            return None, None
        settings = self.db.get_settings()
        title = f"Yearly Report — {start.year}"
        item_sales = self.db.get_item_sales_between(start, end)
        html = build_report_html(settings, title, bills, item_sales)
        return html, start

    def preview(self):
        html, _ = self._report_html_or_warn()
        if html:
            open_report_preview(self, html)

    def download_pdf(self):
        html, start = self._report_html_or_warn()
        if not html:
            return
        default_name = f"yearly_report_{start.year}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Yearly Report", default_name, "PDF Files (*.pdf)")
        if file_path:
            export_html_to_pdf(html, file_path)
            AppMessageBox.success(self, "Saved", f"Report saved to:\n{file_path}")


class OverallReportTab(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("From:"))
        self.from_date = QDateEdit(QDate.currentDate().addDays(-6))
        self.from_date.setCalendarPopup(True)
        self.from_date.setMinimumHeight(36)
        self.from_date.dateChanged.connect(self.refresh)
        controls.addWidget(self.from_date)

        controls.addWidget(QLabel("To:"))
        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setCalendarPopup(True)
        self.to_date.setMinimumHeight(36)
        self.to_date.dateChanged.connect(self.refresh)
        controls.addWidget(self.to_date)
        controls.addStretch()

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: 600;")
        controls.addWidget(self.summary_label)

        preview_btn = QPushButton("  Preview")
        preview_btn.setIcon(qta.icon("fa5s.eye", color="#6b7280"))
        preview_btn.clicked.connect(self.preview)
        controls.addWidget(preview_btn)

        download_btn = QPushButton("  Download PDF")
        download_btn.setIcon(qta.icon("fa5s.file-download", color="white"))
        download_btn.setProperty("variant", "primary")
        download_btn.clicked.connect(self.download_pdf)
        controls.addWidget(download_btn)
        layout.addLayout(controls)

        card = QFrame()
        card.setProperty("card", "true")
        apply_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["S.No", "Date & Time", "Customer / Walk-in", "Items", "Payment Method", "Grand Total", "Actions"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(320)
        card_layout.addWidget(self.table)
        layout.addWidget(card, 2)

        self.items_card, self.items_table = _build_items_sold_card()
        layout.addWidget(self.items_card, 1)

    def range(self):
        fq = self.from_date.date()
        tq = self.to_date.date()
        return date(fq.year(), fq.month(), fq.day()), date(tq.year(), tq.month(), tq.day())

    def refresh(self):
        settings = self.db.get_settings()
        currency = settings["currency_symbol"]
        start, end = self.range()
        bills = self.db.get_bills_between(start, end)
        self.table.setRowCount(0)
        total = 0
        for row_idx, bill in enumerate(bills):
            self.table.insertRow(row_idx)
            values = [
                str(row_idx + 1), bill["created_at"].replace("T", " "), _customer_display(bill),
                str(bill["items_count"]), _payment_display(bill), f"{currency} {bill['grand_total']:.0f}",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col, item)

            actions = _make_bill_actions_widget(
                lambda _c=False, bid=bill["id"]: self.edit_bill(bid),
                lambda _c=False, bid=bill["id"]: self.delete_bill(bid),
            )
            self.table.setCellWidget(row_idx, 6, actions)

            total += bill["grand_total"]
        self.summary_label.setText(f"{len(bills)} bills  •  Total: {currency} {total:.0f}")

        item_sales = self.db.get_item_sales_between(start, end)
        _populate_items_sold_table(self.items_table, item_sales, currency)

    def edit_bill(self, bill_id: int):
        bill = self.db.get_bill(bill_id)
        if not bill:
            return
        dialog = EditBillCustomerDialog(bill, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            customer_name, walkin_no = dialog.values()
            self.db.update_bill_customer(bill_id, customer_name, walkin_no)
            self.refresh()
            AppMessageBox.success(self, "Bill Updated", "The bill has been updated successfully.")

    def delete_bill(self, bill_id: int):
        confirmed = AppMessageBox.question(
            self, "Delete Bill", "Permanently delete this bill from the records?",
            yes_text="Delete", no_text="Cancel",
        )
        if confirmed:
            self.db.delete_bill(bill_id)
            self.refresh()
            AppMessageBox.success(self, "Bill Deleted", "The bill has been deleted successfully.")

    def _report_html_or_warn(self):
        start, end = self.range()
        bills = self.db.get_bills_between(start, end)
        if not bills:
            AppMessageBox.info(self, "No Data", "There are no bills in the selected range.")
            return None, None, None
        settings = self.db.get_settings()
        title = f"Overall Report — {start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')}"
        item_sales = self.db.get_item_sales_between(start, end)
        html = build_report_html(settings, title, bills, item_sales)
        return html, start, end

    def preview(self):
        html, _, _ = self._report_html_or_warn()
        if html:
            open_report_preview(self, html)

    def download_pdf(self):
        html, start, end = self._report_html_or_warn()
        if not html:
            return
        default_name = f"overall_report_{start.isoformat()}_to_{end.isoformat()}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Overall Report", default_name, "PDF Files (*.pdf)")
        if file_path:
            export_html_to_pdf(html, file_path)
            AppMessageBox.success(self, "Saved", f"Report saved to:\n{file_path}")


def build_report_html(settings, title: str, bills, item_sales) -> str:
    currency = settings["currency_symbol"]
    total_revenue = sum(b["grand_total"] for b in bills)
    total_bills = len(bills)
    total_items_sold = sum(b["items_count"] for b in bills)

    border = "1pt solid #9aa5b1"
    cell = "padding:6pt 8pt; border:{b};".format(b=border)

    rows_html = ""
    for idx, bill in enumerate(bills, start=1):
        rows_html += (
            f"<tr>"
            f"<td style='{cell} text-align:center;'>{idx}</td>"
            f"<td style='{cell}'>{bill['created_at'].replace('T', ' ')}</td>"
            f"<td style='{cell}'>{_customer_display(bill)}</td>"
            f"<td style='{cell} text-align:center;'>{bill['items_count']}</td>"
            f"<td style='{cell} text-align:center;'>{_payment_display(bill)}</td>"
            f"<td style='{cell} text-align:right;'>{currency} {bill['grand_total']:.0f}</td>"
            f"</tr>"
        )

    # Item-wise breakdown - every active item in the catalog, one row each,
    # with how many units it sold in this report's period (0 if none).
    item_rows_html = ""
    for idx, row in enumerate(item_sales, start=1):
        item_rows_html += (
            f"<tr>"
            f"<td style='{cell} text-align:center;'>{idx}</td>"
            f"<td style='{cell}'>{row['item_name']}</td>"
            f"<td style='{cell} text-align:center;'>{row['qty_sold']}</td>"
            f"<td style='{cell} text-align:right;'>{currency} {row['revenue']:.0f}</td>"
            f"</tr>"
        )

    # Two things make Qt's rich-text engine render this reliably:
    # 1) every table is sized with the classic HTML "width" attribute
    #    (width="100%"/"N%"), which Qt honours far more consistently than a
    #    CSS width percentage - that's what kept the grid inside the page.
    # 2) every font-size below is in "pt", never "px" - Qt ties CSS px to
    #    the print device's real DPI rather than a fixed 96dpi reference,
    #    so px-sized text on a high-resolution printer/PDF renders at a
    #    near-invisible fraction of its intended size. Points are DPI
    #    independent and print exactly as sized on screen.
    return f"""
    <table width="100%" cellspacing="0" cellpadding="0" style="font-family:'Segoe UI',sans-serif; color:#111;">
    <tr><td>

        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td style="text-align:center; font-size:18pt; font-weight:700;">{settings['hotel_name']}</td></tr>
            <tr><td style="text-align:center; font-size:9pt; color:#555; padding-top:4pt;">{settings['address'] or ''} &nbsp;|&nbsp; Tel: {settings['phone'] or ''}</td></tr>
        </table>

        <table width="100%" cellspacing="0" cellpadding="0" style="margin-top:12pt;">
            <tr><td style="border-top:2pt solid #333;"></td></tr>
        </table>

        <table width="100%" cellspacing="0" cellpadding="0" style="margin-top:10pt;">
            <tr>
                <td style="font-size:13pt; font-weight:700;">{title}</td>
                <td style="font-size:9pt; color:#555; text-align:right;">Generated: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}</td>
            </tr>
        </table>

        <table width="100%" cellspacing="0" cellpadding="0" style="margin:14pt 0; border-collapse:collapse;">
            <tr>
                <td width="34%" style="{cell} background:#f4f7fb; text-align:center;"><div style="font-size:9pt;color:#555;">Total Bills</div><div style="font-size:14pt;font-weight:700;">{total_bills}</div></td>
                <td width="33%" style="{cell} background:#f4f7fb; text-align:center;"><div style="font-size:9pt;color:#555;">Total Items Sold</div><div style="font-size:14pt;font-weight:700;">{total_items_sold}</div></td>
                <td width="33%" style="{cell} background:#f4f7fb; text-align:center;"><div style="font-size:9pt;color:#555;">Total Revenue</div><div style="font-size:14pt;font-weight:700;">{currency} {total_revenue:.0f}</div></td>
            </tr>
        </table>

        <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse; font-size:10pt;">
            <tr style="background:#dfe7f2;">
                <th width="6%" style="{cell} font-size:10pt;">S.No</th>
                <th width="20%" style="{cell} font-size:10pt; text-align:left;">Date &amp; Time</th>
                <th width="24%" style="{cell} font-size:10pt; text-align:left;">Customer / Walk-in</th>
                <th width="10%" style="{cell} font-size:10pt;">Items</th>
                <th width="16%" style="{cell} font-size:10pt;">Payment</th>
                <th width="24%" style="{cell} font-size:10pt; text-align:right;">Grand Total</th>
            </tr>
            {rows_html}
        </table>

        <table width="100%" cellspacing="0" cellpadding="0" style="margin-top:12pt;">
            <tr>
                <td style="text-align:right; padding-top:8pt; font-size:13pt; border-top:2pt solid #333;">
                    <b>Grand Total: {currency} {total_revenue:.0f}</b>
                </td>
            </tr>
        </table>

        <table width="100%" cellspacing="0" cellpadding="0" style="margin-top:18pt;">
            <tr><td style="font-size:13pt; font-weight:700;">Items Sold</td></tr>
        </table>

        <table width="100%" cellspacing="0" cellpadding="0" style="margin-top:8pt; border-collapse:collapse; font-size:10pt;">
            <tr style="background:#dfe7f2;">
                <th width="6%" style="{cell} font-size:10pt;">S.No</th>
                <th width="54%" style="{cell} font-size:10pt; text-align:left;">Item</th>
                <th width="18%" style="{cell} font-size:10pt;">Qty Sold</th>
                <th width="22%" style="{cell} font-size:10pt; text-align:right;">Revenue</th>
            </tr>
            {item_rows_html}
        </table>

    </td></tr>
    </table>
    """


class ReportsPage(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Reports")
        title.setProperty("role", "pageTitle")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        self.daily_tab = DailyReportTab(db)
        self.monthly_tab = MonthlyReportTab(db)
        self.yearly_tab = YearlyReportTab(db)
        self.overall_tab = OverallReportTab(db)
        self.tabs.addTab(self.daily_tab, "Daily Report")
        self.tabs.addTab(self.monthly_tab, "Monthly Report")
        self.tabs.addTab(self.yearly_tab, "Yearly Report")
        self.tabs.addTab(self.overall_tab, "Overall Report")
        layout.addWidget(self.tabs, 1)

    def refresh(self):
        self.daily_tab.refresh()
        self.monthly_tab.refresh()
        self.yearly_tab.refresh()
        self.overall_tab.refresh()
