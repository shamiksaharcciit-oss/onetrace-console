"""One button style for the console: every `<button>` it renders carries one of three styles, defined once in
`frame.py` from the theme's tokens: primary (a form's main action), secondary (every other action) and destructive
(an action that removes something). Each has its own background, text and border, in both themes, and hover,
focus-visible (a visible outline) and disabled states. Text on every button meets 4.5:1 against its background in
both themes, disabled too.

Checked three ways: the console's source, every `<button>` written in it; the public demo's pages as built, every
button on them; and the local console's pages with forms (Set up Explain, sign-in, the Tokenizers page, the neighbours
setup, search), drawn as they are served.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from onetrace_console import frame

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
STYLES = ("btn-primary", "btn-secondary", "btn-destructive")
_BUTTON = re.compile(r"<button\b[^>]*>", re.S)
#: In source, a class written as `btn-{style}` (explain's `_button`, whose callers pass one of the three).
_FORMED = re.compile(r"\bbtn-\{[a-z_]+\}")


def unstyled(html: str) -> list[str]:
    """Each `<button ...>` tag in `html` whose class names none of the three styles."""
    out = []
    for tag in _BUTTON.findall(html):
        m = re.search(r'class="([^"]*)"', tag)
        if not m or not (set(m.group(1).split()) & set(STYLES) or _FORMED.search(m.group(1))):
            out.append(tag)
    return out


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    channels = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _themes() -> dict[str, dict[str, str]]:
    from onetrace_console.viewer import skin_tokens, tokens

    light = dict(re.findall(r"--([a-z-]+):(#[0-9a-f]{6})", skin_tokens.BLOCK))
    return {"light": light, "dark": {**light, **tokens.dark_palette()}}


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\{([^}]*)\}", frame.BUTTON_CSS)
    assert m, selector
    return m.group(1)


def _var(rule: str, prop: str) -> str:
    m = re.search(rf"(?:^|;){prop}:var\(--([a-z-]+)\)", rule)
    assert m, (prop, rule)
    return m.group(1)


def test_every_button_in_the_source_carries_a_style(examined):
    found = {}
    files = sorted(p for p in SRC.rglob("*.py") if "viewer" not in p.parts)
    for path in files:
        tags = unstyled(path.read_text(encoding="utf-8"))
        if tags:
            found[path.relative_to(SRC).as_posix()] = tags
    examined(len(files), "source files")
    assert not found, found


@pytest.mark.parametrize("style", STYLES)
def test_each_style_reads_at_4_5_to_1_in_both_themes_disabled_too(style, examined):
    themes = _themes()
    states = {
        "": _rule(f"button.{style}"),
        ":hover": _rule(f"button.{style}:hover"),
        ":disabled": _rule(f"button.{style}:disabled"),
    }
    examined(len(states) * len(themes), f"{style}'s states in both themes")
    for theme, tokens in themes.items():
        for state, rule in states.items():
            ink = _var(rule, "color") if "color:" in rule else _var(states[""], "color")
            ground = _var(rule, "background") if "background:" in rule else _var(states[""], "background")
            assert contrast(tokens[ink], tokens[ground]) >= 4.5, (style, state, theme, ink, ground)


@pytest.mark.parametrize("style", STYLES)
def test_each_style_has_its_border_and_a_visible_focus_outline(style, examined):
    examined(2, f"{style}'s border and focus")
    assert "border:1px solid var(--" in _rule(f"button.{style}")
    assert re.search(r"outline:2px solid var\(--[a-z-]+\)", _rule(f"button.{style}:focus-visible"))


def test_every_button_on_the_public_demo_s_pages_carries_a_style(shared_demo, examined):
    pages = sorted((shared_demo["folder"] / "store" / "pages").rglob("*.html"))
    found = {p.name: unstyled(p.read_text(encoding="utf-8")) for p in pages}
    examined(len(pages), "public demo pages")
    assert not {k: v for k, v in found.items() if v}


def test_every_button_on_the_local_console_s_forms_carries_a_style(tmp_path, examined):
    from onetrace_console import explain_setup, search_page, signin, token_upload
    from onetrace_console.neighbours import pages as neighbour_pages
    from onetrace_console.store import Store

    store = Store(tmp_path / "store")
    drawn = {
        "explain setup": explain_setup.page(store),
        "sign-in": signin.render_signin_page(csrf_token="t"),
        "tokenizers": token_upload.settings_page(tmp_path / "store"),
        "neighbours missing": neighbour_pages.missing_page(),
        "search": search_page.page(None, "", "", store, public=False),
    }
    examined(len(drawn), "local pages with forms")
    assert all(_BUTTON.search(drawn[name]) for name in ("explain setup", "sign-in", "search")), drawn.keys()
    assert not {name: unstyled(page) for name, page in drawn.items() if unstyled(page)}
