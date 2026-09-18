"""Remember me" credential storage for the auth screen.

Persists via QSettings (Windows registry / per-platform ini) under the app's
own organization/application name. The password is base64-obfuscated before
storage - this is a local, single-user desktop convenience (skip retyping
on next launch), not a security boundary, so it deliberately doesn't pull in
an extra crypto dependency for it.
"""
import base64

from PySide6.QtCore import QSettings

_ORG_KEY = "auth/remember"
_USER_KEY = "auth/username"
_PASS_KEY = "auth/password"


def _obfuscate(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _deobfuscate(token: str) -> str:
    try:
        return base64.b64decode(token.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def save_credentials(username: str, password: str) -> None:
    settings = QSettings()
    settings.setValue(_ORG_KEY, True)
    settings.setValue(_USER_KEY, username)
    settings.setValue(_PASS_KEY, _obfuscate(password))


def load_credentials() -> tuple[str, str] | None:
    settings = QSettings()
    if not settings.value(_ORG_KEY, False, type=bool):
        return None
    username = settings.value(_USER_KEY, "", type=str)
    password = _deobfuscate(settings.value(_PASS_KEY, "", type=str))
    if not username:
        return None
    return username, password


def clear_credentials() -> None:
    settings = QSettings()
    for key in (_ORG_KEY, _USER_KEY, _PASS_KEY):
        settings.remove(key)
