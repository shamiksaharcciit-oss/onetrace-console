"""Dark is the default theme: with no choice saved in the browser, and without scripts, every page
is dark -- a served page, a sealed page, the public demo, and a page the static export writes.

1. The stylesheets resolve to the dark palette with no theme set on the page, whatever the system's
   setting; the light palette only where a reader chose light, or chose to follow a light system.
2. A saved choice is honoured: light, dark, and "follow the system setting", which is now saved as
   a choice of its own (the scripts run in node, where node is installed).
3. Printing stays light: dark text on a light page, whichever theme is on screen.
4. Each inline script's hash is in the policy (tests/test_theme_switch.py, unchanged).
5. The dark palette's text and status colours read at 4.5:1 on every ground they sit on.

The resolver below reads the `:root` rules of a stylesheet as a browser applies them -- each
rule's selector against the page's `data-theme`, each `@media` block against the system's setting
or print, and the later of two equally specific rules winning -- and answers with the page colour.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from onetrace_console import frame

#: The root selectors the theme is written with, and what each needs of the page's `data-theme`.
SELECTORS = {
    ":root": lambda t: True,
    ":root:not([data-theme=light])": lambda t: t != "light",
    ":root[data-theme=light]": lambda t: t == "light",
    ":root[data-theme=dark]": lambda t: t == "dark",
    ":root[data-theme=system]": lambda t: t == "system",
}
MEDIA = {
    "(prefers-color-scheme:dark)": lambda system, printing: system == "dark",
    "(prefers-color-scheme:light)": lambda system, printing: system == "light",
    "print": lambda system, printing: printing,
}


def _root_rules(css: str) -> list[tuple[str | None, str, str]]:
    """Every rule whose selector is the root, as (media or None, selector, declarations), in order."""
    out = []
    css = re.sub(r"/\*.*?\*/|</?style>", "", css, flags=re.S)
    for m in re.finditer(r"@media ([^{]+)\{((?:[^{}]*\{[^{}]*\})*)\}|([^{}@]+)\{([^{}]*)\}", css):
        if m.group(1) is not None:
            for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", m.group(2)):
                for s in sel.split(","):
                    if s.strip().startswith(":root"):
                        out.append((m.group(1).strip(), s.strip(), body))
        else:
            for s in m.group(3).split(","):
                if s.strip().startswith(":root"):
                    out.append((None, s.strip(), m.group(4)))
    return out


def resolve(css: str, theme: str | None, system: str, printing: bool = False) -> dict[str, str]:
    """{role: value} and the colour scheme, as the page draws them."""
    applied = []
    for order, (media, selector, body) in enumerate(_root_rules(css)):
        assert selector in SELECTORS, f"a root selector this test can't read: {selector}"
        if media is not None:
            assert media in MEDIA, f"a media query this test can't read: {media}"
            if not MEDIA[media](system, printing):
                continue
        if SELECTORS[selector](theme):
            applied.append(((0 if selector == ":root" else 1), order, body))
    out: dict[str, str] = {}
    for _spec, _order, body in sorted(applied):
        for name, value in re.findall(r"(--[\w-]+|color-scheme)\s*:\s*([^;]+)", body):
            out[name] = value.strip()
    return out


def _sheets() -> dict[str, str]:
    from onetrace_console.viewer import page
    return {"console": frame.stylesheet().decode("utf-8"), "viewer": page._style()}


def _light_dark() -> tuple[str, str]:
    from onetrace_console.viewer.tokens import dark_palette, palette
    return palette()["--page"], dark_palette()["page"]


@pytest.mark.parametrize("where", ["console", "viewer"])
@pytest.mark.parametrize("system", ["light", "dark"])
def test_with_no_choice_and_without_scripts_the_page_is_dark(where, system, examined):
    light, dark = _light_dark()
    examined(1, f"the {where} stylesheet")
    drawn = resolve(_sheets()[where], None, system)
    assert drawn["--page"] == dark and drawn["color-scheme"] == "dark", drawn.get("--page")


@pytest.mark.parametrize("where", ["console", "viewer"])
@pytest.mark.parametrize("theme, system, want", [
    ("light", "light", "light"), ("light", "dark", "light"),
    ("dark", "light", "dark"), ("dark", "dark", "dark"),
    ("system", "light", "light"), ("system", "dark", "dark"),
])
def test_a_chosen_theme_is_drawn_as_chosen(where, theme, system, want, examined):
    light, dark = _light_dark()
    examined(1, f"the {where} stylesheet")
    drawn = resolve(_sheets()[where], theme, system)
    assert drawn["--page"] == (light if want == "light" else dark), (theme, system, drawn["--page"])
    assert drawn["color-scheme"] == want


@pytest.mark.parametrize("where", ["console", "viewer"])
@pytest.mark.parametrize("theme", [None, "light", "dark", "system"])
def test_printing_stays_light(where, theme, examined):
    from onetrace_console.viewer.tokens import palette
    examined(1, f"the {where} stylesheet")
    drawn = resolve(_sheets()[where], theme, "dark", printing=True)
    for role in ("page", "surface", "ink", "ink-muted"):
        assert drawn[f"--{role}"] == palette()[f"--{role}"], role


def test_no_page_sets_a_theme_of_its_own(examined):
    """The default is the stylesheet's, so a page read without scripts is dark: no page carries a
    theme in its markup (the theme switch's tests read every framed page for this)."""
    from tests.test_theme_switch import switch_problems
    page = "<html><body><footer>" + frame.THEME_SWITCH + frame.THEME_SCRIPT + "</footer></body></html>"
    examined(1, "page")
    assert switch_problems(page) == []


def test_the_sidebar_help_names_dark_as_the_default(examined):
    examined(1, "switch")
    assert "Switch to light theme" in frame.THEME_SWITCH


# ------------------------------------------------------------------ contrast in the dark default

#: The text and status colours the dark theme draws, each on the grounds it sits on: body text,
#: links and the declined chip's outline (the accent), the amber, red, green and neutral chips on
#: their own grounds and on the page's, and the navigation.
GROUNDS = ("page", "surface", "surface-alt", "surface-sunk")
PAIRS = ([(fg, bg) for fg in ("ink", "ink-soft", "ink-muted", "ink-faint", "accent", "cc-ink",
                              "bad-ink", "ok-ink", "neu-ink") for bg in GROUNDS]
         + [("ok-ink", "ok-bg"), ("cc-ink", "cc-bg"), ("bad-ink", "bad-bg"), ("neu-ink", "neu-bg"),
            ("accent-ink", "accent"), ("nav-ink", "nav-bg"), ("nav-ink-faint", "nav-bg"),
            ("nav-on-ink", "nav-on-bg"), ("cc-ink", "hl"), ("page", "cc-ink")])


def test_every_dark_text_and_status_colour_reads_at_4_5_to_1(examined):
    from tests.test_shared_style import _tokens, ratio
    tokens = _tokens("dark")
    examined(len(PAIRS), "dark colour pairs")
    low = [f"--{fg} on --{bg}: {ratio(fg, bg, tokens):.2f}:1" for fg, bg in PAIRS
           if ratio(fg, bg, tokens) < 4.5]
    assert low == []


def test_sabotage_a_dim_accent_is_named(examined):
    from tests.test_shared_style import _tokens, ratio
    dim = dict(_tokens("dark"), accent="#334155")
    examined(1, "planted accent")
    assert any(ratio(fg, bg, dim) < 4.5 for fg, bg in PAIRS if "accent" in (fg, bg))


# ------------------------------------------------------------------ the scripts, run

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed here, so the scripts can't be run")


def _run(stored, steps=(), dark=False):
    from tests.test_theme_switch import _run as run
    return run(stored, steps, dark=dark)


@needs_node
@pytest.mark.parametrize("stored, theme", [("dark", "dark"), ("light", "light"), ("system", "system"),
                                           (None, None), ("blue", None)])
def test_the_head_script_sets_each_saved_choice(stored, theme, examined):
    examined(1, "head script run")
    assert _run(stored)[0] == {"theme": theme}


@needs_node
@pytest.mark.parametrize("system", [False, True], ids=["light-system", "dark-system"])
def test_with_no_choice_the_switch_offers_light_and_the_way_to_the_system(system, examined):
    seen = _run(None, dark=system)
    examined(1, "page")
    assert seen[1] == {"theme": None, "stored": None, "switch": "Switch to light theme", "system": True}


@needs_node
def test_each_press_is_kept_and_follow_the_system_is_saved_as_a_choice(examined):
    seen = _run(None, ["switch", "switch", "system", "switch"], dark=False)
    examined(len(seen), "steps")
    assert seen[1:] == [
        {"theme": None, "stored": None, "switch": "Switch to light theme", "system": True},
        {"theme": "light", "stored": "light", "switch": "Switch to dark theme", "system": True},
        {"theme": "dark", "stored": "dark", "switch": "Switch to light theme", "system": True},
        {"theme": "system", "stored": "system", "switch": "Switch to dark theme", "system": False},
        {"theme": "dark", "stored": "dark", "switch": "Switch to light theme", "system": True},
    ]


@needs_node
@pytest.mark.parametrize("stored, system, switch", [
    ("light", True, "Switch to dark theme"), ("dark", False, "Switch to light theme"),
    ("system", True, "Switch to light theme"), ("system", False, "Switch to dark theme")])
def test_a_saved_choice_is_honoured_on_the_next_page(stored, system, switch, examined):
    seen = _run(stored, dark=system)
    examined(1, "page")
    assert seen[1] == {"theme": stored, "stored": stored, "switch": switch,
                       "system": stored != "system"}
