"""Investigate: a comparison's pages, at their same addresses, titled "Investigate · A → B", with one row of tabs.

- The tabs: What changed (`<key>.html`), Proof (`<key>-proof.html`), Text diff (`<key>-text.html`, only where the
  comparison has one shown) and Authorization (`<key>-authorization.html`, new). Each is a page of its own, linked with
  no script, the current one marked with `aria-current`.
- The pair's Authorization tab: both runs' gated steps side by side, one row a step, the first difference's step
  first; where neither run declares a gated step or cites a decision, one sentence saying so, never a pass. It reads
  the record's own rows only, so a console with the onedoor extension off (every public console) draws it the same.
"""

from __future__ import annotations

import re
from html import escape, unescape

import pytest


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store

    folder = shared_demo["folder"]
    return Store(folder / "store" / "store"), folder / "store" / "pages"


def _tabs(html: str) -> list[tuple[str, str, bool]]:
    """(words, href, current) for each link in the page's one row of view tabs."""
    rows = re.findall(r'<nav data-section="views"[^>]*>(.*?)</nav>', html, re.S)
    assert len(rows) == 1, "not exactly one row of tabs"
    return [
        (unescape(w), unescape(h), bool(c))
        for h, c, w in re.findall(r'<a href="([^"]+)"( aria-current="page")?>([^<]+)</a>', rows[0])
    ]


def _want(c, pages) -> list[tuple[str, str]]:
    text = (pages / "diff" / f"{c.key}-text.html").exists()
    return (
        [("What changed", f"{c.key}.html"), ("Proof", f"{c.key}-proof.html")]
        + ([("Text diff", f"{c.key}-text.html")] if text else [])
        + [("Authorization", f"{c.key}-authorization.html")]
    )


def _title(c, store) -> str:
    from onetrace_console.words import shown_name

    a, b = store.get_run(c.run_a), store.get_run(c.run_b)
    return f"Investigate · {shown_name(a.run_id)} → {shown_name(b.run_id)}"


def test_every_comparison_page_is_titled_investigate_a_to_b(demo, examined):
    store, pages = demo
    seen = 0
    for c in store.comparisons():
        want = _title(c, store)
        for _words, href in _want(c, pages):
            html = (pages / "diff" / href).read_text(encoding="utf-8")
            seen += 1
            assert f"<title>{escape(want, quote=False)}</title>" in html, href
        for href in (f"{c.key}.html", f"{c.key}-proof.html", f"{c.key}-authorization.html"):
            html = (pages / "diff" / href).read_text(encoding="utf-8")
            assert f"<h1>{escape(want, quote=False)}</h1>" in html, href
            assert "<h1>Diff</h1>" not in html, href
    examined(seen, "comparison pages")
    assert seen > 40


def test_each_comparison_page_carries_one_row_of_tabs_its_own_marked(demo, examined):
    store, pages = demo
    seen = texts = 0
    for c in store.comparisons():
        want = _want(c, pages)
        texts += any(w == "Text diff" for w, _h in want)
        for words, href in want:
            got = _tabs((pages / "diff" / href).read_text(encoding="utf-8"))
            seen += 1
            assert [(w, h) for w, h, _c in got] == want, href
            assert [w for w, _h, current in got if current] == [words], href
    examined(seen, "comparison pages' tab rows")
    #: Both kinds are in the demo: with a text diff shown, and without.
    assert 0 < texts < len(store.comparisons())


def test_the_pair_s_authorization_tab_draws_both_runs_by_gated_step(demo, examined):
    """On the demo, a public console with the onedoor extension off: each step from the record's own rows."""
    from onetrace_console import authorization, run_index
    from onetrace_console.pages import _authorization_inputs

    store, pages = demo
    gated = 0
    with store.reading():
        for c in store.comparisons():
            html = (pages / "diff" / f"{c.key}-authorization.html").read_text(encoding="utf-8")
            sides = []
            for k in (c.run_a, c.run_b):
                inputs = _authorization_inputs(store.get_run(k), store)
                sides.append([e["step"] for e in authorization.gated_rows(inputs["manifest"], inputs["steps"])])
            first = (run_index.first_difference(c, store) or {}).get("steps") or []
            if not any(sides):
                assert 'data-state="none"' in html and authorization.NEITHER in unescape(html), c.key
                assert 'data-state="gated"' not in html
                continue
            gated += 1
            rows = re.findall(r'<tr data-step="([^"]+)"', html)
            assert rows == authorization.pair_order(sides[0], sides[1], first), c.key
            for step in rows:
                row = re.search(rf'<tr data-step="{re.escape(step)}".*?</tr>', html, re.S).group(0)
                for side, steps in zip(("a", "b"), sides, strict=True):
                    cell = re.search(rf'<td[^>]*\bdata-side="{side}"[^>]*>(.*?)</td>', row, re.S)
                    assert cell, (c.key, step, side)
                    assert 'data-label="Baseline"' in row and 'data-label="Candidate"' in row, (c.key, step)
                    if step not in steps:
                        assert authorization.NOT_IN_RUN in unescape(cell.group(1)), (c.key, step, side)
            assert authorization.NOTE in unescape(html)
    examined(gated, "pairs with a gated step")
    assert gated >= 2


def test_the_first_difference_s_step_comes_first_then_each_run_s_order(examined):
    from onetrace_console.authorization import pair_order

    examined(4, "orders")
    assert pair_order(["x", "y", "z"], ["y", "w"], ["z"]) == ["z", "x", "y", "w"]
    assert pair_order(["x", "y"], ["y", "x"], []) == ["x", "y"]
    assert pair_order([], ["w"], ["q"]) == ["w"]
    assert pair_order(["a"], ["a"], ["a", "b"]) == ["a"]


def test_a_pair_with_no_gated_step_says_so_and_is_never_a_pass(demo, examined):
    from onetrace_console import authorization

    store, _pages = demo
    c = store.comparisons()[0]
    with store.reading():
        html = authorization.render_pair_authorization(
            c, store, generated_at="2026-01-01T00:00:00Z", sides=([], []), first=[], tabs=""
        )
    examined(1, "pair with no gated step")
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    assert authorization.NEITHER in text and 'data-state="none"' in html
    assert not re.search(r"\b(pass|passed|PASS)\b", text.replace(authorization.NOTE, ""))


#: A run's three tabs: its page's two views and its Authorization page, each at its same address.
RUN_TABS = [("What changed", "case.html"), ("Proof", "proof.html"), ("Authorization", "authorization.html")]
_TAB_COUNT = re.compile(r" · \d+ gated steps?$")


def _drawn(store, pages) -> list:
    """The runs drawn as runs: a run whose record cannot be read or is incomplete has pages saying so, with no tabs."""
    return [
        r for r in store.runs() if 'data-section="views"' in (pages / "runs" / r.key / "case.html").read_text("utf-8")
    ]


def test_a_run_s_authorization_is_its_third_tab_at_its_address(demo, examined):
    store, pages = demo
    runs = _drawn(store, pages)
    examined(len(runs) * len(RUN_TABS), "runs' pages")
    assert len(runs) > 40
    for run in runs:
        for words, href in RUN_TABS:
            got = _tabs((pages / "runs" / run.key / href).read_text(encoding="utf-8"))
            #: The Authorization tab carries its count of gated steps, where the run has any.
            got = [(_TAB_COUNT.sub("", w), h, c) for w, h, c in got]
            assert [(w, h) for w, h, _c in got] == RUN_TABS, (run.run_id, href)
            assert [w for w, _h, current in got if current] == [words], (run.run_id, href)


def test_a_run_page_s_what_changed_is_under_its_head_above_the_case(demo, examined):
    """It moves to the top as it was, the rest of the page in its order; a held comparison is opened as Investigate,
    with its short answer."""
    from onetrace_console import what_changed
    from onetrace_console.render import short_headline

    store, pages = demo
    runs = _drawn(store, pages)
    held = 0
    with store.reading():
        for run in runs:
            case = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
            head = case.index('data-section="run-head"')
            tabs = case.index('<nav data-section="views"')
            at = case.index('<section data-section="what-changed"')
            assert head < tabs < at, run.run_id
            for later in ('data-section="case"', 'data-section="ladder"', 'data-section="reproduce"'):
                if later in case:
                    assert at < case.index(later), (run.run_id, later)
            sec = case[at : case.index("</section>", at)]
            got = what_changed.choose(run, store, public=True)
            c = what_changed.held(store, got[0].key, run.key) if got else None
            if c is None:
                continue
            held += 1
            assert re.search(r'data-what-changed="open">Investigate</a>', sec), run.run_id
            said = short_headline(c, store)
            if said:
                answer = re.search(r'<span data-what-changed="answer">(.*?)</span>', sec, re.S)
                assert answer and unescape(re.sub(r"<[^>]+>", "", answer.group(1))) == said, run.run_id
    examined(held, "runs whose What changed? opens a held comparison")
    assert held >= 5
