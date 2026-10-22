"""A panel wider than the screen says so, and a keyboard can reach it.

The comparison graph scrolls inside its panel, wider than the card at 1280px. Its cue is CSS only
(the page's one script is the print helper): a scrollbar always drawn, and a fade at whichever
edge has more to see, driven by the panel's own scroll position. The fade is a mask, so it
fades the graph's boxes and links themselves rather than sitting behind them. Where a browser
cannot drive it (no scroll timelines), there is no fade and the drawn scrollbar remains.

The comparison page's table of changes scrolls inside its own panel too, so a phone-width screen
never scrolls the whole page sideways. Each scroll panel can be reached with Tab and is named for a
screen reader: what scrolls, and that it scrolls sideways.

The CSS and the HTML are read here; a browser check run beside the suite, at 1280 and 390,
measures them.
"""
from __future__ import annotations

import re

import pytest

from onetrace_console.viewer.page import CSS
from onetrace_console.textdiff_page import SUFFIX as TEXT_PAGE

FADE = 48          #: px, at the edge with more to see
SCROLLBAR = 12     #: px, the drawn scrollbar's height, which the fade leaves alone


def cue_problems(css: str) -> list[str]:
    """What is missing from the graph panel's cue in `css`, or nothing."""
    out = []
    gate = re.search(r"@supports \(animation-timeline:scroll\(\)\)\{\.graph-box(?:,\.scroll-x)?\{(.*?)\}\}",
                     css, re.S)
    if gate is None:
        return ["no fade rule for the graph panel, gated on scroll timelines"]
    rule = gate.group(1)
    for needed in ("animation-timeline:scroll(self inline)", "animation:graph-box-fade",
                   "var(--graph-fade-start)", "var(--graph-fade-end)",
                   f"mask-size:100% calc(100% - {SCROLLBAR}px),100% {SCROLLBAR}px"):
        if needed not in rule:
            out.append(f"the fade rule lacks {needed}")
    if "-webkit-mask-image:" not in rule or re.search(r"(^|;)mask-image:", rule) is None:
        out.append("the fade is not a mask on the panel (both spellings)")
    for name in ("--graph-fade-start", "--graph-fade-end"):
        reg = re.search(rf"@property {name}\{{([^}}]*)\}}", css)
        if reg is None or "syntax:'<length>'" not in reg.group(1) or "initial-value:0px" not in reg.group(1):
            out.append(f"{name} is not a registered length starting at 0px")
    frames = re.search(r"@keyframes graph-box-fade\{from\{([^}]*)\}\s*to\{([^}]*)\}\}", css)
    if frames is None:
        out.append("no keyframes for the fade")
    else:
        start, end = frames.groups()
        if f"--graph-fade-start:0px;--graph-fade-end:{FADE}px" not in start.replace(" ", ""):
            out.append(f"at the start the fade is not at the end edge only ({start})")
        if f"--graph-fade-start:{FADE}px;--graph-fade-end:0px" not in end.replace(" ", ""):
            out.append(f"at the end the fade is not at the start edge only ({end})")
    bar = re.search(r"\.graph-box::-webkit-scrollbar\{height:(\d+)px\}", css)
    if bar is None or int(bar.group(1)) != SCROLLBAR:
        out.append(f"the drawn scrollbar is not {SCROLLBAR}px, the band the fade leaves alone")
    if not re.search(r"\.graph-box:focus-visible\{outline:", css):
        out.append("the panel shows no focus")
    return out


def test_the_graph_panel_has_its_cue(examined):
    examined(1, "stylesheet")
    assert cue_problems(CSS) == []


@pytest.mark.parametrize("removed", ["the gated fade rule", "the scroll timeline", "a registration",
                                     "the keyframes", "the focus ring"])
def test_taking_out_any_part_of_the_cue_is_caught(removed, examined):
    """The sabotage: each part of the cue removed in turn is named."""
    css = {
        "the gated fade rule": re.sub(r"@supports \(animation-timeline:scroll\(\)\)\{\.graph-box[^{]*\{.*?\}\}",
                                      "", CSS, flags=re.S),
        "the scroll timeline": CSS.replace("animation-timeline:scroll(self inline)", ""),
        "a registration": re.sub(r"@property --graph-fade-end\{[^}]*\}", "", CSS),
        "the keyframes": re.sub(r"@keyframes graph-box-fade\{from\{[^}]*\}\s*to\{[^}]*\}\}", "", CSS),
        "the focus ring": re.sub(r"\.graph-box:focus-visible\{[^}]*\}", "", CSS),
    }[removed]
    examined(1, f"stylesheet without {removed}")
    assert css != CSS, "the sabotage changed nothing"
    assert cue_problems(css), removed


# ------------------------------------------------------------------ the pages, as drawn

@pytest.fixture(scope="module")
def pages(shared_cli_demo) -> dict[str, str]:
    """The demo's pages, drawn as the console draws them: the comparison page and the run pages."""
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_cli_demo["folder"]
    root = folder / "store" / "pages"
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*.html")}


#: A comparison page's "Proof" view, beside it.
PROOF_PAGE = "-proof.html"
_REGION = re.compile(r'<div class="graph-box" tabindex="0" role="region" aria-label="([^"]+)">')


def test_each_graph_panel_is_a_named_region_a_keyboard_reaches(pages, examined):
    from onetrace_console.viewer.sentences import template
    compare = [h for rel, h in pages.items() if rel.startswith("diff/") and not rel.endswith(TEXT_PAGE)  # a Diff page, not its text diff's own
               and not rel.endswith(PROOF_PAGE)]  # its "What changed" view, which holds the graph
    runs = [h for rel, h in pages.items() if rel.endswith(("/case.html", "/proof.html"))]
    examined(len(compare) + len(runs), "pages with a graph")
    assert compare and runs
    #: 0.1.1's demo store compares graph-shaped pairs (P2, P3) and straight-line ones (P1); each
    #: comparison page draws one graph, a straight-line pair's as a line, and it is the named region.
    shaped = [h for h in compare if 'data-shape="dag"' in h]
    assert shaped and len(shaped) < len(compare), "both shapes are among the demo's comparisons"
    for html in compare:
        assert html.count('class="graph-box"') == 1
        assert _REGION.findall(html) == [template("graph.region.comparison")]
    for html in runs:
        assert _REGION.findall(html) == [template("graph.region")] * html.count('class="graph-box"')
    assert template("graph.region.comparison") == "Comparison graph, scrolls sideways"


def test_the_changes_table_scrolls_in_its_own_named_region(pages, examined):
    """In the scroll region every wide table has (`words.scroll_region`): its scrollbar drawn, its
    ring drawn by the frame around it, which the fade's mask cannot clip."""
    from onetrace_console.render import CHANGES_REGION
    #: Each comparison as its two views together: a straight-line pair's tables are on "Proof".
    compare = [h + pages.get(rel[:-len(".html")] + PROOF_PAGE, "") for rel, h in pages.items()
               if rel.startswith("diff/") and not rel.endswith((TEXT_PAGE, PROOF_PAGE))]
    examined(len(compare), "comparison pages")
    for html in compare:
        wrapped = re.findall(r'<div class="scroll-frame"><div class="scroll-x" data-scroll="changes" '
                             r'tabindex="0" role="region" aria-label="([^"]+)"><table data-section="changes"',
                             html)
        #: One changes table per verb that draws one: the graph-shaped pair's, the straight-line
        #: pair's two (diff and localize) -- each in its own region.
        tables = html.count('<table data-section="changes"')
        assert tables >= 1 and wrapped == [CHANGES_REGION] * tables
    assert CHANGES_REGION == "Changes, scrolls sideways"
    assert re.search(r"(^|\n)\.scroll-x\{overflow-x:auto;max-width:100%\}", CSS)
    assert re.search(r"(^|\n)\.scroll-x::-webkit-scrollbar\{height:12px\}", CSS)
    assert re.search(r"\.scroll-frame:has\(>\.scroll-x:focus-visible\)\{outline:", CSS)
