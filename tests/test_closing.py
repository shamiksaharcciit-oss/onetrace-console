"""Whether a run closed, and how it ended, in the record's own words: on the run's head and in its own
column of the runs list. A run with no close receipt reads "not closed", never "finished".

The runs are `tests/onetrace_runs/` (`tests/test_onetrace_runs.py`): onetrace 0.7.1's three endings,
and the same pipeline's runs in format 0.3, which hold no close receipt. Each run's words are held to
onetrace-verify 0.7's own row `the close receipt`, read from the run's stored check.
"""
from __future__ import annotations

import html
import json
import re

import pytest

from tests.test_format_04 import RUNS, _pages

WORDS = {
    ("0.7.1", "refund-closed"): "closed: by exit",
    ("0.7.1", "refund-raised"): "closed: by unhandled exception: ValueError",
    ("0.7.1", "refund-killed"): "not closed: the record ends at retrieve and holds no close",
    ("0.6.1", "refund-closed"): "not closed: the record ends at answer and holds no close",
    ("0.6.1", "refund-killed"): "not closed: the record ends at retrieve and holds no close",
    ("0.7.1", "auto-bound"): "closed: by exit",
}


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed
    _require_installed()


def _text(page: str) -> str:
    inline = re.sub(r"</?(?:span|code|strong|a)\b[^>]*>", "", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", inline)))


def _verifier_row(run, store) -> str:
    """onetrace-verify's own row `the close receipt`, its words after the dash, from the stored check."""
    report = json.loads(store.get(run.check_report))
    (row,) = [ln for ln in report["stdout"].splitlines() if "] the close receipt -- " in ln]
    return row.split("] the close receipt -- ", 1)[1].strip()


def _drawn(version: str, name: str, tmp_path):
    from onetrace_console.store import Store
    store = Store(tmp_path / version / name)
    run, pages = _pages(RUNS / version / name, store)
    return run, pages, store


@pytest.mark.parametrize("version, name", sorted(WORDS))
def test_a_run_s_head_and_its_row_say_how_it_ended_in_the_verifier_s_words(version, name, tmp_path, examined):
    run, pages, store = _drawn(version, name, tmp_path)
    want = WORDS[(version, name)]
    examined(1, f"{version} {name}'s ending")
    assert _verifier_row(run, store) == want
    #: On "What changed", or on "Proof" where the record could not be checked: it is read from the
    #: record's contents (`views.RUN_READ_FROM`).
    heads = [re.search(r'<section data-section="run-head">.*?</section>', pages[p], re.S).group(0)
             for p in ("case.html", "proof.html")]
    assert any(want in _text(h) for h in heads), [_text(h) for h in heads]
    row = re.search(r"<tr data-run=.*?</tr>", pages["the run list"], re.S).group(0)
    cell = re.search(r'<td[^>]* data-answer="closed"[^>]*>(.*?)</td>', row, re.S)
    assert cell and _text(cell.group(1)).strip() == want, row


def test_the_runs_list_has_a_column_of_its_own_for_it(tmp_path, examined):
    from onetrace_console import closing, pages
    _run, drawn, _store = _drawn("0.7.1", "refund-killed", tmp_path)
    examined(1, "runs list")
    heads = re.findall(r"<th>([^<]*)</th>", re.search(r'<table class="timeline" data-section="runs-table">.*?</thead>',
                                                     drawn["the run list"], re.S).group(0))
    assert closing.COLUMN in heads and list(pages.RUN_COLUMNS) == heads, heads
    assert heads.index(closing.COLUMN) == heads.index("How far it got") + 1


@pytest.mark.parametrize("version, name", [("0.7.1", "refund-killed"), ("0.6.1", "refund-closed")])
def test_a_run_with_no_close_receipt_never_reads_finished(version, name, tmp_path, examined):
    _run, drawn, _store = _drawn(version, name, tmp_path)
    examined(len(drawn), f"pages of {version} {name}")
    #: A step's own outcome reads "Completed." (its receipt's outcome); "finished" is said of no run here.
    said = {p: re.findall(r"\bfinished\b", _text(t), re.I) for p, t in drawn.items()}
    assert said == {p: [] for p in drawn}, said
    assert all("not closed" in _text(drawn[p]) for p in ("case.html", "the run list"))


def test_the_ending_is_kept_with_the_run_and_a_run_stored_before_it_is_read_again(tmp_path, examined):
    """Kept when the run is checked; a run whose record was derived before the ending was kept is
    derived again from its stored bytes (`checks.DERIVED`)."""
    from dataclasses import replace

    from onetrace_console import closing
    from onetrace_console.checks import DERIVED, rederive
    run, _pages_, store = _drawn("0.7.1", "refund-raised", tmp_path)
    examined(2, "kept endings")
    assert closing.read(run.ending) == {"closed": True, "ended_by": "unhandled exception: ValueError", "last": ""}
    older = replace(run, ending="", derived="derivation-10")
    store.put_run(older)
    assert DERIVED != "derivation-10"
    again = rederive(store.get_run(run.key), store)
    assert again.ending == run.ending and again.derived == DERIVED


def test_sabotage_a_not_closed_run_read_as_finished_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import closing
    monkeypatch.setattr(closing, "NOT_CLOSED", "finished at {last}")
    _run, drawn, _store = _drawn("0.7.1", "refund-killed", tmp_path)
    examined(1, "sabotaged words")
    assert re.search(r"\bfinished\b", _text(drawn["case.html"]))
    with pytest.raises(AssertionError):
        test_a_run_with_no_close_receipt_never_reads_finished("0.7.1", "refund-killed", tmp_path / "again",
                                                              lambda *a: None)
