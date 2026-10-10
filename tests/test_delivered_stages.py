"""The delivery rung counts declared stages with at least one
receipt, out of the declared stages, and states retries apart -- "6 of 6 declared stages; 1 retry
recorded". Counting receipts read "7 of 6" with a retry, and could hide a missing stage: 5 of 6
stages delivered and one retried is 6 receipts, which read "6 of 6".

A retry is a further receipt of a stage after one of that stage's receipts failed with an error;
two instances of one stage that both succeed are not a retry. Tier A: what the evidence shows.
"""
from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pytest

from onetrace_console.ingest import delivered_and_retries
from onetrace_console.render import HOME, _recorded_of_declared, render_all
from tests.test_checks import FIXED_RAN_AT, _require_installed

GENERATED_AT = "2026-10-02T12:00:00+00:00"


@pytest.mark.parametrize("attempts, declared, expected", [
    #: The demo: six stages, the tests stage's first attempt failed and was retried.
    ([("request", "ok"), ("context", "ok"), ("tests", "error"), ("tests", "ok"), ("model", "ok"),
      ("proposal", "ok"), ("config applied", "ok")],
     {"request", "context", "tests", "model", "proposal", "config applied"}, (6, 1)),
    #: No retry.
    ([("a", "ok"), ("b", "ok"), ("c", "ok")], {"a", "b", "c"}, (3, 0)),
    #: A stage missing and another retried: as many receipts as stages, and a stage missing.
    ([("a", "ok"), ("b", "error"), ("b", "ok")], {"a", "b", "c"}, (2, 1)),
    #: Two instances of one stage, both ok, are not a retry; the stage counts once.
    ([("a", "ok"), ("b", "ok"), ("b", "ok"), ("c", "ok")], {"a", "b", "c"}, (3, 0)),
    #: Retried twice: each attempt after a failure is a retry.
    ([("a", "error"), ("a", "error"), ("a", "ok")], {"a"}, (1, 2)),
    #: A failed attempt never retried still delivered a receipt for its stage.
    ([("a", "ok"), ("b", "error")], {"a", "b"}, (2, 0)),
])
def test_the_count_is_of_declared_stages_and_retries_are_apart(attempts, declared, expected):
    got = delivered_and_retries(attempts, declared)
    assert (got["delivered_stages"], got["retries"]) == expected


class _Run:
    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.mark.parametrize("fields, shown", [
    (dict(stage_count=6, delivered_stages=6, retries=1, recorded_count=7),
     "6 of 6 declared stages; 1 retry recorded"),
    (dict(stage_count=6, delivered_stages=6, retries=0, recorded_count=6), "6 of 6 declared stages"),
    (dict(stage_count=6, delivered_stages=5, retries=1, recorded_count=6),
     "5 of 6 declared stages; 1 retry recorded"),
])
def test_the_three_ruled_cases_read_as_ruled(fields, shown):
    assert _recorded_of_declared(_Run(**fields)) == shown


def _emit_missing_and_retried(out: Path) -> None:
    """A real SDK record: declared a, b, c; a ran; b failed once and was retried; c never ran."""
    from onetrace.emit import Instrument, Recorder
    rec = Recorder(str(out), run_id="missing-and-retried", declared_stages=["a", "b", "c"],
                   manifest=Path(__file__), policy="fail-closed", topology=True,
                   anchor_reason="a test record")
    tool = Instrument("tool", "tool", "1.0.0", {"x": "1"})

    def a(ctx):
        return ctx.write_json("a.json", {"a": "1"})

    def b(ctx, attempt):
        ctx.read_receipt("a")
        if attempt == "1":
            raise TimeoutError("a test's staged failure")
        return ctx.write_json("b.json", {"b": "1"})

    rec.run_node("a", None, tool, a)
    with pytest.raises(TimeoutError):
        rec.run_node("b", "1", tool, b, "1")
    rec.run_node("b", "2", tool, b, "2")
    rec.close()


def test_a_retry_never_hides_a_missing_stage_end_to_end(tmp_path, store):
    _require_installed()
    from onetrace_console.checks import run_and_record
    from tests.test_home_and_diff import _deliver
    _emit_missing_and_retried(tmp_path / "run")
    run = run_and_record(_deliver(tmp_path / "run", store), store, ran_at=FIXED_RAN_AT)
    #: Three receipts for three declared stages -- and one of the three never ran.
    assert (run.stage_count, run.recorded_count) == (3, 3)
    assert (run.delivered_stages, run.retries) == (2, 1)
    assert run.nothing_missing == "no", "the run's own page says a stage is missing"
    home = unescape(render_all(store, generated_at=GENERATED_AT)[HOME])
    row = re.search(r'<tr data-recent="[^"]*">(.*?)</tr>', home, re.S).group(1)
    assert "2 of 3 declared stages; 1 retry recorded" in row
    assert "3 of 3" not in home


def test_the_demo_s_runs_read_six_of_six_with_one_retry_and_others_none(store):
    _require_installed()
    from onetrace_console.checks import run_and_record
    from tests.test_home_and_diff import _deliver
    from tests.test_reference_demo import RUNS
    demo = [run_and_record(_deliver(RUNS / f"day-{d}", store), store, ran_at=FIXED_RAN_AT)
            for d in (1, 2)]
    assert [(r.delivered_stages, r.retries) for r in demo] == [(6, 1), (6, 1)]
    home = unescape(render_all(store, generated_at=GENERATED_AT)[HOME])
    assert home.count("6 of 6 declared stages; 1 retry recorded") == 2
    assert "7 of 6" not in home


def test_a_run_stored_before_this_is_re_derived_with_the_count(store):
    """Stored under the earlier derivation, a run has no count; start-up re-derives it once."""
    _require_installed()
    from dataclasses import replace
    from onetrace_console.checks import DERIVED, rederive, run_and_record
    from tests.test_home_and_diff import _deliver
    from tests.test_reference_demo import RUNS
    run = run_and_record(_deliver(RUNS / "day-1", store), store, ran_at=FIXED_RAN_AT)
    old = replace(run, delivered_stages=0, retries=0, derived="derivation-1")
    store.put_run(old)
    again = rederive(old, store)
    assert (again.delivered_stages, again.retries, again.derived) == (6, 1, DERIVED)


def test_a_stage_whose_only_receipt_failed_counts_as_delivered_and_where_the_failure_shows(
        tmp_path, store):
    """A stage with only a failed receipt has a receipt, so it counts as
    delivered -- the rung states presence. What this run's pages show of the failure, measured:
    the step's own row says it failed, with the error it recorded. The verdict strip does not:
    it states the check's verdict over the record (here, held), not each stage's outcome, and
    rung 3 reads Yes. Reported as found, since the strip was asked to show it."""
    _require_installed()
    from onetrace.emit import Instrument, Recorder
    from onetrace_console.checks import run_and_record
    from onetrace_console.pages import CASE, render_execution
    from tests.test_home_and_diff import _deliver
    out = tmp_path / "run"
    rec = Recorder(str(out), run_id="failed-never-retried", declared_stages=["a", "b"],
                   manifest=Path(__file__), policy="fail-closed", topology=True,
                   anchor_reason="a test record")
    tool = Instrument("tool", "tool", "1.0.0", {"x": "1"})
    rec.run_node("a", None, tool, lambda ctx: ctx.write_json("a.json", {"a": "1"}))

    def b(ctx):
        ctx.read_receipt("a")
        raise TimeoutError("b failed")

    with pytest.raises(TimeoutError):
        rec.run_node("b", None, tool, b)
    rec.close()
    run = run_and_record(_deliver(out, store), store, ran_at=FIXED_RAN_AT)
    assert (run.delivered_stages, run.stage_count, run.retries) == (2, 2, 0)
    home = unescape(render_all(store, generated_at=GENERATED_AT)[HOME])
    assert "2 of 2 declared stages" in home
    case = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
    rows = re.findall(r'<tr data-step="\d+">(.*?)</tr>', case, re.S)
    text = [re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", r))) for r in rows]
    assert "failed — TimeoutError : b failed" in text[1], text[1]
    assert "failed" not in text[0]
    #: As found: the strip states the check (held), and rung 3 presence (yes).
    assert re.search(r'<section class="strip ok" data-state="holds"', case)
    assert 'data-rung="nothing-missing" data-state="yes"' in case
