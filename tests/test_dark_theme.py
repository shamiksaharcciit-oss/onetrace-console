"""The dark theme: the same roles as the light skin, darker, from the visual target's own tokens.

1. Every role the light skin has gets a dark value: a token of the target's file, or a translucent
   one mixed over the opaque one it is drawn on. The three roles the target's file has no token
   for are named, with why.
2. Both stylesheets -- the console's and the viewer's own -- carry it, switched by the reader's
   system setting (`prefers-color-scheme`). An explicit `data-theme` on the root wins: the theme
   switch in the sidebar's footer sets it (tests/test_theme_switch.py), and so may a
   screenshot or a test. The navigation carries no other control.
3. The vendored target file is pinned: changed bytes raise.

The contrast of every text colour on its ground, in both themes, is held in
tests/test_shared_style.py. Each check has its sabotage.
"""
from __future__ import annotations

import re

import pytest


def test_every_light_role_has_a_dark_value_and_the_derived_ones_say_why(examined):
    from onetrace_console.viewer import tokens
    dark = tokens.dark_palette()
    examined(len(dark), "roles in the dark theme")
    assert set(dark) == set(tokens.palette_names())
    assert all(re.fullmatch(r"#[0-9a-f]{6}", v) for v in dark.values()), dark
    #: A value written here, not taken from the target's file, is one this console chose: named, with why.
    literal = {r for r, how in tokens.DARK_ROLES.items() if isinstance(how, tuple) and how[0] == "derived"}
    assert literal <= set(tokens.DARK_DERIVED) <= set(dark), (literal, tokens.DARK_DERIVED)


@pytest.mark.parametrize("where", ["console", "viewer"])
def test_each_stylesheet_switches_by_the_system_setting_only(where, examined):
    from onetrace_console import frame
    from onetrace_console.viewer import page
    from onetrace_console.viewer.tokens import dark_palette
    css = frame.stylesheet().decode("utf-8") if where == "console" else page._style()
    examined(1, f"the {where} stylesheet")
    media = re.search(r"@media \(prefers-color-scheme:dark\)\{:root:not\(\[data-theme=light\]\)\{([^}]*)\}\}", css)
    assert media, "no dark theme for the system's dark setting"
    forced = re.search(r":root\[data-theme=dark\]\{([^}]*)\}", css)
    assert forced and forced.group(1) == media.group(1)
    for role, value in dark_palette().items():
        assert f"--{role}:{value};" in media.group(1), role


def test_the_navigation_s_only_control_is_the_theme_switch_in_its_footer(examined):
    """The theme follows the system until a reader picks one with the footer's switch; the
    navigation itself carries nothing to press and nothing to run (the console's no-form rule)."""
    from onetrace_console import frame
    examined(2, "the navigation, without and with its footer")
    nav = frame.nav("home.html", onedoor=False, foot="")
    assert not re.search(r"<(button|form|input|script)\b|theme", nav, re.I), nav
    foot = frame.footer(None)
    rest = foot.replace(frame.THEME_SWITCH, "", 1).replace(frame.THEME_SCRIPT, "", 1)
    assert not re.search(r"<(button|form|input|script)\b", rest, re.I), rest


def test_the_dark_contrast_check_names_a_dim_ink(monkeypatch, examined):
    """Sabotage: the dark theme's body text drawn in the page's own ground colour."""
    from onetrace_console.viewer import tokens
    from tests.test_shared_style import _sheet, contrast_problems
    tokens.dark_palette.cache_clear()
    monkeypatch.setitem(tokens.DARK_ROLES, "ink", "--bg")
    try:
        examined(1, "planted dim ink")
        assert any("--ink on" in p for p in contrast_problems(_sheet(), "dark"))
    finally:
        monkeypatch.undo()
        tokens.dark_palette.cache_clear()


def test_changed_vendored_bytes_raise(monkeypatch, tmp_path, examined):
    from onetrace_console.viewer import tokens
    changed = tmp_path / "TOKENS_DARK.css"
    changed.write_bytes(tokens.DARK_PATH.read_bytes().replace(b"#0b1626", b"#0b1627", 1))
    monkeypatch.setattr(tokens, "DARK_PATH", changed)
    tokens.dark_source.cache_clear()
    try:
        examined(1, "changed vendored file")
        with pytest.raises(tokens.TokenError):
            tokens.dark_source()
    finally:
        monkeypatch.undo()
        tokens.dark_source.cache_clear()
