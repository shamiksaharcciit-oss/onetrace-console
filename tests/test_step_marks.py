"""Each run's steps, kept when it is checked: one entry a step, in recorded order, with its mark and its recorded times.

- **The mark** is the step's last recorded attempt, read from the run's receipts: it ran, it failed with an error, it
  was retried (an attempt after one that failed with an error), or it declined by its own rule. A declared step with no
  receipt is not reached. Never a verdict, and never from the app's own traces.
- **The times** are the receipts' own `time.started` and `time.ended`, as written: the step's first start and its last
  end over its attempts, or none where no attempt states one that reads.
- **Kept with the run** (`StoredRun.steps`), so no list reads a receipt again, and carried in the run index's list
  entry; a run checked before it was kept is derived again at start-up, from its stored bytes.
"""

from __future__ import annotations

import json

import pytest

from onetrace_console.step_marks import MARKS, of_attempts

T0, T1, T2, T3 = (f"2026-01-01T00:00:0{i}.000+00:00" for i in range(4))


def _a(stage, cls, started=T0, ended=T1, status="", reason=""):
    return (stage, cls, status, reason, started, ended)


@pytest.mark.parametrize(
    "attempts, declared, expected",
    [
        #: Each step once, in the order it was recorded.
        (
            [_a("a", "ok", T0, T1), _a("b", "ok", T1, T2)],
            ["a", "b"],
            [("a", "plain", 0, T0, T1), ("b", "plain", 0, T1, T2)],
        ),
        #: Retried until it succeeded: retried, with how many times.
        (
            [_a("a", "error", T0, T1), _a("a", "error", T1, T2), _a("a", "ok", T2, T3)],
            ["a"],
            [("a", "retried", 2, T0, T3)],
        ),
        #: Its last attempt failed with an error: error, with the retries before it.
        ([_a("a", "error", T0, T1), _a("a", "error", T1, T2)], ["a"], [("a", "error", 1, T0, T2)]),
        #: Declined by its own rule; the steps declared after it are not reached, in the declared order.
        (
            [_a("a", "ok"), _a("b", "refused", T1, T2)],
            ["a", "b", "c", "d"],
            [
                ("a", "plain", 0, T0, T1),
                ("b", "declined", 0, T1, T2),
                ("c", "not-reached", 0, None, None),
                ("d", "not-reached", 0, None, None),
            ],
        ),
        #: Two instances that both succeed are not a retry.
        ([_a("a", "ok", T0, T1), _a("a", "ok", T1, T2)], ["a"], [("a", "plain", 0, T0, T2)]),
        #: A time that does not read is not kept; the other is.
        ([_a("a", "ok", "yesterday", T1)], ["a"], [("a", "plain", 0, None, T1)]),
        ([_a("a", "ok", None, 5)], ["a"], [("a", "plain", 0, None, None)]),
        #: A recorded step the receipts don't declare is still a step the run recorded.
        ([_a("x", "ok")], [], [("x", "plain", 0, T0, T1)]),
    ],
)
def test_each_step_s_mark_and_times_are_its_recorded_attempts(attempts, declared, expected, examined):
    examined(len(expected), "steps")
    got = of_attempts(attempts, declared)
    assert [(s["step"], s["mark"], s["retries"], s["started"], s["ended"]) for s in got] == expected
    assert {s["mark"] for s in got} <= set(MARKS)


def test_a_step_with_no_name_is_not_a_step(examined):
    examined(1, "attempt with no stage name")
    assert of_attempts([(None, "ok", "", "", T0, T1), _a("a", "ok")], ["a"]) == [
        {"step": "a", "mark": "plain", "retries": 0, "started": T0, "ended": T1}
    ]


# ------------------------------------------------------------------ real SDK records, end to end


def test_a_checked_run_keeps_its_steps_and_its_index_entry_carries_them(tmp_path, store, examined):
    from tests.test_last_attempt_failed import _require_installed, _stored

    _require_installed()
    from onetrace_console.run_index import LIST, build

    run = _stored(tmp_path, store, "kept-steps", [("a", None, "ok"), ("b", "1", "error"), ("b", "2", "ok")])
    kept = json.loads(run.steps)
    examined(len(kept), "kept steps")
    assert [(s["step"], s["mark"], s["retries"]) for s in kept] == [("a", "plain", 0), ("b", "retried", 1)]
    assert all(s["started"] and s["ended"] for s in kept), kept
    index = build(store)
    (entry,) = [r for r in index["runs"] if r["key"] == run.key]
    assert entry[LIST]["steps"] == kept


def test_a_run_checked_before_the_steps_were_kept_is_derived_again(tmp_path, store, examined):
    from dataclasses import replace

    from tests.test_last_attempt_failed import _require_installed, _stored

    _require_installed()
    from onetrace_console.checks import DERIVED, rederive

    run = _stored(tmp_path, store, "before-steps", [("a", None, "ok"), ("b", None, "declined")])
    older = replace(run, steps="", derived="derivation-12")
    store.put_run(older)
    assert DERIVED != "derivation-12"
    again = rederive(store.get_run(run.key), store)
    examined(1, "run derived again")
    assert again.steps == run.steps and again.derived == DERIVED
    assert [s["mark"] for s in json.loads(again.steps)] == ["plain", "declined"]


def test_the_demo_s_runs_each_keep_their_steps(shared_demo, examined):
    """Every run in the demo whose record reads: one entry a recorded step, each with a mark."""
    from onetrace_console.store import Store

    store = Store(shared_demo["folder"] / "store" / "store")
    kept = [json.loads(r.steps) for r in store.runs() if r.steps]
    examined(len(kept), "runs with their steps kept")
    assert len(kept) > 40
    assert all(isinstance(s, list) for s in kept)
    marks = {m["mark"] for steps in kept for m in steps}
    #: The demo holds runs that retried, that failed, and that declined.
    assert {"plain", "retried", "error", "declined"} <= marks, marks
    timed = sum(1 for steps in kept if any(s["started"] and s["ended"] for s in steps))
    assert timed > 40


def test_drawing_the_runs_list_reads_no_receipt(shared_demo, monkeypatch, examined):
    """The Runs page draws from the index alone: with every way to read a run's record or a receipt refused, it draws
    the same page."""
    from onetrace_console import runs_page
    from onetrace_console.run_index import read

    index = read(shared_demo["folder"] / "store")
    assert index is not None
    before = runs_page.body(index, {"page": "1"}, public=True)

    def refused(*_a, **_k):
        raise AssertionError("a list read a run's record")

    import onetrace_console.checks as checks
    import onetrace_console.store as store_mod
    import onetrace_console.viewer.record as record

    monkeypatch.setattr(record, "read_record", refused)
    monkeypatch.setattr(checks, "materialise", refused)
    monkeypatch.setattr(store_mod.Store, "get", refused)
    monkeypatch.setattr(store_mod.Store, "get_run", refused)
    after = runs_page.body(index, {"page": "1"}, public=True)
    examined(1, "Runs page drawn with no record read")
    assert after == before


# ------------------------------------------------------------------ the Runs page draws them


def _rows(page: str) -> dict[str, str]:
    import re

    return {k: row for k, row in re.findall(r'<tr data-run="[^"]*" data-key="([0-9a-f]{64})">(.*?)</tr>', page, re.S)}


@pytest.fixture(scope="module")
def runs_index(shared_demo):
    from onetrace_console.run_index import read

    index = read(shared_demo["folder"] / "store")
    assert index is not None
    return index


def test_the_runs_page_draws_one_mark_a_step_with_its_words(runs_index, examined):
    import re
    from html import unescape

    from onetrace_console import runs_page, step_marks

    page = runs_page.body(runs_index, {"page": "all"}, public=True)
    assert '<th scope="col">Steps</th>' in page
    rows = _rows(page)
    entries = {r["key"]: r["list"] for r in runs_index["runs"]}
    examined(len(rows), "runs' steps")
    assert len(rows) > 40
    for key, row in rows.items():
        steps = entries[key]["steps"]
        cell = re.search(r'<td[^>]*data-answer="steps">(.*?)</td>', row, re.S).group(1)
        assert re.findall(r'data-step-mark="([a-z-]+)"', cell) == [s["mark"] for s in steps], key
        said = unescape(re.search(r"<span class=\"note\" data-steps-said>(.*?)</span>", cell, re.S).group(1))
        #: Each step that did not simply run is named in the row's words, never by its mark alone.
        for s in steps:
            if s["mark"] in ("error", "retried", "declined"):
                assert step_marks.said(s) in said, (key, s)
            if s["mark"] == "not-reached":
                assert "not reached" in said and s["step"] in said, (key, s)


def test_each_mark_has_its_own_shape_and_the_legend_says_each(runs_index, examined):
    from onetrace_console import runs_page, step_marks

    examined(len(step_marks.MARKS), "marks")
    assert set(step_marks.SHAPES) == set(step_marks.MARKS) == set(step_marks.LEGEND_WORDS)
    assert len(set(step_marks.SHAPES.values())) == len(step_marks.MARKS), "two marks share a shape"
    page = runs_page.body(runs_index, {"page": "1"}, public=True)
    legend = page[page.index('data-runs="step-legend"') :]
    for m, words in step_marks.LEGEND_WORDS.items():
        assert f'<li data-step-mark="{m}">' in legend and words in legend, m


def test_the_bars_are_drawn_to_one_scale_the_page_s_longest_run_and_say_so(runs_index, examined):
    import re
    from html import unescape

    from onetrace_console import runs_page, step_marks

    for params in ({"page": "1"}, {"page": "2"}, {"pipeline": "P1"}):
        page = runs_page.body(runs_index, params, public=True)
        shown = [r for r in runs_index["runs"] if r["key"] in _rows(page)]
        longest = max(t for r in shown for t in (step_marks.seconds(r["list"]["ran"]),) if t is not None)
        said = unescape(re.search(r'<p class="note" data-runs="scale">(.*?)</p>', page).group(1))
        assert said.startswith("Bars are drawn to the longest run on this page: ") and "not a measure" in said
        assert runs_page._seconds_said(longest) in said
        widths = {}
        for key, row in _rows(page).items():
            got = re.search(r'<rect data-run-length data-tone="neu" opacity="\.35" x="0" y="0" width="([0-9.]+)"', row)
            took = step_marks.seconds(next(r["list"]["ran"] for r in shown if r["key"] == key))
            if took is None:
                assert got is None, key
                continue
            widths[key] = float(got.group(1))
            assert abs(widths[key] - max(100 * took / longest, 0.5)) < 0.001, key
        examined(len(widths), f"bars on {params}")
        assert max(widths.values()) == 100.0


def test_a_run_with_no_recorded_times_gets_words_and_no_bar(examined):
    from onetrace_console import runs_page, step_marks

    examined(2, "runs without times")
    assert step_marks.bar("", [], 2.0) == "" and step_marks.bar("yesterday → today", [], 2.0) == ""
    entry = {"ran": "", "steps": [{"step": "a", "mark": "plain", "retries": 0, "started": None, "ended": None}]}
    drawn = runs_page._started(entry, 2.0)
    assert runs_page.NO_TIMES in drawn and "<svg" not in drawn


def test_a_step_s_segment_sits_where_it_ran_on_the_run_s_bar(examined):
    import re

    from onetrace_console import step_marks

    steps = [
        {"step": "a", "mark": "plain", "retries": 0, "started": T0, "ended": T1},
        {"step": "b", "mark": "error", "retries": 0, "started": T2, "ended": T3},
        {"step": "c", "mark": "not-reached", "retries": 0, "started": None, "ended": None},
    ]
    drawn = step_marks.bar(f"{T0} → {T3}", steps, 6.0)
    rects = re.findall(r'<rect data-tone="([a-z]+)" x="([0-9.]+)" y="0" width="([0-9.]+)"', drawn)
    examined(len(rects), "segments")
    assert rects == [("neu", "0.000", "16.667"), ("bad", "33.333", "16.667")]


def test_a_duration_under_a_second_is_said_in_milliseconds(examined):
    from onetrace_console.runs_page import took

    examined(3, "durations")
    assert took(f"{T0} → 2026-01-01T00:00:00.042+00:00") == "42 ms"
    assert took(f"{T0} → {T1}") == "1.0 s"
    assert took(f"{T0} → 2026-01-01T00:01:30.000+00:00") == "1 min 30 s"
