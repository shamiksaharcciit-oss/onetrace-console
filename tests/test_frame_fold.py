"""The frame folds below 600 px: the demo's banner to one line that opens on a press, the navigation to one bar with a
menu button. Every page gets it, and no page loses a link or a word.

- **No script.** Each fold is the browser's own popover (`popover`, `popovertarget`), as the settings menu is: the
  button is a real button, the fold closes on Escape and on a press outside, and a public console, whose pages carry
  no script, folds the same.
- **At 600 px and above nothing moves:** the buttons are not drawn, and each folded part is laid out in place
  (`display: contents`), so the frame is as it was.
- **The banner's words are unchanged:** the line is the banner's own first sentence, and the fold holds the banner
  whole.
- **In a browser,** at 390: folded, then opened by pointer and by keyboard, the links reachable in order, closed by
  Escape; at 768 and 1280: no button, every link shown, and every part of the frame and the page beside it in the
  same box as the frame drawn before it folded.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

import pytest

BROWSER_PYTHON = os.environ.get("ONETRACE_BROWSER_PYTHON", "")


def _nav(public: bool, onedoor: bool = False) -> str:
    from onetrace_console.frame import footer, nav

    return nav("home.html", onedoor=onedoor, foot=footer(None, public=public, setup_link=not public), public=public)


def test_the_links_and_the_footer_fold_behind_one_menu_button(examined):
    from onetrace_console import frame

    examined(4, "frames")
    for public in (False, True):
        for onedoor in (False, True):
            got = _nav(public, onedoor)
            button = re.search(
                r'<button type="button" class="frame-fold btn-secondary" popovertarget="frame-menu">(.*?)</button>', got
            )
            assert button and button.group(1) == frame.MENU, (public, onedoor)
            menu = re.search(r'<div id="frame-menu" popover data-frame-fold="menu">(.*)</div>$', got, re.S)
            assert menu, (public, onedoor)
            hrefs = re.findall(r'<a href="([^"]+)"', menu.group(1))
            assert hrefs[: len(frame.items(onedoor))] == [h for _l, h, _ in frame.items(onedoor)], (public, onedoor)
            assert "<footer" in menu.group(1)


def test_the_banner_folds_to_its_own_first_sentence_its_words_unchanged(examined):
    from onetrace_console import frame
    from onetrace_console.public import BANNER

    got = _nav(True)
    examined(1, "public frame")
    line = re.search(
        r'<button type="button" class="frame-fold btn-secondary" popovertarget="frame-banner">(.*?)</button>', got
    )
    assert line and line.group(1) == BANNER.split(". ")[0] + "."
    fold = re.search(r'<div id="frame-banner" popover data-frame-fold="banner">(.*?)</div>', got, re.S)
    assert fold and fold.group(1) == frame.banner()
    assert "frame-banner" not in _nav(False)


def test_no_page_loses_a_link_or_a_word(examined):
    """The frame's links and words, read with the fold's own two buttons left out, are the frame's before it folded:
    each link once, in order, the banner and the footer whole."""
    from onetrace_console import frame

    examined(4, "frames")
    for public in (False, True):
        for onedoor in (False, True):
            folded = _nav(public, onedoor)
            unfolded = re.sub(r'<button type="button" class="frame-fold[^"]*"[^>]*>.*?</button>', "", folded)
            unfolded = re.sub(r'<div id="frame-(?:banner|menu)" popover data-frame-fold="[a-z]+">', "", unfolded)
            before = (
                '<div class="brand">onetrace</div>'
                + (frame.banner() if public else "")
                + "".join(
                    f'<a href="{h}"' + (' aria-current="page"' if label == "Overview" else "") + f">{label}</a>"
                    for label, h, _ in frame.items(onedoor)
                )
                + frame.footer(None, public=public, setup_link=not public)
            )
            assert unfolded.replace("</div>", "") == before.replace("</div>", ""), (public, onedoor)


def test_at_600_and_above_the_fold_is_not_drawn_and_below_it_is_one_bar(examined):
    from onetrace_console.frame import FOLD_CSS, stylesheet

    examined(1, "stylesheet")
    assert FOLD_CSS in stylesheet().decode("utf-8")
    wide = re.search(r"@media \(min-width:600px\)\{(.*?)\n\}", FOLD_CSS, re.S)
    assert wide and "nav.frame .frame-fold{display:none}" in wide.group(1)
    assert "nav.frame [data-frame-fold]{display:contents}" in wide.group(1)
    assert "@media (max-width:599px)" in FOLD_CSS
    assert "transition" not in FOLD_CSS and "animation" not in FOLD_CSS, "reduced motion: nothing moves"


SCRIPT = r"""
import json, sys
from playwright.sync_api import sync_playwright
page_html = open(sys.argv[1], encoding="utf-8").read()
before_html = open(sys.argv[2], encoding="utf-8").read()
BOXES = '''() => [...document.querySelectorAll("nav.frame a, nav.frame [data-frame=banner], nav.frame footer, nav.frame .brand, main")]
  .map(e => { const r = e.getBoundingClientRect(); return [e.tagName, e.textContent.trim().slice(0, 30), Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] })'''
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (390, 768, 1280):
        page = b.new_page(viewport={"width": width, "height": 900})
        page.set_content(page_html)
        vis = lambda sel: page.evaluate('(s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden" }', sel)
        links = lambda: page.evaluate('() => [...document.querySelectorAll("nav.frame a[href]")].filter(a => { const r = a.getBoundingClientRect(); return r.width > 0 && r.height > 0 }).map(a => a.getAttribute("href"))')
        r = {"menu button": vis('[popovertarget="frame-menu"]'), "links shown": links()}
        if width == 390:
            r["bar height"] = page.evaluate('() => Math.round(document.querySelector("nav.frame").getBoundingClientRect().height)')
            page.click('[popovertarget="frame-menu"]')
            r["links after a press"] = links()
            page.keyboard.press("Escape")
            r["links after Escape"] = links()
            page.focus('[popovertarget="frame-menu"]')
            page.keyboard.press("Enter")
            r["links after Enter"] = links()
            page.keyboard.press("Tab")
            r["focus after Tab"] = page.evaluate('() => document.activeElement.getAttribute("href")')
            page.mouse.click(200, 880)
            r["links after a press outside"] = links()
            page.focus("a.skip-link")
            r["first in tab order"] = page.evaluate('() => document.activeElement.textContent')
        if width != 390:
            r["boxes"] = page.evaluate(BOXES)
            page.set_content(before_html)
            r["boxes before"] = page.evaluate(BOXES)
        out[str(width)] = r
        page.close()
    b.close()
print(json.dumps(out))
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_in_a_browser_the_menu_folds_opens_by_pointer_and_keyboard_and_closes(tmp_path, examined):
    from onetrace_console import frame
    from onetrace_console.render import _document

    css = frame.stylesheet().decode("utf-8")
    page = _document("A page", '<div class="cp"><p id="x">The page.</p></div>', skip=("Skip to the page", "x"))
    page = frame.fill(page.encode(), "home.html", onedoor=False, user=None, public=True).decode()
    page = page.replace('<link rel="stylesheet" href="/static/console.css">', f"<style>{css}</style>")
    assert "<style>" in page, "the stylesheet was not put in"
    f = tmp_path / "page.html"
    f.write_text(page, encoding="utf-8")
    #: The same page with the frame as it was before it folded, from the frame's own parts: the brand, the banner, the
    #: links and the footer, in that order, with no fold.
    old = (
        '<div class="brand">onetrace</div>'
        + frame.banner()
        + "".join(
            f'<a href="{h}"' + (' aria-current="page"' if label == "Overview" else "") + f">{label}</a>"
            for label, h, _ in frame.items(False)
        )
        + frame.footer(None, public=True, setup_link=False)
    )
    head, rest = page.split('<nav class="frame" data-frame>', 1)
    before = head + '<nav class="frame" data-frame>' + old + "</nav>" + rest.split("</nav>", 1)[1]
    frame_before = before.split("<nav", 1)[1].split("</nav>", 1)[0]
    assert "frame-fold" not in frame_before and "popover" not in frame_before
    b = tmp_path / "before.html"
    b.write_text(before, encoding="utf-8")
    script = tmp_path / "fold.py"
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), str(f), str(b)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    every = [h for _l, h, _ in frame.items(False)]
    examined(len(got), "widths")
    small = got["390"]
    assert small["menu button"] is True and small["links shown"] == [], got
    assert small["bar height"] <= 120, got
    assert small["links after a press"][: len(every)] == every, got
    assert small["links after Escape"] == [], got
    assert small["links after Enter"][: len(every)] == every and small["focus after Tab"] == every[0], got
    assert small["links after a press outside"] == [], got
    assert small["first in tab order"] == "Skip to the page", got
    for width in ("768", "1280"):
        assert got[width]["menu button"] is False and got[width]["links shown"][: len(every)] == every, (width, got)
        #: Nothing moves: every part of the frame, and the page beside it, where it was before the frame folded.
        assert got[width]["boxes"] == got[width]["boxes before"], width


SIGNED_IN_SCRIPT = r"""
import json, sys
from playwright.sync_api import sync_playwright
page_html = open(sys.argv[1], encoding="utf-8").read()
BOXES = '''() => { const box = s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) return null;
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return {left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top), bottom: Math.round(r.bottom),
      hit_itself: !!hit && (hit === e || e.contains(hit))} };
  return {gear: box("[data-frame=gear]"), menu: box('[popovertarget="frame-menu"]'),
    width: document.documentElement.clientWidth, scroll_width: document.documentElement.scrollWidth} }'''
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for theme in ("light", "dark"):
        for width in (375, 599, 600, 1440):
            page = b.new_page(viewport={"width": width, "height": 800})
            page.set_content(page_html.replace('<html lang="en">', f'<html lang="en" data-theme="{theme}">', 1))
            out[f"{theme} {width}"] = page.evaluate(BOXES)
            page.close()
    b.close()
print(json.dumps(out))
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_in_a_browser_a_signed_in_page_s_gear_sits_beside_the_menu_button_never_on_it(tmp_path, examined):
    #: A signed-in local console's page, as it serves it: the frame, the settings gear and its menu with Sign out.
    #: Below 600 px the gear is in the bar beside the menu button, each pressable at its middle; at 600 px and above
    #: the menu button is not drawn and the gear keeps its place at the top right.
    from onetrace_console import frame
    from onetrace_console.render import _document
    from onetrace_console.store import Store

    css = frame.stylesheet().decode("utf-8")
    page = _document("A page", '<div class="cp"><h1 id="x">The page</h1></div>', skip=("Skip to the page", "x"))
    page = frame.fill(
        page.encode(),
        "home.html",
        onedoor=False,
        user="Ada Admin",
        setup_link=True,
        store=Store(tmp_path / "store"),
        csrf="t",
    ).decode()
    assert 'data-frame="gear"' in page, "no gear on the signed-in page"
    page = page.replace('<link rel="stylesheet" href="/static/console.css">', f"<style>{css}</style>")
    f = tmp_path / "page.html"
    f.write_text(page, encoding="utf-8")
    script = tmp_path / "signed_in.py"
    script.write_text(SIGNED_IN_SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), str(f)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    examined(len(got), "widths and themes")
    for key, r in got.items():
        theme, width = key.split()
        gear, menu = r["gear"], r["menu"]
        assert gear is not None and gear["hit_itself"], (key, r)
        assert r["scroll_width"] <= r["width"], (key, r)
        if int(width) < 600:
            assert menu is not None and menu["hit_itself"], (key, r)
            apart = gear["right"] <= menu["left"] or menu["right"] <= gear["left"]
            apart = apart or gear["bottom"] <= menu["top"] or menu["bottom"] <= gear["top"]
            assert apart, (key, r)
        else:
            assert menu is None, (key, r)
            assert r["width"] - gear["right"] <= 20 and gear["top"] <= 20, (key, r)
