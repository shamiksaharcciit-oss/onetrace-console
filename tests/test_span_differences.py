"""At a comparison's first difference: the two runs' spans there, side by side, their differences ranked.

1. A planted pair, a retry and a status error on one side: that pair is ranked first, said as the
   app's facts ("candidate: 2 retries on price_lookup, status error, 3.1 s against 0.4 s"), ahead of
   a span three times slower and a span on one side only.
2. Sabotage: ranked by time alone, the slow span comes first.
3. Two trees that differ in none of these say so; a run with no tree says which, and what is missing.
4. On recorded runs with their exports given, the comparison page carries the section, and no
   verdict on it changes.
"""
from __future__ import annotations

import html
import json
import re

import pytest

from onetrace_console import span_tree
from tests.test_span_tree import ROOT, S0, T, _export, _span

TOOL_B, MODEL_B, ONLY = "7" * 16, "9" * 16, "a" * 16


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _sp(sid, name, at_ms, took_ms, base, parent=ROOT, attrs=(), status=None, events=()):
    """A planted span `at_ms` after `base` (ns), taking `took_ms`."""
    sp = _span(sid, name, 0, 0, parent, attrs=attrs, status=status, events=[(n, 0) for n, _ in events])
    sp["startTimeUnixNano"], sp["endTimeUnixNano"] = str(base + at_ms * 10**6), str(base + (at_ms + took_ms) * 10**6)
    for e, (_n, t) in zip(sp.get("events", []), events):
        e["timeUnixNano"] = str(base + t * 10**6)
    return sp


def planted(side: str, base: int = S0, at=lambda ms: ms) -> list:
    """The baseline's or candidate's spans; `at` places each child's start (the recorded fixture puts
    them all at the step's start, inside its recorded times)."""
    root = _span(ROOT, "handle request", 0, 0)
    root["startTimeUnixNano"], root["endTimeUnixNano"] = str(base - 10**6), str(base + 4000 * 10**6)
    model = [("gen_ai.request.model", "example-model")]
    tool = [("gen_ai.tool.name", "price_lookup")]
    if side == "baseline":
        return [root, _sp(MODEL_B, "chat", at(10), 100, base, attrs=model),
                _sp(TOOL_B, "execute_tool", at(200), 400, base, attrs=tool)]
    return [root, _sp(MODEL_B, "chat", at(10), 300, base, attrs=model),
            _sp(TOOL_B, "execute_tool", at(400), 3100, base, attrs=tool,
                status={"code": 2, "message": "price service unavailable"},
                events=[("retry", at(1000)), ("retry", at(2000))]),
            _sp(ONLY, "audit log", at(3600), 100, base)]


def _tree(spans):
    return span_tree.step_tree(span_tree.read_export(_export(*spans)), {"trace": {"trace_id": T, "span_id": ROOT}})


def _baseline():
    return _tree(planted("baseline"))


def _candidate():
    return _tree(planted("candidate"))


def test_a_retry_and_a_status_error_on_one_side_are_ranked_first(examined):
    ranked = span_tree.differences((_baseline(), _candidate()))
    examined(len(ranked), "differences")
    assert ranked[0][2] == "candidate: 2 retries on price_lookup, status error, 3.10 s against 400.0 ms"
    assert [span_tree.RANK[r] for r, _s, _l in ranked] == ["status", "only", "time"]
    assert ranked[1][2] == "candidate: audit log, 100.0 ms, not in the baseline's spans"
    assert ranked[2][2] == "candidate: chat, 300.0 ms against 100.0 ms"


def test_sabotage_ranked_by_time_alone_the_slow_span_comes_first(monkeypatch, examined):
    monkeypatch.setattr(span_tree, "RANK", ("time", "status", "retries", "model", "only", "tokens"))
    ranked = span_tree.differences((_baseline(), _candidate()))
    examined(len(ranked), "differences")
    assert not ranked[0][2].startswith("candidate: 2 retries on price_lookup")


def test_two_trees_that_differ_in_none_of_these_say_so(examined):
    page = span_tree.difference_section((_baseline(), _baseline()))
    examined(1, "pair")
    assert span_tree.DIFF_NONE in _text(page) and 'data-span-side' in page
    for line in span_tree.NON_CLAIMS:
        assert line in _text(page)


@pytest.mark.parametrize("word", ["none", "unjoined", "unreadable", "absent", "no-step"])
def test_a_run_with_no_tree_says_which_and_what_is_missing(word, examined):
    page = span_tree.difference_section((_baseline(), word))
    examined(1, "pair")
    if word in ("none", "absent", "no-step"):
        assert f'data-span-no-tree="{word}"' in page
        assert span_tree.NO_TREE_WORDS[word] in _text(page)
    else:
        assert f'data-span-no-tree="{word}"' in page and "data-span-ranked" not in page
    assert span_tree.difference_section(("absent", "none")) == ""


@pytest.fixture(scope="module")
def compared(tmp_path_factory):
    """Two runs recorded inside the app's span, with their exports given: the candidate's planted."""
    import os
    from onetrace_console import beside
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.store import Store
    from tests.model_call_runs import record_run
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    folder = tmp_path_factory.mktemp("span-diffs")
    before = os.environ.get("TRACEPARENT")
    os.environ["TRACEPARENT"] = f"00-{T}-{ROOT}-01"
    try:
        made = [record_run(folder / "a", "sd-a"), record_run(folder / "b", "sd-b", output="sha256:" + "e" * 64)]
    finally:
        os.environ.pop("TRACEPARENT") if before is None else os.environ.__setitem__("TRACEPARENT", before)
    store = Store(folder / "store")
    runs = [run_and_record(_deliver(m, store, outputs=True), store, ran_at=FIXED_RAN_AT) for m in made]
    for m, run, side in zip(made, runs, ("baseline", "candidate")):
        receipt = json.loads(next((m / "receipts").glob("*.json")).read_bytes())
        s0 = span_tree._ns(receipt["time"]["started"])
        beside.keep(store, run.key, trace=_export(*planted(side, s0, at=lambda ms: 0)), trace_source=beside.GIVEN)
    return store, compare(runs[0], runs[1], store, ran_at=FIXED_RAN_AT)


def _diff_page(store, c) -> str:
    from onetrace_console.frame import rendering
    from onetrace_console.render import render_diff
    with rendering(onedoor=False, sign_in=False, public=True):
        return render_diff(c, store, generated_at="2026-11-02T06:00:00+00:00")


def test_the_comparison_page_carries_the_section_and_nothing_else_changes(compared, monkeypatch, examined):
    store, c = compared
    page = _diff_page(store, c)
    section = re.search(r'<section data-section="span-differences".*?</section>', page, re.S).group(0)
    examined(1, "comparison page")
    first = re.search(r'<li data-rank="([a-z]+)">([^<]*)</li>', section)
    assert first.group(1) == "status" and first.group(2).startswith("candidate: 2 retries on price_lookup, status error")
    #: The page without the spans is the same page, less the section: no verdict, line or count moves.
    monkeypatch.setattr(span_tree, "found_at", lambda *a, **k: "absent")
    assert _diff_page(store, c) == page.replace(section, "")
