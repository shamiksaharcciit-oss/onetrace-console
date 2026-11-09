"""The sign-in design note says what each cookie is: the session cookie is `HttpOnly`, and the CSRF cookie
is readable by the page, by design (a page's script sends it back as `X-CSRF-Token`). Held against the
`Set-Cookie` headers a sign-in answers with. The note is read only where it is (the public export leaves
docs/design/ out)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_signin_flow import _get_signin_form, _post, signin_enabled  # noqa: F401

NOTE = Path(__file__).resolve().parent.parent / "docs" / "design" / "signin-and-roles.md"
SESSION_LINE = "The session cookie is `Secure`, `HttpOnly` and `SameSite=Strict`."
CSRF_LINE = ("The CSRF cookie is `Secure` and `SameSite=Strict`, and readable by the page by design: a page's script "
             "sends it back as `X-CSRF-Token`.")


@pytest.mark.skipif(not NOTE.is_file(), reason="the public export leaves docs/design/ out")
def test_the_note_says_the_session_cookie_is_httponly_and_the_csrf_cookie_readable(examined):
    text = " ".join(NOTE.read_text(encoding="utf-8").split())
    examined(1, "design note")
    assert text.count(SESSION_LINE) == 2 and text.count(CSRF_LINE) == 2
    assert "Cookies are `Secure`, `HttpOnly`" not in text and "Cookies carry `Secure`, `HttpOnly`" not in text


def test_a_sign_in_answers_with_the_cookies_the_note_describes(signin_enabled, examined):
    base = signin_enabled
    csrf, form_token = _get_signin_form(base)
    _, _, headers, _ = _post(
        base, "/signin", f"username=alice&password=correct+horse+battery+staple&csrf_token={form_token}".encode(),
        headers={"Cookie": f"onetrace_csrf={csrf}", "Content-Type": "application/x-www-form-urlencoded"})
    cookies = headers.get("Set-Cookie")
    cookies = cookies if isinstance(cookies, list) else [c for c in (cookies or "").split(", ") if "=" in c]
    by_name = {c.split("=", 1)[0]: c for c in cookies}
    examined(len(by_name), "cookies set")
    assert "HttpOnly" in by_name["onetrace_session"] and "SameSite=Strict" in by_name["onetrace_session"]
    assert "HttpOnly" not in by_name["onetrace_csrf"] and "SameSite=Strict" in by_name["onetrace_csrf"]
