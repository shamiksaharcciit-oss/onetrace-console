"""The text diff on a page of its own, two panes (the TextDiff board).

Every comparison of the public demo whose text diff was shown has the page, and its Diff page's
text-diff section links to it; the page says only what the stored document says: its title names
the first difference's stage, the left pane lists each output from the first difference on in the
SDK's order with the inputs the SDK says changed, and the right pane draws each of those outputs
exactly as the Diff page draws it. A comparison with no shown text diff has no page and no link.
Each check has its sabotage.
"""
from __future__ import annotations

import re
from html import escape

import pytest

from tests.test_runs_list import demo  # noqa: F401

#: "From the first difference on": the first difference and every stage the SDK marks after it.
LISTED = ("FIRST DIFFERENCE", "downstream")


def page_problems(page: str, diff_page: str, comparison, store) -> list[str]:
    from onetrace_console.textdiff_page import OPEN, page_name, shown_document
    from onetrace_console.textdiff_view import _render_output
    out = []
    doc = shown_document(comparison, store)
    link = f'<a href="{escape(page_name(comparison))}">{escape(OPEN)}</a>'
    section = re.search(r'<section data-section="text-diff">.*?</section>', diff_page, re.S)
    if section is None or link not in section.group(0):
        out.append("the Diff page's text-diff section does not link the page")
    first = next(n for n in doc["nodes"] if n["verdict"] == "FIRST DIFFERENCE")
    if not re.search(rf"<h1>Text diff · {re.escape(escape(first['node']))}</h1>", page):
        out.append("the title does not name the first difference")
    if f'href="{escape(comparison.key)}.html"' not in page:
        out.append("no way back to the Diff page")
    listed = [(n["node"], o) for n in doc["nodes"] if n["verdict"] in LISTED for o in n["outputs"]]
    items = re.findall(r'<li data-listed="(output-\d+)"><a href="#(output-\d+)">(.*?)</a></li>', page, re.S)
    if [(a, b) for a, b, _ in items] != [(f"output-{i}", f"output-{i}") for i in range(1, len(listed) + 1)]:
        out.append(f"the left pane lists {len(items)} outputs, the document {len(listed)}")
    for (anchor, _, said), (stage, output) in zip(items, listed):
        if said != f'{escape(stage)} · <span class="mono">{escape(output["name"] or "")}</span>':
            out.append(f"{anchor}: listed as {said!r}")
        drawn = re.search(rf'<div id="{anchor}" data-pane-output><h3>(.*?)</h3>', page)
        if drawn is None or drawn.group(1) != escape(stage):
            out.append(f"{anchor}: no diff on the right")
        elif f'<div id="{anchor}" data-pane-output><h3>{escape(stage)}</h3>{_render_output(output)}</div>' not in page:
            out.append(f"{anchor}: not drawn as the Diff page draws it")
    inputs = list(dict.fromkeys(s for n in doc["nodes"] if n["verdict"] in LISTED for s in n["inputs"]))
    if re.findall(r"<p data-input>(.*?)</p>", page) != [escape(s) for s in inputs]:
        out.append("the inputs are not the SDK's")
    return out


def _pages(demo):
    store, pages = demo
    out = []
    for comparison in store.comparisons():
        text = pages / "diff" / f"{comparison.key}-text.html"
        diff = (pages / "diff" / f"{comparison.key}.html").read_text(encoding="utf-8")
        out.append((comparison, text, diff))
    return store, out


def test_every_shown_text_diff_has_its_page_and_says_only_what_the_document_says(demo, examined):
    from onetrace_console.textdiff_page import shown_document
    store, found = _pages(demo)
    shown = 0
    for comparison, text, diff in found:
        if shown_document(comparison, store) is None:
            assert not text.exists() and "-text.html" not in diff, comparison.key
            continue
        shown += 1
        assert page_problems(text.read_text(encoding="utf-8"), diff, comparison, store) == [], comparison.key
    examined(shown, "text-diff pages")
    assert shown >= 2


def test_a_comparison_without_a_shown_text_diff_has_no_page_and_no_link(demo, monkeypatch, examined):
    from onetrace_console import compare
    from onetrace_console.render import render_diff
    from onetrace_console.textdiff_page import render_text_diff_page
    store, found = _pages(demo)
    comparison = found[0][0]
    monkeypatch.setattr(compare, "text_diff_raw", lambda c, s: None)
    examined(1, "comparison")
    assert render_text_diff_page(comparison, store, generated_at="now") is None
    assert "-text.html" not in render_diff(comparison, store, generated_at="now")


def test_sabotage_each_check_catches_its_fault(demo, examined):
    from onetrace_console.textdiff_page import shown_document
    store, found = _pages(demo)
    comparison, text, diff = next(f for f in found if shown_document(f[0], store) is not None)
    page = text.read_text(encoding="utf-8")
    faults = {
        "no link from the Diff page": (lambda p: p, lambda d: d.replace("-text.html", "-gone.html"), "does not link"),
        "the title names another stage": (lambda p: re.sub(r"<h1>Text diff · [^<]*</h1>", "<h1>Text diff · elsewhere</h1>", p), None, "title"),
        "an output left out of the list": (lambda p: re.sub(r'<li data-listed="output-\d+">.*?</li>', "", p, count=1, flags=re.S), None, "left pane"),
        "a line of a diff changed": (lambda p: p.replace("<mark class=\"ins\">", "<mark class=\"ins\">!", 1), None, "not drawn as"),
        "an input of the page's own": (lambda p: p.replace("<p data-input>", "<p data-input>made up</p><p data-input>", 1), None, "inputs"),
    }
    caught = 0
    for name, (on_page, on_diff, said) in faults.items():
        broken, broken_diff = on_page(page), (on_diff(diff) if on_diff else diff)
        assert (broken, broken_diff) != (page, diff), f"{name}: the fault changed nothing"
        problems = page_problems(broken, broken_diff, comparison, store)
        assert any(said in p for p in problems), f"{name}: not caught ({problems})"
        caught += 1
    examined(caught, "faults caught")


def test_a_redrawing_without_a_shown_text_diff_removes_the_page_drawn_before(demo, tmp_path, monkeypatch,
                                                                            examined):
    """Never a page left from an earlier drawing: GET serves what is on disk."""
    from onetrace_console import compare
    from onetrace_console.serve import PAGES_DIRNAME, _render_diff_page
    from onetrace_console.textdiff_page import page_name, shown_document
    store, found = _pages(demo)
    comparison = next(f[0] for f in found if shown_document(f[0], store) is not None)
    _render_diff_page(comparison, store, tmp_path)
    drawn = tmp_path / PAGES_DIRNAME / "diff" / page_name(comparison)
    assert drawn.exists()
    monkeypatch.setattr(compare, "text_diff_raw", lambda c, s: None)
    _render_diff_page(comparison, store, tmp_path)
    examined(1, "redrawn comparison")
    assert not drawn.exists()
