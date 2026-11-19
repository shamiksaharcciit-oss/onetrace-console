"""Keyboard and narrow-screen paths on Runs and Investigate.

- **Skip links.** "Skip to the runs" on the Runs page and "Skip to the first difference" on Investigate's What changed
  tab are each the page's first focusable item, linking to the part they name (the table; the short answer), which the page holds once. A page with
  no such part has no skip link.
- **The tab row at 760 px and below** is one row scrolling sideways inside its own labelled region (`nav`, with its
  label), never wrapping, and the layout check holds it as such a region.
- **The layout check** holds each Runs kind and Investigate's first tab to its skip link first in tab order, and
  Investigate's short answer to the first 900 px at every width it reads.
"""

from __future__ import annotations

import re

import pytest


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console import run_index
    from onetrace_console.store import Store

    folder = shared_demo["folder"]
    index = run_index.read(folder / "store")
    assert index is not None
    return Store(folder / "store" / "store"), index, folder / "store" / "pages"


def _first_focusable(page: str) -> str:
    body = page[page.index("<body>") :]
    m = re.search(r"<(?:a\b[^>]*\bhref=|button\b|input\b|select\b|textarea\b|summary\b)[^>]*>", body)
    assert m, "nothing focusable"
    return m.group(0)


def test_the_runs_page_s_first_focusable_item_skips_to_the_runs(demo, examined):
    from onetrace_console import runs_page

    _store, index, _pages = demo
    kinds = ({}, {"pipeline": "P1"}, {"page": "2"}, {"pipeline": "P1", "a": "x", "b": "y"})
    examined(len(kinds), "Runs pages")
    for params in kinds:
        page = runs_page.page(index, params, public=True)
        assert _first_focusable(page) == '<a class="skip-link" href="#the-runs">', params
        assert "Skip to the runs</a>" in page and page.count('id="the-runs"') == 1, params
    none = runs_page.page(index, {"q": "verdict:NOPE"}, public=True)
    assert "skip-link" not in none and 'id="the-runs"' not in none


def test_investigate_s_what_changed_skips_to_the_first_difference(demo, examined):
    store, _index, pages = demo
    seen = 0
    for c in store.comparisons():
        what = (pages / "diff" / f"{c.key}.html").read_text(encoding="utf-8")
        proof = (pages / "diff" / f"{c.key}-proof.html").read_text(encoding="utf-8")
        assert "skip-link" not in proof, c.key
        if 'data-short="headline"' not in what:
            assert "skip-link" not in what, c.key
            continue
        seen += 1
        assert _first_focusable(what) == '<a class="skip-link" href="#first-difference">', c.key
        assert what.count('id="first-difference"') == 1, c.key
        assert '<section data-section="short-answer" class="short-answer" id="first-difference">' in what, c.key
    examined(seen, "comparisons' What changed tabs")
    assert seen >= 10


def test_the_tab_row_scrolls_sideways_in_its_own_region_when_narrow(examined):
    from onetrace_console.views import VIEWS_CSS, tabs_row

    examined(1, "tab row")
    narrow = re.search(r"@media \(max-width:760px\)\{(.*?)\}\}", VIEWS_CSS, re.S)
    assert narrow, "no narrow rule for the tab row"
    assert "nav[data-section=views]{flex-wrap:nowrap;overflow-x:auto" in narrow.group(1)
    assert "white-space:nowrap" in narrow.group(1)
    assert 'aria-label="This page\'s views"' in tabs_row([("A", "a.html"), ("B", "b.html")], "A")


def test_the_layout_check_holds_the_skip_links_and_the_short_answer(examined):
    from tools import layout_check as lc

    examined(len(lc.SKIPS), "kinds with a skip link")
    assert set(lc.RUNS_PAGES) <= set(lc.SKIPS) and set(lc.RUNS_PAGES) <= set(lc.KINDS)
    assert lc.SKIPS["comparison-line"] == "Skip to the first difference"
    assert (
        lc.ANSWER_WITHIN == 900
        and lc.ANSWER_FROM_WIDTH == 0
        and set(lc.ANSWER_KINDS) == {"comparison-line", "comparison-graph"}
    )
    assert "nav[data-section=views]" in lc.SCROLL_ALLOWED
    assert "first: first, answer: answer" in lc.PROBE
