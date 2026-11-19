"""0.9's known gaps for the audit log: pruning, its retention setting and the head
location's change as an event are not built yet, so 0.9.0's entry lists them where a reader
of the release looks. A gap is not an entry: its line has no bold lead."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRUNE_GAP = (
    "The audit log has no `audit prune` and no `audit.keep_days` yet: it is kept whole, every segment, until a "
    "release builds them."
)
HEAD_GAP = "A change of `audit.head_location` is not recorded as an event of its own yet."


def _unreleased() -> str:
    """The 0.9.0 section: `## [Unreleased]` until its version was set."""
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.index("## [0.9.0]")
    return text[start : text.index("\n## [", start + 1)]


def test_the_unreleased_entry_lists_the_audit_log_s_gaps(examined):
    parts = _unreleased().split("\n### Known gaps\n", 1)
    assert len(parts) == 2, "no Known gaps under 0.9.0's entry"
    lines = [" ".join(ln.split()) for ln in parts[1].splitlines() if ln.startswith("- ")]
    for gap in (PRUNE_GAP, HEAD_GAP):
        assert f"- {gap}" in lines, (gap, lines)
    assert not any(re.match(r"- \*\*", ln) for ln in lines), "a gap has no bold lead"
    examined(2, "gaps")
