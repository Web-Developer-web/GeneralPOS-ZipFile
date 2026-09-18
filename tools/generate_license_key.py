"""Vendor-only tool: generate a Lifetime activation key for a customer's
Machine ID.

Run this on YOUR machine after a customer sends you the Machine ID shown
on their Lifetime signup screen, license-locked screen, or Settings ->
License tab. Never ship this script (or the app/licensing.py secret it
relies on) to a customer - anyone holding both can mint their own keys.

Usage:
    python tools/generate_license_key.py <MACHINE-ID>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.licensing import generate_lifetime_key, format_id, _normalize_key  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("Usage: python tools/generate_license_key.py <MACHINE-ID>")
        sys.exit(1)

    machine_id = _normalize_key(sys.argv[1])
    key = generate_lifetime_key(machine_id)
    print(f"Machine ID : {format_id(machine_id)}")
    print(f"License Key: {key}")


if __name__ == "__main__":
    main()
