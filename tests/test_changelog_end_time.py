"""0.8.0's CHANGELOG says, among its fixes, that a sign-in just after `admin sessions end` is no longer signed out on a
coarse clock (`accounts._write_time`)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEAD = "**A sign-in just after ending an account's sessions stays signed in.**"


def test_the_0_8_0_entry_says_a_sign_in_after_the_end_stays(examined):
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.index("\n## [0.8.0]")
    entry = text[start : text.index("\n## [", start + 1)]
    lines = [line for line in entry.splitlines() if LEAD in line]
    assert len(lines) == 1, lines
    assert "admin sessions end" in lines[0] and "Windows" in lines[0]
    assert entry.index(LEAD) < entry.index("\n### Security"), "among the fixes, before the Security heading"
    examined(1, "the entry's line")
