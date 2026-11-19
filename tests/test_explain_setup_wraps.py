"""Nothing on Set up Explain runs past its card: at 1280, 1024, 768 and 390 pixels wide, every element in each of the
page's cards (`section.step`) ends at or inside the card's right edge, and no code block scrolls sideways: its
paragraphs and code lines wrap within the card, and long values (an address, the Python path, a long model name)
break where they must.

In a browser (Playwright's Chromium, named by ONETRACE_BROWSER_PYTHON), on a local console whose configuration names
a model with a long unbroken name; it skips where no browser is named, as the settings menu's browser test does.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request

import pytest

from tests.http_limits import limit
from tests.keychain import keychain, keyring_lib  # noqa: F401 - fixtures, requested by name
from tests.test_explain_panel import pair  # noqa: F401 - a fixture, requested by `local`
from tests.test_explain_setup import local  # noqa: F401 - a fixture
from tests.test_explain_setup_form import _post

BROWSER_PYTHON = os.environ.get("ONETRACE_BROWSER_PYTHON", "")
WIDTHS = (1280, 1024, 768, 390)
LONG_NAME = "a-model-name-with-no-break-in-it-" + "x" * 90
SCRIPT = r"""
import json, sys
from playwright.sync_api import sync_playwright
url, widths = sys.argv[1], json.loads(sys.argv[2])
PROBE = '''() => {
  const out = [];
  for (const card of document.querySelectorAll("section.step")) {
    const edge = card.getBoundingClientRect().right;
    for (const el of card.querySelectorAll("*")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      if (r.right > edge + 0.5) out.push(el.tagName.toLowerCase() + " past its card by " + Math.round(r.right - edge) + "px: " + (el.textContent || "").slice(0, 60));
      if ((el.tagName === "PRE" || el.tagName === "CODE") && el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).display !== "inline")
        out.push(el.tagName.toLowerCase() + " scrolls sideways: " + (el.textContent || "").slice(0, 60));
    }
    //: Each run of text, as it is laid out: a sentence that may not wrap runs past an element that does not.
    const walk = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
    for (let t = walk.nextNode(); t; t = walk.nextNode()) {
      if (!t.textContent.trim()) continue;
      const range = document.createRange(); range.selectNodeContents(t);
      for (const r of range.getClientRects()) {
        if (r.right > edge + 0.5) { out.push("text past its card by " + Math.round(r.right - edge) + "px: " + t.textContent.trim().slice(0, 60)); break; }
      }
    }
  }
  return out;
}'''
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    found = {}
    for w in widths:
        page.set_viewport_size({"width": w, "height": 900})
        if url.startswith("planted:"):
            page.set_content(url[len("planted:"):])
        else:
            page.goto(url)
        found[str(w)] = page.evaluate(PROBE)
    print(json.dumps(found))
    b.close()
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_nothing_runs_past_its_card_at_any_width(local, keychain, tmp_path, examined):
    _check(local, tmp_path, examined)


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_with_no_keychain_the_python_path_and_install_lines_wrap_too(local, tmp_path, examined):
    """No keychain: the page names the Python the console runs from and its install lines."""
    _check(local, tmp_path, examined, keychain=False)


def _check(local, tmp_path, examined, keychain: bool = True):
    base, _, _, _, _ = local
    status, _ = _post(
        f"{base}/explain/setup",
        {"action": "save", "provider": "openai", "name": LONG_NAME, "base_url": "http://127.0.0.1:8080/v1", "key": ""},
    )
    assert status == 200
    script = tmp_path / "wraps.py"
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run(
        [BROWSER_PYTHON, str(script), f"{base}/explain/setup", json.dumps(WIDTHS)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr
    found = json.loads(done.stdout)
    examined(len(WIDTHS), "widths of the setup page")
    assert not {w: f for w, f in found.items() if f}, found
    if not keychain:
        page = urllib.request.urlopen(f"{base}/explain/setup", timeout=limit(30)).read().decode("utf-8")
        assert 'data-setup="no-keychain"' in page


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_sabotage_a_line_that_cannot_wrap_is_found(tmp_path, examined):
    """A planted card holding a sentence that may not wrap, and a code line that scrolls: both found at 390."""
    planted = (
        '<main style="max-width:360px"><section class="step" style="border:1px solid">'
        '<p style="white-space:nowrap">Anyone who can run code as this user can read it, and so can any program they run.</p>'
        '<pre style="white-space:pre;overflow-x:auto"><code>pip install "onetrace-explain[keyring]&gt;=0.3" --and-more-options</code></pre>'
        "</section></main>"
    )
    script = tmp_path / "wraps.py"
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run(
        [BROWSER_PYTHON, str(script), "planted:" + planted, json.dumps([390])],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr
    found = json.loads(done.stdout)["390"]
    examined(2, "planted lines")
    assert any(f.startswith("text past its card") and "Anyone who can run code" in f for f in found), found
    assert any("scrolls sideways" in f for f in found), found
