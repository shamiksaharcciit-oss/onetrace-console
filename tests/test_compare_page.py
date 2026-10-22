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
def demo(shared_demo, tmp_path_factory):
    """Its own copy of the session's demo build: the pages drawn here change the store."""
    from onetrace_console.store import Store
    from tests.conftest import demo_copy
    from tests.test_checks import _require_installed
    _require_installed()
    folder = demo_copy(shared_demo, tmp_path_factory.mktemp("compare") / "demo")
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
    said = html.unescape(re.sub(r"<[^>]+>", " ", what))
    #: What the card says of the stage: what is recorded as differing there (a setting, the code,
    #: an input), or, with nothing recorded, the SDK's sentence that there is no recorded cause; and
    #: with a recorded change, never that why the output differs is not established.
    recorded = any(w in said for w in ("settings differ in", "recorded configuration differs", "input "))
    if not recorded and "no recorded cause:" not in said:
        out.append("the card says neither what is recorded as differing nor that nothing is")
    if recorded and "is not established by this evidence." in said:
        out.append("the card says not established beside a recorded change")
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
    #: Each box opens its stage's row, on this page or on its "Proof" view, which holds the table.
    boxes = re.findall(r'<a href="(?:[0-9a-f]{64}-proof\.html)?#step-(\d+)"[^>]*?data-tone="(\w+)"><rect[^>]*/>'
                       r'<title>([^<]*)</title>', svg.group(0))
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
    #: Each box links to its stage's row, on the comparison's "Proof" view, which holds the table.
    folder, store = demo
    ids = {r.run_id: r.key for r in store.runs()}
    c = next(c for c in store.comparisons() if (c.run_a, c.run_b) == tuple(ids[r] for r in HEADLINE))
    proof = (folder / "store" / "pages" / "diff" / f"{c.key}-proof.html").read_text(encoding="utf-8")
    assert all(f'id="step-{i}"' in proof for i, _ in ladder), "each box links to its row"
    assert all(f'href="{c.key}-proof.html#step-{i}"' in page for i, _ in ladder), "each box links to its row"


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
    assert 'data-mark="first" data-tone="fd"' in _page(demo, *HEADLINE)
    page = _page(demo, *HEADLINE).replace('data-mark="first" data-tone="fd"', 'data-mark="first" data-tone="ok"', 1)
    assert any(p.startswith("stage 2 is toned 'ok'") for p in graph_problems(
        page, [("2", "FIRST DIFFERENCE")]))


def test_sabotage_an_invented_setting_row_is_named(demo, examined):
    examined(1, "planted page")
    page = _page(demo, *HEADLINE).replace('<tr data-setting="', '<tr data-setting="9:invented"></tr><tr data-setting="', 1)
    assert any("the table's rows are" in p for p in settings_problems(page, _annotations(demo, *HEADLINE)))


#: The demo's graph-shaped pair whose classify step's recorded constant `rules` changes, 1 to 2.
GRAPH_PAIR = ("p3-23-t-1-rules1", "p3-27-t-1-rules2")


def _ladder(demo, base: str, cand: str) -> list[dict]:
    folder, store = demo
    ids = {r.run_id: r.key for r in store.runs()}
    comparison = next(c for c in store.comparisons() if (c.run_a, c.run_b) == (ids[base], ids[cand]))
    return json.loads(store.get(dict(comparison.verb("diff").reports)["diff.json"]))["ladder"]


def _receipt(demo, run_id: str, index: str) -> dict:
    """A run's receipt at a chain index, read from the run's own folder, not the store."""
    folder, _ = demo
    run = folder / "runs" / run_id
    chain = json.loads((run / "MANIFEST.json").read_text(encoding="utf-8"))["chain"]
    entry = next(e for e in chain if str(e["index"]) == index)
    return json.loads((run / entry["file"]).read_text(encoding="utf-8"))


def graph_settings_problems(page: str, ladder: list[dict], receipt_a, receipt_b) -> list[str]:
    """Each setting a node's note says differs is a row of "Settings that changed", with the value
    each run's receipt records; and the table lists nothing the notes don't name."""
    section = re.search(r'<section data-section="settings-changed">(.*?)</section>', page, re.S)
    if not section:
        return ["no settings table"]
    rows = dict(re.findall(r'<tr data-setting="([^"]+)">(.*?)</tr>', section.group(1), re.S))
    want, out = {}, []
    for n, row in enumerate(ladder, start=1):
        for note in row["annotations"]:
            m = re.fullmatch(r"instrument (\S+) differs: .*", note)
            if m:
                field, key = f"instrument.{m[1]}", ("instrument", m[1])
            elif (m := re.fullmatch(r"constant (.+) differs", note)):
                field, key = f"assertions.constants.{m[1]}", ("constants", m[1])
            else:
                continue
            ra, rb = receipt_a(row["index_baseline"]), receipt_b(row["index_candidate"])
            value = (lambda r: r["instrument"][key[1]]) if key[0] == "instrument" else \
                    (lambda r: r["assertions"]["constants"][key[1]])
            want[f"{n}:{field}"] = (str(value(ra)), str(value(rb)))
    if set(rows) != set(want):
        out.append(f"the table's rows are {sorted(rows)}, the notes name {sorted(want)}")
    for name, values in want.items():
        cells = html.unescape(re.sub(r"<[^>]+>", " ", rows.get(name, "")))
        out += [f"{name}: {v} is not in its row" for v in values if v not in cells]
    return out


def test_settings_that_changed_on_a_graph_pair_are_the_notes_settings_with_both_values(demo, examined):
    ladder = _ladder(demo, *GRAPH_PAIR)
    page = _page(demo, *GRAPH_PAIR)
    problems = graph_settings_problems(page, ladder, lambda i: _receipt(demo, GRAPH_PAIR[0], i),
                                       lambda i: _receipt(demo, GRAPH_PAIR[1], i))
    rows = re.findall(r'<tr data-setting="([^"]+)">', page)
    examined(len(rows), "settings rows on the graph pair")
    assert problems == []
    assert "2:assertions.constants.rules" in rows, rows
    assert "No recorded setting differs" not in page


def test_sabotage_a_graph_pair_s_missing_setting_row_is_named(demo, examined):
    examined(1, "planted page")
    page = re.sub(r'<tr data-setting="2:assertions\.constants\.rules">.*?</tr>', "", _page(demo, *GRAPH_PAIR),
                  flags=re.S)
    problems = graph_settings_problems(page, _ladder(demo, *GRAPH_PAIR),
                                       lambda i: _receipt(demo, GRAPH_PAIR[0], i),
                                       lambda i: _receipt(demo, GRAPH_PAIR[1], i))
    assert any("the notes name" in p for p in problems), problems


def text_count_problems(page: str) -> list[str]:
    """Each step's "settings: N changed" in the text diff against the rows "Settings that changed"
    lists for that step, its fingerprints under Details included: N must be that count."""
    def words(s: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()
    section = re.search(r'<section data-section="settings-changed">(.*?)</section>', page, re.S)
    listed: dict[str, int] = {}
    for row in re.findall(r'<tr data-setting="[^"]+">(.*?)</tr>', section.group(1) if section else "", re.S):
        stage = words(re.search(r"<td[^>]*>(.*?)</td>", row, re.S).group(1))
        listed[stage] = listed.get(stage, 0) + 1
    out = []
    for node, body in re.findall(r'<article data-node="([^"]*)">(.*?)</article>', page, re.S):
        m = re.search(r"settings: (\d+) changed", body)
        if m and int(m[1]) != listed.get(html.unescape(node), 0):
            out.append(f"{html.unescape(node)}: the text diff says {m[1]} changed, the table lists "
                       f"{listed.get(html.unescape(node), 0)}")
    return out


def _every_diff_page(demo) -> dict[str, str]:
    folder, _ = demo
    return {p.name: p.read_text(encoding="utf-8") for p in (folder / "store" / "pages" / "diff").glob("*.html")
            if not p.name.endswith("-text.html")}


def test_the_text_diff_s_settings_count_is_what_the_settings_table_lists(demo, examined):
    pages = _every_diff_page(demo)
    counted = sum(len(re.findall(r"settings: \d+ changed", p)) for p in pages.values())
    examined(counted, "settings counts in the demo's text diffs")
    assert {name: text_count_problems(p) for name, p in pages.items() if text_count_problems(p)} == {}


def test_sabotage_a_settings_count_the_table_does_not_list_is_named(demo, examined):
    examined(1, "planted page")
    page = _page(demo, *GRAPH_PAIR).replace("settings: 2 changed", "settings: 3 changed", 1)
    assert text_count_problems(page) == ["classify: the text diff says 3 changed, the table lists 2"]
