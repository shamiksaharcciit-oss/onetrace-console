"""Authorization, reachable from every run that has a gated step and from every page (`authorization_list`).

Read on the public demo as built: p8-50 (its gated step carried a permit for another amount; its record does not hold
up), p8-49 (paid on a decision that denied it) and p1-01 (no gated step).

- A run with a gated step has an Authorization tab with the count, on each of its pages; a run without one has none.
- p8-50's Authorization page renders what the record says, under the same "does not hold up" lines as its other views.
- "The decisions, as checked" leads to the run's Authorization page.
- Proof's Policy line counts the record's gated steps where it said "No authorization records for this run." beside
  them; a run with none still says that.
- The console's Authorization page lists every run with a gated step, its gated steps, its decisions and
  onetrace-verify's decision rows in one word; with none, "No authorization records in this console".
- The sidebar holds Authorization after Incidents on every page; the Runs list marks a run with a gated step; the
  Overview names p8-50 as the run to open; the page is a viewer's route, as the Runs list is.
"""

from __future__ import annotations

import json
import re
from html import unescape

from tests.test_export_static import exported, source  # noqa: F401 - fixtures, requested by name
from tests.test_public_mode import built, served  # noqa: F401 - fixtures, requested by name
from tests.test_run_page_order import _pages_of


def _run_folder(shared_demo, run_id):
    root = shared_demo["folder"] / "store" / "pages" / "runs"
    for case in root.glob("*/case.html"):
        title = re.search(r"<title>(.*?)</title>", case.read_text(encoding="utf-8"), re.S)
        if title and title.group(1).strip().endswith(run_id):
            return case.parent
    raise AssertionError(run_id)


def test_a_run_with_a_gated_step_has_its_tab_with_the_count_on_each_of_its_pages(shared_demo, examined):
    folder = _run_folder(shared_demo, "p8-50-invoice-permit-other-amount")
    pages = sorted(
        p for p in folder.glob("*.html") if 'aria-label="This run\'s pages"' in p.read_text(encoding="utf-8")
    )
    examined(len(pages), "p8-50's pages with the run's tabs")
    assert len(pages) >= 4, [p.name for p in pages]
    for p in pages:
        #: One tab with the count on each page: among the views' tabs where the page has them, else the run's own.
        rows = re.findall(
            r'<nav (?:class="tabs" aria-label="This run\'s pages"|data-section="views"[^>]*)>(.*?)</nav>',
            p.read_text(encoding="utf-8"),
            re.S,
        )
        tabs = [a for row in rows for a in re.findall(r'<a href="authorization\.html"[^>]*>([^<]*)</a>', row)]
        assert tabs == ["Authorization · 1 gated step"], (p.name, tabs)
    plain = _run_folder(shared_demo, "p1-01-baseline-set1")
    assert "Authorization · " not in (plain / "case.html").read_text(encoding="utf-8")


def test_a_failing_record_s_authorization_page_shows_what_it_says_under_the_same_lines(shared_demo, examined):
    page = (_run_folder(shared_demo, "p8-50-invoice-permit-other-amount") / "authorization.html").read_text(
        encoding="utf-8"
    )
    examined(1, "page")
    withheld = page.index('data-section="withheld"')
    integrity = page.index('data-section="integrity"')
    gated = page.index("approve_payment")
    assert withheld < integrity < gated
    assert "These rows come from a record that does not hold up." in unescape(page)


def test_the_decisions_as_checked_lead_to_the_authorization_page(shared_demo, examined):
    page = _pages_of(shared_demo, "p8-50-invoice-permit-other-amount")["case.html"]
    examined(1, "page")
    section = re.search(r'<section data-section="onedoor-rows".*?</section>', page, re.S).group(0)
    assert '<a href="authorization.html">Open the run\'s Authorization page</a>' in unescape(section)


def test_proof_s_policy_counts_the_gated_steps_and_a_run_with_none_still_says_none(shared_demo, examined):
    gated = _pages_of(shared_demo, "p8-50-invoice-permit-other-amount")["proof.html"]
    none = _pages_of(shared_demo, "p1-01-baseline-set1")["proof.html"]
    examined(2, "Proof pages")
    policy = re.search(r'<section data-section="policy">.*?</section>', gated, re.S).group(0)
    assert "No authorization records for this run" not in policy
    assert "The record names 1 gated step: the run's Authorization page shows each, with its decision." in unescape(
        policy
    )
    assert "No authorization records for this run" in re.search(
        r'<section data-section="policy">.*?</section>', none, re.S
    ).group(0)


def test_the_console_s_page_lists_each_run_with_a_gated_step_and_its_result(shared_demo, examined):
    page = (shared_demo["folder"] / "store" / "pages" / "authorization.html").read_text(encoding="utf-8")
    rows = re.findall(r'<tr data-run="[0-9a-f]{64}">(.*?)</tr>', page, re.S)
    examined(len(rows), "rows")
    by_id = {
        re.search(r'data-words="record">([^<]+)<', r).group(1): re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        for r in rows
    }
    assert "p8-50-invoice-permit-other-amount" in by_id and "p1-01-baseline-set1" not in by_id
    cells = by_id["p8-50-invoice-permit-other-amount"]
    assert cells[2] == "1" and cells[4] == "FAIL", cells
    assert all(c[4] in ("PASS", "FAIL", "couldn&#x27;t check") for c in by_id.values()), by_id


def test_with_no_gated_step_the_page_says_so(tmp_path, examined):
    from onetrace_console import authorization_list
    from onetrace_console.store import Store

    examined(1, "page")
    page = authorization_list.render(Store(tmp_path / "store"), generated_at="2026-11-16T00:00:00+00:00")
    assert "No authorization records in this console" in page and "<table" not in page


def test_the_result_is_fail_on_any_failing_row_pass_only_on_all_passing_and_couldn_t_check_otherwise(examined):
    from onetrace_console.authorization_list import COULDNT, FAIL, PASS, result_of

    examined(5, "row sets")
    assert result_of([{"result": "PASS"}, {"result": "FAIL"}]) == FAIL
    assert result_of([{"result": "PASS"}, {"result": "PASS"}]) == PASS
    assert result_of([{"result": "PASS"}, {"result": "NOT-RUN"}]) == COULDNT
    assert result_of([]) == COULDNT
    assert result_of([{"result": "NOT-RUN"}]) == COULDNT


def test_the_sidebar_holds_authorization_after_incidents_on_every_page(examined):
    from onetrace_console import frame

    labels = [label for label, _h, _r in frame.items(False)]
    examined(2, "sidebars")
    assert labels[labels.index("Incidents") + 1] == "Authorization"
    assert [label for label, _h, _r in frame.items(True)][-2:] == ["Authorization", "Policy"]


def test_the_runs_list_marks_a_run_with_a_gated_step(shared_demo, examined):
    from onetrace_console.runs_page import page as runs_page

    index = json.loads((shared_demo["folder"] / "store" / "run_index.json").read_text(encoding="utf-8"))
    entry = next(r for r in index["runs"] if r["run_id"] == "p8-50-invoice-permit-other-amount")
    examined(2, "the index's entry, the page")
    assert entry["list"]["gated"] == 1
    page = runs_page(index, {"q": "pipeline:P8"}, public=True)
    assert 'data-gated="1"' in page and "1 gated step</a>" in page
    #: On a line of its own under the run's link, so neither crowds the other's target.
    assert '</a><br><a class="pill neu" data-gated="1"' in page


def test_the_overview_names_the_run_to_open(shared_demo, examined):
    home = (shared_demo["folder"] / "store" / "pages" / "home.html").read_text(encoding="utf-8")
    examined(1, "page")
    line = re.search(r'<p data-section="authorization-example">(.*?)</p>', home, re.S)
    assert line and "p8-50-invoice-permit-other-amount" in line.group(1) and "/authorization.html" in line.group(1)


def test_the_page_is_read_by_whoever_reads_the_runs_list(examined):
    from onetrace_console import roles

    examined(2, "routes")
    assert roles.required_role("GET", "/authorization.html", rel_for_get="authorization.html") == roles.required_role(
        "GET", "/comparisons.html", rel_for_get="comparisons.html"
    )


def test_a_static_export_holds_the_page_and_the_tab(exported, examined):  # noqa: F811
    root = exported if not isinstance(exported, tuple) else exported[0]
    page = next(p for p in sorted(root.rglob("authorization.html")) if p.parent == root or p.parent.name == "pages")
    examined(1, "exported page")
    text = page.read_text(encoding="utf-8")
    assert "<h1>Authorization</h1>" in text


def test_a_public_console_serves_the_page(served, examined):  # noqa: F811
    from tests.test_search_engines import _get

    base, _folder, _c = served
    examined(1, "served page")
    status, kind, page = _get(base, "/authorization.html")
    assert status == 200 and kind.startswith("text/html") and "p8-50-invoice-permit-other-amount" in page
