"""In the console, rung 1 is set only by the console's own check.

The "records agree" rung reads yes **only from the console's own run of the pinned verifier
over the stored bundle** (`--require-artifacts`) returning PASS. A kept or supplied report
(`render --report`) is shown as a report, and never sets the rung.

The viewer now makes every caller say whose check it holds (`build_model(..., own_check=...)`,
no default). The console's stored report is its own: `checks.run_and_record` runs the pinned
verifier over the stored bundle at ingest, and nothing else writes a run's `check_report`. The
second test holds that premise in place, since `own_check=True` is only true while it is.

The `--require-artifacts` half waits on blocker B4: the pinned verifier (0.1.0) does not check
artifacts, and the one that does (0.1.1) needs the viewer taught its new row first.
"""
from __future__ import annotations

import re
from pathlib import Path

from onetrace_console.pages import CASE, render_execution
from tests.test_pages import GENERATED_AT, checked  # noqa: F401  (fixture)

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"


def _rungs(case: str) -> dict[str, str]:
    ladder = re.search(r'<section data-section="ladder">(.*?)</section>', case, re.S).group(1)
    return dict(re.findall(r'<tr data-rung="([^"]+)" data-state="([^"]+)">', ladder))


def test_a_stored_runs_rung_one_is_the_consoles_own_check(checked, store):  # noqa: F811
    """Its own check, so never the supplied-report sentence. Run without
    `--require-artifacts` (the pinned verifier has no such flag, B4), so not a yes either:
    the confirmation review held rung 1 to a check with the output files required. With
    the flag it reads yes; see tests/test_review_fixes.py."""
    case = render_execution(checked, store, generated_at=GENERATED_AT).pages[CASE]
    assert _rungs(case)["records-agree"] == "not-checked"
    assert "did not require the run&#x27;s output files" in case
    assert "was given the check" not in case, "the supplied-report sentence"


def test_only_the_consoles_own_check_writes_a_runs_stored_report():
    """`own_check=True` rests on this: every `check_report=` in the source is `run_and_record`'s."""
    writers = [(p.relative_to(SRC).as_posix(), n) for p in sorted(SRC.rglob("*.py"))
               for n, text in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
               if re.search(r"\bcheck_report\s*=(?!=)", text)]
    assert [w for w, _ in writers] == ["checks.py"], writers
    checks = (SRC / "checks.py").read_text(encoding="utf-8")
    body = checks[checks.index("def run_and_record("):]
    body = body[:body.index("\ndef ", 1)]
    assert "check_report=report_key" in body, "the one writer is run_and_record, over its own check"
