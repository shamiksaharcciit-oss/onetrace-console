"""Rung 3 for a run stopped at a step's own rule: the declared steps after it are not reached.

A run whose last recorded attempt was declined by the step's own rule (the SDK's `refused` class,
recorded in that step's receipt -- never inferred from a missing receipt) did not leave the steps
after it out: it never reached them. Its rung 3, "Nothing declared is missing", reads "Not
reached", stopped at the step, and names the declared steps not reached, in the declined outline,
never red. It leaves the Overview's "A declared stage missing" for a group of its own, "Stopped at
a step", in the same blue.

Three cases stay No, in red, each held here with a sabotage that takes away the one condition
that keeps it red:
  * a declared step missing BEFORE the declining step;
  * a run with no recorded decline (the run simply stopped);
  * a declined run that nonetheless has receipts for later declared steps (a contradiction): the
    exemption never applies to it, so a declared step it lacks is missing, as in any other run.
    (Its case declares a fourth step with no receipt; with every declared step recorded there
    is nothing missing to read, and rung 3 reads Yes, as before.)

The verifier has no row on declared steps (its own rows on such a run all pass), so rung 3 is the
console's reading alone; the verifier's rows are quoted as they are.
"""
from __future__ import annotations

import re
from html import unescape

import pytest

from tests.test_checks import _require_installed
from tests.test_declined_runs import _emit, _stored

STAGES = ["intake", "approve", "pay"]
STOPPED = [("intake", "ok"), ("approve", "declined")]
#: The three that stay No, each with the one condition that holds it there.
RED = {
    "a-step-missing-before-the-declining-one": (STAGES, [("approve", "declined")]),
    "no-recorded-decline": (STAGES, [("intake", "ok"), ("approve", "ok")]),
    "a-receipt-for-a-later-step": (STAGES + ["notify"],
                                   [("intake", "ok"), ("pay", "ok"), ("approve", "declined")]),
}
GENERATED_AT = "2026-10-06T12:00:00+00:00"


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def _rung3(page: str) -> tuple[str, str]:
    """(state, text) of rung 3 in a run page's ladder."""
    m = re.search(r'<tr data-rung="nothing-missing" data-state="([^"]+)">(.*?)</tr>', page, re.S)
    assert m, "no rung 3 on the page"
    return m.group(1), _text(m.group(2))


def _case_page(run, store) -> str:
    from onetrace_console.pages import CASE, render_execution
    return render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]


@pytest.fixture
def stopped(tmp_path, store):
    _require_installed()
    return _stored(tmp_path, store, "stopped", STAGES, STOPPED), store


# ------------------------------------------------------------------ the run stopped at a step

def test_its_rung_3_reads_not_reached_in_the_declined_outline(stopped, examined):
    from onetrace_console import tones
    run, store = stopped
    examined(1, "run stopped at a step")
    assert run.nothing_missing == "not-reached"
    page = _case_page(run, store)
    state, text = _rung3(page)
    assert state == "not-reached"
    #: (`_text` turns the tag around each record word into a space: hence "approve .".)
    assert text == "Nothing declared is missing Not reached · Stopped at approve . Declared steps not reached: pay ."
    #: The ladder's state word is coloured by its `data-state`: the stylesheet draws "not-reached"
    #: in the declined outline and nothing else.
    from onetrace_console.frame import stylesheet
    from tests.test_tones import _drawn
    assert tones.tone(tones.RUNG, "not-reached") == "dec"
    assert _drawn(stylesheet().decode("utf-8")).get("not-reached") == {"dec"}, "never red"


def test_it_leaves_a_declared_stage_missing_for_stopped_at_a_step(stopped, examined):
    from onetrace_console import tones
    from onetrace_console.overview import ATTENTION_WORDS, attention_kind, needs_attention
    run, store = stopped
    examined(1, "run stopped at a step")
    assert attention_kind(run, store) == "stopped-at-a-step"
    assert ATTENTION_WORDS["stopped-at-a-step"] == "Stopped at a step"
    assert tones.tone(tones.ATTENTION, "stopped-at-a-step") == "dec"
    assert [k for k, r in needs_attention(store) if r.key == run.key] == ["stopped-at-a-step"]


def test_the_overviews_rung_3_counts_it_apart_and_every_run_once(stopped, examined):
    """Its own count beside "missing a declared stage" and "not established", so the counts still
    add up to every stored run, and the count opens exactly that run."""
    from onetrace_console.home import tallies
    run, store = stopped
    by = {t.slug: t for t in tallies(store)}
    examined(len(store.runs()), "stored runs counted on rung 3")
    parts = ("nothing-missing", "missing-a-declared-stage", "missing-not-established",
             "stopped-at-a-step")
    assert sum(by[s].count for s in parts) == len(store.runs())
    assert [r.key for r in by["stopped-at-a-step"].runs] == [run.key]
    assert by["missing-a-declared-stage"].count == 0


# ------------------------------------------------------------------ the three that stay red

@pytest.mark.parametrize("name", list(RED))
def test_these_stay_no_in_red(tmp_path, store, name, examined):
    from onetrace_console.overview import attention_kind
    _require_installed()
    run = _stored(tmp_path, store, name, *RED[name])
    examined(1, name)
    assert run.nothing_missing == "no", run.nothing_missing
    #: A missing stage, unless its records come first in the order: a run whose only step declined
    #: wrote no output files, so its records are not checked, which the order lists before it.
    from onetrace_console import records
    agree = records.state(run, store)
    assert attention_kind(run, store) == ("missing-stage" if agree == "yes" else agree), agree
    state, _ = _rung3(_case_page(run, store))
    assert state == "no"


#: Each sabotage takes away the one condition that keeps its case red; the case must then read
#: "not-reached", so the test above would fail on that sabotage.
SABOTAGE = {
    "a-step-missing-before-the-declining-one": ("_missing_before", lambda *a: ()),
    "no-recorded-decline": ("declined_at_step",
                            lambda record: (str(record.steps[-1].data["stage"]["name"]), "", ())),
    "a-receipt-for-a-later-step": ("_recorded_after", lambda *a: ()),
}


@pytest.mark.parametrize("name", list(RED))
def test_sabotage_each_condition_that_keeps_it_red(tmp_path, monkeypatch, name, examined):
    import onetrace_console.viewer.model as model
    from onetrace_console.checks import nothing_missing_state
    _require_installed()
    folder = tmp_path / name
    _emit(folder, name, *RED[name])
    examined(1, f"sabotaged rule on {name}")
    assert nothing_missing_state(folder) == "no", "before the sabotage"
    attr, broken = SABOTAGE[name]
    monkeypatch.setattr(model, attr, broken)
    assert nothing_missing_state(folder) == "not-reached", f"{attr} taken away is not what holds it red"


def test_sabotage_a_stopped_run_read_as_missing_is_caught(tmp_path, monkeypatch, examined):
    """The other way: with the rule taken away, the stopped run reads No again."""
    import onetrace_console.viewer.model as model
    from onetrace_console.checks import nothing_missing_state
    _require_installed()
    folder = tmp_path / "stopped"
    _emit(folder, "stopped", STAGES, STOPPED)
    examined(1, "sabotaged stopped run")
    assert nothing_missing_state(folder) == "not-reached"
    monkeypatch.setattr(model, "not_reached", lambda record: ())
    assert nothing_missing_state(folder) == "no"
