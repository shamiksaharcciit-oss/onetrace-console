"""The theme switch: light or dark for this browser, from the sidebar's footer.

1. With no choice made, a page follows the system setting: nothing on it sets a theme.
2. A stored choice is applied before the first paint: the head script is the first thing in
   `<head>`, before the stylesheet, and sets the theme from storage; blocked storage leaves the
   system's.
3. The switch's words say what a press does, a press is kept in this browser's storage and nowhere
   else, and "Follow the system setting" returns to the system's theme (the scripts run in node,
   where node is installed).
4. The policy names both scripts' hashes, as each page carries them.
5. No page has a form or an input; the switch's two buttons are the one named exception to "no
   mechanism to press", and nothing else is.
6. Without scripts the page is the page it was: both buttons `hidden`, nothing sets a theme.
7. Everywhere the sidebar is: a served page, a sealed page, the public demo and the static export.
The switch's contrast, in both themes, is held with every other pair in tests/test_shared_style.py.
Each check has its sabotage.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from onetrace_console import frame


@pytest.fixture(scope="module")
def pages(tmp_path_factory) -> Path:
    from onetrace_console.folder_load import build_public
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("theme") / "demo"
    build_public(folder)
    return folder


class Served:
    """A page of the demo as a public console serves it: its frame filled (a sealed page's was
    filled before its seal, and is served as written)."""
    def __init__(self, path: Path, root: Path):
        self.path, self.name = path, path.relative_to(root).as_posix()

    def read_text(self, encoding: str = "utf-8") -> str:
        return frame.fill(self.path.read_bytes(), self.name, onedoor=False, user=None,
                          public=True).decode(encoding)


def _framed(folder: Path) -> list[Served]:
    """Every page of the demo that carries the sidebar, as it is served."""
    root = folder / "store" / "pages"
    return [Served(p, root) for p in sorted(root.rglob("*.html"))
            if 'class="frame"' in p.read_text(encoding="utf-8")]


def without_the_console_s_own(page: str) -> str:
    """`page` with the console's own inline scripts (each named in the policy by its hash) and the
    theme switch taken out, each where it is: what other tests' "no script, no button" rules then
    read. The switch is the one named exception to "no mechanism to press"."""
    from onetrace_console.public import inline_scripts
    for own in (*inline_scripts(), frame.THEME_SWITCH):
        page = page.replace(own, "")
    return page


def head_problems(page: str) -> list[str]:
    """The stored choice is set before the page is drawn: the head script first in `<head>`, before
    any stylesheet, run as it is parsed."""
    head = re.search(r"<head>(.*?)</head>", page, re.S)
    if not head:
        return ["no <head>"]
    inner = head.group(1)
    at = inner.find(frame.THEME_HEAD_SCRIPT)
    if at < 0:
        return ["the head script is not in <head>"]
    out = []
    sheet = inner.find("<link rel=\"stylesheet\"")
    if sheet >= 0 and sheet < at:
        out.append("the stylesheet is linked before the head script")
    if re.search(r"<script[^>]*\b(?:async|defer)\b", inner):
        out.append("a head script is deferred")
    if page.count(frame.THEME_HEAD_SCRIPT) != 1:
        out.append(f"the head script appears {page.count(frame.THEME_HEAD_SCRIPT)} times")
    return out


def switch_problems(page: str) -> list[str]:
    """The switch once, in the footer, both buttons hidden until the script shows them, and the
    page's only buttons; no form, no input; nothing in the page sets a theme of its own."""
    out = []
    footer = re.findall(r"<footer>(.*?)</footer>", page, re.S)
    if sum(f.count(frame.THEME_SWITCH) for f in footer) != 1 or page.count(frame.THEME_SWITCH) != 1:
        out.append("the switch is not in the footer exactly once")
    if page.count(frame.THEME_SCRIPT) != 1:
        out.append("the switch's script is not on the page exactly once")
    buttons = re.findall(r"<button\b[^>]*>", page, re.I)
    named = re.findall(r"<button\b[^>]*>", frame.THEME_SWITCH)
    if buttons != named:
        out.append(f"buttons other than the switch's: {buttons}")
    if any(" hidden" not in b for b in buttons):
        out.append("a switch button is shown without the script")
    for mechanism in ("<form", "<input", "onclick=", "onsubmit=", "onchange="):
        if mechanism in page.lower():
            out.append(f"the page carries {mechanism!r}")
    if re.search(r"<html[^>]*data-theme", page):
        out.append("the page sets a theme of its own: it no longer follows the system")
    return out


def csp_problems(page: str, policy: str) -> list[str]:
    """Every inline script on the page is named in the policy by its own hash."""
    out = []
    for body in re.findall(r"<script>(.*?)</script>", page, re.S):
        digest = "'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'"
        if digest not in policy:
            out.append(f"a script the policy doesn't name: {body[:60]!r}")
    return out + ([] if "'unsafe-inline'" not in policy.split("script-src", 1)[1].split(";")[0]
                  else ["script-src allows 'unsafe-inline'"])


# ------------------------------------------------------------------ on every framed page

def test_every_framed_page_sets_the_stored_choice_before_paint(pages, examined):
    found = _framed(pages)
    examined(len(found), "framed pages")
    assert len(found) > 50
    assert [(p.name, h) for p in found for h in head_problems(p.read_text(encoding="utf-8"))] == []


def test_every_framed_page_has_the_switch_and_no_other_mechanism(pages, examined):
    found = _framed(pages)
    examined(len(found), "framed pages")
    assert [(p.name, s) for p in found for s in switch_problems(p.read_text(encoding="utf-8"))] == []


@pytest.mark.parametrize("local", [False, True], ids=["public", "local"])
def test_the_policy_names_both_scripts_hashes(pages, local, examined):
    from onetrace_console.public import content_security_policy
    policy = content_security_policy(local=local)
    found = _framed(pages)
    examined(len(found), "framed pages' scripts")
    assert [(p.name, c) for p in found for c in csp_problems(p.read_text(encoding="utf-8"), policy)] == []


def test_the_default_follows_the_system(examined):
    """No page sets a theme; the stylesheet's dark theme is the system's, unless a theme is set."""
    from onetrace_console.viewer.tokens import theme_css
    css = theme_css()
    examined(1, "the theme rules")
    assert "@media (prefers-color-scheme:dark){:root:not([data-theme=light])" in css
    assert ":root[data-theme=dark]" in css and ":root{color-scheme:light}" in css


def test_served_sealed_and_public_footers_all_carry_the_switch(examined):
    feet = [frame.footer(None), frame.footer("ana"), frame.footer(None, public=True),
            frame.sealed_footer(True), frame.sealed_footer(False), frame.sealed_footer(False, public=True)]
    examined(len(feet), "footers")
    assert all(f.count(frame.THEME_SWITCH) == 1 and f.count(frame.THEME_SCRIPT) == 1 for f in feet)
    #: Beside the version line.
    assert all(f.index("onetrace-console ") < f.index(frame.THEME_SWITCH) for f in feet)


def test_the_static_export_carries_the_switch(pages, tmp_path, examined):
    from onetrace_console.export_static import export
    from onetrace_console.store import Store
    key = Store(pages / "store" / "store").runs()[0].key
    written = export(pages / "store", [key], tmp_path / "export")
    found = [tmp_path / "export" / p for p in written if p.endswith(".html")
             and 'class="frame"' in (tmp_path / "export" / p).read_text(encoding="utf-8")]
    examined(len(found), "exported framed pages")
    assert found
    for p in found:
        page = p.read_text(encoding="utf-8")
        assert head_problems(page) == [] and switch_problems(page) == [], p.name


# ------------------------------------------------------------------ the scripts, run

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed here, so the scripts can't be run")

#: A page's worth of DOM for the scripts: the root's attributes, the two buttons, storage (or
#: storage that throws), and the system's setting. Prints what a reader would see after each step.
_HARNESS = r"""
const [head, foot, stored, blocked, systemDark, steps] = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const attrs = {};
const store = stored === null || blocked ? {} : {'KEY': stored};
global.localStorage = blocked ? {getItem(){throw new Error('blocked')}, setItem(){throw new Error('blocked')},
                                 removeItem(){throw new Error('blocked')}}
  : {getItem: k => (k in store ? store[k] : null), setItem: (k, v) => {store[k] = String(v)}, removeItem: k => {delete store[k]}};
function button(){ return {hidden: true, textContent: '', on: {}, addEventListener(e, f){this.on[e] = f}, focus(){}}; }
const a = button(), b = button();
global.document = {documentElement: {setAttribute(k, v){attrs[k] = v}, getAttribute(k){return k in attrs ? attrs[k] : null},
                                     hasAttribute(k){return k in attrs}, removeAttribute(k){delete attrs[k]}},
                   querySelector: s => s === '[data-theme-switch]' ? a : s === '[data-theme-system]' ? b : null};
global.matchMedia = () => ({matches: systemDark, addEventListener(){}});
const seen = [];
const look = () => seen.push({theme: attrs['data-theme'] || null, stored: 'KEY' in store ? store['KEY'] : null,
                              switch: a.hidden ? null : a.textContent, system: !b.hidden});
eval(head); seen.push({theme: attrs['data-theme'] || null});
eval(foot); look();
for (const s of steps) { (s === 'switch' ? a : b).on.click(); look(); }
console.log(JSON.stringify(seen));
"""


def _run(stored, steps=(), *, blocked=False, dark=False, head=None, foot=None) -> list[dict]:
    head = (head or frame.THEME_HEAD_SCRIPT).removeprefix("<script>").removesuffix("</script>")
    foot = (foot or frame.THEME_SCRIPT).removeprefix("<script>").removesuffix("</script>")
    harness = _HARNESS.replace("KEY", frame.THEME_KEY)
    done = subprocess.run([NODE, "-e", harness], input=json.dumps([head, foot, stored, blocked, dark, list(steps)]),
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@needs_node
@pytest.mark.parametrize("stored, theme", [("dark", "dark"), ("light", "light"), (None, None), ("blue", None)])
def test_the_head_script_sets_the_stored_choice_and_nothing_else(stored, theme, examined):
    examined(1, "head script run")
    assert _run(stored)[0] == {"theme": theme}


@needs_node
def test_blocked_storage_leaves_the_system_s_theme_and_the_switch_still_works(examined):
    seen = _run("dark", ["switch", "switch", "system"], blocked=True, dark=False)
    examined(len(seen), "steps")
    assert seen[0] == {"theme": None}
    assert [s["theme"] for s in seen[1:]] == [None, "dark", "light", None]
    assert all(s["stored"] is None for s in seen[1:])


@needs_node
def test_a_press_switches_names_the_next_theme_and_is_kept_and_follow_returns(examined):
    seen = _run(None, ["switch", "switch", "system"], dark=True)
    examined(len(seen), "steps")
    assert seen[1:] == [
        {"theme": None, "stored": None, "switch": "Switch to light theme", "system": False},
        {"theme": "light", "stored": "light", "switch": "Switch to dark theme", "system": True},
        {"theme": "dark", "stored": "dark", "switch": "Switch to light theme", "system": True},
        {"theme": None, "stored": None, "switch": "Switch to light theme", "system": False},
    ]


@needs_node
def test_a_stored_choice_shows_the_way_back_to_the_system(examined):
    seen = _run("light", dark=True)
    examined(len(seen), "steps")
    assert seen[1] == {"theme": "light", "stored": "light", "switch": "Switch to dark theme", "system": True}


# ------------------------------------------------------------------ sabotages

def test_sabotage_the_head_script_after_the_stylesheet_is_named(pages, examined):
    page = _framed(pages)[0].read_text(encoding="utf-8")
    moved = page.replace(frame.THEME_HEAD_SCRIPT + "\n", "", 1).replace("</head>", frame.THEME_HEAD_SCRIPT + "</head>", 1)
    gone = page.replace(frame.THEME_HEAD_SCRIPT, "", 1)
    examined(2, "planted heads")
    assert "the stylesheet is linked before the head script" in head_problems(moved)
    assert "the head script is not in <head>" in head_problems(gone)


@needs_node
def test_sabotage_a_head_script_that_does_nothing_is_caught(examined):
    examined(1, "planted script")
    assert _run("dark", head="<script></script>")[0] != {"theme": "dark"}


def test_sabotage_a_page_setting_its_own_theme_is_named(pages, examined):
    page = _framed(pages)[0].read_text(encoding="utf-8")
    examined(1, "planted page")
    assert any("follows the system" in p for p in switch_problems(page.replace("<html", '<html data-theme="dark"', 1)))


def test_sabotage_a_changed_script_the_policy_doesn_t_name_is_named(pages, examined):
    from onetrace_console.public import content_security_policy
    page = _framed(pages)[0].read_text(encoding="utf-8")
    changed = page.replace("'Switch to '", "'Switch to the '", 1)
    examined(1, "planted script")
    assert changed != page and csp_problems(changed, content_security_policy())


@pytest.mark.parametrize("planted, said", [
    ('<form action="/x"></form>', "'<form'"),
    ('<input name="q">', "'<input'"),
    ("<button>re-check</button>", "buttons other than the switch's"),
])
def test_sabotage_a_form_an_input_or_another_button_is_named(pages, planted, said, examined):
    page = _framed(pages)[0].read_text(encoding="utf-8")
    examined(1, "planted page")
    assert any(said in p for p in switch_problems(page.replace("</main>", planted + "</main>", 1)))


def test_sabotage_a_switch_shown_without_the_script_is_named(pages, examined):
    page = _framed(pages)[0].read_text(encoding="utf-8")
    examined(1, "planted page")
    shown = page.replace("<button type=\"button\" data-theme-switch hidden>", "<button type=\"button\" data-theme-switch>", 1)
    assert "a switch button is shown without the script" in switch_problems(shown)
