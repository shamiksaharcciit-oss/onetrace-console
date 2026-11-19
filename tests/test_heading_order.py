"""Headings go down one level at a time: no page jumps from a heading to one two levels below it.

A screen reader moves through a page by its headings; a level skipped reads as a missing part (axe's
`heading-order`). Read over every page of the public demo as built.
"""

from __future__ import annotations

import re

_HEADING = re.compile(r"<h([1-6])\b")


def skips(page: str) -> list[tuple[int, int]]:
    """Each (from, to) where a heading goes more than one level below the one before it."""
    levels = [int(m.group(1)) for m in _HEADING.finditer(page)]
    return [(a, b) for a, b in zip(levels, levels[1:]) if b > a + 1]


def test_no_page_skips_a_heading_level(shared_demo, examined):
    pages = sorted((shared_demo["folder"] / "store" / "pages").rglob("*.html"))
    examined(len(pages), "demo pages")
    found = {}
    for p in pages:
        bad = skips(p.read_text(encoding="utf-8"))
        if bad:
            found[p.relative_to(shared_demo["folder"]).as_posix()] = bad[:3]
    assert found == {}, f"{len(found)} pages: {dict(list(found.items())[:12])}"


def test_the_rule_names_a_skip(examined):
    examined(2, "planted pages")
    assert skips("<h1>a</h1><h3>b</h3>") == [(1, 3)]
    assert skips("<h1>a</h1><h2>b</h2><h3>c</h3><h2>d</h2>") == []
