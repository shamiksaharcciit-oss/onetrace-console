"""The Runs page at a phone's width: one compact row per run, its details on the run's own page.

Below 600 px each run's row says its id (its link) and its pipeline, when it started and how long it took, whether
its records agree and its verdict, on three or four lines; its step marks, its duration bar, its closing, its kinds,
its drift and its "More" are on the run's own page. At 375 px, every row of fifty was a stack of every cell, each
under its label: up to 441 px a row, 26,000 px of page.

Read in a browser (Playwright's Chromium, named by ONETRACE_BROWSER_PYTHON; skipped elsewhere), on the public
demo's Runs page as a public console serves it.
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
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (375, 1440):
        page = b.new_page(viewport={"width": width, "height": 800})
        page.set_content(html)
        out[str(width)] = page.evaluate('''() => { const rows = [...document.querySelectorAll('table[data-section=runs-page] tbody tr:not(.more-row)')];
          return {rows: rows.length, tallest: Math.max(...rows.map(r => r.getBoundingClientRect().height)),
            links: rows.filter(r => r.querySelector('a[href*="case.html"]')).length,
            steps_shown: rows.filter(r => { const c = r.querySelector('[data-answer=steps]'); return c && c.getBoundingClientRect().height > 0 }).length,
            page: [document.documentElement.scrollWidth, document.documentElement.clientWidth]} }''')
        page.close()
    b.close()
print(json.dumps(out))
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_at_375_each_run_is_a_compact_row_and_at_1440_the_table_is_whole(shared_demo, tmp_path, examined):
    from onetrace_console import frame
    from onetrace_console.runs_page import page as runs_page

    index = json.loads((shared_demo["folder"] / "store" / "run_index.json").read_text(encoding="utf-8"))
    html = runs_page(index, {}, public=True)
    html = frame.fill(html.encode(), "runs", onedoor=False, user=None, public=True).decode()
    html = html.replace(
        '<link rel="stylesheet" href="/static/console.css">', f"<style>{frame.stylesheet().decode('utf-8')}</style>"
    )
    f = tmp_path / "runs.html"
    f.write_text(html, encoding="utf-8")
    script = tmp_path / "runs.py"
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), str(f)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    examined(len(got), "widths")
    small, wide = got["375"], got["1440"]
    assert small["rows"] >= 20 and small["links"] == small["rows"], small
    #: Three or four lines, a long id wrapping once, and a run with a gated step its mark: within about six lines.
    assert small["tallest"] <= 240 and small["steps_shown"] == 0, small
    assert small["page"][0] <= small["page"][1], small
    assert wide["steps_shown"] == wide["rows"], wide
