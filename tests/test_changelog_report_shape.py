"""0.8.0's CHANGELOG says that the three errors about a report of the wrong shape now say what to do, and those
three messages say it: write the report again with the pinned SDK."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEAD = "**Three errors about a report of the wrong shape say what to do.**"


def _entry(version: str) -> str:
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.index(f"\n## [{version}]")
    return text[start : text.index("\n## [", start + 1)]


def test_the_0_8_0_entry_says_the_three_errors_now_say_what_to_do(examined):
    entry = _entry("0.8.0")
    lines = [line for line in entry.splitlines() if LEAD in line]
    assert len(lines) == 1, lines
    assert "write the report again with the pinned SDK" in lines[0]
    assert entry.index(LEAD) < entry.index("\n### Security"), "among the changes, before the Security heading"
    examined(1, "the entry's line")


def test_the_three_messages_say_to_write_the_report_again_with_the_pinned_sdk(examined):
    raw = (REPO / "src" / "onetrace_console" / "viewer" / "verbs.py").read_text(encoding="utf-8")
    source = re.sub(r'"\s*\n\s*f?"', "", raw)  # a message's string pieces, joined
    said = re.findall(r"(?i)write (?:it|the report) again with (?:that SDK|the pinned SDK)", source)
    assert len(said) == 3, said
    examined(len(said), "messages")
