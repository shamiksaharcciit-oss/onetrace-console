"""Kept as a test: the console shows the SDK's own text once, as it is,
because the SDK's escaping covers everything the console's own escaping (the viewer's `display`)
did, and is one-to-one. An SDK that narrowed its class, or stopped doubling a backslash, fails here
before a record could draw a line of the Diff page.

Measured over every code point, U+0000 to U+10FFFF, as canary's report did (2,123 escaped by
`display`; 2,285 by the SDK, 163 of them format characters `display` leaves as they are).
"""
from __future__ import annotations

from onetrace.escaping import ESCAPED_RANGES, escaped
from onetrace_console.viewer.page import display


def _escaped_by(fn) -> set[int]:
    out = set()
    for cp in range(0x110000):
        ch = chr(cp)
        try:
            if fn(ch) != ch:
                out.add(cp)
        except (UnicodeEncodeError, ValueError):
            out.add(cp)
    return out


def test_the_sdk_escapes_everything_the_console_did(examined):
    console, sdk = _escaped_by(display), _escaped_by(escaped)
    examined(0x110000, "code points compared")
    missing = sorted(console - sdk)
    assert not missing, ("the SDK leaves these as they are and the console escaped them: "
                         + ", ".join(f"U+{cp:04X}" for cp in missing[:20]))
    assert len(sdk) >= 2285, f"the SDK's class narrowed: {len(sdk)} code points"


def test_the_sdks_escaping_is_one_to_one():
    """A backslash is doubled first, so a raw control and its written-out escape never print
    alike -- the property that let the console retire its own collision check."""
    assert escaped("\\") == "\\\\"
    for a, b in (("\r", "\\u000d"), ("a\r", "a\\u000d"), ("‮", "\\u202e"), ("\x00", "\\u0000")):
        assert escaped(a) != escaped(b), (a, b)
    assert ESCAPED_RANGES[0] == (0x0000, 0x001F)
