"""Billing page: build a cart from items and generate a bill/receipt.

Keyboard-first workflow (see the on-screen hint label for the short
version) - deliberately kept to just Enter / Ctrl-combos / Arrow keys so
it stays predictable and doesn't collide with normal typing:
    Search item -> type + arrows -> Enter adds it -> repeat
    Cart row selected -> Enter edits exact quantity -> Enter confirms
    Ctrl+D -> discount (a plain, optional Rs. amount) -> Enter validates,
        moves to payment method
    Payment method dropdown (defaults to Cash) -> arrows browse, Enter
        moves into the reference field (Cash needs nothing further)
    Ctrl+Enter -> validate everything and generate the bill
    Escape -> cancel whatever is being edited (search filter, qty edit,
              discount edit) without ever closing the app
    Ctrl+Z -> restore the last item removed from the cart
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import qtawesome as qta
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QAbstractItemView,
    QFileDialog, QDialog, QScrollArea, QComboBox,
)

from app.core.database import Database
from app.core.pdf_utils import (
    export_receipt_to_pdf, print_receipt as print_receipt_thermal,
    render_html_to_pixmap, _new_document,
)
from app.ui.widgets.message_box import AppMessageBox
from app.ui.theme import apply_card_shadow

CENT = Decimal("1")  # bills are recorded to whole currency units, matching
                      # the item price field (QDoubleSpinBox, 0 decimals)
PAYMENT_METHODS = ["Cash", "EasyPaisa", "JazzCash", "Bank Transfer"]


class ReceiptDialog(QDialog):
    def __init__(self, html: str, width_mm: float = 80, printer_name: str = "", parent=None):
        super().__init__(parent)
        self.html = html
        self.width_mm = width_mm
        self.printer_name = printer_name
        self.setWindowTitle("Bill Receipt")
        self.setMinimumSize(380, 580)

        layout = QVBoxLayout(self)
        # Rendered to a plain QPixmap (not a live QTextEdit) - a QTextEdit's
        # native ClearType text rendering shows real RGB colour fringing at
        # glyph edges the moment it's captured or screenshotted, even though
        # the CSS color is correctly black. See pdf_utils.render_html_to_pixmap.
        self.preview_label = QLabel()
        self.preview_label.setPixmap(render_html_to_pixmap(html, width_mm=width_mm))
        self.preview_label.setStyleSheet("background: white; border-radius: 8px;")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        scroll = QScrollArea()
        scroll.setWidget(self.preview_label)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: white; border-radius: 8px; border: 1px solid #e5e7eb;")
        layout.addWidget(scroll, 1)

        row1 = QHBoxLayout()
        save_pdf_btn = QPushButton("  Save as PDF")
        save_pdf_btn.setIcon(qta.icon("fa5s.file-pdf", color="#dc2626"))
        save_pdf_btn.clicked.connect(self.save_pdf)

        other_printer_btn = QPushButton("  Print to...")
        other_printer_btn.setIcon(qta.icon("fa5s.print", color="#6b7280"))
        other_printer_btn.setToolTip("Choose a printer manually")
        other_printer_btn.clicked.connect(self.print_via_dialog)

        row1.addWidget(save_pdf_btn)
        row1.addWidget(other_printer_btn)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        quick_print_btn = QPushButton("  Print Receipt (Thermal)")
        quick_print_btn.setProperty("variant", "success")
        quick_print_btn.setIcon(qta.icon("fa5s.receipt", color="white"))
        quick_print_btn.setMinimumHeight(44)
        quick_print_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quick_print_btn.clicked.connect(self.quick_print)

        close_btn = QPushButton("  New Bill")
        close_btn.setProperty("variant", "primary")
        close_btn.setIcon(qta.icon("fa5s.plus-circle", color="white"))
        close_btn.setMinimumHeight(44)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close this receipt and start the next bill")
        # Default button so pressing Enter/Return on the dialog (e.g. right
        # after printing) immediately moves on to the next bill instead of
        # doing nothing - this is the action a cashier takes most often.
        close_btn.setDefault(True)
        close_btn.setAutoDefault(True)
        close_btn.clicked.connect(self.accept)

        row2.addWidget(quick_print_btn, 1)
        row2.addWidget(close_btn, 1)
        layout.addLayout(row2)

    def save_pdf(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Receipt", "receipt.pdf", "PDF Files (*.pdf)"
        )
        if file_path:
            export_receipt_to_pdf(self.html, file_path, width_mm=self.width_mm)
            AppMessageBox.success(self, "Saved", f"Receipt saved to:\n{file_path}")

    def quick_print(self):
        ok = print_receipt_thermal(self.html, width_mm=self.width_mm, printer_name=self.printer_name)
        if ok:
            AppMessageBox.success(self, "Printing", "Receipt sent to the printer.")
        else:
            AppMessageBox.warning(
                self, "No Printer Found",
                "No thermal printer is configured or connected.\n\n"
                "Set one up in Settings → Printer, or use “Print to...” to choose one manually.",
            )

    def print_via_dialog(self):
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageLayout
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        # A regular page printer defaults to a 0mm top margin on some
        # drivers, which crams the receipt right up against the top edge
        # even with "fit to page" selected - give it a sane, even margin on
        # every side up front so the print dialog (and the print itself)
        # start from a page that already looks right.
        printer.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            document = _new_document(self.html)
            page_rect = printer.pageRect(QPrinter.Unit.Point)
            document.setTextWidth(page_rect.width())
            document.print_(printer)


class BillingPage(QWidget):
    def __init__(self, db: Database, current_user, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_user = current_user
        self.cart = []  # list of {id, name, price, quantity, total}
        self.current_payment_method = "Cash"
        self._qty_editor = None
        self._last_removed = None  # (index, entry) - Ctrl+Z target
        self._last_net_total = Decimal("0")
        self._submitting = False

        root = QHBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        # ---------------- Left: menu ----------------
        left = QVBoxLayout()
        left.setSpacing(12)

        title = QLabel("Billing")
        title.setProperty("role", "pageTitle")
        left.addWidget(title)

        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search menu items... (Enter adds top match, ↓ jumps into the list)")
        self.search_input.setMinimumHeight(38)
        self.search_input.textChanged.connect(self.refresh_menu)
        self.search_input.returnPressed.connect(self.add_top_menu_match)
        self.search_input.installEventFilter(self)
        filter_row.addWidget(self.search_input, 1)
        left.addLayout(filter_row)

        keyboard_hint = QLabel(
            "Keyboard: ↑/↓ browse items • Enter adds/repeats an item • in the order list Enter edits qty, "
            "←/→ +/-1, Delete removes (Ctrl+Z undo) • Ctrl+D discount • ↑/↓ + Enter for payment method • "
            "Ctrl+Enter generates the bill"
        )
        keyboard_hint.setProperty("role", "subtitle")
        keyboard_hint.setWordWrap(True)
        left.addWidget(keyboard_hint)

        menu_card = QFrame()
        menu_card.setProperty("card", "true")
        apply_card_shadow(menu_card)
        menu_layout = QVBoxLayout(menu_card)
        menu_layout.setContentsMargins(12, 12, 12, 12)

        self.menu_table = QTableWidget(0, 3)
        self.menu_table.setHorizontalHeaderLabels(["Item", "Price", ""])
        header = self.menu_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.menu_table.verticalHeader().setVisible(False)
        self.menu_table.verticalHeader().setDefaultSectionSize(44)
        self.menu_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.menu_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.menu_table.setAlternatingRowColors(True)
        self.menu_table.setMinimumHeight(420)
        self.menu_table.itemActivated.connect(lambda _item: self.add_current_menu_row())
        menu_layout.addWidget(self.menu_table)
        left.addWidget(menu_card, 1)

        root.addLayout(left, 3)

        # ---------------- Right: cart ----------------
        right = QVBoxLayout()
        right.setSpacing(12)

        cart_title = QLabel("Current Order")
        cart_title.setStyleSheet("font-size: 18px; font-weight: 600;")
        right.addWidget(cart_title)

        cart_card = QFrame()
        cart_card.setProperty("card", "true")
        apply_card_shadow(cart_card)
        cart_layout = QVBoxLayout(cart_card)
        cart_layout.setContentsMargins(14, 14, 14, 14)
        cart_layout.setSpacing(10)

        customer_row = QHBoxLayout()
        customer_row.setSpacing(8)
        self.customer_name_input = QLineEdit()
        self.customer_name_input.setPlaceholderText("Customer name (optional)")
        self.customer_name_input.setMinimumHeight(36)
        self.customer_name_input.returnPressed.connect(
            lambda: self.customer_name_input.focusNextChild()
        )
        customer_row.addWidget(self.customer_name_input, 1)
        self.walkin_input = QLineEdit()
        self.walkin_input.setPlaceholderText("Walk-in / Table No. (optional)")
        self.walkin_input.setMinimumHeight(36)
        self.walkin_input.returnPressed.connect(lambda: self.walkin_input.focusNextChild())
        customer_row.addWidget(self.walkin_input, 1)
        cart_layout.addLayout(customer_row)

        self.cart_table = QTableWidget(0, 5)
        self.cart_table.setHorizontalHeaderLabels(["S.No", "Item", "Qty", "Total", ""])
        cheader = self.cart_table.horizontalHeader()
        cheader.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        cheader.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        cheader.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        cheader.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        cheader.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.verticalHeader().setDefaultSectionSize(40)
        self.cart_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cart_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cart_table.setMinimumHeight(320)
        self.cart_table.installEventFilter(self)
        # Stretch factor 1 so the cart list is the one thing in this card
        # that actually absorbs extra vertical space - the rows below it
        # (discount, payment method, totals, buttons) stay their natural
        # size, and the item list gets whatever room that leaves instead
        # of being squeezed down to its bare minimum.
        cart_layout.addWidget(self.cart_table, 1)

        self.status_label = QLabel("")
        self.status_label.setProperty("role", "subtitle")
        cart_layout.addWidget(self.status_label)

        # ---- Discount: a single optional Rs. amount, entered directly ----
        discount_row = QHBoxLayout()
        discount_row.setSpacing(8)
        discount_label = QLabel("Discount (Rs.)")
        discount_label.setStyleSheet("font-weight: 600;")
        self.discount_value_input = QLineEdit()
        self.discount_value_input.setPlaceholderText("0 (optional)")
        self.discount_value_input.setValidator(QDoubleValidator(0.0, 1_000_000.0, 2, self))
        self.discount_value_input.setMinimumHeight(34)
        self.discount_value_input.setMaximumWidth(140)
        self.discount_value_input.textChanged.connect(lambda _t: self.recompute_totals())
        self.discount_value_input.returnPressed.connect(self.confirm_discount)
        discount_row.addWidget(discount_label)
        discount_row.addWidget(self.discount_value_input)
        discount_row.addStretch()
        cart_layout.addLayout(discount_row)

        # ---- Totals breakdown ----
        self.subtotal_value = QLabel("Rs. 0")
        self.discount_amount_value = QLabel("Rs. 0")
        self.grand_total_value = QLabel("Rs. 0")
        cart_layout.addLayout(self._totals_row("Subtotal", self.subtotal_value))
        cart_layout.addLayout(self._totals_row("Discount", self.discount_amount_value))
        cart_layout.addLayout(self._totals_row("Total", self.grand_total_value, big=True))

        # ---- Payment method ----
        payment_label = QLabel("Payment Method")
        payment_label.setStyleSheet("font-weight: 600;")
        cart_layout.addWidget(payment_label)

        self.payment_method_combo = QComboBox()
        self.payment_method_combo.addItems(PAYMENT_METHODS)
        self.payment_method_combo.setMinimumHeight(36)
        # Arrow Up/Down already change the current item on a closed,
        # non-editable QComboBox without opening its popup - exactly the
        # plain "arrow keys" behaviour wanted here. Every method is just a
        # selection - none of them need any further input.
        self.payment_method_combo.currentTextChanged.connect(self.select_payment_method)
        cart_layout.addWidget(self.payment_method_combo)
        self.payment_method_combo.setCurrentIndex(0)  # Cash, by default

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        clear_btn = QPushButton("  Clear")
        clear_btn.setIcon(qta.icon("fa5s.times", color="#dc2626"))
        clear_btn.setProperty("variant", "danger")
        clear_btn.setMinimumHeight(42)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setToolTip("Remove all items from the current order")
        clear_btn.clicked.connect(self.clear_cart)
        generate_btn = QPushButton("  Generate Bill  (Ctrl+Enter)")
        generate_btn.setProperty("variant", "primary")
        generate_btn.setIcon(qta.icon("fa5s.receipt", color="white"))
        generate_btn.setMinimumHeight(42)
        generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        generate_btn.clicked.connect(self.generate_bill)
        self.generate_btn = generate_btn
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(generate_btn, 1)
        cart_layout.addLayout(btn_row)

        right.addWidget(cart_card, 1)
        root.addLayout(right, 2)

        # ---------------- Keyboard shortcuts ----------------
        # QShortcut's default context fires window-wide regardless of which
        # sibling page is on top of the QStackedWidget in MainWindow, so
        # every handler below starts with an isVisible() guard - it's False
        # for any page that isn't the one currently shown by the stack.
        generate_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        generate_shortcut.activated.connect(self.generate_bill)
        generate_shortcut_enter = QShortcut(QKeySequence("Ctrl+Enter"), self)
        generate_shortcut_enter.activated.connect(self.generate_bill)

        discount_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        discount_shortcut.activated.connect(self.focus_discount)

        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self.undo_last_removal)

        self._build_tab_order(clear_btn, generate_btn)

    # ------------------------------------------------------------------ #
    # Layout helpers
    # ------------------------------------------------------------------ #
    def _totals_row(self, label_text, value_widget, big=False):
        row = QHBoxLayout()
        label = QLabel(label_text)
        if big:
            label.setStyleSheet("font-size: 16px; font-weight: 600;")
            value_widget.setStyleSheet("font-size: 24px; font-weight: 700; color: #2563eb;")
        else:
            label.setStyleSheet("color: #6b7280;")
        value_widget.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(label)
        row.addStretch()
        row.addWidget(value_widget)
        return row

    def _build_tab_order(self, clear_btn, generate_btn):
        chain = [
            self.search_input, self.menu_table, self.customer_name_input, self.walkin_input,
            self.cart_table, self.discount_value_input, self.payment_method_combo,
            clear_btn, generate_btn,
        ]
        for a, b in zip(chain, chain[1:]):
            self.setTabOrder(a, b)

    # ------------------------------------------------------------------ #
    def refresh(self):
        self.refresh_menu()
        self.render_cart()
        self.search_input.setFocus()

    def refresh_menu(self):
        search = self.search_input.text().strip()
        items = self.db.get_items(active_only=True, search=search)
        currency = self.db.get_settings()["currency_symbol"]
        self.menu_table.setRowCount(0)

        for row_idx, item in enumerate(items):
            self.menu_table.insertRow(row_idx)
            name_item = QTableWidgetItem(item["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, (item["id"], item["name"], item["price"]))
            self.menu_table.setItem(row_idx, 0, name_item)
            price_item = QTableWidgetItem(f"{currency} {item['price']:.0f}")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.menu_table.setItem(row_idx, 1, price_item)

            add_btn = QPushButton()
            add_btn.setIcon(qta.icon("fa5s.plus-circle", color="#2563eb"))
            add_btn.setProperty("variant", "icon")
            add_btn.setFixedSize(32, 32)
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_btn.setToolTip("Add to cart (or press Enter on the selected row)")
            add_btn.clicked.connect(
                lambda _c=False, i=item["id"], n=item["name"], p=item["price"]: self.add_to_cart(i, n, p)
            )
            self.menu_table.setCellWidget(row_idx, 2, add_btn)

        if self.menu_table.rowCount():
            self.menu_table.setCurrentCell(0, 0)

    def add_current_menu_row(self):
        """Add whichever menu row is currently selected - used by both the
        Enter key (keyboard-driven billing) and double-click activation."""
        row = self.menu_table.currentRow()
        if row < 0:
            return
        name_item = self.menu_table.item(row, 0)
        if not name_item:
            return
        item_id, name, price = name_item.data(Qt.ItemDataRole.UserRole)
        self.add_to_cart(item_id, name, price)

    def add_top_menu_match(self):
        """Enter pressed in the search box: add the first row of the
        (possibly filtered) menu list - lets a cashier type + Enter repeatedly
        to keep adding/incrementing the same item without touching the mouse."""
        if self.menu_table.rowCount() == 0:
            return
        self.menu_table.setCurrentCell(0, 0)
        self.add_current_menu_row()

    # ------------------------------------------------------------------ #
    # Keyboard event handling
    # ------------------------------------------------------------------ #
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()

            if obj is self.search_input:
                if key == Qt.Key.Key_Down:
                    if self.menu_table.rowCount():
                        self.menu_table.setFocus()
                        self.menu_table.setCurrentCell(0, 0)
                    return True
                if key == Qt.Key.Key_Escape and self.search_input.text():
                    self.search_input.clear()
                    self.refresh_menu()
                    return True

            elif obj is self.cart_table:
                row = self.cart_table.currentRow()
                if 0 <= row < len(self.cart):
                    item_id = self.cart[row]["id"]
                    if key in (Qt.Key.Key_Right, Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                        self.change_qty(item_id, 1)
                        return True
                    if key in (Qt.Key.Key_Left, Qt.Key.Key_Minus):
                        self.change_qty(item_id, -1)
                        return True
                    if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                        self.remove_from_cart(item_id)
                        return True
                    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                        self.start_qty_edit()
                        return True

            elif obj is self._qty_editor and key == Qt.Key.Key_Escape:
                # Cancel the in-place quantity edit and restore the row.
                self._qty_editor = None
                self.render_cart()
                self.cart_table.setFocus()
                return True

        return super().eventFilter(obj, event)

    def focus_discount(self):
        if not self.isVisible():
            return
        self.discount_value_input.setFocus()
        self.discount_value_input.selectAll()

    # ------------------------------------------------------------------ #
    # Cart mutation
    # ------------------------------------------------------------------ #
    def add_to_cart(self, item_id, name, price):
        for entry in self.cart:
            if entry["id"] == item_id:
                entry["quantity"] += 1
                entry["total"] = entry["quantity"] * entry["price"]
                self.render_cart()
                return
        self.cart.append({"id": item_id, "name": name, "price": price, "quantity": 1, "total": price})
        self.render_cart()

    def change_qty(self, item_id, delta):
        for entry in self.cart:
            if entry["id"] == item_id:
                entry["quantity"] = max(1, entry["quantity"] + delta)
                entry["total"] = entry["quantity"] * entry["price"]
                break
        self.render_cart()

    def start_qty_edit(self):
        """Enter on a selected cart row: swap its qty cell for a live editor
        so the cashier can type an exact quantity instead of pressing +/-
        repeatedly. Enter commits, Escape (handled in eventFilter) cancels."""
        row = self.cart_table.currentRow()
        if not (0 <= row < len(self.cart)):
            return
        entry = self.cart[row]
        editor = QLineEdit(str(entry["quantity"]))
        editor.setValidator(QIntValidator(1, 99999, editor))
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.selectAll()
        editor.returnPressed.connect(lambda r=row, e=editor: self.commit_qty_edit(r, e))
        editor.installEventFilter(self)
        self._qty_editor = editor
        self.cart_table.setCellWidget(row, 2, editor)
        editor.setFocus()

    def commit_qty_edit(self, row, editor):
        if not (0 <= row < len(self.cart)):
            return
        try:
            qty = int(editor.text().strip())
        except ValueError:
            qty = 0
        if qty < 1:
            AppMessageBox.warning(self, "Invalid Quantity", "Quantity must be a whole number of 1 or more.")
            editor.selectAll()
            editor.setFocus()
            return
        entry = self.cart[row]
        entry["quantity"] = qty
        entry["total"] = entry["quantity"] * entry["price"]
        self._qty_editor = None
        # render_cart() below destroys this very editor (setCellWidget over
        # it) while we're still inside the editor's own returnPressed
        # handler - Qt defers that destruction via deleteLater(), and its
        # own focus cleanup can run *after* our code and steal focus back.
        # Deferring the rebuild+refocus to the next event-loop tick lets
        # that deferred cleanup finish first, so our setFocus() wins.
        QTimer.singleShot(0, self._finish_qty_edit)

    def _finish_qty_edit(self):
        self.render_cart()
        # Continuous billing: confirming a quantity sends focus straight
        # back to product search so the cashier can add the next item.
        self.search_input.setFocus()

    def remove_from_cart(self, item_id):
        for idx, entry in enumerate(self.cart):
            if entry["id"] == item_id:
                self._last_removed = (idx, entry)
                del self.cart[idx]
                self.render_cart()
                self._flash_status(f"Removed {entry['name']} — Ctrl+Z to undo")
                return

    def undo_last_removal(self):
        if not self.isVisible() or not self._last_removed:
            return
        idx, entry = self._last_removed
        self._last_removed = None
        idx = min(idx, len(self.cart))
        self.cart.insert(idx, entry)
        self.render_cart()
        self._flash_status(f"Restored {entry['name']}")

    def _flash_status(self, text, timeout_ms=4000):
        self.status_label.setText(text)
        QTimer.singleShot(
            timeout_ms,
            lambda t=text: self.status_label.setText("") if self.status_label.text() == t else None,
        )

    def clear_cart(self):
        if not self.cart:
            return
        confirmed = AppMessageBox.question(
            self, "Clear Order", "Remove all items from the current order?",
            yes_text="Clear", no_text="Cancel",
        )
        if confirmed:
            self.cart = []
            self._last_removed = None
            self.render_cart()

    def render_cart(self):
        currency = self.db.get_settings()["currency_symbol"]
        previous_row = self.cart_table.currentRow()
        self._qty_editor = None
        self.cart_table.setRowCount(0)

        for row_idx, entry in enumerate(self.cart):
            self.cart_table.insertRow(row_idx)
            sno_item = QTableWidgetItem(str(row_idx + 1))
            sno_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cart_table.setItem(row_idx, 0, sno_item)
            self.cart_table.setItem(row_idx, 1, QTableWidgetItem(entry["name"]))

            qty_widget = QWidget()
            qty_layout = QHBoxLayout(qty_widget)
            qty_layout.setContentsMargins(0, 0, 0, 0)
            qty_layout.setSpacing(4)
            minus_btn = QPushButton()
            minus_btn.setIcon(qta.icon("fa5s.minus", color="#dc2626"))
            minus_btn.setIconSize(minus_btn.iconSize() * 0.7)
            minus_btn.setProperty("variant", "qty")
            minus_btn.setFixedSize(24, 24)
            minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            minus_btn.setToolTip("Decrease quantity (← key)")
            minus_btn.clicked.connect(lambda _c=False, i=entry["id"]: self.change_qty(i, -1))
            qty_label = QLabel(str(entry["quantity"]))
            qty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qty_label.setStyleSheet("font-weight: 700;")
            qty_label.setFixedWidth(22)
            qty_label.setToolTip("Press Enter on this row to type an exact quantity")
            plus_btn = QPushButton()
            plus_btn.setIcon(qta.icon("fa5s.plus", color="#16a34a"))
            plus_btn.setIconSize(plus_btn.iconSize() * 0.7)
            plus_btn.setProperty("variant", "qty")
            plus_btn.setFixedSize(24, 24)
            plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            plus_btn.setToolTip("Increase quantity (→ key)")
            plus_btn.clicked.connect(lambda _c=False, i=entry["id"]: self.change_qty(i, 1))
            qty_layout.addWidget(minus_btn)
            qty_layout.addWidget(qty_label)
            qty_layout.addWidget(plus_btn)
            self.cart_table.setCellWidget(row_idx, 2, qty_widget)

            total_item = QTableWidgetItem(f"{currency} {entry['total']:.0f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cart_table.setItem(row_idx, 3, total_item)

            remove_btn = QPushButton()
            remove_btn.setIcon(qta.icon("fa5s.trash-alt", color="#dc2626"))
            remove_btn.setProperty("variant", "icon")
            remove_btn.setFixedSize(28, 28)
            remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            remove_btn.setToolTip("Remove item (Delete key)")
            remove_btn.clicked.connect(lambda _c=False, i=entry["id"]: self.remove_from_cart(i))
            self.cart_table.setCellWidget(row_idx, 4, remove_btn)

        if 0 <= previous_row < self.cart_table.rowCount():
            self.cart_table.setCurrentCell(previous_row, 1)
        elif self.cart_table.rowCount():
            self.cart_table.setCurrentCell(self.cart_table.rowCount() - 1, 1)

        self.recompute_totals()

    # ------------------------------------------------------------------ #
    # Discount / totals
    # ------------------------------------------------------------------ #
    def _parse_discount_input(self):
        """Returns (Decimal value, error message or None) for the discount
        Rs. amount - it's a plain optional rupee amount now, no % option.
        Only flags genuine problems - clamping for the live preview happens
        separately in recompute_totals()."""
        raw = self.discount_value_input.text().strip()
        if not raw:
            return Decimal("0"), None
        try:
            value = Decimal(raw)
        except InvalidOperation:
            return Decimal("0"), "Discount value must be a valid number."
        if value < 0:
            return value, "Discount cannot be negative."
        return value, None

    def recompute_totals(self):
        """Single source of truth for Subtotal/Discount/Total - always
        derived fresh from self.cart rather than trusting stale labels."""
        subtotal = sum((Decimal(str(e["price"])) * e["quantity"] for e in self.cart), Decimal("0"))
        value, error = self._parse_discount_input()

        discount_amount = value
        if value > subtotal:
            error = error or "Discount cannot exceed the subtotal."
            discount_amount = subtotal
        discount_amount = discount_amount.quantize(CENT, rounding=ROUND_HALF_UP)
        net_total = subtotal - discount_amount
        if net_total < 0:
            net_total = Decimal("0")
        net_total = net_total.quantize(CENT, rounding=ROUND_HALF_UP)
        subtotal = subtotal.quantize(CENT, rounding=ROUND_HALF_UP)

        self._set_error(self.discount_value_input, bool(error))

        currency = self.db.get_settings()["currency_symbol"]
        self.subtotal_value.setText(f"{currency} {subtotal:.0f}")
        self.discount_amount_value.setText(f"{currency} {discount_amount:.0f}")
        self.grand_total_value.setText(f"{currency} {net_total:.0f}")
        self._last_net_total = net_total
        return subtotal, discount_amount, net_total, error

    def confirm_discount(self):
        _, _, _, error = self.recompute_totals()
        if error:
            AppMessageBox.warning(self, "Invalid Discount", error)
            self.discount_value_input.selectAll()
            self.discount_value_input.setFocus()
            return
        self.payment_method_combo.setFocus()

    @staticmethod
    def _set_error(widget, is_error: bool):
        if widget.property("error") == is_error:
            return
        widget.setProperty("error", is_error)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    # ------------------------------------------------------------------ #
    # Payment method
    # ------------------------------------------------------------------ #
    def select_payment_method(self, method):
        """Called both from the combo's own currentTextChanged (live, as
        the cashier arrows through options) and programmatically (e.g. on
        reset) - every method is just a selection, nothing else to fill
        in, so this only needs to keep state and the combo in sync."""
        self.current_payment_method = method
        if self.payment_method_combo.currentText() != method:
            self.payment_method_combo.setCurrentText(method)

    # ------------------------------------------------------------------ #
    # Bill generation
    # ------------------------------------------------------------------ #
    def generate_bill(self):
        if not self.isVisible() or self._submitting:
            return

        if not self.cart:
            AppMessageBox.warning(self, "Empty Order", "Add at least one item before generating a bill.")
            self.search_input.setFocus()
            return
        for entry in self.cart:
            if not isinstance(entry["quantity"], int) or entry["quantity"] < 1:
                AppMessageBox.warning(
                    self, "Invalid Quantity", f"'{entry['name']}' has an invalid quantity."
                )
                self.cart_table.setFocus()
                return

        settings = self.db.get_settings()

        subtotal, discount_amount, net_total, discount_error = self.recompute_totals()
        if discount_error:
            AppMessageBox.warning(self, "Invalid Discount", discount_error)
            self.discount_value_input.selectAll()
            self.discount_value_input.setFocus()
            return

        method = self.current_payment_method
        currency = settings["currency_symbol"]

        # Nothing is written to the database until this is confirmed -
        # Cancel leaves the cart exactly as it was so the cashier can keep
        # editing, matching Clear Cart's own confirm-first pattern above.
        confirmed = AppMessageBox.question(
            self, "Confirm Bill",
            f"Save this bill for {currency} {net_total:.0f} via {method}?",
            yes_text="Confirm", no_text="Cancel",
        )
        if not confirmed:
            return

        self._submitting = True
        self.generate_btn.setEnabled(False)
        try:
            customer_name = self.customer_name_input.text().strip()
            walkin_no = self.walkin_input.text().strip()
            raw_discount_value = self.discount_value_input.text().strip()
            discount_value = Decimal(raw_discount_value) if raw_discount_value else Decimal("0")

            bill = self.db.create_bill(
                self.current_user["id"], self.cart, customer_name, walkin_no,
                subtotal=float(subtotal), discount_type="fixed",
                discount_value=float(discount_value), discount_amount=float(discount_amount),
                net_total=float(net_total), payment_method=method,
            )
            html = self._build_receipt_html(bill, self.cart, settings)

            self.reset_billing_screen()

            width_mm = settings["paper_width_mm"] if "paper_width_mm" in settings.keys() else 80
            printer_name = settings["printer_name"] if "printer_name" in settings.keys() else ""
            dialog = ReceiptDialog(html, width_mm=width_mm, printer_name=printer_name or "", parent=self)
            dialog.exec()
        finally:
            self._submitting = False
            self.generate_btn.setEnabled(True)

        # Ready for the next bill straight away - keyboard-driven billing
        # depends on the search box already having focus.
        self.search_input.setFocus()

    def reset_billing_screen(self):
        self.cart = []
        self._last_removed = None
        self.customer_name_input.clear()
        self.walkin_input.clear()
        self.discount_value_input.clear()
        self.status_label.setText("")
        self.render_cart()
        self.select_payment_method("Cash")

    def _build_receipt_html(self, bill, cart_items, settings) -> str:
        currency = settings["currency_symbol"]

        # Customer / walk-in line, shown only when the cashier filled at
        # least one of the two fields in - most walk-in orders leave both
        # blank and this whole block is skipped.
        customer_name = bill["customer_name"] if "customer_name" in bill.keys() else None
        walkin_no = bill["walkin_no"] if "walkin_no" in bill.keys() else None
        customer_html = ""
        if customer_name or walkin_no:
            lines = []
            if customer_name:
                lines.append(f"<div style='font-size:10pt; color:#111;'><b>Customer:</b> {customer_name}</div>")
            if walkin_no:
                lines.append(f"<div style='font-size:10pt; color:#111;'><b>Table/Walk-in:</b> {walkin_no}</div>")
            customer_html = "".join(lines)

        # A proper 4-column table - # / Item / Qty / Total - each value
        # aligned directly under its own header, matching a standard POS
        # receipt layout. The currency symbol is shown once in the "Total"
        # header rather than repeated on every row - on a 58mm receipt
        # repeating "Rs. 1500" in a ~30%-wide column wraps onto its own
        # line, which is exactly the crushed layout this rewrite is meant
        # to avoid. Every cell sets its color explicitly rather than
        # relying on inheriting it from the outer wrapper - Qt's rich-text
        # engine does not reliably cascade CSS color (or font-family) from
        # an ancestor into a *nested* <table>, so any cell left unstyled
        # here was silently falling back to the palette's link-blue instead
        # of the intended dark text.
        rows_html = ""
        for idx, entry in enumerate(cart_items, start=1):
            rows_html += (
                "<tr>"
                f"<td width='8%' style='padding:3pt 2pt; color:#111; vertical-align:top;'>{idx}</td>"
                f"<td width='47%' style='padding:3pt 2pt; color:#111; vertical-align:top; font-weight:600;'>{entry['name']}</td>"
                f"<td width='15%' style='padding:3pt 2pt; color:#111; text-align:center; vertical-align:top;'>{entry['quantity']}</td>"
                f"<td width='30%' style='padding:3pt 2pt; color:#111; text-align:right; vertical-align:top; font-weight:600;'>{entry['total']:.0f}</td>"
                "</tr>"
            )
        created = datetime.fromisoformat(bill["created_at"])

        # Subtotal/Discount lines only appear when a discount was actually
        # applied - most bills have none, and an always-present "Discount:
        # Rs. 0" row would just be clutter on a narrow thermal receipt.
        discount_amount = bill["discount_amount"] if "discount_amount" in bill.keys() else 0
        subtotal = bill["subtotal"] if "subtotal" in bill.keys() and bill["subtotal"] is not None else bill["grand_total"]
        breakdown_html = ""
        total_label = "Total"
        if discount_amount and discount_amount > 0:
            breakdown_html = f"""
            <table width="100%" cellspacing="0" cellpadding="0" style="margin-top:2pt; font-size:9.5pt;">
                <tr>
                    <td style="color:#111;">Subtotal</td>
                    <td style="color:#111; text-align:right;">{currency} {subtotal:.0f}</td>
                </tr>
                <tr>
                    <td style="color:#111;">Discount</td>
                    <td style="color:#111; text-align:right;">- {currency} {discount_amount:.0f}</td>
                </tr>
            </table>
            """

        # Payment method + method-specific detail (cash tender/change, or a
        # transaction reference for the digital wallets/bank transfer).
        payment_method = bill["payment_method"] if "payment_method" in bill.keys() and bill["payment_method"] else "Cash"
        payment_html = f"<div style='font-size:9.5pt; color:#111; margin-top:4pt;'><b>Payment:</b> {payment_method}</div>"
        if payment_method == "Cash":
            # Cash no longer tracks an amount received/change on the
            # billing screen - only show this line for older bills (from
            # before that was removed) that still have it recorded.
            received = bill["amount_received"] if "amount_received" in bill.keys() else None
            if received is not None:
                change = bill["change_due"] if "change_due" in bill.keys() and bill["change_due"] is not None else 0
                payment_html += (
                    f"<div style='font-size:9pt; color:#333;'>Received: {currency} {received:.0f}"
                    f" &nbsp;•&nbsp; Change: {currency} {change:.0f}</div>"
                )
        else:
            ref = bill["transaction_ref"] if "transaction_ref" in bill.keys() and bill["transaction_ref"] else ""
            if ref:
                payment_html += f"<div style='font-size:9pt; color:#333;'>Ref: {ref}</div>"
            bank_info = bill["bank_info"] if "bank_info" in bill.keys() and bill["bank_info"] else ""
            if bank_info:
                payment_html += f"<div style='font-size:9pt; color:#333;'>{bank_info}</div>"

        # width="100%"/"N%" (HTML attributes, not just CSS) are what make
        # Qt's rich text engine stretch/split this table across the full
        # receipt width, and every font-size below is in "pt" rather than
        # "px" - Qt ties CSS px to the printer's real DPI, so px-sized text
        # on a high-res printer/PDF renders at a near-invisible fraction of
        # its intended size, while points print at exactly the size they
        # appear in the preview. This same HTML is used for the 58mm/80mm
        # thermal path and the full-page "Print to..." dialog on a regular
        # printer - the percentage-based table adapts to either width.
        return f"""
        <div style="font-family:'Segoe UI',sans-serif; color:#111;">
            <div style="text-align:center; font-size:13pt; font-weight:700; color:#111;">{settings['hotel_name']}</div>
            <div style="text-align:center; font-size:9pt; margin-top:2pt; color:#333;">{settings['address'] or ''}</div>
            <div style="text-align:center; font-size:9pt; color:#333;">Tel: {settings['phone'] or ''}</div>
            <div style="border-top:1pt solid #333; margin:4pt 0;"></div>
            <div style="font-size:10pt; color:#111;"><b>Date:</b> {created.strftime('%d-%m-%Y %I:%M %p')}</div>
            {customer_html}
            <div style="border-top:1pt solid #333; margin:4pt 0;"></div>
            <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse; font-size:9.5pt;">
                <tr style="border-bottom:1.5pt solid #333;">
                    <th width="8%" style="padding:4pt 2pt; text-align:left; color:#111;">#</th>
                    <th width="47%" style="padding:4pt 2pt; text-align:left; color:#111;">Item</th>
                    <th width="15%" style="padding:4pt 2pt; text-align:center; color:#111;">Qty</th>
                    <th width="30%" style="padding:4pt 2pt; text-align:right; color:#111;">Total ({currency})</th>
                </tr>
                {rows_html}
            </table>
            <div style="border-top:1pt solid #333; margin:4pt 0;"></div>
            {breakdown_html}
            <table width="100%" cellspacing="0" cellpadding="0" style="margin-top:2pt;">
                <tr>
                    <td style="font-size:12pt; font-weight:700; color:#111;">{total_label}</td>
                    <td style="font-size:14pt; font-weight:700; color:#111; text-align:right;">{currency} {bill['grand_total']:.0f}</td>
                </tr>
            </table>
            <div style="border-top:1pt solid #333; margin:4pt 0;"></div>
            {payment_html}
            <div style="border-top:1pt solid #333; margin:4pt 0;"></div>
            <div style="text-align:center; font-size:9pt; margin-top:8pt; color:#333;">{settings['footer_message'] or ''}</div>
        </div>
        """
