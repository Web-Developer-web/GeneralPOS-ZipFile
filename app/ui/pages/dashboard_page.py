"""Dashboard page: KPI cards + recent bills."""
import qtawesome as qta
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

from app.core.database import Database
from app.ui.widgets.stat_card import StatCard
from app.ui.widgets.credit_label import AnimatedCreditLabel
from app.ui.widgets.digital_clock import DigitalClockWidget
from app.ui.widgets.wavy_background import WavyGradientBackground
from app.ui.widgets.animations import fade_slide_in
from app.ui.theme import apply_card_shadow, SUCCESS


def _amount_pill(text: str) -> QWidget:
    """Grand Total cell rendered as a tinted rounded pill - reuses the same
    accent-tint-gradient language as StatCard's icon chips instead of a
    plain bold-colored table cell."""
    wrapper = QWidget()
    wrap_layout = QHBoxLayout(wrapper)
    wrap_layout.setContentsMargins(4, 4, 4, 4)
    wrap_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pill = QLabel(text)
    pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pill.setStyleSheet(
        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f" stop:0 {SUCCESS}26, stop:1 {SUCCESS}14);"
        f" color: {SUCCESS}; border-radius: 10px; padding: 4px 14px;"
        f" font-weight: 700; border: none;"
    )
    wrap_layout.addWidget(pill)
    return wrapper


class DashboardPage(QWidget):
    def __init__(self, db: Database, user=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.user = user
        self._entered = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)

        # A softly animated gradient "hero" banner in place of a plain page
        # title - gives the dashboard a welcoming, professional first
        # impression instead of a flat header bar.
        self.hero = WavyGradientBackground(
            colors=["#1d4ed8", "#4f46e5", "#7c3aed"], wave_color="#ffffff",
        )
        self.hero.setFixedHeight(168)
        apply_card_shadow(self.hero, blur=36, y_offset=8, alpha=45)
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(28, 16, 28, 16)

        greeting_col = QVBoxLayout()
        greeting_col.setSpacing(4)
        first_name = self.user["full_name"].split()[0] if self.user else "there"
        greeting = QLabel(f"Welcome back, {first_name}")
        greeting.setStyleSheet("color: white; font-size: 21px; font-weight: 700; border: none;")
        greeting_col.addWidget(greeting)
        sub = QLabel("Here is a summary of your hotel's sales and activity for today.")
        sub.setStyleSheet("color: #dbeafe; font-size: 12px; border: none;")
        greeting_col.addWidget(sub)
        hero_layout.addLayout(greeting_col)
        hero_layout.addStretch()

        # Live clock (Dashboard-only) - a self-updating time/day/date card.
        self.clock = DigitalClockWidget()
        hero_layout.addWidget(self.clock)
        layout.addWidget(self.hero)

        grid = QGridLayout()
        grid.setSpacing(16)
        self.card_items = StatCard("Total Items", "fa5s.box-open", "#2563eb")
        self.card_daily_revenue = StatCard("Today's Revenue", "fa5s.coins", "#16a34a")
        self.card_daily_bills = StatCard("Today's Bills", "fa5s.receipt", "#d97706")
        self.card_total_revenue = StatCard("Total Revenue", "fa5s.chart-line", "#7c3aed")
        grid.addWidget(self.card_items, 0, 0)
        grid.addWidget(self.card_daily_revenue, 0, 1)
        grid.addWidget(self.card_daily_bills, 0, 2)
        grid.addWidget(self.card_total_revenue, 0, 3)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        for card in (self.card_items, self.card_daily_revenue, self.card_daily_bills, self.card_total_revenue):
            apply_card_shadow(card)
        layout.addLayout(grid)

        self.recent_card = QFrame()
        self.recent_card.setProperty("card", "true")
        apply_card_shadow(self.recent_card)
        recent_layout = QVBoxLayout(self.recent_card)
        recent_layout.setContentsMargins(20, 18, 20, 18)

        recent_title_row = QHBoxLayout()
        recent_icon = QLabel()
        recent_icon.setPixmap(qta.icon("fa5s.history", color="#2563eb").pixmap(16, 16))
        recent_title_row.addWidget(recent_icon)
        recent_title = QLabel("Recent Bills — Today")
        recent_title.setStyleSheet("font-size: 15px; font-weight: 600; border: none;")
        recent_title_row.addWidget(recent_title)
        recent_title_row.addStretch()
        recent_layout.addLayout(recent_title_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Bill No.", "Time", "Items", "Grand Total"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(260)
        recent_layout.addWidget(self.table)

        layout.addWidget(self.recent_card, 1)

        # The badge carries its own translucent dark-glass fill, so it
        # stays readable regardless of the active light/dark page theme.
        footer = AnimatedCreditLabel("Developed By: Abdul Wahid Khan", font_size=11)
        layout.addWidget(footer, alignment=Qt.AlignmentFlag.AlignHCenter)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._entered:
            self._entered = True
            QTimer.singleShot(60, self._play_entrance)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._entered = False

    def _play_entrance(self):
        cards = [
            self.card_items, self.card_daily_revenue,
            self.card_daily_bills, self.card_total_revenue, self.recent_card,
        ]
        for i, card in enumerate(cards):
            fade_slide_in(card, delay=i * 90)

    def refresh(self):
        settings = self.db.get_settings()
        currency = settings["currency_symbol"]
        stats = self.db.get_dashboard_stats()

        self.card_items.set_value(str(stats["total_items"]))
        self.card_daily_revenue.set_value(f"{currency} {stats['daily_revenue']:.0f}")
        self.card_daily_bills.set_value(str(stats["daily_bills"]))
        self.card_total_revenue.set_value(f"{currency} {stats['total_revenue']:.0f}")

        from datetime import date
        bills = self.db.get_bills_by_date(date.today())
        self.table.setRowCount(0)
        for row_idx, bill in enumerate(bills):
            self.table.insertRow(row_idx)
            time_str = bill["created_at"].split("T")[1] if "T" in bill["created_at"] else bill["created_at"]
            values = [bill["bill_no"], time_str, str(bill["items_count"])]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col, item)
            self.table.setCellWidget(row_idx, 3, _amount_pill(f"{currency} {bill['grand_total']:.0f}"))
