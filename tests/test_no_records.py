"""Release 1's "no authorization records", wherever authorization would appear.

    It is never counted as a pass. It is never blank. The ladder rung reads "No records ·
    needs an AADP policy engine". Tests first: a run with no onedoor export shows "no
    records" in each of those places.

The run detail is the viewer's case page, rendered through the vendored viewer: its evidence
ladder and its Policy section. The authorization page (board 3) is batch 3, and this console
has no receipt page (board 5) yet, so those two places are not asserted here.
"""
from __future__ import annotations

import re
from html import unescape

import pytest

from onetrace_console.pages import CASE, render_execution
from tests.test_pages import GENERATED_AT, checked  # noqa: F401  (fixture)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def _section(page: str, name: str) -> str:
    m = re.search(rf'<section data-section="{name}">(.*?)</section>', page, re.S)
    assert m, f"no {name} section on the run page"
    return m.group(1)


@pytest.fixture
def case_page(checked, store) -> str:  # noqa: F811
    assert not store.decision_export_records(), "the store holds no onedoor export"
    return render_execution(checked, store, generated_at=GENERATED_AT).pages[CASE]


def test_the_run_ladder_reads_no_records_for_authorization(case_page, examined):
    ladder = _section(case_page, "ladder")
    rows = re.findall(r'<tr data-rung="([^"]+)" data-state="([^"]+)">(.*?)</tr>', ladder, re.S)
    examined(len(rows), "rungs of a stored run's evidence ladder")
    rung = {name: (state, _text(cells)) for name, state, cells in rows}
    state, words = rung["authorized"]
    assert state == "no-records"
    assert words == "Action authorized, effect confirmed No records · This console does not record authorization."
    assert "No records · This console does not record authorization." in _text(ladder), "the fixed phrase, whole"


def test_no_records_is_never_counted_as_a_pass(case_page):
    ladder = _section(case_page, "ladder")
    states = dict(re.findall(r'<tr data-rung="([^"]+)" data-state="([^"]+)">', ladder))
    assert states["authorized"] != "yes"
    assert "authorized" not in [r for r, s in states.items() if s == "yes"]


def test_the_run_detail_says_no_authorization_records_and_is_never_blank(case_page):
    policy = _text(_section(case_page, "policy"))
    assert "No authorization records for this run." in policy
    assert "The record stops here" not in policy
