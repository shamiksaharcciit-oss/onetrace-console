"""A quoted field is never broken mid-word when the word fits.

    A quoted field broken mid-word ("so it was not ru / n" on the 1440 run page): quoted fields
    wrap with `overflow-wrap: anywhere`, not break-all, so a word breaks only when it can't fit
    whole. Verbatim text is unchanged.

`word-break: break-all` breaks between any two characters even where the whole word would fit on
the next line; `overflow-wrap: anywhere` moves the word to the next line first and breaks it only
if it is longer than the line. The two rules that broke quoted text were `pre` (every verbatim
layer, the report's quoted lines among them) and `.fp` (fingerprints and record words).
"""
from __future__ import annotations

import re

from onetrace_console.viewer.page import CSS, FRAME_CSS


def _rules(css: str) -> list[tuple[str, str]]:
    return [(s.strip(), b) for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def test_no_rule_breaks_a_word_that_fits():
    rules = _rules(CSS) + _rules(FRAME_CSS)
    assert len(rules) > 50, "the stylesheets were not read"
    breaking = [s for s, b in rules if re.search(r"word-break:\s*break-all", b)]
    assert not breaking, f"break-all breaks a word that would fit whole: {breaking}"


def test_quoted_fields_wrap_anywhere_only_when_a_word_cannot_fit():
    for selector in ("pre", ".fp"):
        body = [b for s, b in _rules(CSS) if s == selector]
        assert len(body) == 1, selector
        assert "overflow-wrap:anywhere" in body[0].replace(" ", ""), selector
