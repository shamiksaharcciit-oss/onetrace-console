"""The graph keeps the page's own words apart from the words it quotes from a report.

A node's `tags` are the page's own short lines about it (its verdict, in the page's words). Its
`quoted` lines are a report's own words about it (the comparison's annotations), shown as they are:
each is marked as quoted (`data-words="report"`) and carries its whole text as its own title, so a
line shortened to fit the box loses nothing. A box's own title names the node and the page's words.
"""
from __future__ import annotations

import re

from onetrace_console.viewer.graph import GraphNode, lay_out, svg

QUOTED = "instrument config_digest differs: sha256:aaaa -> sha256:bbbb"


def _drawing(nodes) -> str:
    return svg(lay_out(nodes, None))


def test_a_quoted_line_is_marked_and_titled_whole(examined):
    node = GraphNode(node_id="model", name="model", index=1, href="#step-1",
                     tags=("Changed",), quoted=(QUOTED,))
    drawing = _drawing([node])
    examined(1, "node drawn")
    quoted = re.findall(r'<text class="state" data-words="report"[^>]*>([^<]*)<title>([^<]*)</title></text>',
                        drawing)
    assert quoted and quoted[0][1] == QUOTED.replace(">", "&gt;"), drawing
    assert quoted[0][0].endswith("…"), "the box's line is the shortened one"
    #: The page's own words: the first state is the box's chip.
    own = re.findall(r'<text class="chip" x=[^>]*>([^<]*)</text>', drawing)
    assert own == ["Changed"], own


def test_the_box_title_holds_only_the_page_s_own_words(examined):
    node = GraphNode(node_id="model", name="model", index=1, href="#step-1",
                     tags=("Changed",), quoted=(QUOTED,))
    titles = re.findall(r'<rect [^>]*/><title>([^<]*)</title>', _drawing([node]))
    examined(len(titles), "box titles")
    assert titles == ["model · Changed"], titles


def test_a_fold_keeps_each_member_s_quoted_words_marked(examined):
    nodes = [GraphNode(node_id=f"tests#{i}", name="tests", index=i, href=f"#step-{i}",
                       tags=("Same",), quoted=(f"attempt {i} differs",)) for i in (1, 2)]
    drawing = _drawing(nodes)
    examined(2, "folded members")
    assert drawing.count('data-words="report"') >= 1
    assert "attempt 1 differs" in drawing and "attempt 1 differs</text>" not in drawing.replace(
        "<title>attempt 1 differs</title></text>", "")
