"""Offline trial/license enforcement.

No backend server exists for this desktop app, so the license record is
kept in three independent local stores - the SQLite DB, a file under
%LOCALAPPDATA%, and (on Windows) the registry - each one HMAC-signed so a
hand-edited value fails verification and is treated as absent. On every
check the stores are reconciled to whichever record is *most restrictive*
(soonest expiry, lowest tier) and the others are re-synced to match, so
deleting or rolling back any single store alone does not reset a trial.
A "last_seen" date travels with the record too, so turning the system
clock backward can't rewind the countdown.

This raises the bar past casual tampering; it cannot be made bulletproof
against someone willing to read and patch the Python source directly,
which would need a server-side check to fully close.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

# Embedded signing secret. Anyone who can read this source (or decompile a
# packaged build) can forge trial records or mint their own Lifetime keys -
# an inherent limit of purely offline activation. It still stops the
# realistic threat here: a non-technical user deleting a file or row to
# reset their trial.
_SECRET = b"HotelPOS-v1-8f3a1c9d2e7b4059a6d1c8e3f0b7a2d4-AbdulWahidKhan"

TIER_TRIAL_1WEEK = "trial_1week"
TIER_TRIAL_15DAY = "trial_15day"
TIER_TRIAL_1MONTH = "trial_1month"
TIER_LIFETIME = "lifetime"

TRIAL_DAYS = {
    TIER_TRIAL_1WEEK: 7,
    TIER_TRIAL_15DAY: 15,
    TIER_TRIAL_1MONTH: 30,
}

TIER_LABELS = {
    TIER_TRIAL_1WEEK: "1 Week Trial",
    TIER_TRIAL_15DAY: "15 Day Trial",
    TIER_TRIAL_1MONTH: "1 Month Trial",
    TIER_LIFETIME: "Lifetime",
}

_REG_PATH = r"Software\HotelPOS\License"


# ---------------------------------------------------------------------- #
# Machine identity
# ---------------------------------------------------------------------- #
def get_machine_id() -> str:
    raw = f"{uuid.getnode()}:{platform.node()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()


def format_id(flat: str) -> str:
    """Group a flat hex string into readable dashed 4-char blocks."""
    return "-".join(flat[i:i + 4] for i in range(0, len(flat), 4))


def _normalize_key(key: str) -> str:
    return "".join(ch for ch in key.upper() if ch.isalnum())


# ---------------------------------------------------------------------- #
# Signed token helpers (HMAC integrity, not secrecy - these values aren't
# sensitive, they just must not be silently editable).
# ---------------------------------------------------------------------- #
def _sign_payload(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    mac = hmac.new(_SECRET, raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode() + "." + base64.urlsafe_b64encode(mac).decode()


def _verify_token(token: str) -> dict | None:
    try:
        raw_b64, mac_b64 = token.strip().split(".")
        raw = base64.urlsafe_b64decode(raw_b64.encode())
        mac = base64.urlsafe_b64decode(mac_b64.encode())
        if not hmac.compare_digest(mac, hmac.new(_SECRET, raw, hashlib.sha256).digest()):
            return None
        return json.loads(raw)
    except Exception:
        return None


# ---------------------------------------------------------------------- #
# Store: local file (%LOCALAPPDATA%\HotelPOS\license.dat)
# ---------------------------------------------------------------------- #
def _file_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "HotelPOS"
    base.mkdir(parents=True, exist_ok=True)
    return base / "license.dat"


def _read_file() -> dict | None:
    try:
        return _verify_token(_file_path().read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_file(payload: dict) -> None:
    try:
        _file_path().write_text(_sign_payload(payload), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------- #
# Store: Windows registry (HKCU) - skipped on non-Windows platforms
# ---------------------------------------------------------------------- #
def _read_registry() -> dict | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
            token, _ = winreg.QueryValueEx(key, "data")
        return _verify_token(token)
    except Exception:
        return None


def _write_registry(payload: dict) -> None:
    if sys.platform != "win32":
        return
    try:
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH)
        winreg.SetValueEx(key, "data", 0, winreg.REG_SZ, _sign_payload(payload))
        winreg.CloseKey(key)
    except Exception:
        pass


# ---------------------------------------------------------------------- #
# Store: DB row (fields in plain columns + a signature over them)
# ---------------------------------------------------------------------- #
def _read_db(db) -> dict | None:
    row = db.get_license_row()
    if not row:
        return None
    payload = {
        "tier": row["tier"],
        "activated_at": row["activated_at"],
        "expires_at": row["expires_at"],
        "last_seen": row["last_seen"],
        "machine_id": row["machine_id"],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    mac = hmac.new(_SECRET, raw, hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(base64.urlsafe_b64decode(row["signature"]), mac):
            return None
    except Exception:
        return None
    return payload


def _write_db(db, payload: dict) -> None:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    mac = hmac.new(_SECRET, raw, hashlib.sha256).digest()
    db.save_license_row(
        tier=payload["tier"],
        activated_at=payload["activated_at"],
        expires_at=payload["expires_at"],
        last_seen=payload["last_seen"],
        machine_id=payload["machine_id"],
        signature=base64.urlsafe_b64encode(mac).decode(),
    )


def _write_all(db, payload: dict) -> None:
    _write_db(db, payload)
    _write_file(payload)
    _write_registry(payload)


def _gather_valid_records(db) -> list[dict]:
    records = []
    for record in (_read_db(db), _read_file(), _read_registry()):
        if record is not None:
            records.append(record)
    return records


# ---------------------------------------------------------------------- #
# Public status / activation API
# ---------------------------------------------------------------------- #
def get_status(db) -> dict:
    """Reconcile the three stores and return the current license status:
    {"state": "none"|"active"|"expired"|"invalid", "tier", "days_left", "expires_at"}.

    "none"    - fresh install, no license chosen yet (signup should offer one).
    "invalid" - users already exist but no valid record survived anywhere;
                should not happen post-migration short of deliberate tampering.
    """
    records = _gather_valid_records(db)
    today = date.today()

    if not records:
        if db.count_users() == 0:
            return {"state": "none", "tier": None, "days_left": None, "expires_at": None}
        return {"state": "invalid", "tier": None, "days_left": None, "expires_at": None}

    lifetime_votes = [r for r in records if r["tier"] == TIER_LIFETIME]
    if len(lifetime_votes) == len(records):
        resolved_tier, resolved_expires = TIER_LIFETIME, None
    else:
        # A lone store claiming Lifetime while the others don't agree is
        # treated as tampering, not an upgrade - only activate_lifetime()
        # (which writes all three stores at once) can grant it.
        non_lifetime = [r for r in records if r["tier"] != TIER_LIFETIME]
        source = non_lifetime or records
        chosen = min(source, key=lambda r: r["expires_at"])
        resolved_tier, resolved_expires = chosen["tier"], chosen["expires_at"]

    last_seen_dates = [date.fromisoformat(r["last_seen"]) for r in records]
    effective_today = max([today, *last_seen_dates])

    payload = {
        "tier": resolved_tier,
        "activated_at": min(r["activated_at"] for r in records),
        "expires_at": resolved_expires,
        "last_seen": effective_today.isoformat(),
        "machine_id": get_machine_id(),
    }
    _write_all(db, payload)  # self-heal weaker stores + persist advanced last_seen

    if resolved_tier == TIER_LIFETIME:
        return {"state": "active", "tier": TIER_LIFETIME, "days_left": None, "expires_at": None}

    days_left = (date.fromisoformat(resolved_expires) - effective_today).days
    state = "active" if days_left >= 0 else "expired"
    return {
        "state": state,
        "tier": resolved_tier,
        "days_left": max(days_left, 0),
        "expires_at": resolved_expires,
    }


def activate_trial(db, tier: str) -> dict:
    if tier not in TRIAL_DAYS:
        raise ValueError(f"Unknown trial tier: {tier!r}")
    today = date.today()
    payload = {
        "tier": tier,
        "activated_at": today.isoformat(),
        "expires_at": (today + timedelta(days=TRIAL_DAYS[tier])).isoformat(),
        "last_seen": today.isoformat(),
        "machine_id": get_machine_id(),
    }
    _write_all(db, payload)
    return get_status(db)


def generate_lifetime_key(machine_id: str) -> str:
    """Deterministic Lifetime key for a given Machine ID - the vendor-side
    tools/generate_license_key.py CLI calls this to issue a key once a
    customer has paid."""
    digest = hmac.new(_SECRET, f"LIFETIME:{_normalize_key(machine_id)}".encode(), hashlib.sha256).hexdigest()
    return format_id(digest[:20].upper())


def verify_lifetime_key(machine_id: str, key: str) -> bool:
    return _normalize_key(key) == _normalize_key(generate_lifetime_key(machine_id))


def activate_lifetime(db, key: str) -> tuple[bool, str]:
    machine_id = get_machine_id()
    if not verify_lifetime_key(machine_id, key):
        return False, "This license key is not valid for this computer."
    today = date.today()
    payload = {
        "tier": TIER_LIFETIME,
        "activated_at": today.isoformat(),
        "expires_at": None,
        "last_seen": today.isoformat(),
        "machine_id": machine_id,
    }
    _write_all(db, payload)
    return True, "Lifetime license activated."


def grandfather_existing_install(db) -> None:
    """One-time migration hook: an install that already has users the
    moment the license table is first created predates this feature and
    must not be locked out - grant it Lifetime outright. Called exactly
    once, from Database._init_schema(), only when the license table did
    not exist yet and users already do."""
    today = date.today()
    payload = {
        "tier": TIER_LIFETIME,
        "activated_at": today.isoformat(),
        "expires_at": None,
        "last_seen": today.isoformat(),
        "machine_id": get_machine_id(),
    }
    _write_all(db, payload)
