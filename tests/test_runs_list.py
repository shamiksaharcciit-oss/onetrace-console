"""The runs list: one row per run -- the run, linked to its page; its pipeline; when it ran and when
this console received it; how far it got; and the four answers the store holds per run (records
agree, signed, committed, ran as approved), each as the run's own page says it. "Ran as approved"
reads "Couldn't check" where the run doesn't verify: the plan can't be decided then, and the run
page's own state for it is drawn in the same words.

Every row of the demo's lists is held to its run's own page: each chip's state equals that page's
rung, the link opens a page this console has, and the times and counts are the run's. Each check
has its sabotage.
"""
from __future__ import annotations

import re
from html import unescape

import pytest

ANSWERS = ("records-agree", "signed", "anchored", "approved")
#: A run page's state that the list words as another: the plan can't be decided where the run
#: doesn't verify, and the page draws that state in "Couldn't check"'s words too.
AS_LISTED = {"does-not-verify": "couldnt-check"}


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    from onetrace_console.folder_load import build_public
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("demo") / "demo"
    build_public(folder)
    return Store(folder / "store" / "store"), folder / "store" / "pages"


def row_problems(list_page: str, store, pages) -> list[str]:
    from onetrace_console.overview import pipelines, ran_at
    from onetrace_console.words import short_time
    label = {r.key: p.label for p in pipelines(store) for r in p.runs}
    out = []
    rows = re.findall(r'<tr data-run="[^"]*" data-key="([0-9a-f]+)">(.*?)</tr>', list_page, re.S)
    if not rows:
        return ["no rows"]
    for key, row in rows:
        run = store.get_run(key)
        case_path = pages / "runs" / key / "case.html"
        if f'href="runs/{key}/case.html"' not in row or not case_path.exists():
            out.append(f"{run.run_id}: no link to its page")
            continue
        #: The ladder is on "What changed", or on "Proof" for a run whose records don't hold up.
        case = case_path.read_text(encoding="utf-8") + (case_path.parent / "proof.html").read_text(encoding="utf-8")
        rungs = dict(re.findall(r'<tr data-rung="([^"]+)" data-state="([^"]+)">', case))
        for k in ANSWERS:
            got = re.search(rf'<td[^>]*data-answer="{k}"[^>]*><span class="pill \w+" data-state="([^"]+)">', row)
            if got is None or got.group(1) != AS_LISTED.get(rungs.get(k), rungs.get(k)):
                out.append(f"{run.run_id}: {k} {got.group(1) if got else None} on the list, {rungs.get(k)} on its page")
        cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        ran = ran_at(run)
        if cells[1] != label.get(key, ""):
            out.append(f"{run.run_id}: pipeline {cells[1]!r}")
        if cells[2] != (short_time(ran) if ran else "not recorded"):
            out.append(f"{run.run_id}: ran {cells[2]!r}")
        if cells[3] != short_time(run.received_at):
            out.append(f"{run.run_id}: received {cells[3]!r}")
        if not cells[4].startswith(f"{run.delivered_stages} of {run.stage_count} declared stages"):
            out.append(f"{run.run_id}: how far {cells[4]!r}")
    return out


def test_every_row_is_its_run_s_page_in_brief(demo, examined):
    store, pages = demo
    lists = sorted(pages.glob("executions-*.html"))
    rows = 0
    for page in lists:
        html = page.read_text(encoding="utf-8")
        found = len(re.findall(r'<tr data-run="', html))
        if found:
            assert row_problems(html, store, pages) == [], page.name
        rows += found
    examined(rows, "rows across the runs lists")
    every = (pages / "executions-all.html").read_text(encoding="utf-8")
    assert len(re.findall(r'<tr data-run="', every)) == len(store.runs())
    assert "Ran as approved" in _text(re.search(r'<table class="timeline" data-section="runs-table">.*?</thead>',
                                                every, re.S).group(0))


def test_sabotage_a_row_that_strays_from_its_run_is_named(demo, examined):
    store, pages = demo
    every = (pages / "executions-all.html").read_text(encoding="utf-8")
    key = re.search(r'<tr data-run="[^"]*" data-key="([0-9a-f]+)">', every).group(1)
    row = re.search(rf'<tr data-run="[^"]*" data-key="{key}">.*?</tr>', every, re.S).group(0)
    state = re.search(r'data-answer="signed"[^>]*><span class="pill \w+" data-state="([^"]+)"', row).group(1)
    other = "no" if state != "no" else "yes"
    planted = {
        "a chip its page doesn't say": every.replace(row, row.replace(
            f'data-answer="signed"><span class="pill', f'data-answer="signed"><span class="pill', 1).replace(
            f'data-state="{state}">', f'data-state="{other}">', 1), 1),
        "a link to nowhere": every.replace(f'href="runs/{key}/case.html"', 'href="runs/nowhere/case.html"', 1),
    }
    examined(len(planted), "planted pages")
    for name, bad in planted.items():
        assert bad != every, name
        assert row_problems(bad, store, pages), name


def test_a_list_with_no_run_says_so_in_one_grey_line(demo, examined):
    """A count at zero opens a list with no run: no empty table, one line, its sentence kept."""
    from onetrace_console.pages import NO_RUNS
    store, pages = demo
    empty = [p for p in sorted(pages.glob("executions-*.html"))
             if not re.findall(r'<tr data-run="', p.read_text(encoding="utf-8"))]
    examined(len(empty), "lists with no run")
    assert empty, "the demo has counts at zero"
    for p in empty:
        html = p.read_text(encoding="utf-8")
        assert f'<p class="zero" data-section="no-runs">{NO_RUNS}</p>' in html, p.name
        assert "<table" not in re.search(r'<section data-section="executions">.*?</section>', html, re.S).group(0)
        assert "none of the" in _text(html), "its sentence kept"


#: Every state the run page's plan rung can decide (`viewer.model.Approval`), and the list's.
APPROVAL_STATES = {"approved": "yes", "departed": "no", "edges-mismatch": "no", "no-plan": "not-declared",
                   "not-a-graph-run": "not-a-graph-run", "cant-check": "couldnt-check", "no-paths": "couldnt-check",
                   "does-not-verify": "couldnt-check", "couldnt-check": "couldnt-check",
                   "not-checked": "not-checked"}


def test_ran_as_approved_is_listed_in_every_state_the_run_page_decides(examined):
    """The seven states and the console's two, each listed in the run page's state words; wherever
    the plan can't be decided, "Couldn't check" -- never "Yes" without the run page's own Yes."""
    import inspect

    from onetrace_console import tones
    from onetrace_console.pages import _APPROVED_STATE
    from onetrace_console.viewer.model import Approval
    from onetrace_console.viewer.sentences import template
    named = set(re.findall(r"`([a-z-]+)`", inspect.getdoc(Approval).split("is one of:")[1].split("`detail`")[0]))
    examined(len(named), "plan rung states")
    assert named == set(APPROVAL_STATES), named ^ set(APPROVAL_STATES)
    assert {k: v for k, v in _APPROVED_STATE.items() if k} == APPROVAL_STATES
    for state in set(APPROVAL_STATES.values()):
        assert template("rung.state." + state.replace("-", "_")), state
        assert state in tones.RUNG, state
    assert [k for k, v in _APPROVED_STATE.items() if v == "yes"] == ["approved"]


def test_sabotage_a_run_that_does_not_verify_listed_as_approved_is_named(demo, monkeypatch, examined):
    from onetrace_console import pages as pages_module
    from onetrace_console.pages import runs_table
    store, pages = demo
    every = (pages / "executions-all.html").read_text(encoding="utf-8")
    run = next(r for r in store.runs() if r.approved == "approved")
    monkeypatch.setitem(pages_module._APPROVED_STATE, "approved", "no")
    bad = re.sub(r'<table class="timeline" data-section="runs-table">.*?</table>', lambda m: re.search(
        r'<table class="timeline" data-section="runs-table">.*?</table>', runs_table(store.runs(), store), re.S).group(0),
        every, count=1, flags=re.S)
    examined(1, "planted list")
    assert bad != every and any(f"{run.run_id}: approved no on the list, yes on its page" == p
                                for p in row_problems(bad, store, pages))
