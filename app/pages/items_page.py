"""Item Management page: CRUD for menu items."""
import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFormLayout,
    QDoubleSpinBox, QComboBox, QFrame, QAbstractItemView,
)

from app.database import Database
from app.widgets.message_box import AppMessageBox
from app.theme import apply_card_shadow


class ItemDialog(QDialog):
    def __init__(self, currency: str, parent=None, item=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle("Edit Item" if item else "Add New Item")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)

        self.name_input = QLineEdit(item["name"] if item else "")
        self.name_input.setPlaceholderText("e.g. Chicken Karahi")
        form.addRow("Item Name", self.name_input)

        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.addItems(
            ["Rice & Biryani", "BBQ", "Karahi", "Fast Food", "Beverages", "Bread", "Desserts", "Other"]
        )
        if item and item["category"]:
            self.category_input.setCurrentText(item["category"])
        form.addRow("Category", self.category_input)

        self.price_input = QDoubleSpinBox()
        self.price_input.setPrefix(f"{currency} ")
        self.price_input.setMaximum(1_000_000)
        self.price_input.setDecimals(0)
        self.price_input.setSingleStep(10)
        if item:
            self.price_input.setValue(item["price"])
        form.addRow("Price", self.price_input)

        layout.addLayout(form)
        layout.addSpacing(10)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("  Cancel")
        cancel_btn.setIcon(qta.icon("fa5s.times", color="#6b7280"))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("  Save Item")
        save_btn.setIcon(qta.icon("fa5s.save", color="white"))
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self._on_save)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _on_save(self):
        if not self.name_input.text().strip():
            AppMessageBox.warning(self, "Missing Name", "Please enter an item name.")
            return
        if self.price_input.value() <= 0:
            AppMessageBox.warning(self, "Invalid Price", "Price must be greater than zero.")
            return
        self.accept()

    def values(self):
        return {
            "name": self.name_input.text().strip(),
            "category": self.category_input.currentText().strip(),
            "price": self.price_input.value(),
        }


class ItemsPage(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        header_row = QHBoxLayout()
        title = QLabel("Item Management")
        title.setProperty("role", "pageTitle")
        header_row.addWidget(title)
        header_row.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search items...")
        self.search_input.setFixedWidth(240)
        self.search_input.setMinimumHeight(36)
        self.search_input.textChanged.connect(self.refresh)
        header_row.addWidget(self.search_input)

        add_btn = QPushButton("  Add Item")
        add_btn.setProperty("variant", "primary")
        add_btn.setIcon(qta.icon("fa5s.plus", color="white"))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setMinimumHeight(36)
        add_btn.clicked.connect(self.add_item)
        header_row.addWidget(add_btn)
        layout.addLayout(header_row)

        card = QFrame()
        card.setProperty("card", "true")
        apply_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Item Name", "Category", "Price", "Status", "Actions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        # Rows default to a style-provided height that's too short for the
        # 30px action buttons in the last column, clipping them top/bottom -
        # a fixed, generous row height keeps every icon fully visible.
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(360)
        card_layout.addWidget(self.table)

        layout.addWidget(card, 1)

    def refresh(self):
        currency = self.db.get_settings()["currency_symbol"]
        search = self.search_input.text().strip()
        items = self.db.get_items(active_only=False, search=search)
        self.table.setRowCount(0)

        for row_idx, item in enumerate(items):
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(item["name"]))
            self.table.setItem(row_idx, 1, QTableWidgetItem(item["category"] or "-"))
            price_item = QTableWidgetItem(f"{currency} {item['price']:.0f}")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 2, price_item)

            status_item = QTableWidgetItem("Active" if item["is_active"] else "Inactive")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 3, status_item)

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)

            edit_btn = QPushButton()
            edit_btn.setIcon(qta.icon("fa5s.edit", color="#2563eb"))
            edit_btn.setProperty("variant", "icon")
            edit_btn.setFixedSize(30, 30)
            edit_btn.setToolTip("Edit")
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.clicked.connect(lambda _c=False, i=item["id"]: self.edit_item(i))

            toggle_btn = QPushButton()
            is_active = bool(item["is_active"])
            toggle_btn.setIcon(qta.icon("fa5s.toggle-on" if is_active else "fa5s.toggle-off",
                                         color="#16a34a" if is_active else "#9ca3af"))
            toggle_btn.setProperty("variant", "icon")
            toggle_btn.setFixedSize(30, 30)
            toggle_btn.setToolTip("Disable" if is_active else "Enable")
            toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle_btn.clicked.connect(lambda _c=False, i=item["id"], a=is_active: self.toggle_item(i, a))

            delete_btn = QPushButton()
            delete_btn.setIcon(qta.icon("fa5s.trash-alt", color="#dc2626"))
            delete_btn.setProperty("variant", "icon")
            delete_btn.setFixedSize(30, 30)
            delete_btn.setToolTip("Delete")
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.clicked.connect(lambda _c=False, i=item["id"]: self.delete_item(i))

            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(toggle_btn)
            actions_layout.addWidget(delete_btn)
            actions_layout.addStretch()
            self.table.setCellWidget(row_idx, 4, actions)

    def add_item(self):
        currency = self.db.get_settings()["currency_symbol"]
        dialog = ItemDialog(currency, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            self.db.add_item(values["name"], values["price"], values["category"])
            self.refresh()
            AppMessageBox.success(self, "Item Added", f"'{values['name']}' has been added successfully.")

    def edit_item(self, item_id: int):
        currency = self.db.get_settings()["currency_symbol"]
        item = next((i for i in self.db.get_items(active_only=False) if i["id"] == item_id), None)
        if not item:
            return
        dialog = ItemDialog(currency, self, item=item)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            self.db.update_item(item_id, values["name"], values["price"], values["category"])
            self.refresh()
            AppMessageBox.success(self, "Item Updated", f"'{values['name']}' has been updated successfully.")

    def toggle_item(self, item_id: int, currently_active: bool):
        self.db.set_item_active(item_id, not currently_active)
        self.refresh()

    def delete_item(self, item_id: int):
        item = next((i for i in self.db.get_items(active_only=False) if i["id"] == item_id), None)
        item_name = item["name"] if item else "this item"
        confirmed = AppMessageBox.question(
            self, "Delete Item", f"Are you sure you want to permanently delete '{item_name}'?",
            yes_text="Delete", no_text="Cancel",
        )
        if confirmed:
            self.db.delete_item(item_id)
            self.refresh()
            AppMessageBox.success(self, "Item Deleted", f"'{item_name}' has been deleted successfully.")
