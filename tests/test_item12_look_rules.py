"""Two rules every restyled page keeps, whatever the boards draw.

1. No caveat is dropped by styling. `tests/test_visible_text.py` holds that no sentence leaves a
   page's HTML; this holds that no rule of the boards' look hides one -- no `display:none`,
   `visibility:hidden`, zero opacity or zero font size -- in the console's page skin or the
   viewer's frame. The one exception: the frame's navigation is not printed.
2. Every text colour the look draws on its background reads: WCAG AA, 4.5:1, for each pair the
   rules set, worked out from the skin's own tokens.
"""
from __future__ import annotations

import re

import pytest

HIDING = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?![.\d])"
                    r"|font-size\s*:\s*0(?![.\d])")


def _sheets() -> dict[str, str]:
    from onetrace_console.viewer.page import FRAME_CSS
    from onetrace_console.frame import PAGE_CSS
    return {"PAGE_CSS": PAGE_CSS, "FRAME_CSS": FRAME_CSS}


def test_no_rule_of_the_look_hides_text(examined):
    found = []
    for name, css in _sheets().items():
        printing = re.sub(r"@media print\{[^{}]*\{[^{}]*\}\}", "", css)
        found += [f"{name}: {m.group(0)}" for m in HIDING.finditer(printing)]
    examined(len(_sheets()), "stylesheets read for a rule that hides text")
    assert not found, found


def test_the_only_rule_that_hides_is_the_navigation_in_print():
    from onetrace_console.viewer.page import FRAME_CSS
    assert re.findall(r"@media print\{([^{}]*)\{display:none\}\}", FRAME_CSS) == ["nav.frame"]


def _tokens() -> dict[str, str]:
    from onetrace_console.viewer.tokens import root_css
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", root_css()))


def _luminance(hex_colour: str) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _ratio(fg: str, bg: str) -> float:
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


#: (text, background): every pair the look sets -- pills, the banner, cards and panels, the page,
#: the first difference in the bad ink, the links, and the navigation.
PAIRS = [("ok-ink", "ok-bg"), ("cc-ink", "cc-bg"), ("bad-ink", "bad-bg"), ("neu-ink", "neu-bg"),
         ("ink", "surface"), ("ink", "page"), ("ink-muted", "surface"), ("ink-muted", "page"),
         ("bad-ink", "surface"), ("accent", "surface"), ("accent", "page"),
         #: Couldn't check, amber ink on the neutral fill with an amber outline.
         ("cc-ink", "neu-bg"),
         ("nav-ink", "nav-bg"), ("nav-on-ink", "nav-on-bg"), ("nav-ink-faint", "nav-bg")]


@pytest.mark.parametrize("fg, bg", PAIRS)
def test_each_text_colour_the_look_draws_reads_on_its_background(fg, bg):
    tokens = _tokens()
    ratio = _ratio(tokens[fg], tokens[bg])
    assert ratio >= 4.5, f"--{fg} on --{bg}: {ratio:.2f}:1"


def test_every_pair_the_look_uses_is_one_this_file_checks():
    """A colour the rules set on a background must be among PAIRS, or this test is told about it."""
    css = "".join(_sheets().values())
    used = set(re.findall(r"background:var\(--([\w-]+)\);\s*color:var\(--([\w-]+)\)", css))
    assert len(used) >= 6, used
    assert {(fg, bg) for bg, fg in used} <= set(PAIRS), {(fg, bg) for bg, fg in used} - set(PAIRS)
