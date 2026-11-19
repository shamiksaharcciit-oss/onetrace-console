"""Every button that starts work shows that it is working (`busy_script`).

- The scan: every `<button>` the console's source draws that starts work (a form's press or a fetch that waits on the
  console) carries the shared hook, `data-busy="<the work in progress>"`; the instant ones (the theme switch, the
  settings gear, Copy) carry none; and a static export's disabled stand-ins (Find, Compare's "Needs a running
  console") are neither, being no press at all.
- The policy: a local console's names the script by hash; a public console's is as it was, and no public page
  carries the script.
- In a browser (Playwright's Chromium, named by ONETRACE_BROWSER_PYTHON; skipped elsewhere): pages built from the
  console's own functions (Send's button with the panel's script, Compare's with its script, Remove's confirmation
  page, the sign-in page), served by a small server of the test's own on 127.0.0.1, whose answers it holds or fails. For each: a press
  disables the button with `aria-busy` within 100 ms, its label the work in progress; a double click makes one
  request; an error answer brings the button back with its own label (Send, Compare); Back leaves no button busy
  (Remove's confirmation, Sign in). And: a held Compare says "Waiting for the comparison: N s" after 5 s; with
  reduced motion the spinner is still; with script off, the forms still post.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from onetrace_console.busy_script import BUSY_SCRIPT

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
_BUTTON = re.compile(r"<button\b[^>]*>", re.S)
#: The instant presses: nothing waits on the console.
#: The frame's folds below 600 px open a part of the frame (`frame.FOLD_BUTTONS`).
INSTANT = (
    "data-theme-switch",
    "data-theme-system",
    "data-copy=",
    'class="gear ',
    'class="frame-fold ',
    #: A comparison's text diff switch, side by side or inline: it shows one view, and waits on nothing.
    "data-view=",
)
#: A static export's disabled stand-ins: no press at all.
NEITHER = ("data-compare-needs-console", 'type="button" \'\n')
BROWSER_PYTHON = os.environ.get("ONETRACE_BROWSER_PYTHON", "")


def _kind(tag: str) -> str:
    if any(m in tag for m in INSTANT):
        return "instant"
    if "data-compare-needs-console" in tag or ("disabled" in tag and "data-busy" not in tag and "btn-primary" in tag):
        return "neither"
    return "starts work"


def test_every_button_that_starts_work_carries_the_hook_and_no_instant_one_does(examined):
    wrong = []
    files = sorted(p for p in SRC.rglob("*.py") if "viewer" not in p.parts and p.name != "busy_script.py")
    seen = 0
    for path in files:
        for tag in _BUTTON.findall(path.read_text(encoding="utf-8")):
            seen += 1
            kind, hooked = _kind(tag), "data-busy=" in tag
            if (kind == "starts work") != hooked:
                wrong.append((path.name, kind, tag[:120]))
    examined(seen, "buttons in the source")
    assert not wrong, wrong


def test_the_local_policy_names_the_script_and_the_public_one_is_as_it_was(examined):
    from onetrace_console.public import _script_hash, content_security_policy

    examined(2, "policies")
    assert _script_hash(BUSY_SCRIPT) in content_security_policy(local=True)
    assert _script_hash(BUSY_SCRIPT) not in content_security_policy()


def test_no_public_page_carries_the_script(shared_demo, examined):
    pages = sorted((shared_demo["folder"] / "store" / "pages").rglob("*.html"))
    examined(len(pages), "public demo pages")
    assert not [p.name for p in pages if "onetraceBusy" in p.read_text(encoding="utf-8")]


# ------------------------------------------------------------------ in a browser

KEY = "a" * 64


def _pages() -> dict[str, str]:
    """The pages the browser loads, by path, each built from the console's own functions."""
    from onetrace_console import explain, explain_setup, frame
    from onetrace_console.compare_script import COMPARE_SCRIPT
    from onetrace_console.explain_script import EXPLAIN_SCRIPT
    from onetrace_console.render import _document
    from onetrace_console.signin import render_signin_page

    def framed(body: str) -> str:
        return frame.fill(_document("A page", body).encode(), "x", onedoor=False, user=None).decode()

    send = explain._button(f"/explain?c={KEY}&send=yes", "Send to 127.0.0.1", "primary", "Sending…")
    compare = (
        f'<p><button class="btn-secondary" data-busy="Comparing…" data-busy-wait="the comparison" type="button" '
        f'hidden data-compare-post="/compare?a={KEY}&amp;b={"b" * 64}">Compare</button> '
        '<span data-compare-said role="status"></span></p>'
    )
    import onetrace_console.explain as ex

    real = ex.model_config
    ex.model_config = lambda: {"provider": "openai", "name": "m", "base_url": "http://127.0.0.1:8080/v1"}
    try:
        confirm = explain_setup.confirm_page(None).replace('value=""', 'value="t"')
    finally:
        ex.model_config = real
    return {
        "/send": framed(
            f'<section data-section="explain" id="explain" class="explain" data-c="{KEY}">'
            f'<p data-explain="buttons">{send}</p><p data-explain-said role="status"></p></section>'
        )
        + EXPLAIN_SCRIPT,
        "/compare-page": framed(compare) + COMPARE_SCRIPT,
        "/confirm": frame.fill(confirm.encode(), "explain/setup", onedoor=False, user=None).decode(),
        "/signin": render_signin_page(csrf_token="t"),
        "/after": framed("<p>After the press.</p>"),
    }


SCRIPT = r"""
import json, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright
pages = json.loads(open(sys.argv[1], encoding="utf-8").read())
out = {}
hold = {"ms": 0, "status": 200}
posts = []

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def _send(self, status, ctype, body, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        self._send(200, "text/html; charset=utf-8", pages.get(self.path.split("?")[0], "<p>none</p>").encode())
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n).decode() if n else ""
        path = self.path.split("?")[0]
        posts.append((path, data))
        time.sleep(hold["ms"] / 1000)
        if hold["status"] >= 400:
            return self._send(hold["status"], "application/json", json.dumps({"error": "refused"}).encode())
        if path in ("/explain/setup", "/signin"):
            return self._send(303, "text/plain", b"", (("Location", "/after"),))
        return self._send(200, "application/json", json.dumps({"pages": {"diff": "/after"}}).encode())

server = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=server.serve_forever, daemon=True).start()
ORIGIN = f"http://127.0.0.1:{server.server_address[1]}"

def busy_at(page, sel, ms=100):
    return page.evaluate('''([sel, ms]) => new Promise(r => { const b = document.querySelector(sel); b.click();
      setTimeout(() => r([b.disabled, b.getAttribute("aria-busy"), b.textContent]), ms) })''', [sel, ms])

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context()
    page = ctx.new_page()
    # Send and Compare: a fetch the press starts
    for name, sel in (("send", "button[data-explain-post]"), ("compare", "button[data-compare-post]")):
        path = "/send" if name == "send" else "/compare-page"
        hold.update(ms=800, status=200); posts.clear(); page.goto(ORIGIN + path)
        out[name + " busy at 100 ms"] = busy_at(page, sel)
        out[name + " said at 100 ms"] = page.evaluate('''() => { const s = document.querySelector("[data-busy-said]");
          return s ? [s.getAttribute("role"), s.getAttribute("aria-live"), s.textContent] : null }''')
        page.goto(ORIGIN + path); posts.clear(); hold.update(ms=800, status=200)
        page.dblclick(sel); page.wait_for_timeout(1200)
        out[name + " requests from a double click"] = len(posts)
        hold.update(ms=300, status=500); page.goto(ORIGIN + path)
        page.click(sel); page.wait_for_timeout(1200)
        out[name + " said after an error"] = page.evaluate('() => document.querySelectorAll("[data-busy-said]").length')
        out[name + " after an error"] = page.evaluate('''(sel) => { const b = document.querySelector(sel);
          return [b.disabled, b.getAttribute("aria-busy"), b.textContent] }''', sel)
    # the 5 s line, on a Compare held for 6.5 s
    hold.update(ms=6500, status=200); page.goto(ORIGIN + "/compare-page")
    page.click("button[data-compare-post]"); page.wait_for_timeout(6000)
    out["the waiting line"] = page.evaluate('() => (document.querySelector("[data-busy-wait-line]") || {}).textContent || ""')
    page.wait_for_timeout(1500)
    # Remove's confirmation and Sign in: a form's press, then Back (the confirm lands at the setup page's
    # section, #setup-form, which the 303 keeps)
    for name, path, sel in (("confirm", "/confirm", 'button[value="remove-confirmed"]'), ("signin", "/signin", "button[type=submit]")):
        hold.update(ms=800, status=200); posts.clear(); page.goto(ORIGIN + path)
        if name == "signin":
            page.fill("input[name=username]", "u"); page.fill("input[name=password]", "p")
        #: A form's press leaves the page as it posts: the reading at 100 ms is kept in localStorage, read after.
        page.evaluate('''(sel) => { localStorage.removeItem("busy"); const b = document.querySelector(sel); b.click();
          setTimeout(() => localStorage.setItem("busy", JSON.stringify([b.disabled, b.getAttribute("aria-busy"),
            b.textContent, [...(b.closest("[data-busy-scope]") || b.form).querySelectorAll("button")].filter(x => !x.disabled).length])),
            100) }''', sel)
        page.wait_for_url(lambda u: u.split("#")[0] == ORIGIN + "/after", timeout=10000)
        state = json.loads(page.evaluate('() => localStorage.getItem("busy")') or "null")
        out[name + " busy at 100 ms"] = state if name == "confirm" else state[:3]
        out[name + " posted"] = [d for _, d in posts]
        page.go_back(); page.wait_for_timeout(300)
        out[name + " busy after Back"] = page.evaluate('() => document.querySelectorAll("button[aria-busy=true]").length')
        hold.update(ms=800, status=200); posts.clear(); page.goto(ORIGIN + path)
        if name == "signin":
            page.fill("input[name=username]", "u"); page.fill("input[name=password]", "p")
        page.dblclick(sel); page.wait_for_url(lambda u: u.split("#")[0] == ORIGIN + "/after", timeout=10000)
        out[name + " requests from a double click"] = len(posts)
    # reduced motion
    ctx2 = b.new_context(reduced_motion="reduce"); page2 = ctx2.new_page()
    hold.update(ms=1500, status=200); page2.goto(ORIGIN + "/compare-page"); page2.click("button[data-compare-post]")
    page2.wait_for_timeout(200)
    out["spinner under reduced motion"] = page2.evaluate('() => getComputedStyle(document.querySelector(".busy-spin")).animationName')
    page2.wait_for_timeout(1500)
    # script off: the forms still post
    ctx3 = b.new_context(java_script_enabled=False); page3 = ctx3.new_page()
    hold.update(ms=0, status=200); posts.clear()
    page3.goto(ORIGIN + "/signin"); page3.fill("input[name=username]", "u"); page3.fill("input[name=password]", "p")
    page3.click("button[type=submit]"); page3.wait_for_url(lambda u: u.split("#")[0] == ORIGIN + "/after", timeout=10000)
    page3.goto(ORIGIN + "/confirm"); page3.click('button[value="remove-confirmed"]'); page3.wait_for_url(lambda u: u.split("#")[0] == ORIGIN + "/after", timeout=10000)
    out["posted with script off"] = [path for path, _ in posts]
    print(json.dumps(out))
    b.close()
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_in_a_browser_each_press_is_busy_at_once_counts_once_and_always_ends(tmp_path, examined):
    pages = tmp_path / "pages.json"
    pages.write_text(json.dumps(_pages()), encoding="utf-8")
    script = tmp_path / "busy.py"
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), str(pages)], capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    examined(len(got), "browser readings")
    assert got["send busy at 100 ms"] == [True, "true", "Sending…"], got
    assert got["compare busy at 100 ms"] == [True, "true", "Comparing…"], got
    assert got["send requests from a double click"] == 1 and got["compare requests from a double click"] == 1, got
    #: Said at once in a polite live region, in the button's own busy words; gone when the busy state ends.
    assert got["send said at 100 ms"] == ["status", "polite", "Sending…"], got
    assert got["compare said at 100 ms"] == ["status", "polite", "Comparing…"], got
    assert got["send said after an error"] == 0 and got["compare said after an error"] == 0, got
    assert got["send after an error"] == [False, None, "Send to 127.0.0.1"], got
    assert got["compare after an error"] == [False, None, "Compare"], got
    assert re.fullmatch(r"Waiting for the comparison: [56] s", got["the waiting line"]), got
    assert got["confirm busy at 100 ms"] == [True, "true", "Removing…", 0], got
    assert got["signin busy at 100 ms"] == [True, "true", "Signing in…"], got
    assert any("action=remove-confirmed" in d for d in got["confirm posted"]), got
    assert got["confirm busy after Back"] == 0 and got["signin busy after Back"] == 0, got
    assert got["confirm requests from a double click"] == 1 and got["signin requests from a double click"] == 1, got
    assert got["spinner under reduced motion"] == "none", got
    assert got["posted with script off"] == ["/signin", "/explain/setup"], got
