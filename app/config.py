"""Application-wide constants and paths."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "hotelpos.db"

APP_NAME = "Hotel POS"
ORG_NAME = "HotelPOS"
APP_VERSION = "1.0.0"

DEFAULT_HOTEL_NAME = "My Hotel & Restaurant"
DEFAULT_ADDRESS = "Main Boulevard, Lahore, Pakistan"
DEFAULT_PHONE = "0300-0000000"
DEFAULT_CURRENCY = "Rs."
DEFAULT_FOOTER_MESSAGE = "Thank you for dining with us! Please visit again."
DEFAULT_THEME = "light"

ROLE_ADMIN = "Admin"
ROLE_CASHIER = "Cashier"
ROLES = [ROLE_ADMIN, ROLE_CASHIER]

PASSWORD_MIN_LENGTH = 6
