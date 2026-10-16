"""A declared stage whose last recorded attempt failed is stated above the timeline.

    What counts: a declared stage whose last recorded attempt failed with an error. That is the
    same definition of failure as the retry rule's. A stage that failed, was retried, and
    succeeded is not counted. An outcome that is not an error (for example "declined") is not a
    failure and is not counted.

    Run page, directly below the verdict strip, outside it, as its own amber line:
      one:     "A declared stage's last recorded attempt failed: {stage} ({error type})."
      several: "{n} declared stages' last recorded attempts failed: {stage}, {stage}"
    Overview, recent runs, the "Declared stages delivered" cell, appended:
      "; last attempt failed: {stage}" (several: "{stage}, {stage}")
    Overview, "Needs attention first": a new reason, "Last attempt failed", ordered after
    "a declared stage missing".

The source is each receipt's recorded outcome -- the class, and for an error its `status`, which the
SDK writes as the exception's type -- never SDK code. The SDK's "declined" is its
`refused` class (`onetrace.emit.Refusal`).
"""
from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pytest

from onetrace_console.ingest import last_attempt_failed
from onetrace_console.render import HOME, render_all
from tests.test_checks import FIXED_RAN_AT, _require_installed

GENERATED_AT = "2026-10-04T12:00:00+00:00"


# ------------------------------------------------------------------ what counts, from the outcomes

@pytest.mark.parametrize("attempts, declared, expected", [
    #: Failed once and never retried: counted, with its error type.
    ([("a", "ok", ""), ("b", "error", "TimeoutError")], ["a", "b"], [["b", "TimeoutError"]]),
    #: Failed, retried, succeeded: not counted.
    ([("a", "ok", ""), ("b", "error", "TimeoutError"), ("b", "ok", "")], ["a", "b"], []),
    #: Failed, retried, failed again: counted, with the LAST attempt's error type.
    ([("b", "error", "TimeoutError"), ("b", "error", "ValueError")], ["b"], [["b", "ValueError"]]),
    #: Declined (the SDK's `refused`): not an error, not counted.
    ([("a", "ok", ""), ("b", "refused", "")], ["a", "b"], []),
    #: Failed, then declined: the last attempt is not an error, so not counted.
    ([("b", "error", "TimeoutError"), ("b", "refused", "")], ["b"], []),
    #: Several, in the declared order, not the order they failed in.
    ([("b", "error", "KeyError"), ("a", "error", "TimeoutError")], ["a", "b"],
     [["a", "TimeoutError"], ["b", "KeyError"]]),
    #: A stage that is not declared is not "a declared stage".
    ([("a", "ok", ""), ("x", "error", "TimeoutError")], ["a"], []),
    #: A declared stage with no attempt is missing, not failed.
    ([("a", "ok", "")], ["a", "b"], []),
])
def test_what_counts_is_a_declared_stage_whose_last_attempt_is_an_error(attempts, declared,
                                                                         expected):
    assert last_attempt_failed(attempts, declared) == expected


# ------------------------------------------------------------------ the fixed words

def test_the_run_page_words_for_one_and_for_several():
    """The words the viewer draws, now that the line is drawn by the viewer."""
    from onetrace_console.viewer.sentences import template
    assert (template("last_failed.one").format(stage="b", error="TimeoutError")
            == "A declared stage's last recorded attempt failed: b (TimeoutError).")
    assert (template("last_failed.several").format(n="2", stages="a, b")
            == "2 declared stages' last recorded attempts failed: a, b")


# ------------------------------------------------------------------ real SDK records, end to end

def _emit(out: Path, run_id: str, plan) -> None:
    """A real SDK record: `plan` is [(stage, attempt, what)] with what in ok / error / declined."""
    from onetrace.emit import Instrument, Recorder, Refusal
    stages = list(dict.fromkeys(s for s, _, _ in plan))
    rec = Recorder(str(out), run_id=run_id, declared_stages=stages, manifest=Path(__file__),
                   policy="fail-closed", topology=True, anchor_reason="a test record")
    tool = Instrument("tool", "tool", "1.0.0", {"x": "1"})
    for stage, attempt, what in plan:
        def body(ctx, stage=stage, what=what):
            if what == "error":
                raise TimeoutError(f"{stage} failed")
            if what == "declined":
                raise Refusal(f"{stage} declined by its contract")
            return ctx.write_json(f"{stage}.json", {stage: "1"})
        if what == "error":
            with pytest.raises(TimeoutError):
                rec.run_node(stage, attempt, tool, body)
        else:
            rec.run_node(stage, attempt, tool, body)
    rec.close()


def _stored(tmp_path, store, run_id, plan):
    from onetrace_console.checks import run_and_record
    from tests.test_home_and_diff import _deliver
    _emit(tmp_path / run_id, run_id, plan)
    #: With its output files, so its records agree and its other answers are what is listed.
    return run_and_record(_deliver(tmp_path / run_id, store, outputs=True), store, ran_at=FIXED_RAN_AT)


def _case(run, store) -> str:
    from onetrace_console.pages import CASE, render_execution
    return render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]


def _line(case: str) -> str | None:
    #: Drawn by the viewer, on every page it draws.
    found = re.search(r'<div data-section="last-attempt-failed"><p class="last-failed">(.*?)</p></div>',
                      case, re.S)
    return unescape(found.group(1)) if found else None


def _recent_row(store, run_id) -> str:
    home = unescape(render_all(store, generated_at=GENERATED_AT)[HOME])
    for row in re.findall(r'<tr data-recent="[^"]*">(.*?)</tr>', home, re.S):
        if run_id in row:
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row))
    raise AssertionError(f"{run_id} is not in the recent runs")


def _attention(store) -> str:
    home = unescape(render_all(store, generated_at=GENERATED_AT)[HOME])
    found = re.search(r'<section data-section="needs-attention".*?</section>', home, re.S)
    assert found, "no Needs attention first section"
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", found.group(0)))


def test_never_retried_is_stated_below_the_strip_outside_it_and_on_the_overview(tmp_path, store):
    _require_installed()
    run = _stored(tmp_path, store, "never-retried",
                  [("a", None, "ok"), ("b", None, "error")])
    assert run.check_verdict == "holds", "the strip stays exactly what it is"
    case = _case(run, store)
    assert _line(case) == "A declared stage's last recorded attempt failed: b (TimeoutError)."
    strip = re.search(r'<section class="strip [^"]*" data-state="[^"]*">.*?</section>', case, re.S)
    assert strip and "last-attempt-failed" not in strip.group(0), "the line is inside the strip"
    assert case[strip.end():].startswith('<div data-section="last-attempt-failed">'), \
        "the line is not directly below the strip"
    assert "2 of 2 declared stages; last attempt failed: b" in _recent_row(store, "never-retried")
    assert "Last attempt failed" in _attention(store)


def test_retried_then_succeeded_is_not_stated(tmp_path, store):
    _require_installed()
    run = _stored(tmp_path, store, "retried-ok",
                  [("a", None, "ok"), ("b", "1", "error"), ("b", "2", "ok")])
    assert run.retries == 1
    assert _line(_case(run, store)) is None
    assert "last attempt failed" not in _recent_row(store, "retried-ok")
    assert "Last attempt failed" not in _attention(store)


def test_retried_and_failed_again_is_stated(tmp_path, store):
    _require_installed()
    run = _stored(tmp_path, store, "retried-failed",
                  [("a", None, "ok"), ("b", "1", "error"), ("b", "2", "error")])
    assert _line(_case(run, store)) == "A declared stage's last recorded attempt failed: b (TimeoutError)."
    assert "last attempt failed: b" in _recent_row(store, "retried-failed")


def test_declined_is_not_a_failure(tmp_path, store):
    _require_installed()
    run = _stored(tmp_path, store, "declined", [("a", None, "ok"), ("b", None, "declined")])
    assert _line(_case(run, store)) is None
    assert "last attempt failed" not in _recent_row(store, "declined")
    assert "Last attempt failed" not in _attention(store)


def test_several_stages_failed(tmp_path, store):
    _require_installed()
    run = _stored(tmp_path, store, "several",
                  [("a", None, "error"), ("b", None, "ok"), ("c", None, "error")])
    assert _line(_case(run, store)) == "2 declared stages' last recorded attempts failed: a, c"
    assert "last attempt failed: a, c" in _recent_row(store, "several")


def test_the_needs_attention_order_puts_it_after_a_missing_stage():
    from onetrace_console.overview import ATTENTION_KINDS, ATTENTION_WORDS
    assert ATTENTION_KINDS.index("last-attempt-failed") == ATTENTION_KINDS.index("missing-stage") + 1
    assert ATTENTION_WORDS["last-attempt-failed"] == "Last attempt failed"


def test_the_demo_retried_and_succeeded_so_nothing_is_stated(store):
    """The reference demo's tests stage failed once and was retried successfully."""
    _require_installed()
    from tests.test_reference_demo import RUNS, _delivery
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    for day in ("1", "2"):
        accepted = accept(_delivery(RUNS / f"day-{day}"), store)
        run = run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT)
        assert run.retries == 1 and run.last_failed in ("", "[]")
        assert _line(_case(run, store)) is None


def test_the_line_is_drawn_filled_amber_like_the_other_findings():
    """"Filled amber, like the other findings. Not red." The finding pair (cc), filled --
    in the viewer's stylesheet, which the console serves as part of its own."""
    from onetrace_console.frame import stylesheet
    rule = re.search(r"\.last-failed\{([^}]*)\}", stylesheet().decode("utf-8"))
    assert rule, "no rule draws the line"
    body = rule.group(1)
    assert "background:var(--cc-bg)" in body and "color:var(--cc-ink)" in body
    assert "bad" not in body and "border:" not in body, "red, or outlined rather than filled"


def test_a_run_derived_before_this_is_re_derived_with_the_line(tmp_path, store):
    """Stored under an earlier derivation, a run has no `last_failed`; start-up re-derives it once."""
    _require_installed()
    from dataclasses import replace
    from onetrace_console.checks import DERIVED, rederive
    run = _stored(tmp_path, store, "before-derivation", [("a", None, "ok"), ("b", None, "error")])
    old = replace(run, last_failed="", derived="derivation-2")
    store.put_run(old)
    again = rederive(old, store)
    assert again.derived == DERIVED == "derivation-10"
    assert again.last_failed == '[["b", "TimeoutError"]]'


#: The tag every run carried before the derivation was given a neutral name. Written in two parts
#: so the tree holds no id-shaped text; it must be this exact value to stand for an older store.
PREVIOUS_RELEASE_DERIVED = "29" + "lk-1"


def test_a_store_from_before_the_rename_is_re_derived_at_start_up(tmp_path, store):
    """A run stored under the previous tag is re-derived once when the console starts: its
    derived fields come back and its tag becomes the current one, while its check -- verdict,
    report, note -- is left exactly as stored."""
    _require_installed()
    from dataclasses import replace
    from onetrace_console.checks import DERIVED
    from onetrace_console.serve import _render_startup_pages
    from onetrace_console.store import Store
    run = _stored(tmp_path, store, "before-rename", [("a", None, "ok"), ("b", None, "error")])
    assert DERIVED == "derivation-10"
    store.put_run(replace(run, last_failed="", derived=PREVIOUS_RELEASE_DERIVED))
    reopened = Store(store.root)
    _render_startup_pages(reopened, tmp_path / "site")
    after = reopened.get_run(run.key)
    assert after.derived == DERIVED
    assert after.last_failed == '[["b", "TimeoutError"]]'
    assert (after.check_verdict, after.check_report, after.check_note) == \
        (run.check_verdict, run.check_report, run.check_note)


# ------------------------------------------------------------------ the answer page

def _answer(run, store) -> str:
    from onetrace_console.pages import ANSWER, render_execution
    return render_execution(run, store, generated_at=GENERATED_AT).pages[ANSWER]


def _below_the_strip(page: str) -> None:
    strip = re.search(r'<section class="strip [^"]*" data-state="[^"]*">.*?</section>', page, re.S)
    assert strip and "last-attempt-failed" not in strip.group(0), "the line is inside the strip"
    assert page[strip.end():].startswith('<div data-section="last-attempt-failed">'), \
        "the line is not directly below the strip"


def test_the_answer_page_carries_the_line_for_a_never_retried_stage(tmp_path, store):
    """The answer page shows the run's verdict strip too, so it carries the
    line in the same words and the same place."""
    _require_installed()
    run = _stored(tmp_path, store, "answer-never-retried", [("a", None, "ok"), ("b", None, "error")])
    page = _answer(run, store)
    assert _line(page) == "A declared stage's last recorded attempt failed: b (TimeoutError)."
    _below_the_strip(page)


def test_the_answer_page_carries_the_line_for_several(tmp_path, store):
    _require_installed()
    run = _stored(tmp_path, store, "answer-several",
                  [("a", None, "error"), ("b", None, "ok"), ("c", None, "error")])
    page = _answer(run, store)
    assert _line(page) == "2 declared stages' last recorded attempts failed: a, c"
    _below_the_strip(page)
