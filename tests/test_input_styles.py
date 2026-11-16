"""Inputs, selects and placeholders follow the theme: background, text and border from the theme's tokens
(`frame.INPUT_CSS`), the placeholder at 4.5:1 or more against the field (it is the only hint `base_url` has), and a
visible focus outline. Computed from the tokens in both themes; the rules are in the console's one stylesheet.
"""

from __future__ import annotations

import re

import pytest

from onetrace_console import frame
from tests.test_button_styles import _themes, contrast

FIELD = "input:not([type=hidden],[type=checkbox],[type=radio]),select,textarea"
FOCUS = ":is(input,select,textarea):focus-visible"


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\{([^}]*)\}", frame.INPUT_CSS)
    assert m, selector
    return m.group(1)


def _var(rule: str, prop: str) -> str:
    m = re.search(rf"(?:^|;){prop}:var\(--([a-z-]+)\)", rule)
    assert m, (prop, rule)
    return m.group(1)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_field_s_text_and_placeholder_read_at_4_5_to_1(theme, examined):
    tokens = _themes()[theme]
    field = _rule(FIELD)
    ground = tokens[_var(field, "background")]
    placeholder = tokens[_var(_rule("::placeholder"), "color")]
    examined(2, f"a field's text and placeholder, {theme}")
    assert contrast(tokens[_var(field, "color")], ground) >= 4.5
    assert contrast(placeholder, ground) >= 4.5
    #: A field's edge reads at 3:1 or more, as a control's edge must.
    assert contrast(tokens[re.search(r"border:1px solid var\(--([a-z-]+)\)", field).group(1)], tokens["surface"]) >= 3


def test_a_field_has_a_visible_focus_outline_and_the_stylesheet_carries_the_rules(examined):
    examined(2, "the focus outline and the stylesheet")
    assert re.search(r"outline:2px solid var\(--[a-z-]+\)", _rule(FOCUS))
    assert frame.INPUT_CSS in frame.stylesheet().decode("utf-8")
