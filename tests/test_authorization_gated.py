"""A run's Authorization page where the run declares a gated step or cites a decision (console 0.8.0).

One row per gated step, from the record as onetrace 0.5 to 0.7 writes it: the step; its decision
references; its decisions as recorded, in call order (`permit`, `deny`, `propose`); the permit, if any,
as its payload states it; and the step's outcome as recorded, with onetrace-verify's own words where its
row says the step acted on a decision that did not permit it. Below, the verifier's five `decisions:`
rows. The page says what it does not claim. Nothing is inferred: the words are the record's members and
the verifier's rows.

Read from four runs recorded with onetrace 0.7.1 (`tools/make_authorization_runs.py`, committed in
`tests/gated_runs_071/`): a permitted step, a denied step that did not run, a denied step
that ran, and a step held and then approved. A run with no gated step keeps the "No records" page
(`tests/test_authorization_page.py`). Recipient-confirmation rows are not read yet: a 0.7 run shows none.
"""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "gated_runs_071"
GENERATED_AT = "2026-11-09T00:00:00+00:00"


def _text(h: str) -> str:
    #: A tag's place reads as a space, less before a comma that follows it.
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", h)).split()).replace(" ,", ",")


@pytest.fixture(scope="module")
def gated(tmp_path_factory):
    """Each fixture run delivered and checked as a console loads a folder, with the files beside it."""
    from onetrace_console.config import Config
    from onetrace_console.folder_load import deliver_one
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store

    root = tmp_path_factory.mktemp("gated")
    shutil.copytree(FIXTURES, root / "runs")
    store = Store(root / "store")
    out = {}
    for run_dir in sorted(p for p in (root / "runs").iterdir() if p.is_dir()):
        loaded = deliver_one(run_dir, store, Config())
        assert loaded.run is not None, loaded
        pages = render_execution(loaded.run, store, generated_at=GENERATED_AT).pages
        out[run_dir.name] = pages["authorization.html"]
    return out


def _row(page: str, step: str = "pay") -> str:
    found = re.search(rf'<tr data-step="{step}"[^>]*>.*?</tr>', page, re.S)
    assert found, page[-3000:]
    return found.group(0)


def test_each_fixture_s_page_has_one_row_for_its_gated_step(gated, examined):
    examined(len(gated), "authorization pages")
    assert sorted(gated) == ["auth-denied-not-run", "auth-denied-ran", "auth-held-then-approved", "auth-permitted"]
    for name, page in gated.items():
        assert 'data-state="gated"' in page and 'data-state="no-records"' not in page, name
        assert len(re.findall(r'<tr data-step="', page)) == 1, name
        assert [html.unescape(t) for t in re.findall(r"<th[^>]*>([^<]*)</th>", page)[:5]] == [
            "Step",
            "Decision reference",
            "Decision, as recorded",
            "Permit",
            "The step's outcome, as recorded",
        ], name


def test_a_permitted_step(gated, examined):
    row = _row(gated["auth-permitted"])
    examined(1, "row")
    said = _text(row)
    assert 'data-verdicts="permit"' in row and 'data-outcome="ok"' in row
    assert "auth-permitted/pay/1" in said and "permit" in said
    assert "https://payments-approver.example/issuer" in said and "no permit recorded" not in said
    assert "onetrace-verify on this step" not in said


def test_a_denied_step_that_did_not_run(gated, examined):
    row = _row(gated["auth-denied-not-run"])
    examined(1, "row")
    said = _text(row)
    assert 'data-verdicts="deny"' in row and 'data-outcome="refused"' in row
    assert "no permit recorded" in said and "onetrace-verify on this step" not in said


def test_a_denied_step_that_ran_reads_so_in_the_verifier_s_words(gated, examined):
    row = _row(gated["auth-denied-ran"])
    examined(1, "row")
    said = _text(row)
    assert 'data-verdicts="deny"' in row and 'data-outcome="ok"' in row
    assert (
        "onetrace-verify on this step: pay: acted on a decision whose last verdict is 'deny', not 'permit'" in said
    ), said


def test_a_step_held_then_approved_shows_both_decisions_in_call_order(gated, examined):
    row = _row(gated["auth-held-then-approved"])
    examined(1, "row")
    said = _text(row)
    assert 'data-verdicts="propose permit"' in row and 'data-outcome="ok"' in row
    assert "propose, then permit" in said
    assert said.index("auth-held-then-approved/pay/1") < said.index("auth-held-then-approved/pay/2")


def test_the_verifier_s_five_rows_are_below_in_its_words(gated, examined):
    examined(len(gated), "pages")
    for name, page in gated.items():
        rows = re.findall(r'<li data-onedoor-row="([^"]+)">', page)
        assert len(rows) == 5, name
    ran = _text(gated["auth-denied-ran"])
    assert "FAIL decisions: a step that acted cites a permitting decision" in ran


def test_the_page_says_what_it_does_not_claim(gated, examined):
    from onetrace_console.authorization import NON_CLAIMS

    examined(len(gated), "pages")
    for page in gated.values():
        assert NON_CLAIMS in _text(page)
        assert "No authorization records for this run" not in page


def test_a_0_7_run_shows_no_recipient_confirmation_rows(gated, examined):
    examined(len(gated), "pages")
    for page in gated.values():
        assert 'data-section="confirmations"' not in page and "recipient" not in _text(page).lower()


def test_the_page_is_read_only_so_a_static_export_s_is_too(gated, examined):
    examined(len(gated), "pages")
    for name, page in gated.items():
        section = re.search(r'<section data-section="authorization".*?</section>', page, re.S).group(0)
        assert "<form" not in page and "<input" not in page, name
        assert "<button" not in section and "<script" not in section, name


def test_each_cell_is_labelled_by_its_column_for_a_narrow_screen(gated, examined):
    from tests.test_labelled_tables import label_problems

    examined(len(gated), "pages")
    for name, page in gated.items():
        table = re.search(r'<table class="authorization">.*?</table>', page, re.S).group(0)
        assert 'class="scroll-x"' in page and label_problems(table, table.replace(' scope="col"', "")) == [], name
