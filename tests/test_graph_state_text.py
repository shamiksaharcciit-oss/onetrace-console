"""A graph box's own state lines are drawn whole: wrapped inside the box, the box as tall as they
need. A run's check that found its record contradicting itself read "Checked — and the record …"
in its Proof graph's box, cut at the box's edge.

1. A node's own words after its chip are drawn whole, in lines that fit the box's width, in order,
   with no "…", and every line inside the box.
2. On the demo, every box of every run page's graph draws its own words whole: joined, its drawn
   lines are the words its title names. The longest the demo draws is a check that found the record
   contradicting itself.
A report's quoted words keep their own rule (tests/viewer/test_graph_quoted_words.py): a quoted
line is shortened with its whole text in its own title and in the page's table.

Each check is a function returning the problems it finds; each has its sabotage.
"""
from __future__ import annotations

import html
import re

import pytest

from onetrace_console.viewer.graph import BOX_W, GraphNode, lay_out, svg

#: A state line is drawn in 12px IBM Plex Mono, 7.2px a character, measured in Chromium on the demo's
#: p7-41 Proof graph ("found sha256:aa79bfb8d85c…", 26 characters, 187.2px). A line fits its box
#: within the box's 10px each side.
MONO_12PX = 7.2

#: The longest kind of reading a box shows: the check's words where the record contradicts itself.
LONG = ("Checked — and the record contradicts itself here: output artifact 'decision.json' matches "
        "— expected sha256:ef859d7a959e… , found sha256:aa79bfb8d85c… .")


def _boxes(drawing: str) -> list[tuple[str, int, int, list[tuple[int, str]]]]:
    """(title, top, height, [(y, own line)]) for each box: its own state lines, not quoted ones."""
    out = []
    for m in re.finditer(r'<rect class="node" x="\d+" y="(\d+)" width="\d+" height="(\d+)"[^>]*/>'
                         r"<title>([^<]*)</title>(.*?)(?=</a>|</g>)", drawing, re.S):
        own = [(int(y), html.unescape(t)) for y, t in
               re.findall(r'<text class="state" x="\d+" y="(\d+)">([^<]*)</text>', m.group(4))]
        out.append((html.unescape(m.group(3)), int(m.group(1)), int(m.group(2)), own))
    return out


def quoted_problems(drawing: str) -> list[str]:
    """A quoted line, shortened, still fits its box: its whole text is in its own title."""
    return [f"a quoted line wider than its box: {html.unescape(t)!r}" for t in
            re.findall(r'<text class="state" data-words="report" x="\d+" y="\d+">([^<]*)<title>', drawing)
            if len(html.unescape(t)) * MONO_12PX > BOX_W - 20]


def whole_problems(drawing: str, words: dict[str, str]) -> list[str]:
    """`words`: a box's title -> the own words it must draw after its chip."""
    out = []
    for title, top, height, own in _boxes(drawing):
        want = words.get(title)
        if want is None:
            continue
        drawn = " ".join(t for _, t in own)
        if drawn != want:
            out.append(f"{title[:40]!r}: draws {drawn!r}")
        for y, t in own:
            if "…" in t and "…" not in want:
                out.append(f"{title[:40]!r}: a line cut: {t!r}")
            if len(t) * MONO_12PX > BOX_W - 20:
                out.append(f"{title[:40]!r}: a line wider than the box: {t!r}")
            if not top < y <= top + height:
                out.append(f"{title[:40]!r}: a line outside its box: {t!r} at {y}")
    return out


def test_a_quoted_line_fits_its_box_with_its_whole_text_in_its_title():
    node = GraphNode(node_id="model", name="model", index=1, href="#step-1", tags=("Changed",),
                     quoted=("instrument config_digest differs: sha256:aaaa -> sha256:bbbb",))
    assert quoted_problems(svg(lay_out([node], None))) == []


def test_a_long_reading_is_drawn_whole_inside_its_box(examined):
    node = GraphNode(node_id="release", name="release", index=3, href="#step-3",
                     tags=("1 output file", LONG))
    drawing = svg(lay_out([node], None, tag_lines=3))
    title = f"release · 1 output file · {LONG}"
    assert whole_problems(drawing, {title: LONG}) == []
    examined(1, "box")


def _demo_words(drawing: str) -> dict[str, str]:
    """Each box's own words after its chip, from its title: `name · chip · words`."""
    out = {}
    for title, _, _, _ in _boxes(drawing):
        parts = title.split(" · ")
        if len(parts) >= 3:
            out[title] = " · ".join(parts[2:])
    return out


@pytest.fixture(scope="module")
def demo_graphs(tmp_path_factory):
    from onetrace_console.folder_load import build_public
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("graph-text") / "demo"
    build_public(folder)
    out = {}
    for page in sorted((folder / "store" / "pages" / "runs").glob("*/*.html")):
        text = page.read_text(encoding="utf-8")
        for g in re.findall(r'<svg class="graph".*?</svg>', text, re.S):
            out.setdefault(str(page.relative_to(folder)), []).append(g)
    return out


def test_every_demo_box_draws_its_own_words_whole(demo_graphs, examined):
    problems, longest = [], ""
    for page, graphs in demo_graphs.items():
        for g in graphs:
            words = _demo_words(g)
            problems += [f"{page}: {p}" for p in whole_problems(g, words) + quoted_problems(g)]
            longest = max([longest, *words.values()], key=len)
    assert problems == []
    assert longest.startswith("Checked — and the record contradicts itself here"), longest
    examined(sum(len(g) for g in demo_graphs.values()), "graphs")


def test_sabotage_a_reading_cut_at_the_box_s_edge_is_named(monkeypatch):
    from onetrace_console.viewer import graph
    monkeypatch.setattr(graph, "_state_lines", lambda text: [graph._short(text, graph.STATE_MAX)])
    node = GraphNode(node_id="release", name="release", index=3, href="#step-3",
                     tags=("1 output file", LONG))
    drawing = svg(lay_out([node], None, tag_lines=3))
    assert whole_problems(drawing, {f"release · 1 output file · {LONG}": LONG})


def test_sabotage_a_box_too_short_for_its_lines_is_named():
    node = GraphNode(node_id="release", name="release", index=3, href="#step-3",
                     tags=("1 output file", LONG))
    drawing = svg(lay_out([node], None, tag_lines=3))
    short = re.sub(r'(<rect class="node" [^>]*height=")(\d+)', r"\g<1>40", drawing, count=1)
    assert any("outside its box" in p for p in whole_problems(short, {f"release · 1 output file · {LONG}": LONG}))
