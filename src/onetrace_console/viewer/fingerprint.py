"""This file's fingerprint, printed in its own footer (019 §1.3, §6(d)).

WHY NOT SIMPLY THE FILE'S SHA-256
---------------------------------
019 §1.3: "The file's own SHA-256 is printed in its footer." Read literally that cannot be
done: a file that contains the hash of its own bytes would have to be a fixed point of
SHA-256. The record format meets the same wall and forbids the attempt outright
(`canonicalize.py` rule 7; rejection vector R09: *a record may not contain the proof of its
own final state*).

So the page carries a **slot**: exactly one `<!--fingerprint-->` + 64 hex characters +
`<!--/fingerprint-->`. The fingerprint is the SHA-256 of the whole file with those 64
characters set to `0`. Every other byte of the file is covered, including everything after
the slot. The reading is declared to core as a question in the milestone note, not settled
here.

A reader checks it without us: the page prints a Python standard-library one-liner
(`STANDALONE_CHECK`) that does exactly what `check()` does. A test runs that one-liner as a
reader would, from the text on the page.

This is one of two modules in `viewer/` that imports `hashlib`; the other hashes the
vendored design spec. Neither hashes a record.
"""
from __future__ import annotations

import hashlib
import re

from onetrace_console.viewer.slot import CLOSE, OPEN, SLOT, STANDALONE_CHECK, ZEROS  # noqa: F401

_FILLED = re.compile(re.escape(OPEN) + r"([0-9a-f]{64})" + re.escape(CLOSE))


class FingerprintError(ValueError):
    """The page does not carry exactly one fingerprint slot."""


def seal(html: str) -> str:
    """Fill the page's one empty slot with the fingerprint of the page as it stands."""
    if html.count(OPEN) != 1 or html.count(CLOSE) != 1 or html.count(SLOT) != 1:
        raise FingerprintError("a page must carry exactly one empty fingerprint slot to seal")
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    return html.replace(SLOT, OPEN + digest + CLOSE)


def check(data: bytes) -> tuple[bool, str]:
    """(does the fingerprint match, why). Reads bytes; never repairs them."""
    text = data.decode("utf-8")
    found = _FILLED.findall(text)
    if len(found) != 1 or text.count(OPEN) != 1 or text.count(CLOSE) != 1:
        return False, f"expected exactly one fingerprint; found {len(found)}"
    zeroed = data.replace((OPEN + found[0]).encode(), (OPEN + ZEROS).encode())
    got = hashlib.sha256(zeroed).hexdigest()
    return (got == found[0],
            "matches" if got == found[0] else f"printed {found[0]}, computed {got}")
