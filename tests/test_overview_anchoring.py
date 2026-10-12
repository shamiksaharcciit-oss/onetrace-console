"""The Overview's "Committed by a known time?" row.

"{n} yes · {c} couldn't check · {f} the check failed · {u} not anchored · {x} not checked" -- any
at 0 left out, the runs without this console's own check inline in the words "Records agree" uses
for them, and every count over all runs stored, like every other count. Each run is counted as its own page
reads it (`StoredRun.anchored`, from `viewer.model.anchor_reading` at check time), so the row and
the run pages cannot disagree.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest

from onetrace_console.home import ANCHOR_FORMS, tallies
from onetrace_console.render import HOME, render_all
from tests.test_home_and_diff import RUN_C, _deliver, _fake_run, _require_exam
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_overview import _section, _text
from tests.test_pages import GENERATED_AT
from tests.test_step3_receipt_anchor import _case_rung, anchored, declared  # noqa: F401
from tests.test_stage_pages import demo  # noqa: F401


def _row(store) -> tuple[str, str]:
    """(the row's words, its markup)."""
    section = _section(render_all(store, generated_at=GENERATED_AT)[HOME], "evidence")
    found = re.search(r'<tr data-rung="anchored">(.*?)</tr>', section, re.S)
    assert found, "no anchoring row"
    return _text(found.group(1)).strip(), found.group(1)


@pytest.fixture
def mixed(store):
    """One stored run per reading, two not anchored, and one the check runner has not reached."""
    from onetrace_console.checks import run_and_record
    _require_installed()
    _require_exam()
    real = run_and_record(_deliver(RUN_C, store), store, ran_at=FIXED_RAN_AT)
    plan = [("y-1", "yes"), ("c-1", "couldnt-check"), ("f-1", "failed"), ("n-1", "not-anchored")]
    for run_id, reading in plan:
        made = _fake_run(store, real, run_id=run_id, verdict=real.check_verdict,
                         note=real.check_note)
        store.put_run(replace(made, anchored=reading))
    _fake_run(store, real, run_id="unchecked-1", verdict="")
    assert len(store.runs()) == 6 and not store.unreadable_runs, "the premise: all six stored"
    return store


def test_the_row_counts_each_form_and_the_runs_without_the_check_inline(mixed, examined):
    store = mixed
    total = len(store.runs())
    t = {x.slug: x for x in tallies(store)}
    examined(total, "runs counted")
    said, markup = _row(store)
    n = t["anchored-not-anchored"].count
    assert n == 2, "the real run and n-1"
    assert said == (f"Committed by a known time? 1 yes · 1 couldn't check · 1 the check failed · "
                    f"{n} not anchored · 1 not checked"), said
    #: Each count opens exactly the runs it counted.
    for reading, _ in ANCHOR_FORMS + (("not-checked", ""),):
        assert f'href="executions-anchored-{reading}.html"' in markup, reading


def test_the_denominator_is_all_runs_stored(mixed):
    """"of {all stored}", like every other count; the runs with the check are all
    stored less the inline "not checked"."""
    store = mixed
    total = len(store.runs())
    t = {x.slug: x for x in tallies(store)}
    for reading, _ in ANCHOR_FORMS + (("not-checked", ""),):
        assert t[f"anchored-{reading}"].denominator == total, reading
        assert f"of {total}" in t[f"anchored-{reading}"].sentence, reading
    checked = sum(1 for r in store.runs() if r.anchored)
    assert checked == total - t["anchored-not-checked"].count == total - 1


def test_a_form_at_zero_is_left_out(demo):  # noqa: F811
    run, store = demo
    said, _ = _row(store)
    assert said == "Committed by a known time? 1 not anchored", said
    for word in ("yes", "couldn't check", "the check failed", "not checked"):
        assert f" {word}" not in said.split("? ", 1)[1], word


def test_each_run_is_counted_as_its_own_page_reads_it(anchored, declared, demo):  # noqa: F811
    """The stored reading is the run page's rung, from the pinned verifier's own check: its FAIL on
    a placeholder anchor; a record declaring an anchor it does not have; and no anchor."""
    states = {"Not anchored · no anchor beside the chain": "not-anchored"}
    for run, store in (anchored, declared, demo):
        rung = _case_rung(run, store)
        if rung.startswith("No · the check says:"):
            assert run.anchored == "failed", (rung, run.anchored)
        else:
            assert run.anchored == states[rung], (rung, run.anchored)


def test_a_run_stored_before_is_re_derived_to_the_same_reading(anchored):
    from onetrace_console.checks import DERIVED, rederive
    run, store = anchored
    older = replace(run, anchored="", derived="derivation-3")
    store.put_run(older)
    again = rederive(older, store)
    assert (again.anchored, again.derived) == ("failed", DERIVED)


def test_a_reading_outside_the_four_is_refused_when_read(demo):  # noqa: F811
    """As every field of a stored run is: a record this version does not write is refused."""
    from onetrace_console.store import StoredRun
    run, _store = demo
    with pytest.raises(ValueError, match="`anchored` is"):
        StoredRun.from_json(replace(run, anchored="anchored").to_json())


def test_a_run_whose_report_cannot_be_read_is_not_checked(anchored):
    """No own check the page reads: its rung is what the record declares, so it is counted with
    the runs without the check, never as a form."""
    from onetrace_console.checks import rederive
    run, store = anchored
    envelope = json.loads(store.get(run.check_report).decode("utf-8"))
    envelope["stdout"] += "forged: a line after the summary\n"
    broken = replace(run, check_report=store.put(json.dumps(envelope).encode("utf-8")))
    assert rederive(broken, store).anchored == ""
