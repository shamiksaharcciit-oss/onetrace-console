"""The graph, redrawn to the visual target: whole names, the state as a chip, the marks in amber.

1. A box's name is drawn whole, on as many lines as it takes, never cut with "…".
2. A box's first state is a chip: a pill, in the box's tone, holding the state's words.
3. Each chip's words read on its own fill at 4.5:1 or more, in both themes, for every tone a box
   can take -- and the HTML chips of the same two comparison findings likewise.
4. A hostile name, state or quoted line is escaped in every part of the drawing: markup is text,
   and control and bidirectional characters are shown as escapes.

Each check has its sabotage.
"""
from __future__ import annotations

import re
from html import unescape

import pytest

from tests.test_shared_style import _tokens, ratio


def _drawn(labels, tags=(), quoted=(), tone=""):
    from onetrace_console.viewer.graph import GraphNode, lay_out, svg
    from onetrace_console.viewer.page import escape
    nodes = [GraphNode(node_id=f"n{i}", name=f"n{i}", index=i, href=f"#step-{i}", label=lb,
                       tags=tuple(tags), quoted=tuple(quoted), tone=tone)
             for i, lb in enumerate(labels, start=1)]
    return svg(lay_out(nodes, None, wrap_labels=True), esc=escape)


def name_problems(drawing: str, labels: list[str]) -> list[str]:
    boxes = re.findall(r"<rect class=\"node\".*?(?=<rect class=\"node\"|</svg>)", drawing, re.S)
    out = []
    for label, box in zip(labels, boxes):
        lines = [unescape(t) for t in re.findall(r'<text class="name"[^>]*>([^<]*)</text>', box)]
        if any("…" in line for line in lines):
            out.append(f"{label[:20]}: cut with an ellipsis")
        if "".join(lines).replace(" ", "") != label.replace(" ", ""):
            out.append(f"{label[:20]}: drawn as {lines}")
    return out


LONG = ["load_documents_from_the_shared_policy_folder_and_split", "answer", "a stage name with spaces in it all"]


def test_a_name_is_drawn_whole_on_as_many_lines_as_it_takes(examined):
    drawing = _drawn(LONG)
    examined(len(LONG), "names drawn")
    assert name_problems(drawing, LONG) == []
    assert len(re.findall(r'<text class="name"', drawing)) > len(LONG), "nothing wrapped"


def test_sabotage_a_name_cut_short_is_named(monkeypatch, examined):
    from onetrace_console.viewer import graph
    monkeypatch.setattr(graph, "_label_lines", lambda label: [graph._short(label)])
    examined(1, "names cut")
    assert any("ellipsis" in p for p in name_problems(_drawn(LONG), LONG))


def test_the_first_state_is_a_chip_in_the_box_s_tone(examined):
    drawing = _drawn(["split"], tags=("First difference", "chunk_size 1024 → 512"), tone="fd")
    examined(1, "box with states")
    assert re.search(r'<a href="#step-1" data-tone="fd"><rect class="node"', drawing)
    chip = re.search(r'<rect class="chip"[^>]*/><text class="chip"[^>]*>([^<]*)</text>', drawing)
    assert chip and unescape(chip.group(1)) == "First difference"
    assert '<text class="state" ' in drawing and "chunk_size 1024" in drawing


#: Each tone's chip in the graph: its words' colour and its fill, as the stylesheet sets them.
#: "ca" is outlined, its fill the box's own surface.
GRAPH_CHIPS = {"ok": ("ok-ink", "ok-bg"), "bad": ("bad-ink", "bad-bg"), "cc": ("cc-ink", "cc-bg"),
               "neu": ("neu-ink", "neu-bg"), "fd": ("page", "cc-ink"), "ca": ("cc-ink", "surface")}
HTML_CHIPS = {"fd": ("page", "cc-ink"), "ca": ("cc-ink", "surface"), "dec": ("accent", "surface")}


def chip_problems(css: str, theme: str) -> list[str]:
    tokens = _tokens(theme)
    out = []
    for tone, (fg, bg) in GRAPH_CHIPS.items():
        if tone != "neu":
            text = re.search(rf"\[data-tone={tone}\] text\.chip\{{fill:var\(--([\w-]+)\)\}}", css)
            if not text or text.group(1) != fg:
                out.append(f"{tone}: the chip's words are not --{fg}")
        if ratio(fg, bg, tokens) < 4.5:
            out.append(f"{tone}: --{fg} on --{bg} reads {ratio(fg, bg, tokens):.2f}:1 ({theme})")
    for tone, (fg, bg) in HTML_CHIPS.items():
        if ratio(fg, bg, tokens) < 4.5:
            out.append(f".{tone}: --{fg} on --{bg} reads {ratio(fg, bg, tokens):.2f}:1 ({theme})")
    return out


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_chip_s_words_read_on_its_fill(theme, examined):
    from tests.test_shared_style import _sheet
    examined(len(GRAPH_CHIPS) + len(HTML_CHIPS), f"chips, {theme}")
    assert chip_problems(_sheet(), theme) == []


def test_sabotage_a_dim_chip_is_named(examined):
    from tests.test_shared_style import _sheet
    sheet = _sheet().replace("[data-tone=fd] text.chip{fill:var(--page)}", "[data-tone=fd] text.chip{fill:var(--hl)}")
    examined(1, "planted chip")
    assert any(p.startswith("fd:") for p in chip_problems(sheet, "light"))


def test_a_hostile_name_state_and_quoted_line_stay_escaped(examined):
    rlo, bell = "\u202e", "\x07"
    drawing = _drawn([f"<b>a&b{rlo}</b>"], tags=(f"<i>state{bell}</i>",), quoted=("<script>x</script>",))
    examined(3, "hostile parts")
    assert "<b>" not in drawing and "<i>" not in drawing and "<script>x" not in drawing
    assert "&lt;b&gt;a&amp;b" in drawing and "&lt;script&gt;x" in drawing
    assert rlo not in drawing and bell not in drawing
    assert "\\u202e" in drawing and "\\u0007" in drawing
