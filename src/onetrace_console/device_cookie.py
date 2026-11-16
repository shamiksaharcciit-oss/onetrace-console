"""The known-browser cookie the sign-in limiter reads: `onetrace_device`.

A right password sets it: the account name, a random id and an expiry, with an HMAC-SHA256 tag under
a key kept beside the accounts (`<accounts>/.device_key`, made at first start, mode 0600). It grants
nothing on its own: only the sign-in limiter reads it, and its value is never logged. Rotating the
key (`onetrace-console admin device-key rotate`) ends every device cookie; a lost key does the same,
and an attempt with no valid cookie counts as any other does, never as an open door.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

COOKIE = "onetrace_device"
KEY_NAME = ".device_key"
#: 90 days.
LIFETIME_SECONDS = 90 * 86400


def _write_key(accounts: Path) -> None:
    accounts.mkdir(parents=True, exist_ok=True)
    path = accounts / KEY_NAME
    tmp = accounts / f"{KEY_NAME}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (secrets.token_hex(32) + "\n").encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def ensure_key(accounts: Path) -> None:
    """Make the device key where there is none; leave one that exists as it is."""
    if not (Path(accounts) / KEY_NAME).is_file():
        _write_key(Path(accounts))


def rotate_key(accounts: Path) -> None:
    """A new device key: every device cookie made under the old one counts as none."""
    _write_key(Path(accounts))


def read_key(accounts: Path) -> bytes | None:
    """The device key, or None where it can't be read (then no cookie is valid)."""
    try:
        text = (Path(accounts) / KEY_NAME).read_text(encoding="ascii").strip()
        return bytes.fromhex(text) if len(text) >= 64 else None
    except (OSError, ValueError):
        return None


def _tag(key: bytes, account: str, ident: str, expires: int) -> str:
    return hmac.new(key, f"{account}\n{ident}\n{expires}".encode(), hashlib.sha256).hexdigest()


def make(key: bytes, account: str, *, now: float | None = None) -> str:
    """A new cookie value for `account`: `account.id.expires.tag`."""
    now = time.time() if now is None else now
    ident = secrets.token_hex(16)
    expires = int(now) + LIFETIME_SECONDS
    return f"{account}.{ident}.{expires}.{_tag(key, account, ident, expires)}"


def valid_for(key: bytes | None, value: str | None, account: str, *, now: float | None = None) -> str | None:
    """The device's id where `value` is a cookie made under `key` for `account` and not expired; else
    None. A bad tag, another account's cookie or an expired one counts as no cookie."""
    if not key or not value or not account:
        return None
    parts = value.split(".")
    if len(parts) != 4:
        return None
    name, ident, expires, tag = parts
    if name != account or not expires.isdigit():
        return None
    if not hmac.compare_digest(tag.encode("ascii", "replace"), _tag(key, name, ident, int(expires)).encode("ascii")):
        return None
    if int(expires) <= (time.time() if now is None else now):
        return None
    return f"{name}.{ident}"
