"""Backup page: shows the daily-automatic backups and lets an Admin take
an extra one on demand."""
import os
from datetime import datetime

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from app import backup as backup_mod
from app.database import Database
from app.widgets.message_box import AppMessageBox
from app.theme import apply_card_shadow


class BackupPage(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        header_row = QHBoxLayout()
        title = QLabel("Backup")
        title.setProperty("role", "pageTitle")
        header_row.addWidget(title)
        header_row.addStretch()

        open_folder_btn = QPushButton("  Open Backup Folder")
        open_folder_btn.setIcon(qta.icon("fa5s.folder-open", color="#6b7280"))
        open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_folder_btn.setMinimumHeight(36)
        open_folder_btn.clicked.connect(self.open_backup_folder)
        header_row.addWidget(open_folder_btn)

        backup_btn = QPushButton("  Backup Now")
        backup_btn.setIcon(qta.icon("fa5s.database", color="white"))
        backup_btn.setProperty("variant", "primary")
        backup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        backup_btn.setMinimumHeight(36)
        backup_btn.clicked.connect(self.backup_now)
        header_row.addWidget(backup_btn)
        layout.addLayout(header_row)

        self.status_label = QLabel("")
        self.status_label.setProperty("role", "subtitle")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        card = QFrame()
        card.setProperty("card", "true")
        apply_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Backup File", "Date & Time", "Size"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(360)
        card_layout.addWidget(self.table)
        layout.addWidget(card, 1)

    def refresh(self):
        today_done = backup_mod.has_backup_today()
        self.status_label.setText(
            "Today's automatic backup is already saved below."
            if today_done else
            "No backup yet today - one is taken automatically each time the "
            "app starts, or click \"Backup Now\" to take one right away."
        )
        self.table.setRowCount(0)
        for row_idx, (path, mtime, size) in enumerate(backup_mod.list_backups()):
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(path.name))
            when = datetime.fromtimestamp(mtime).strftime("%d %B %Y, %I:%M %p")
            self.table.setItem(row_idx, 1, QTableWidgetItem(when))
            size_item = QTableWidgetItem(f"{size / 1024:.0f} KB")
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 2, size_item)

    def backup_now(self):
        try:
            backup_mod.backup_now(self.db.conn)
        except Exception as exc:
            AppMessageBox.error(self, "Backup Failed", f"Could not create a backup:\n{exc}")
            return
        self.refresh()
        AppMessageBox.success(self, "Backup Complete", "A fresh backup has been saved.")

    def open_backup_folder(self):
        backup_mod.BACKUP_DIR.mkdir(exist_ok=True)
        os.startfile(backup_mod.BACKUP_DIR)
