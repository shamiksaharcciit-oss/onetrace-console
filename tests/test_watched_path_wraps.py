"""A local console's watched-folder line wraps its path at a phone's width.

The line names the folder in `<code>`, which did not wrap: a Windows path (`C:\\Users\\...`) has no place to break, so
at 390 px it ran past the window on the runs list where the line is drawn. It now wraps anywhere, as the console's
other machine names do. Laid out in a browser at 390 px, the frame's own stylesheet, a long Windows path planted.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

BROWSER_PYTHON = os.environ.get("ONETRACE_BROWSER_PYTHON", "")
#: A path with no hyphen or space, as a temp folder's is: no place to break.
LONG = "C:\\Users\\someonewithalongname\\AppData\\Local\\Temp\\tmpq8w7e6r5t4y3u2i1o0p9a8s7d6\\agents\\runs"

SCRIPT = r"""
import json, sys
from playwright.sync_api import sync_playwright
html = open(sys.argv[1], encoding="utf-8").read()
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 390, "height": 900})
    page.set_content(html)
    print(json.dumps(page.evaluate('''() => { const c = document.querySelector('[data-section=watched] code');
        const r = c.getBoundingClientRect(); return {right: Math.round(r.right), width: innerWidth} }''')))
    b.close()
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_the_watched_folder_s_path_stays_inside_a_phone_s_width(tmp_path, monkeypatch, examined):
    from types import SimpleNamespace

    from onetrace_console import frame, render, watch

    state = SimpleNamespace(folder=LONG, version=1, taken=[], interval=2.0, last_read="", changed={})
    monkeypatch.setattr(watch, "CURRENT", SimpleNamespace(state=state))
    section = render.watched_section()
    assert "tmpq8w7e6r5t4y3u2i1o0p9a8s7d6" in section
    page = (
        '<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<style>{frame.stylesheet().decode()}</style></head><body>"
        f'<div class="shell"><main class="page">{section}</main></div></body></html>'
    )
    f, script = tmp_path / "page.html", tmp_path / "measure.py"
    f.write_text(page, encoding="utf-8")
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), str(f)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    examined(1, "watched-folder line")
    assert got["right"] <= got["width"], got
