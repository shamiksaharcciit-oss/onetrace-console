"""The Compare page in 0.1.1's look, on the demo's own comparisons.

1. The headline card: where the runs first differ (the stage, and the stages identical before
   it) beside what (settings, output, the stages after it, what is not established), and the
   command that repeats the comparison.
2. A straight-line pair is drawn as a graph too, with the stage table's stages and no links, each
   box toned by its verdict and keeping its words; it fits a 1280-wide page without scrolling.
3. "Settings that changed": exactly the report's annotations, a digest short with its whole value
   one click away.
4. Two runs from different pipelines are said to be so, first; two from one pipeline are not.

Each check has its sabotage.
"""
from __future__ import annotations

import html
import json
import re

import pytest

from onetrace_console import tones

#: The page's widest drawing at 1280: the window less the navigation (232) and the page's and the
#: panel's side padding (36 and 18, each side).
WIDTH_AT_1280 = 1280 - 232 - 2 * 36 - 2 * 18


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    from onetrace_console.folder_load import build_public
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("compare") / "demo"
    build_public(folder)
    return folder, Store(folder / "store" / "store")


def _page(demo, base: str, cand: str) -> str:
    folder, store = demo
    ids = {r.run_id: r.key for r in store.runs()}
    comparison = next(c for c in store.comparisons()
                      if (c.run_a, c.run_b) == (ids[base], ids[cand]))
    return (folder / "store" / "pages" / "diff" / f"{comparison.key}.html").read_text(encoding="utf-8")


def _annotations(demo, base: str, cand: str) -> list[dict]:
    import json
    folder, store = demo
    ids = {r.run_id: r.key for r in store.runs()}
    comparison = next(c for c in store.comparisons() if (c.run_a, c.run_b) == (ids[base], ids[cand]))
    key = dict(comparison.verb("diff").reports)["diff.json"]
    return json.loads(store.get(key))["annotations"]


HEADLINE = ("p1-02-baseline-set2", "p1-08-candidate-set2")


def headline_problems(page: str, command: str) -> list[str]:
    card = re.search(r'<section data-section="first-difference"><div data-part="where">(.*?)</div>'
                     r'<div data-part="what">(.*?)</div></section>', page, re.S)
    if not card:
        return ["no headline card"]
    out = []
    where = [html.unescape(p) for p in re.findall(r"<p>(.*?)</p>", card.group(1))]
    if not (where and where[0].startswith("First difference: stage ")
            and where[1].startswith("Stages identical before it: ")):
        out.append(f"the card's where is {where}")
    what = card.group(2)
    if "is not established by this evidence." not in html.unescape(what):
        out.append("the card no longer says what is not established")
    shown = re.search(r'<pre data-section="headline-command"><code>(.*?)</code></pre>', what, re.S)
    if not shown or html.unescape(shown.group(1)) != command:
        out.append("the card's command is not the comparison's own")
    return out


def graph_problems(page: str, ladder: list[tuple[str, str]], reads: int = 0) -> list[str]:
    """`reads`: how many stages' receipts record reading the stage just before them (in the
    candidate): exactly those are drawn as lines, and no other."""
    svg = re.search(r'<svg class="graph"[^>]*width="(\d+)".*?</svg>', page, re.S)
    if not svg:
        return ["no graph"]
    out = []
    if int(svg.group(1)) > WIDTH_AT_1280:
        out.append(f"the graph is {svg.group(1)} wide, more than {WIDTH_AT_1280}")
    if svg.group(0).count('class="link"') != reads:
        out.append(f"{svg.group(0).count('class=\"link\"')} links drawn for {reads} recorded reads")
    boxes = re.findall(r'<a href="#step-(\d+)"[^>]*?data-tone="(\w+)"><rect[^>]*/><title>([^<]*)</title>',
                       svg.group(0))
    drawn = {i: (tone, html.unescape(title)) for i, tone, title in boxes}
    from onetrace_console.render import _RESULT_WORDS
    for index, verdict in ladder:
        tone, title = drawn.get(index, ("", ""))
        if tone != tones.tone(tones.DIFF, verdict):
            out.append(f"stage {index} is toned {tone!r}, not {tones.tone(tones.DIFF, verdict)!r}")
        if not title.endswith(" · " + _RESULT_WORDS[verdict]):
            out.append(f"stage {index} has lost its words: {title!r}")
    return out


def settings_problems(page: str, annotations: list[dict]) -> list[str]:
    section = re.search(r'<section data-section="settings-changed">(.*?)</section>', page, re.S)
    if not section:
        return ["no settings table"]
    rows = re.findall(r'<tr data-setting="([^"]+)">', section.group(1))
    want = [f"{n['index']}:{field}" for n in annotations for field in n["differs"]]
    out = [] if rows == want else [f"the table's rows are {rows}, the report's {want}"]
    for n in annotations:
        for old, new in n["differs"].values():
            for value in (old, new):
                if value not in html.unescape(section.group(1)):
                    out.append(f"{value} is not in the table, whole")
    return out


def test_the_headline_card_where_beside_what_with_its_command(demo, examined):
    folder, store = demo
    ids = {r.run_id: r.key for r in store.runs()}
    comparison = next(c for c in store.comparisons() if (c.run_a, c.run_b) == tuple(ids[r] for r in HEADLINE))
    examined(1, "comparison page")
    from onetrace_console.render import typed_command
    assert headline_problems(_page(demo, *HEADLINE),
                             typed_command(comparison, store, "diff", text=True)) == []


def test_a_straight_line_pair_is_drawn_toned_and_fits_1280(demo, examined):
    page = _page(demo, *HEADLINE)
    ladder = [("1", "same"), ("2", "FIRST DIFFERENCE"), ("3", "downstream"), ("4", "downstream"),
              ("5", "downstream")]
    examined(len(ladder), "stages drawn")
    assert 'data-section="graph-linear"' in page
    folder, _store = demo
    receipts = [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted((folder / "runs" / HEADLINE[1] / "receipts").glob("*.json"))]
    names = [r["stage"]["name"] for r in receipts]
    reads = sum(f"receipt:{a}" in {i["name"] for i in r.get("inputs", [])}
                for a, r in zip(names, receipts[1:]))
    assert reads, "the demo's candidate records its reads"
    assert graph_problems(page, ladder, reads) == []
    assert graph_problems(page, ladder, reads - 1), "a line the records don't hold is named"
    assert all(f'id="step-{i}"' in page for i, _ in ladder), "each box links to its row"


def test_settings_that_changed_are_the_reports_annotations(demo, examined):
    annotations = _annotations(demo, *HEADLINE)
    examined(sum(len(n["differs"]) for n in annotations), "settings")
    page = _page(demo, *HEADLINE)
    assert settings_problems(page, annotations) == []
    assert "chunk_size" in page and re.search(r"<summary class=\"mono\">sha256:[0-9a-f]{8}…", page)


def test_a_pair_from_one_pipeline_is_not_said_to_be_from_two(demo, examined):
    examined(1, "comparison page")
    assert 'data-section="different-pipelines"' not in _page(demo, *HEADLINE)


def _cross_pipeline_page(demo) -> str:
    from onetrace_console.compare import compare
    from onetrace_console.render import render_diff
    folder, store = demo
    ids = {r.run_id: r for r in store.runs()}
    comparison = compare(ids["p1-01-baseline-set1"], ids["p3-23-t-1-rules1"], store)
    return render_diff(comparison, store, generated_at="2026-10-11T00:00:00Z")


def test_a_pair_from_two_pipelines_says_so_first(demo, examined):
    from onetrace_console.render import DIFFERENT_PIPELINES
    page = _cross_pipeline_page(demo)
    examined(1, "comparison page")
    line = f'<p data-section="different-pipelines">{html.escape(DIFFERENT_PIPELINES)}</p>'
    assert line in page
    assert page.index(line) < page.index("<h2>"), "said before anything the comparison found"


# ------------------------------------------------------------------ the sabotages

def test_sabotage_the_condition_inverted_is_caught(demo, monkeypatch, examined):
    """With the condition inverted, the same-pipeline pair carries the line and the two-pipeline
    pair loses it: both of the tests above would fail."""
    from onetrace_console import overview, render
    examined(2, "comparison pages")
    real = overview.declared_list
    monkeypatch.setattr(overview, "declared_list", lambda run: (real(run), id(run)))
    folder, store = demo
    ids = {r.run_id: r for r in store.runs()}
    from onetrace_console.compare import compare
    same = compare(ids[HEADLINE[0]], ids[HEADLINE[1]], store)
    assert 'data-section="different-pipelines"' in render.render_diff(same, store, generated_at="x")


def test_sabotage_a_card_with_another_command_is_named(demo, examined):
    examined(1, "planted page")
    page = _page(demo, *HEADLINE)
    assert "the card's command is not the comparison's own" in headline_problems(page, "onetrace diff x y")


def test_sabotage_a_box_toned_off_the_rule_is_named(demo, examined):
    examined(1, "planted page")
    page = _page(demo, *HEADLINE).replace('data-mark="first" data-tone="bad"', 'data-mark="first" data-tone="ok"', 1)
    assert any(p.startswith("stage 2 is toned 'ok'") for p in graph_problems(
        page, [("2", "FIRST DIFFERENCE")]))


def test_sabotage_an_invented_setting_row_is_named(demo, examined):
    examined(1, "planted page")
    page = _page(demo, *HEADLINE).replace('<tr data-setting="', '<tr data-setting="9:invented"></tr><tr data-setting="', 1)
    assert any("the table's rows are" in p for p in settings_problems(page, _annotations(demo, *HEADLINE)))
