"""The Overview, pipelines first: four tiles, then one card per pipeline with one mark per run.

Checked on the demo's own Overview, as a public console serves it:
1. the tiles, in order: Pipelines, Runs, Records agree, Need attention; Pipelines counts
   `overview.pipelines`, Need attention counts `overview.needs_attention` -- the same number as the
   Needs attention panel below -- with its parts named, each the number of runs of that kind;
2. the Records agree tile's bar: one part per state with runs, each the count of that state's
   tally, the parts together every run;
3. one card per pipeline, in id order, each one link to the pipeline's page; its marks are its runs'
   "Records agree" (`records.state`) in the order the console received them, the same states as the
   pipeline page's tiles; its text equivalent and its count line say the same counts;
4. the legend once, every state's mark a different shape;
5. a pipeline's name from the demo builder on a public demo only.

Each check is a function returning the problems it finds; each has its sabotage.
"""
from __future__ import annotations

import html
import re
from collections import Counter

import pytest

DEMO: dict = {}


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_demo["folder"]
    pages = folder / "store" / "pages"
    DEMO.update(store=Store(folder / "store" / "store"), pages=pages,
                home=(pages / "home.html").read_text(encoding="utf-8"))
    return DEMO


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _card(page: str, name: str) -> str:
    m = re.search(rf'<div data-card="{name}">(.*?)</details></div>', page, re.S)
    return m.group(1) if m else ""


def _kpi(card: str) -> int | None:
    m = re.search(r'<span class="kpi">(\d+)</span>', card)
    return int(m.group(1)) if m else None


def tile_problems(page: str, store) -> list[str]:
    from onetrace_console.overview import ATTENTION_KINDS, ATTENTION_WORDS, needs_attention, pipelines
    out = []
    cards = re.findall(r'<div data-card="([^"]+)">', page)
    if cards != ["pipelines", "runs", "records-agree", "need-attention"]:
        out.append(f"tiles {cards}")
    if _kpi(_card(page, "pipelines")) != len(pipelines(store)):
        out.append(f"Pipelines tile {_kpi(_card(page, 'pipelines'))}, {len(pipelines(store))} pipelines")
    listed = needs_attention(store)
    tile = _card(page, "need-attention")
    if _kpi(tile) != len(listed):
        out.append(f"Need attention tile {_kpi(tile)}, {len(listed)} need attention")
    panel = re.search(r'<section data-section="needs-attention">.*?Needs attention first · (\d+) of', page, re.S)
    if not panel or int(panel.group(1)) != _kpi(tile):
        out.append(f"Need attention tile {_kpi(tile)}, the panel {panel.group(1) if panel else None}")
    kinds = Counter(k for k, _ in listed)
    want = [(ATTENTION_WORDS[k], kinds[k]) for k in ATTENTION_KINDS if kinds[k]]
    got = [(html.unescape(w), int(n)) for w, n in
           re.findall(r'<span data-kind="[\w-]+">([^<]+): (\d+)</span>', tile)]
    if got != want:
        out.append(f"Need attention parts {got}, {want}")
    return out


def bar_problems(page: str, store) -> list[str]:
    from onetrace_console import records
    tile = _card(page, "records-agree")
    got = [(s, int(n)) for s, n in re.findall(r'data-bar-part="([\w-]+)" data-count="(\d+)"', tile)]
    runs = store.runs()
    want = [(s, len(records.runs_in(runs, store, s))) for s in records.STATES
            if records.runs_in(runs, store, s)]
    out = [] if got == want else [f"bar {got}, the states {want}"]
    if sum(n for _, n in got) != len(runs):
        out.append(f"the bar's parts hold {sum(n for _, n in got)} of {len(runs)} runs")
    return out


def _cards(page: str) -> list[tuple[str, str, str]]:
    return re.findall(r'<a class="pcard" data-pipeline-card="(P\d+)" href="([^"]+)">(.*?)</a>\s*(?=<a class="pcard"|</div>)',
                      page, re.S)


def card_problems(page: str, store, read=None) -> list[str]:
    from onetrace_console import records
    from onetrace_console.overview import pipelines
    from onetrace_console.pipeline_pages import count_line, page_href
    out = []
    found = pipelines(store)
    cards = _cards(page)
    if [c[0] for c in cards] != [p.label for p in found]:
        out.append(f"cards {[c[0] for c in cards]}, pipelines {[p.label for p in found]}")
    for (label, href, inner), p in zip(cards, found):
        if href != page_href(p.label):
            out.append(f"{label} links to {href}")
        marks = re.findall(r'data-mark="([\w-]+)"', inner)
        if marks != [records.state(r, store) for r in p.runs]:
            out.append(f"{label}: marks {marks}")
        said = re.search(r'<span class="marks" role="img" aria-label="([^"]*)">', inner)
        line = re.search(r'<p data-line="count">(.*?)</p>', inner, re.S)
        want = count_line(p.runs, store)
        if not said or html.unescape(said.group(1)) != want:
            out.append(f"{label}: marks say {said.group(1) if said else None!r}, {want!r}")
        if not line or _text(line.group(1)) != want:
            out.append(f"{label}: count line {line.group(1) if line else None!r}")
        if read is not None:
            tiles = re.findall(r'<li data-run="[0-9a-f]{64}" data-state="([\w-]+)">', read(href))
            if tiles != marks:
                out.append(f"{label}: card marks {marks}, its page's tiles {tiles}")
    return out


def legend_problems(page: str) -> list[str]:
    from onetrace_console.pipeline_pages import MARK_SHAPES
    out = []
    if page.count('data-section="legend"') != 1:
        out.append(f"{page.count('data-section=' + chr(34) + 'legend' + chr(34))} legends")
    if len(set(MARK_SHAPES.values())) != len(MARK_SHAPES):
        out.append("two states share a mark's shape")
    return out


def _read(rel: str) -> str:
    return (DEMO["pages"] / rel).read_text(encoding="utf-8")


def test_the_tiles_count_as_the_console_does(demo, examined):
    assert tile_problems(demo["home"], demo["store"]) == []
    examined(4, "tiles")


def test_the_records_agree_bar_is_the_states_tallies(demo):
    assert bar_problems(demo["home"], demo["store"]) == []


def test_one_card_per_pipeline_with_its_runs_marks(demo, examined):
    assert card_problems(demo["home"], demo["store"], _read) == []
    examined(len(_cards(demo["home"])), "pipeline cards")


def test_the_legend_once_and_a_shape_per_state(demo):
    assert legend_problems(demo["home"]) == []


def test_the_builder_s_names_on_a_public_demo_only(demo):
    from onetrace_console import demo_store
    from onetrace_console.overview import pipelines
    from onetrace_console.render import render_home
    store = demo["store"]
    named = dict(re.findall(r'data-pipeline-card="(P\d+)".*?<span data-name>([^<]+)</span>', demo["home"], re.S))
    want = {p.label: demo_store.name_of(r.run_id for r in p.runs) for p in pipelines(store)}
    assert {k: html.unescape(v) for k, v in named.items()} == want
    assert "data-name" not in render_home(store, generated_at="2026-01-01T00:00:00+00:00")


# ------------------------------------------------------------------------------- sabotages

def test_sabotage_a_tile_off_by_one_or_out_of_order_is_named(demo):
    page = demo["home"]
    tile = _card(page, "need-attention")
    off = page.replace(tile, re.sub(r'<span class="kpi">(\d+)</span>',
                                    lambda m: f'<span class="kpi">{int(m.group(1)) + 1}</span>', tile, count=1))
    assert any("Need attention tile" in p for p in tile_problems(off, demo["store"]))
    swapped = page.replace('<div data-card="pipelines">', '<div data-card="x">', 1) \
        .replace('<div data-card="runs">', '<div data-card="pipelines">', 1) \
        .replace('<div data-card="x">', '<div data-card="runs">', 1)
    assert any(p.startswith("tiles") for p in tile_problems(swapped, demo["store"]))


def test_sabotage_a_bar_part_wrong_is_named(demo):
    page = re.sub(r'(data-bar-part="yes" data-count=")(\d+)', lambda m: m.group(1) + str(int(m.group(2)) - 1),
                  demo["home"], count=1)
    assert bar_problems(page, demo["store"])


def test_sabotage_a_mark_swapped_or_a_card_dropped_is_named(demo):
    page = demo["home"]
    i = page.index('<div class="pcards">')
    swapped = page[:i] + page[i:].replace('data-mark="no"', 'data-mark="yes"', 1)
    assert any("marks" in p for p in card_problems(swapped, demo["store"]))
    first = _cards(page)[0]
    dropped = re.sub(r'<a class="pcard" data-pipeline-card="P1".*?</a>\s*(?=<a class="pcard")', "", page,
                     count=1, flags=re.S)
    assert dropped != page and any(p.startswith("cards") for p in card_problems(dropped, demo["store"]))
    del first


def test_sabotage_a_second_legend_is_named(demo):
    page = demo["home"].replace('<div data-section="legend">', '<div data-section="legend"></div>'
                                '<div data-section="legend">', 1)
    assert legend_problems(page)


def test_sabotage_a_card_s_marks_unlike_its_page_is_named(demo):
    def read(rel):
        text = _read(rel)
        return text.replace('data-state="yes"', 'data-state="no"', 1) if rel == "pipeline-p1.html" else text
    assert any("its page's tiles" in p for p in card_problems(demo["home"], demo["store"], read))
