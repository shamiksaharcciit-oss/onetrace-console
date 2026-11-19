"""Text that scrolls sideways scrolls in a region a keyboard can reach.

The verifier's printed output on a run's receipt is a `<pre>` inside a named, focusable region (`words.scroll_region`).
The region scrolls, never the `<pre>` inside it: a `<pre>` that scrolled on its own could not be reached by keyboard
(axe's `scrollable-region-focusable`), and below 1024 px, where a region's tables stack, a long row would push the page
sideways. Read in a browser (Playwright's Chromium, named by ONETRACE_BROWSER_PYTHON; skipped elsewhere), on the
public demo's receipt of p1-01, at 1440 and 375 px.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

BROWSER_PYTHON = os.environ.get("ONETRACE_BROWSER_PYTHON", "")

SCRIPT = r"""
import json, sys
from playwright.sync_api import sync_playwright
html = open(sys.argv[1], encoding="utf-8").read()
READ = '''() => { const pre = document.querySelector('pre[data-section="verifier-output"]'); const box = pre.closest('.scroll-x');
  return {pre: getComputedStyle(pre).overflowX, region: getComputedStyle(box).overflowX, focusable: box.tabIndex === 0,
    region_scrolls: box.scrollWidth > box.clientWidth, pre_scrolls: pre.scrollWidth > pre.clientWidth && getComputedStyle(pre).overflowX !== 'visible',
    page: [document.documentElement.scrollWidth, document.documentElement.clientWidth]} }'''
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (1440, 375):
        page = b.new_page(viewport={"width": width, "height": 900})
        page.set_content(html)
        out[str(width)] = page.evaluate(READ)
        page.close()
    b.close()
print(json.dumps(out))
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_the_receipt_s_printed_output_scrolls_in_its_region_never_by_itself(shared_demo, tmp_path, examined):
    from onetrace_console import frame
    from tests.test_run_page_order import _pages_of

    case = _pages_of(shared_demo, "p1-01-baseline-set1")
    assert case, "no p1-01"
    root = shared_demo["folder"] / "store" / "pages" / "runs"
    receipt = next(
        p.parent / "receipt.html"
        for p in sorted(root.glob("*/case.html"))
        if p.read_text(encoding="utf-8") == case["case.html"]
    )
    css = frame.stylesheet().decode("utf-8")
    html = receipt.read_text(encoding="utf-8").replace(
        '<link rel="stylesheet" href="/static/console.css">', f"<style>{css}</style>"
    )
    f = tmp_path / "receipt.html"
    f.write_text(html, encoding="utf-8")
    script = tmp_path / "scroll.py"
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), str(f)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    examined(len(got), "widths")
    for width, r in got.items():
        assert r["focusable"] and r["pre"] == "visible" and not r["pre_scrolls"], (width, r)
        assert r["region"] in ("auto", "scroll"), (width, r)
        assert r["page"][0] <= r["page"][1], (width, r)
