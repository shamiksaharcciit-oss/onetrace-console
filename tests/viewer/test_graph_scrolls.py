"""A graph wider than its panel is never cut; the panel scrolls, visibly.

    The graph clips nodes. [...] on the `ingest-r1-chunker-3.4` case page the straight-line graph
    shows 5 of its 9 nodes [...] Either the graph panel scrolls horizontally, visibly (a scroll
    container with a visible scrollbar), or the graph is scaled to fit. The viewer chooses; a node is
    never cut.

The scroll was chosen. A nine-node straight line is 2112px wide, and scaled into a 1098px
panel its 12px labels would draw at about 6px. Measured in Chromium: the
panel already scrolled (`overflow-x:auto`), but its scrollbar was drawn 0px tall where scrollbars
overlay or are hidden (headless Chromium, macOS), so nothing showed there were nodes past the
edge. The panel's scrollbar is now styled, which Chromium and Safari always draw, with the
standard properties for browsers without `::-webkit-scrollbar`.
"""
from __future__ import annotations

import re

from onetrace_console.viewer.graph import BOX_W, GraphNode, lay_out, svg
from onetrace_console.viewer.page import CSS, FRAME_CSS


def _rules(css: str) -> list[tuple[str, str]]:
    """(selector, body) of every innermost rule."""
    return [(s.strip(), b) for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def _body(selector: str) -> str:
    """The body of the one top-level rule for `selector` (the @supports fallback is read apart)."""
    top_level = re.sub(r"@supports[^{}]*\{[^{}]*\{[^{}]*\}\}", "", CSS)
    found = [b for s, b in _rules(top_level) if s == selector]
    assert len(found) == 1, f"{selector}: {len(found)} rules"
    return found[0]


def test_the_graph_panel_scrolls_and_nothing_hides_its_overflow():
    assert re.search(r"(^|;)overflow-x:(auto|scroll)(;|$)", _body(".graph-box")), \
        "the graph panel does not scroll"
    rules = _rules(CSS) + _rules(FRAME_CSS)
    assert len(rules) > 50, "the stylesheets were not read"
    hiding = [s for s, b in rules if re.search(r"overflow(-x)?:\s*(hidden|clip)", b)]
    assert not hiding, f"a rule hides overflow, which can cut a node: {hiding}"


def test_the_panels_scrollbar_is_drawn():
    """A styled scrollbar is drawn even where the platform's own would overlay or hide."""
    height = re.search(r"height:(\d+)px", _body(".graph-box::-webkit-scrollbar"))
    assert height and int(height.group(1)) >= 8, "the scrollbar has no drawn height"
    assert "background:var(" in _body(".graph-box::-webkit-scrollbar-thumb")
    assert "background:var(" in _body(".graph-box::-webkit-scrollbar-track")
    fallback = re.search(r"@supports not selector\(::-webkit-scrollbar\)\{\.graph-box\{([^{}]*)\}\}",
                         CSS)
    assert fallback and "scrollbar-color:" in fallback.group(1), "no scrollbar for other browsers"


def test_every_node_of_a_wide_straight_line_is_inside_what_the_panel_scrolls_over():
    """The scroll reaches every node: each box lies inside the drawing's own width and height."""
    nodes = [GraphNode(node_id=f"stage-{i}", name=f"stage-{i}", index=i, href=f"#step-{i}")
             for i in range(1, 10)]
    layout = lay_out(nodes, None)
    drawn = svg(layout)
    width, height = map(int, re.search(r'<svg[^>]* width="(\d+)" height="(\d+)"', drawn).groups())
    boxes = [tuple(map(int, b)) for b in
             re.findall(r'<rect class="node" x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"',
                        drawn)]
    assert len(boxes) == 9 and width > 1098, "not wider than the widest panel: proves nothing"
    for x, y, w, h in boxes:
        assert w == BOX_W and 0 <= x and x + w <= width and 0 <= y and y + h <= height
