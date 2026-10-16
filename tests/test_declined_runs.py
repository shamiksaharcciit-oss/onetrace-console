"""A run that stopped at a step's own rule: the step declined (the SDK's `Refusal`, recorded as the
`refused` class), and the run ended there.

What counts: the run's LAST recorded attempt was declined. A step that declined and was followed by
further receipts did not stop the run. Never a failure: the check ran and a rule refused.

What is kept, derived when the run is checked (`ingest.declined_at`, stored as `declined`): the
step, the reason it recorded, and the declared steps left with no receipt. Held here to the rule
itself, to real SDK records, and to a store from before (re-derived once at start-up). Each check
has its sabotage.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from onetrace_console.ingest import declined_at
from tests.test_checks import FIXED_RAN_AT, _require_installed


@pytest.mark.parametrize("attempts, declared, expected", [
    #: Declined at b; c left with no receipt.
    ([("a", "ok", "", ""), ("b", "refused", "", "over the limit")], ["a", "b", "c"],
     {"stage": "b", "reason": "over the limit", "left": ["c"]}),
    #: Declined at the last declared step: a stop, with nothing left.
    ([("a", "ok", "", ""), ("b", "refused", "", "no")], ["a", "b"], {"stage": "b", "reason": "no", "left": []}),
    #: Declined, then the run went on: not a stop.
    ([("a", "refused", "", "no"), ("b", "ok", "", "")], ["a", "b"], None),
    #: An error last is a failure, never a decline.
    ([("a", "ok", "", ""), ("b", "error", "TimeoutError", "")], ["a", "b", "c"], None),
    #: No reason recorded: kept empty, for the page to say so in its own words.
    ([("a", "refused", "", "")], ["a", "b"], {"stage": "a", "reason": "", "left": ["b"]}),
    ([], ["a"], None),
])
def test_what_counts_as_stopped_by_a_step(attempts, declared, expected, examined):
    examined(1, "attempt lists")
    assert declined_at(attempts, declared) == expected


def test_the_kept_value_is_read_back_or_none(examined):
    from onetrace_console.overview import declined
    good = {"stage": "b", "reason": "r", "left": ["c"]}
    cases = {json.dumps(good): good, "null": None, "": None, "[1]": None,
             json.dumps({**good, "left": [1]}): None, json.dumps({"stage": "b"}): None, "{": None}
    examined(len(cases), "kept values")
    for kept, want in cases.items():
        assert declined(type("Run", (), {"declined": kept})()) == want, kept


# ------------------------------------------------------------------ real SDK records

def _emit(out: Path, run_id: str, declared: list[str], plan) -> None:
    """A real SDK record declaring `declared`; `plan` is [(stage, what)], what in ok / declined."""
    from onetrace.emit import Instrument, Recorder, Refusal
    rec = Recorder(str(out), run_id=run_id, declared_stages=declared, manifest=Path(__file__),
                   policy="fail-closed", topology=True, anchor_reason="a test record")
    tool = Instrument("tool", "tool", "1.0.0", {"x": "1"})
    for stage, what in plan:
        def body(ctx, stage=stage, what=what):
            if what == "declined":
                raise Refusal("the amount is over the approval limit")
            return ctx.write_json(f"{stage}.json", {stage: "1"})
        rec.run_node(stage, None, tool, body)
    rec.close()


def _stored(tmp_path, store, run_id, declared, plan):
    """The run delivered with its output files, so its records agree and what is read of it here
    -- rung 3, and the Overview's lists -- is not put behind "not checked"."""
    from onetrace_console.checks import run_and_record
    from tests.test_home_and_diff import _deliver
    _emit(tmp_path / run_id, run_id, declared, plan)
    return run_and_record(_deliver(tmp_path / run_id, store, outputs=True), store, ran_at=FIXED_RAN_AT)


def test_a_real_run_declined_at_a_step_keeps_the_step_its_reason_and_what_was_left(tmp_path, store,
                                                                                  examined):
    _require_installed()
    from onetrace_console.overview import declined
    stopped = _stored(tmp_path, store, "stopped", ["intake", "approve", "pay"],
                      [("intake", "ok"), ("approve", "declined")])
    went_on = _stored(tmp_path, store, "went-on", ["intake", "approve", "pay"],
                      [("intake", "declined"), ("approve", "ok"), ("pay", "ok")])
    examined(2, "real runs")
    assert declined(stopped) == {"stage": "approve", "reason": "the amount is over the approval limit",
                                 "left": ["pay"]}
    assert declined(went_on) is None
    assert stopped.check_verdict == "holds", "declining is the run's own rule, not a broken record"


def test_a_store_from_0_1_2_is_re_derived_once_at_start_up(tmp_path, store, examined):
    _require_installed()
    from onetrace_console.checks import DERIVED
    from onetrace_console.overview import declined
    from onetrace_console.serve import _render_startup_pages
    from onetrace_console.store import Store
    run = _stored(tmp_path, store, "older", ["intake", "approve", "pay"],
                  [("intake", "ok"), ("approve", "declined")])
    store.put_run(replace(run, declined="", derived="derivation-6"))
    reopened = Store(store.root)
    _render_startup_pages(reopened, tmp_path / "site")
    after = reopened.get_run(run.key)
    examined(1, "run stored under 0.1.2's derivation")
    assert after.derived == DERIVED
    assert declined(after) == {"stage": "approve", "reason": "the amount is over the approval limit",
                               "left": ["pay"]}
    assert (after.check_verdict, after.check_report) == (run.check_verdict, run.check_report)


def test_sabotage_each_check_catches_its_fault(monkeypatch, examined):
    from onetrace_console import ingest, overview
    caught = 0
    #: Any refusal counted as a stop, not only the last attempt.
    def any_refusal(attempts, declared):
        hit = next((a for a in attempts if a[1] == "refused"), None)
        return None if hit is None else {"stage": hit[0], "reason": hit[3], "left": []}
    went_on = [("a", "refused", "", "no"), ("b", "ok", "", "")]
    assert any_refusal(went_on, ["a", "b"]) != ingest.declined_at(went_on, ["a", "b"])
    caught += 1
    #: A reader that takes any JSON object as a stop.
    monkeypatch.setattr(overview, "load_json_bounded", lambda text, what: {"stage": "x"})
    assert overview.declined(type("Run", (), {"declined": "{}"})()) is None, "a malformed value reads as a stop"
    caught += 1
    examined(caught, "faults caught")


# ------------------------------------------------------------------ the pages

GENERATED_AT = "2026-10-13T12:00:00+00:00"
REASON = "the amount is over the approval limit"


@pytest.fixture
def two_runs(tmp_path, store):
    """One run stopped at `approve`, `pay` left; one that ran every step."""
    _require_installed()
    stopped = _stored(tmp_path, store, "stopped", ["intake", "approve", "pay"],
                      [("intake", "ok"), ("approve", "declined")])
    whole = _stored(tmp_path, store, "whole", ["intake", "approve", "pay"],
                    [("intake", "ok"), ("approve", "ok"), ("pay", "ok")])
    return store, stopped, whole


def _case(run, store) -> str:
    from onetrace_console.pages import CASE, render_execution
    return render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]


def page_problems(case: str, stage: str, reason: str, left: list[str]) -> list[str]:
    """The run page of a run stopped at `stage`: its banner, in the declined outline, and its chip."""
    from html import escape, unescape
    import re
    out = []
    banner = re.findall(r'<div data-section="declined"><p class="declined">(.*?)</p></div>', case, re.S)
    if len(banner) != 1:
        return [f"the banner is there {len(banner)} times"]
    said = unescape(banner[0])
    if f"The run stopped at {stage}" not in said or reason not in said:
        out.append(f"the banner does not name the step and its reason: {said!r}")
    if left and f"Declared steps left without a receipt: {', '.join(left)}." not in said:
        out.append(f"the banner does not name the steps left: {said!r}")
    chips = re.findall(r'<span class="pill (\w+)" data-declined="true">(.*?)</span>', case)
    if chips != [("dec", escape(f"Declined at {stage}"))]:
        out.append(f"the head's chip is {chips}")
    return out


def test_the_run_page_says_where_the_run_stopped_why_and_what_was_left(two_runs, examined):
    store, stopped, whole = two_runs
    examined(2, "run pages")
    assert page_problems(_case(stopped, store), "approve", REASON, ["pay"]) == []
    plain = _case(whole, store)
    assert 'data-section="declined"' not in plain and 'data-declined="true"' not in plain


def test_the_viewer_reads_the_same_stop_as_the_store_keeps(two_runs, examined):
    from onetrace_console.overview import declined
    from onetrace_console.viewer.model import declined_at_step
    from onetrace_console.viewer.record import read_record
    import tempfile
    from onetrace_console.checks import materialise
    store, stopped, whole = two_runs
    examined(2, "runs read both ways")
    for run in (stopped, whole):
        with tempfile.TemporaryDirectory() as tmp:
            viewer = declined_at_step(read_record(materialise(run, store, Path(tmp) / "run")))
        kept = declined(run)
        assert (viewer and (viewer[0], viewer[1], list(viewer[2]))) == (
            kept and (kept["stage"], kept["reason"], kept["left"])) or (not viewer and kept is None)


def test_the_runs_list_and_the_overview_count_the_stopped_run(two_runs, examined):
    import re
    from html import unescape
    from onetrace_console.render import HOME, render_all
    store, stopped, whole = two_runs
    pages = render_all(store, generated_at=GENERATED_AT)
    home = pages[HOME]
    line = re.search(r'<p data-line="stopped"[^>]*><a href="([^"]+)">(.*?)</a></p>', home)
    examined(1, "Overview")
    assert line and unescape(line.group(2)) == "1 of 2 stopped by a step", line
    listed = pages[line.group(1)]
    keys = re.findall(r'<tr data-run="[^"]*" data-key="([0-9a-f]{64})">', listed)
    assert keys == [stopped.key], "the count's list is not exactly the stopped run"
    every = pages["executions-all.html"]
    rows = dict(re.findall(r'<tr data-run="[^"]*" data-key="([0-9a-f]{64})">(.*?)</tr>', every, re.S))
    assert 'class="pill dec" data-declined="true">Declined at approve</span>' in rows[stopped.key]
    assert "data-declined" not in rows[whole.key]


def test_a_hostile_step_name_and_reason_stay_escaped(tmp_path, store, examined):
    """A step whose name holds an ampersand (the SDK refuses markup, control and bidirectional
    characters in a stage name: it becomes a folder name), declining with markup, a control
    character and a right-to-left override in its reason, which is free text. Every hostile
    character is written here as an escape, never raw."""
    _require_installed()
    from onetrace.emit import Instrument, Recorder, Refusal
    rlo, bell = "\u202e", "\x07"
    name, reason = "a & approve", f'<script>alert(1)</script>{bell} "over" {rlo}timil'
    out = tmp_path / "hostile"
    rec = Recorder(str(out), run_id="hostile", declared_stages=["intake", name, "pay"], manifest=Path(__file__),
                   policy="fail-closed", topology=True, anchor_reason="a test record")
    tool = Instrument("tool", "tool", "1.0.0", {"x": "1"})
    rec.run_node("intake", None, tool, lambda ctx: ctx.write_json("i.json", {"i": "1"}))

    def no(ctx):
        raise Refusal(reason)
    rec.run_node(name, None, tool, no)
    rec.close()
    from onetrace_console.checks import run_and_record
    from tests.test_home_and_diff import _deliver
    run = run_and_record(_deliver(out, store), store, ran_at=FIXED_RAN_AT)
    case = _case(run, store)
    examined(1, "hostile run page")
    assert "<script>alert(1)" not in case and "a & approve" not in case, "markup or a bare ampersand drawn raw"
    assert "&lt;script&gt;alert(1)" in case and "a &amp; approve" in case, "not escaped as text"
    assert bell not in case and rlo not in case, "a control or bidirectional character drawn raw"
    assert "\\u0007" in case and "\\u202e" in case, "not shown as escapes"


def test_sabotage_the_page_checks_catch_their_faults(two_runs, examined):
    store, stopped, _ = two_runs
    case = _case(stopped, store)
    faults = {
        "banner removed": case.replace('<div data-section="declined">', '<div data-section="gone">'),
        "chip drawn red": case.replace('class="pill dec" data-declined', 'class="pill bad" data-declined'),
        "steps left dropped": case.replace("Declared steps left without a receipt: pay.", ""),
    }
    examined(len(faults), "faults planted")
    for what, page in faults.items():
        assert page != case and page_problems(page, "approve", REASON, ["pay"]) != [], what
