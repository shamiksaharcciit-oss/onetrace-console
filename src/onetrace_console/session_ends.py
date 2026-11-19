"""The time before which a person's sessions are ended: written by `admin sessions end`, read by a running console at
each request.

The command runs apart from the server, whose sessions are in its memory, so it writes a time, and the server reads
it for the principal of each request and ends every session of that person through its index (`sessions.py`). A
principal is a local account's name or an Entra ID key, `<tenant id>/<object id>`; the file is named by a sha256 of
the principal, so an Entra ID key needs no account file. 0.8.0's rule holds: a session made at or before the time
ends, and a sign-in after it stands.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

#: Under the store's root, beside `accounts/`.
DIRNAME = "sessions_ended"

_GUID = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
#: An Entra ID key, as `oidc_identity.identity` makes it: two GUIDs, lower-cased.
ENTRA_KEY = re.compile(rf"{_GUID}/{_GUID}")
ENTRA_KEY_SAID = "<tenant id>/<object id>, two GUIDs"


def entra_key(text: str) -> str | None:
    """`text` as an Entra ID key, lower-cased as the SCIM join reads an `externalId`, or None where it is not one."""
    key = text.lower()
    return key if ENTRA_KEY.fullmatch(key) else None


def _name(principal: str) -> str:
    return hashlib.sha256(principal.encode("utf-8")).hexdigest()


class EndTimes:
    """The end times, one file per principal under `root` (`<store_root>/sessions_ended/`)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def write(self, principal: str) -> int:
        """End `principal`'s sessions as of now: the time written (time.time_ns()), returned only once the clock reads
        past it (`accounts._write_time`). On a clock whose tick is coarse (Windows'), a sign-in just after the end
        could read the same time and be ended with the sessions before it; waiting for the next tick keeps it after.
        A session made before the end in the same tick is still ended: `<=` stays."""
        from onetrace_console.accounts import _write_time

        self.root.mkdir(parents=True, exist_ok=True)
        return _write_time(self.root / _name(principal))

    def read(self, principal: str) -> int | None:
        """The time last written for `principal`, or None."""
        try:
            return int((self.root / _name(principal)).read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None
