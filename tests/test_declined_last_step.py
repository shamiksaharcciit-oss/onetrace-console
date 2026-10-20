"""A run declined at its last declared step is listed as stopped at a step.

A step's own rule that declines the run's last recorded attempt stops the run, whether or not any
declared step is left after it. Needs attention first lists such a run under "Stopped at a step"
when the declining step is the last declared one too, as the demo's pump run asking for a slot
outside the maintenance window is. "What the evidence establishes" keeps counting rung 3 as each
run's own page reads it, so its row still counts each run once.
"""
from __future__ import annotations

import re
from html import unescape

from tests.test_compare_page import demo  # noqa: F401

LAST = "p5-35-pump-outside-window-declined"


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _runs(store):
    return {r.run_id: r for r in store.runs()}


def stopped_problems(store) -> list[str]:
    """Every run whose last recorded attempt was declined is listed as stopped at a step."""
    from onetrace_console.overview import declined, needs_attention
    listed = {r.key for kind, r in needs_attention(store) if kind == "stopped-at-a-step"}
    return [f"{r.run_id} declined at {declined(r)['stage']} but not listed as stopped"
            for r in store.runs() if declined(r) is not None and r.key not in listed]


def test_the_last_step_decline_is_listed_as_stopped(demo, examined):  # noqa: F811
    from onetrace_console.overview import attention_kind, declined
    _folder, store = demo
    run = _runs(store)[LAST]
    examined(1, "run")
    assert declined(run) == {"stage": "work_order", "reason": declined(run)["reason"], "left": []}
    assert attention_kind(run, store) == "stopped-at-a-step"


def test_every_declined_run_is_listed_as_stopped(demo, examined):  # noqa: F811
    from onetrace_console.overview import declined
    _folder, store = demo
    found = [r for r in store.runs() if declined(r) is not None]
    examined(len(found), "declined runs")
    assert len(found) >= 2 and any(declined(r)["left"] for r in found), "an early stop held too"
    assert stopped_problems(store) == []


def test_the_needs_attention_list_holds_it_declined(demo, examined):  # noqa: F811
    folder, _store = demo
    page = (folder / "store" / "pages" / "executions-needs-attention.html").read_text(encoding="utf-8")
    examined(1, "needs-attention list")
    row = next((r for r in re.findall(r"<tr[^>]*>.*?</tr>", page, re.S) if LAST in r), None)
    assert row is not None, "not listed"
    assert "Declined at work_order" in _text(row), _text(row)


def test_the_evidence_row_still_counts_each_run_once(demo, examined):  # noqa: F811
    from onetrace_console.home import tallies
    _folder, store = demo
    by = {t.slug: t for t in tallies(store)}
    examined(1, "evidence row")
    parts = ("nothing-missing", "missing-a-declared-stage", "stopped-at-a-step", "missing-not-established")
    assert sum(by[s].count for s in parts) == len(store.runs())


def test_sabotage_the_old_rule_misses_the_last_step_decline(demo, examined, monkeypatch):  # noqa: F811
    from onetrace_console import overview
    _folder, store = demo
    examined(1, "planted rule")
    monkeypatch.setattr(overview, "stopped_at_a_step", lambda run: run.nothing_missing == overview.NOT_REACHED)
    assert any(LAST in p for p in stopped_problems(store))
