"""The evidence ladder's "Action authorized, effect confirmed" row (`pages.authorization_rung`).

Where a run declares a gated step or cites a decision, the row reads the verifier's `decisions:` rows:
their combined result (any FAIL is No, all PASS is Yes, otherwise couldn't check), the counts as the
verifier words them, each row that is not PASS named, and a link to the run's Gated steps section on
the same view. Only where a run declares no gated step and cites no decision does it read "No records".

1. p8-42, its five rows PASS: Yes.
2. p8-49, planted (paid after a deny): No, at "a step that acted cites a permitting decision".
3. p1-02, no gated step: No records, and no link.
4. The Overview's row says where the row is read, not that the console records no authorization.
"""
from __future__ import annotations

import html
import re

import pytest


def _text(h: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", h)).split())


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    return folder, store, {r.run_id: r for r in store.runs()}


def _row(folder, run) -> tuple[str, str, str]:
    """(the view holding the row, its state, the row's HTML), from whichever of the run's two views has it."""
    for view in ("case.html", "proof.html"):
        page = (folder / "store" / "pages" / "runs" / run.key / view).read_text(encoding="utf-8")
        m = re.search(r'<tr data-rung="authorized" data-state="([^"]*)">.*?</tr>', page, re.S)
        if m:
            return page, m.group(1), m.group(0)
    raise AssertionError(f"{run.run_id}: no authorization row on either view")


def test_a_gated_run_whose_decision_rows_pass_reads_yes(demo, examined):
    folder, store, runs = demo
    page, state, row = _row(folder, runs["p8-42-invoice-tolerance-2pct"])
    examined(1, "run")
    assert state == "yes", state
    said = _text(row)
    assert "Yes · onetrace-verify's decisions rows, as the Gated steps section lists them: 5 PASS" in said, said
    assert "No records" not in said and "does not record authorization" not in said
    assert '<a href="#gated-steps" data-link="gated-steps">Gated steps</a>' in row
    assert 'id="gated-steps"' in page, "the link's section is not on the same view"


def test_a_planted_run_reads_no_at_the_row_that_failed(demo, examined):
    folder, store, runs = demo
    page, state, row = _row(folder, runs["p8-49-invoice-paid-on-deny"])
    examined(1, "run")
    assert state == "no", state
    said = _text(row)
    assert said.startswith("Action authorized, effect confirmed No · ")
    assert "1 FAIL" in said and "FAIL decisions: a step that acted cites a permitting decision" in said, said
    assert 'id="gated-steps"' in page


def test_a_run_with_no_gated_step_reads_no_records(demo, examined):
    from onetrace_console.pages import declares_authorization
    folder, store, runs = demo
    run = runs["p1-02-baseline-set2"]
    page, state, row = _row(folder, run)
    examined(1, "run")
    assert not declares_authorization(run, store)
    assert state == "no-records", state
    assert "No records · This console does not record authorization." in _text(row)
    assert "data-link=\"gated-steps\"" not in row


def test_the_combined_result_is_the_verifier_s(examined):
    """Any FAIL is No, all PASS is Yes, otherwise couldn't check: each state from its rows."""
    from onetrace_console.pages import AUTHORIZED_STATES
    examined(3, "results")
    assert AUTHORIZED_STATES == {"PASS": ("yes", "rung.state.yes"), "FAIL": ("no", "rung.state.no"),
                                 "NOT-RUN": ("couldnt-check", "rung.state.couldnt_check")}


def test_the_overview_says_where_the_row_is_read(demo, examined):
    from onetrace_console.words import AUTHORIZED_OVERVIEW
    folder, _store, _runs = demo
    pages = [p for p in (folder / "store" / "pages").glob("*.html")
             if 'data-rung="authorized"' in p.read_text(encoding="utf-8")]
    examined(len(pages), "pages with the all-runs row")
    assert pages
    for p in pages:
        row = re.search(r'<tr data-rung="authorized">.*?</tr>', p.read_text(encoding="utf-8"), re.S).group(0)
        assert AUTHORIZED_OVERVIEW in html.unescape(row) and "does not record authorization" not in row, p.name
