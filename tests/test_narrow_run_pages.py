"""A run's page at a phone's width: nothing pushes it sideways, and its title fits in two lines.

- At 320 px (WCAG's reflow width), the case's values (the run's id, its times, its stages) wrap in their own column
  rather than push the page wider than the window: the demo's p8-50, its Proof page.
- At 375 px, the run's title (its id, in the record's own monospace) is drawn small enough to take at most two lines,
  breaking at its hyphens: the demo's p1-14.

Read in a browser (Playwright's Chromium, named by ONETRACE_BROWSER_PYTHON; skipped elsewhere).
"""

from __future__ import annotations

import json
import os
import re
import subprocess

import pytest

BROWSER_PYTHON = os.environ.get("ONETRACE_BROWSER_PYTHON", "")

SCRIPT = r"""
import json, sys
from playwright.sync_api import sync_playwright
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, path, width in json.loads(sys.argv[1]):
        page = b.new_page(viewport={"width": width, "height": 800})
        page.set_content(open(path, encoding="utf-8").read())
        out[name] = page.evaluate('''() => { const t = document.querySelector("[data-section=run-head] .run-title");
          const cs = getComputedStyle(t); const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.25;
          return {scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth,
            title_lines: Math.round(t.getBoundingClientRect().height / lh), title_px: parseFloat(cs.fontSize)} }''')
        page.close()
    b.close()
print(json.dumps(out))
"""


def _inline(path, css: str) -> str:
    return path.read_text(encoding="utf-8").replace(
        '<link rel="stylesheet" href="/static/console.css">', f"<style>{css}</style>"
    )


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_a_run_page_reflows_at_320_and_its_title_fits_two_lines_at_375(shared_demo, tmp_path, examined):
    from onetrace_console import frame

    css = frame.stylesheet().decode("utf-8")
    root = shared_demo["folder"] / "store" / "pages" / "runs"

    def folder(run_id):
        for case in root.glob("*/case.html"):
            title = re.search(r"<title>(.*?)</title>", case.read_text(encoding="utf-8"), re.S)
            if title and title.group(1).strip().endswith(run_id):
                return case.parent
        raise AssertionError(run_id)

    cases = []
    for name, run_id, page, width in (
        ("p8-50 proof at 320", "p8-50-invoice-permit-other-amount", "proof.html", 320),
        ("p1-14 at 375", "p1-14-candidate-set3-byte-changed", "case.html", 375),
        ("p1-14 proof at 320", "p1-14-candidate-set3-byte-changed", "proof.html", 320),
    ):
        f = tmp_path / f"{len(cases)}.html"
        f.write_text(_inline(folder(run_id) / page, css), encoding="utf-8")
        cases.append((name, str(f), width))
    script = tmp_path / "narrow.py"
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), json.dumps(cases)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    examined(len(got), "pages and widths")
    for name, r in got.items():
        assert r["scroll"] <= r["width"], (name, r)
    assert got["p1-14 at 375"]["title_lines"] <= 2 and got["p1-14 at 375"]["title_px"] <= 20, got
