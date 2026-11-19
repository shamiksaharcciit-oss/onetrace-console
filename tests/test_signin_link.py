"""Sign-in through Entra ID starts with a link, not a form.

Every response carries `form-action 'self'` (`public.content_security_policy`), and a Chromium-based browser applies
it to the redirect a form's submission is answered with: a form that leads to the identity provider, even through
the console's own `/signin/oidc/start`, is blocked there, and the button does nothing. So every control that leads to
the issuer is a link, drawn as a button, and the policy stays as it is:

- the sign-in page's "Sign in with Microsoft", to `/signin/oidc/start?next=<the same-origin path>`;
- a refused sign-in's "Start again", to `/signin`;
- the signed-out page's "Sign out of Microsoft too", to Entra ID's own end-session endpoint.

Each keeps its busy state (`busy_script`, which takes a link's press as it takes a button's).

- **Read:** no sign-in page holds a `<form>`; each control is an `<a>` with its destination, its class and its busy
  words; `next` is carried escaped.
- **In a browser** (Playwright's Chromium, named by ONETRACE_BROWSER_PYTHON; skipped elsewhere, saying why): the
  console served with the suite's fake Entra ID (`tests/fake_entra.py`), from the press of "Sign in with Microsoft"
  to the signed-in Overview, the browser's console holding no policy violation.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

import pytest

from tests.test_entra_flow import entra  # noqa: F401 - the fixture, used by name

BROWSER_PYTHON = os.environ.get("ONETRACE_BROWSER_PYTHON", "")
_FORM = re.compile(r"<form\b[^>]*>", re.S)


def _pages(issuer_logout: str) -> dict[str, str]:
    from onetrace_console.signin import render_oidc_refused_page, render_oidc_signin_page, render_signed_out_page

    return {
        "sign in": render_oidc_signin_page("/comparisons.html?a=1&b=2"),
        "refused": render_oidc_refused_page("The sign-in took too long."),
        "no role": render_oidc_refused_page("No role.", no_role=True),
        "signed out": render_signed_out_page(issuer_logout),
        "signed out, Microsoft unreachable": render_signed_out_page(None),
    }


def test_no_sign_in_page_holds_a_form(examined):
    pages = _pages("https://login.example.invalid/tenant/oauth2/v2.0/logout")
    examined(len(pages), "sign-in pages")
    assert {name: _FORM.findall(page) for name, page in pages.items() if _FORM.search(page)} == {}


def test_each_control_that_leads_to_the_issuer_is_a_link_drawn_as_a_button_with_its_busy_state(examined):
    pages = _pages("https://login.example.invalid/tenant/oauth2/v2.0/logout")
    examined(3, "controls")
    assert (
        '<a class="btn-primary" href="/signin/oidc/start?next=%2Fcomparisons.html%3Fa%3D1%26b%3D2" '
        'data-busy="Signing in…">Sign in with Microsoft</a>'
    ) in pages["sign in"]
    assert (
        '<a class="btn-secondary" href="/signin" data-busy="Opening the sign-in page…">Start again</a>'
        in pages["refused"]
    )
    assert (
        '<a class="btn-secondary" href="https://login.example.invalid/tenant/oauth2/v2.0/logout" '
        'data-busy="Signing out of Microsoft…">Sign out of Microsoft too</a>'
    ) in pages["signed out"]


def test_a_link_drawn_as_a_button_has_the_button_s_look_and_the_policy_is_unchanged(examined):
    from onetrace_console.frame import BUTTON_CSS
    from onetrace_console.public import content_security_policy

    examined(3, "rules and policies")
    assert "a.btn-primary[href]" in BUTTON_CSS and "a.btn-secondary[href]" in BUTTON_CSS
    for local in (True, False):
        assert "form-action 'self'" in content_security_policy(local=local)


SCRIPT = r"""
import json, sys
from playwright.sync_api import sync_playwright
base = sys.argv[1]
out = {"console": []}
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    page.on("console", lambda m: out["console"].append(m.text) if m.type == "error" else None)
    page.goto(base + "/signin", wait_until="networkidle")
    page.click("text=Sign in with Microsoft")
    try:
        page.wait_for_url(base + "/", timeout=15000)
        page.wait_for_load_state("networkidle")
    except Exception as e:
        out["waited"] = str(e).splitlines()[0]
    out["url"] = page.url
    out["signed in as"] = page.evaluate("(document.querySelector('footer') || document.body).innerText.includes('Signed in as')")
    out["title"] = page.title()
    b.close()
print(json.dumps(out))
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_in_a_browser_the_button_reaches_the_issuer_and_signs_in(entra, tmp_path, examined):  # noqa: F811
    base, fake, _root = entra
    fake.user = {**fake.user, "roles": ["onetrace.viewer"]}
    script = tmp_path / "signin.py"
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), base], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    examined(1, "sign-in in Chromium, from the press to the Overview")
    assert not [m for m in got["console"] if "Content Security Policy" in m], got
    assert got["url"] == base + "/" and got["signed in as"], got
