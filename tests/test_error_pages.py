"""An error a browser meets is a page in the console's frame; every other client gets the plain line as before
(`error_pages`).

- 404: an address with no page, asked for by a browser (`Accept: text/html`): a page with its title, `lang`, a
  heading, the words, the console's own line and a link to the Overview, the frame's navigation around it, and the
  theme's head script, so it follows the saved theme. Asked for without `Accept: text/html`: the line, byte for byte.
- 403: a viewer at an admin page, through Entra ID sign-in (the suite's fake): the same, signed in.
- 500: the server's error path, reached here by a test-only stand-in that raises inside the request's handling (no
  route of its own): the page keeps the line's reference; without `Accept: text/html`, the line as it was.
- An API path (`/v1/...`) answers a browser with the line, never a page.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request

from tests.http_limits import limit
from tests.test_entra_flow import entra, sign_in  # noqa: F401 - the fixture, used by name

HTML = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def _get(base, path, headers=None):
    req = urllib.request.Request(base + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=limit(30)) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read().decode("utf-8")


def _post(base, path, headers=None, body=b""):
    req = urllib.request.Request(base + path, data=body, method="POST", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=limit(30)) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read().decode("utf-8")


def _is_a_page(page: str, title: str) -> None:
    assert page.startswith("<!doctype html>") and '<html lang="en">' in page, page[:200]
    assert f"<title>{title} · onetrace</title>" in page, page[:400]
    assert re.search(r"<h1>[^<]+</h1>", page) and "<main>" in page
    assert '<a href="/">Go to the Overview</a>' in page
    assert '<nav class="frame" data-frame>' in page and "Overview</a>" in page
    assert "onetrace-console-theme" in page, "the theme's head script, so the page follows the saved theme"


def test_a_page_not_found_is_a_page_for_a_browser_and_the_line_for_anyone_else(server, examined):
    base, _root = server
    examined(2, "answers: a browser's, another client's")
    status, ctype, page = _get(base, "/runs/" + "0" * 64 + "/case.html", HTML)
    assert status == 404 and ctype.startswith("text/html"), (status, ctype)
    _is_a_page(page, "Page not found")
    assert "The console said: <code>not rendered: runs/" + "0" * 64 + "/case.html</code>" in page
    status, ctype, line = _get(base, "/runs/" + "0" * 64 + "/case.html")
    assert (status, ctype, line) == (404, "text/plain", "not rendered: runs/" + "0" * 64 + "/case.html\n")


def test_an_api_path_answers_a_browser_with_the_line(server, examined):
    base, _root = server
    examined(1, "API answer")
    status, ctype, line = _get(base, "/v1/nothing-here", HTML)
    assert status == 404 and ctype == "text/plain", (status, ctype, line)


def test_a_viewer_at_an_admin_page_meets_a_page_signed_in(entra, examined):  # noqa: F811
    base, fake, _root = entra
    examined(2, "answers")
    _s, _b, _h, session, _csrf = sign_in(base, fake, roles=("onetrace.viewer",))
    cookie = {"Cookie": f"onetrace_session={session}"}
    status, ctype, page = _get(base, "/admin/people", {**HTML, **cookie})
    assert status == 403 and ctype.startswith("text/html"), (status, ctype)
    _is_a_page(page, "Not available to you")
    assert "this credential does not grant the required role" in page
    status, ctype, line = _get(base, "/admin/people", cookie)
    assert (status, line) == (403, "this credential does not grant the required role\n")


def test_the_server_s_error_is_a_page_for_a_browser_keeping_its_reference(server, monkeypatch, examined):
    from onetrace_console.serve import Handler

    base, _root = server

    def fails(self, *a, **k):
        raise RuntimeError("a planted failure inside the request's handling")

    #: The test-only stand-in: no route, a failure inside the handling of a POST the console serves.
    monkeypatch.setattr(Handler, "_enforce_role", fails)
    examined(2, "answers")
    headers = {"Origin": base, "Content-Type": "application/x-www-form-urlencoded"}
    status, ctype, page = _post(base, "/compare", {**HTML, **headers}, b"a=x&b=y")
    assert status == 500 and ctype.startswith("text/html"), (status, ctype, page[:300])
    _is_a_page(page, "The console could not answer")
    assert re.search(r"its log names the cause under reference [0-9a-f]{8}", page)
    assert "planted failure" not in page
    status, ctype, line = _post(base, "/compare", headers, b"a=x&b=y")
    assert status == 500 and ctype == "text/plain"
    assert re.fullmatch(
        r"the console could not answer this request; its log names the cause under reference [0-9a-f]{8}\n", line
    )


def test_each_status_has_its_title_and_words_and_says_nothing_of_the_address(examined):
    from onetrace_console.error_pages import PAGES, document

    examined(len(PAGES), "statuses")
    for status, (title, words) in PAGES.items():
        page = document(status, "the line")
        assert f"<h1>{title}</h1>" in page and words.split(".")[0] in page, status
    assert '<a href="/signin">Sign in</a>' in document(401, "x") and "Sign in</a>" not in document(404, "x")
