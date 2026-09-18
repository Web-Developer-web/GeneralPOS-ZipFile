"""Daily database backup.

One backup file per calendar day, in a `backups/` folder next to the live
database. Uses SQLite's own online-backup API (`Connection.backup`) rather
than copying the .db file directly - a plain file copy can grab a
half-written page while the app is actively writing to it, while the
backup API produces a consistent snapshot safely while the source
connection stays open and in use.
"""
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import List, Tuple

from app import config

BACKUP_DIR = config.BASE_DIR / "backups"
_PREFIX = config.DB_PATH.stem


def _backup_path_for(day: date) -> Path:
    return BACKUP_DIR / f"{_PREFIX}_{day.isoformat()}.db"


def list_backups() -> List[Tuple[Path, float, int]]:
    """Newest first: (path, modified_timestamp, size_bytes)."""
    if not BACKUP_DIR.exists():
        return []
    files = sorted(BACKUP_DIR.glob(f"{_PREFIX}_*.db"), reverse=True)
    return [(f, f.stat().st_mtime, f.stat().st_size) for f in files]


def has_backup_today() -> bool:
    return _backup_path_for(datetime.now().date()).exists()


def backup_now(source_conn: sqlite3.Connection, day: date = None) -> Path:
    """Snapshot the live database into that day's backup file (today, by
    default) - overwrites the existing file for that day if run again."""
    BACKUP_DIR.mkdir(exist_ok=True)
    day = day or datetime.now().date()
    dest_path = _backup_path_for(day)
    dest_conn = sqlite3.connect(str(dest_path))
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
    return dest_path


def ensure_daily_backup(source_conn: sqlite3.Connection) -> bool:
    """Called once at app startup - silently creates today's backup if one
    doesn't already exist. Never raises: a failed backup should not block
    the app from starting. Returns True if a new backup was taken."""
    if has_backup_today():
        return False
    try:
        backup_now(source_conn)
        return True
    except Exception:
        return False
