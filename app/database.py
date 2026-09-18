"""SQLite data-access layer for HotelPOS."""
from __future__ import annotations

import sqlite3
from datetime import datetime, date
from typing import Optional

from app import config
from app.security import hash_password


class Database:
    def __init__(self, path=config.DB_PATH):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #
    def _init_schema(self):
        cur = self.conn.cursor()
        license_table_existed = self._table_exists("license")
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                phone TEXT,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Cashier',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                hotel_name TEXT NOT NULL,
                address TEXT,
                phone TEXT,
                currency_symbol TEXT NOT NULL DEFAULT 'Rs.',
                footer_message TEXT,
                theme TEXT NOT NULL DEFAULT 'light'
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                category TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_no TEXT NOT NULL UNIQUE,
                cashier_id INTEGER,
                customer_name TEXT,
                walkin_no TEXT,
                grand_total REAL NOT NULL,
                items_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (cashier_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS bill_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                total REAL NOT NULL,
                FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS license (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                tier TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                expires_at TEXT,
                last_seen TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                signature TEXT NOT NULL
            );
            """
        )
        # Migrations for databases created before printer support was added.
        self._ensure_column("settings", "printer_name", "TEXT")
        self._ensure_column("settings", "paper_width_mm", "INTEGER NOT NULL DEFAULT 80")
        # Migration for databases created before the hotel photo/logo upload.
        self._ensure_column("settings", "logo_path", "TEXT")
        # Migrations for databases created before walk-in/customer name support.
        self._ensure_column("bills", "customer_name", "TEXT")
        self._ensure_column("bills", "walkin_no", "TEXT")
        # Migrations for databases created before discount/payment-method
        # support. `grand_total` keeps meaning "final total charged" (now
        # post-discount) so every existing report/query built on it keeps
        # working unchanged; `subtotal` records the pre-discount value.
        self._ensure_column("bills", "subtotal", "REAL")
        self._ensure_column("bills", "discount_type", "TEXT")
        self._ensure_column("bills", "discount_value", "REAL NOT NULL DEFAULT 0")
        self._ensure_column("bills", "discount_amount", "REAL NOT NULL DEFAULT 0")
        self._ensure_column("bills", "payment_method", "TEXT NOT NULL DEFAULT 'Cash'")
        self._ensure_column("bills", "amount_received", "REAL")
        self._ensure_column("bills", "change_due", "REAL")
        self._ensure_column("bills", "transaction_ref", "TEXT")
        self._ensure_column("bills", "bank_info", "TEXT")

        cur.execute("SELECT COUNT(*) FROM settings")
        if cur.fetchone()[0] == 0:
            cur.execute(
                """INSERT INTO settings (id, hotel_name, address, phone, currency_symbol,
                   footer_message, theme, printer_name, paper_width_mm)
                   VALUES (1, ?, ?, ?, ?, ?, ?, NULL, 80)""",
                (
                    config.DEFAULT_HOTEL_NAME,
                    config.DEFAULT_ADDRESS,
                    config.DEFAULT_PHONE,
                    config.DEFAULT_CURRENCY,
                    config.DEFAULT_FOOTER_MESSAGE,
                    config.DEFAULT_THEME,
                ),
            )
        self.conn.commit()

        if not license_table_existed and self.count_users() > 0:
            # This DB already had users the moment the license table was
            # first added - it predates licensing entirely, so grandfather
            # it into Lifetime rather than locking out a live install.
            from app import licensing
            licensing.grandfather_existing_install(self)

    def _table_exists(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None

    def _ensure_column(self, table: str, column: str, declaration: str):
        existing = [row[1] for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    # ------------------------------------------------------------------ #
    # License
    # ------------------------------------------------------------------ #
    def get_license_row(self) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM license WHERE id = 1").fetchone()

    def save_license_row(self, tier, activated_at, expires_at, last_seen, machine_id, signature):
        self.conn.execute(
            """INSERT INTO license (id, tier, activated_at, expires_at, last_seen, machine_id, signature)
               VALUES (1, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   tier = excluded.tier, activated_at = excluded.activated_at,
                   expires_at = excluded.expires_at, last_seen = excluded.last_seen,
                   machine_id = excluded.machine_id, signature = excluded.signature""",
            (tier, activated_at, expires_at, last_seen, machine_id, signature),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Users / Auth
    # ------------------------------------------------------------------ #
    def count_users(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def username_exists(self, username: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM users WHERE lower(username) = lower(?)", (username,)
        ).fetchone()
        return row is not None

    def email_exists(self, email: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM users WHERE lower(email) = lower(?)", (email,)
        ).fetchone()
        return row is not None

    def create_user(self, full_name, username, email, phone, password, role) -> int:
        password_hash, salt = hash_password(password)
        cur = self.conn.execute(
            """INSERT INTO users (full_name, username, email, phone, password_hash,
               password_salt, role, is_active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                full_name.strip(),
                username.strip(),
                email.strip(),
                phone.strip() if phone else None,
                password_hash,
                salt,
                role,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_user_by_username(self, username: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM users WHERE lower(username) = lower(?)", (username,)
        ).fetchone()

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def list_users(self):
        return self.conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        ).fetchall()

    def update_user_role(self, user_id: int, role: str):
        self.conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        self.conn.commit()

    def set_user_active(self, user_id: int, is_active: bool):
        self.conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id)
        )
        self.conn.commit()

    def delete_user(self, user_id: int):
        self.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.conn.commit()

    def update_password(self, user_id: int, new_password: str):
        password_hash, salt = hash_password(new_password)
        self.conn.execute(
            "UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
            (password_hash, salt, user_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #
    def get_settings(self) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()

    def update_settings(self, **fields):
        if not fields:
            return
        columns = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values())
        self.conn.execute(f"UPDATE settings SET {columns} WHERE id = 1", values)
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Items
    # ------------------------------------------------------------------ #
    def add_item(self, name: str, price: float, category: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO items (name, price, category, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            (name.strip(), price, category.strip() if category else None,
             datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_item(self, item_id: int, name: str, price: float, category: str):
        self.conn.execute(
            "UPDATE items SET name = ?, price = ?, category = ? WHERE id = ?",
            (name.strip(), price, category.strip() if category else None, item_id),
        )
        self.conn.commit()

    def set_item_active(self, item_id: int, is_active: bool):
        self.conn.execute(
            "UPDATE items SET is_active = ? WHERE id = ?", (1 if is_active else 0, item_id)
        )
        self.conn.commit()

    def delete_item(self, item_id: int):
        self.conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self.conn.commit()

    def get_items(self, active_only: bool = False, search: str = ""):
        query = "SELECT * FROM items"
        clauses = []
        params = []
        if active_only:
            clauses.append("is_active = 1")
        if search:
            clauses.append("name LIKE ?")
            params.append(f"%{search}%")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY name ASC"
        return self.conn.execute(query, params).fetchall()

    def count_items(self, active_only: bool = True) -> int:
        if active_only:
            return self.conn.execute(
                "SELECT COUNT(*) FROM items WHERE is_active = 1"
            ).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    # ------------------------------------------------------------------ #
    # Bills
    # ------------------------------------------------------------------ #
    def _next_bill_no(self) -> str:
        today_str = date.today().strftime("%Y%m%d")
        row = self.conn.execute(
            "SELECT COUNT(*) FROM bills WHERE bill_no LIKE ?", (f"INV-{today_str}-%",)
        ).fetchone()
        seq = row[0] + 1
        return f"INV-{today_str}-{seq:04d}"

    def create_bill(self, cashier_id: Optional[int], cart_items: list[dict],
                     customer_name: str = "", walkin_no: str = "",
                     subtotal: Optional[float] = None, discount_type: Optional[str] = None,
                     discount_value: float = 0.0, discount_amount: float = 0.0,
                     net_total: Optional[float] = None, payment_method: str = "Cash",
                     amount_received: Optional[float] = None, change_due: Optional[float] = None,
                     transaction_ref: Optional[str] = None, bank_info: Optional[str] = None) -> sqlite3.Row:
        bill_no = self._next_bill_no()
        computed_subtotal = sum(i["total"] for i in cart_items)
        if subtotal is None:
            subtotal = computed_subtotal
        if net_total is None:
            net_total = subtotal - discount_amount
        items_count = sum(i["quantity"] for i in cart_items)
        created_at = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.execute(
            """INSERT INTO bills (bill_no, cashier_id, customer_name, walkin_no,
               grand_total, items_count, created_at, subtotal, discount_type,
               discount_value, discount_amount, payment_method, amount_received,
               change_due, transaction_ref, bank_info)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bill_no, cashier_id, customer_name.strip() if customer_name else None,
             walkin_no.strip() if walkin_no else None, net_total, items_count, created_at,
             subtotal, discount_type, discount_value, discount_amount, payment_method,
             amount_received, change_due, transaction_ref.strip() if transaction_ref else None,
             bank_info.strip() if bank_info else None),
        )
        bill_id = cur.lastrowid
        for entry in cart_items:
            self.conn.execute(
                """INSERT INTO bill_items (bill_id, item_name, price, quantity, total)
                   VALUES (?, ?, ?, ?, ?)""",
                (bill_id, entry["name"], entry["price"], entry["quantity"], entry["total"]),
            )
        self.conn.commit()
        return self.get_bill(bill_id)

    def get_bill(self, bill_id: int) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()

    def get_bill_items(self, bill_id: int):
        return self.conn.execute(
            "SELECT * FROM bill_items WHERE bill_id = ? ORDER BY id ASC", (bill_id,)
        ).fetchall()

    def get_bills_by_date(self, day: date):
        day_str = day.isoformat()
        return self.conn.execute(
            "SELECT * FROM bills WHERE substr(created_at, 1, 10) = ? ORDER BY created_at DESC",
            (day_str,),
        ).fetchall()

    def get_bills_between(self, start: date, end: date):
        return self.conn.execute(
            """SELECT * FROM bills WHERE substr(created_at, 1, 10) BETWEEN ? AND ?
               ORDER BY created_at DESC""",
            (start.isoformat(), end.isoformat()),
        ).fetchall()

    def get_item_sales_between(self, start: date, end: date):
        """Every active item in the catalog, with how many units it sold
        and the revenue it earned in the given date range - 0/0 for an item
        that had no sales at all that range, so every item in the software
        shows up, not just the ones that sold. Used by the Reports page's
        item-wise breakdown."""
        return self.conn.execute(
            """
            SELECT i.name AS item_name,
                   COALESCE(s.qty_sold, 0) AS qty_sold,
                   COALESCE(s.revenue, 0) AS revenue
            FROM items i
            LEFT JOIN (
                SELECT bi.item_name AS item_name,
                       SUM(bi.quantity) AS qty_sold,
                       SUM(bi.total) AS revenue
                FROM bill_items bi
                JOIN bills b ON b.id = bi.bill_id
                WHERE substr(b.created_at, 1, 10) BETWEEN ? AND ?
                GROUP BY bi.item_name
            ) s ON s.item_name = i.name
            WHERE i.is_active = 1
            ORDER BY qty_sold DESC, i.name ASC
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

    def update_bill_customer(self, bill_id: int, customer_name: str, walkin_no: str):
        self.conn.execute(
            "UPDATE bills SET customer_name = ?, walkin_no = ? WHERE id = ?",
            (customer_name.strip() if customer_name else None,
             walkin_no.strip() if walkin_no else None, bill_id),
        )
        self.conn.commit()

    def delete_bill(self, bill_id: int):
        self.conn.execute("DELETE FROM bills WHERE id = ?", (bill_id,))
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Dashboard aggregates
    # ------------------------------------------------------------------ #
    def get_dashboard_stats(self) -> dict:
        today_str = date.today().isoformat()
        total_items = self.count_items(active_only=True)
        daily_row = self.conn.execute(
            """SELECT COUNT(*) AS bill_count, COALESCE(SUM(grand_total), 0) AS revenue
               FROM bills WHERE substr(created_at, 1, 10) = ?""",
            (today_str,),
        ).fetchone()
        total_row = self.conn.execute(
            "SELECT COALESCE(SUM(grand_total), 0) AS revenue FROM bills"
        ).fetchone()
        return {
            "total_items": total_items,
            "daily_revenue": daily_row["revenue"],
            "daily_bills": daily_row["bill_count"],
            "total_revenue": total_row["revenue"],
        }

    def close(self):
        self.conn.close()
