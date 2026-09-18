"""Password hashing utilities (PBKDF2-HMAC-SHA256, stdlib only)."""
import hashlib
import os
import re

_ITERATIONS = 200_000

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Pakistani mobile format: 03XXXXXXXXX (11 digits) - optional field, lenient check
PHONE_RE = re.compile(r"^0\d{9,10}$")


def hash_password(password: str) -> tuple[str, str]:
    """Return (password_hash_hex, salt_hex)."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return digest.hex() == password_hash


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))


def is_valid_phone(phone: str) -> bool:
    if not phone:
        return True
    return bool(PHONE_RE.match(phone.strip()))
