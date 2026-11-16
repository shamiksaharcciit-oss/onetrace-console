"""Every page kind answers within its budget: the measuring tool, run.

`tools/measure_pages.py` starts a local console on the demo store and on the committed token-level fixture
runs, and asks for each page kind 20 times over fresh connections. The budget is a p95 under 500 ms of the
server's time for a full page (a comparison's first build is an action, measured with the actions); a page
kind whose p95 is more than half over it (750 ms) fails here, by name, with its time.
"""

from __future__ import annotations

import json
import subprocess
import sys

BUDGET_MS = 500


def over(result: dict) -> list[str]:
    """Each page kind more than half over its budget, with its p95."""
    return [
        f"{store['store']}: {kind} at {m['last_byte']['p95']} ms (p95), budget {BUDGET_MS} ms"
        for store in result["stores"]
        for kind, m in store["pages"].items()
        if m["last_byte"]["p95"] > BUDGET_MS * 1.5
    ]


def test_every_page_kind_answers_within_its_budget(tmp_path, examined):
    from tests.export_tree import tool
    from tests.test_checks import _require_installed

    _require_installed()
    #: A public export leaves the gate's tools out: there the test skips; here a missing one fails.
    measure = tool("measure_pages.py")
    out = tmp_path / "measured"
    got = subprocess.run(
        [sys.executable, "-B", str(measure), "--out", str(out), "--n", "20", "--only-pages"],
        capture_output=True,
        text=True,
        timeout=1800,
        env={**__import__("os").environ, "TMPDIR": str(tmp_path)},
    )
    assert got.returncode == 0, got.stdout[-2000:] + got.stderr[-2000:]
    result = json.loads((out / "measure.json").read_text(encoding="utf-8"))
    kinds = sum(len(s["pages"]) for s in result["stores"])
    examined(kinds, "page kinds, on the demo store and the fixture runs")
    assert {s["store"] for s in result["stores"]} == {"demo", "fixtures"}
    assert all(m["status"] == [200] for s in result["stores"] for m in s["pages"].values())
    assert over(result) == []


def test_sabotage_a_page_kind_over_its_budget_is_named():
    planted = {"stores": [{"store": "demo", "pages": {"run": {"last_byte": {"p95": 751.0}}}}]}
    assert over(planted) == ["demo: run at 751.0 ms (p95), budget 500 ms"]
