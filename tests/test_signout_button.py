"""Sign out, in the settings menu: every signed-in session sees it, a local account's and one from Entra ID of
each role. It is a plain form (a POST with the session's CSRF token), so it works without script, and its press
shows the busy state. After it, the sign-in page; with Entra ID, the page that offers Microsoft's own sign-out.
Not drawn with no session, nor on a public console. A second press is harmless."""

from __future__ import annotations

import html
import re
import urllib.request

import pytest

from tests.http_limits import limit
from tests.test_entra_flow import entra, sign_in  # noqa: F401 -- the fixture, used by name
from tests.test_roles_enforcement import _sign_in as local_sign_in
from tests.test_roles_enforcement import roles_enabled  # noqa: F401 -- the fixture, used by name
from tests.test_signin_flow import _get, _post

FORM = re.compile(r'<form method="post" action="/signout"[^>]*>(.*?)</form>', re.S)


def _signout_form(page: str) -> str | None:
    m = FORM.search(page)
    return m.group(1) if m else None


def _token_in(form: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]*)"', form).group(1)


def _press(base, session: str, token: str):
    return _post(
        base,
        "/signout",
        f"csrf_token={token}".encode(),
        headers={
            "Cookie": f"onetrace_session={session}; onetrace_csrf={token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": base,
        },
    )


def test_a_local_session_sees_sign_out_and_one_press_ends_it(roles_enabled, examined):  # noqa: F811
    base, _token = roles_enabled
    examined(7, "the form, its token, its busy words; the press; the session gone; a second press; the search page")
    session, csrf = local_sign_in(base)
    status, body, _h, _ = _get(base, "/", headers={"Cookie": f"onetrace_session={session}; onetrace_csrf={csrf}"})
    form = _signout_form(body.decode())
    assert status == 200 and form is not None
    assert _token_in(form) == csrf
    assert '<button class="btn-secondary" data-busy="Signing out…" type="submit">Sign out</button>' in form
    status, _b, headers, _ = _press(base, session, csrf)
    assert status == 303 and headers["Location"] == "/signin"
    assert _get(base, "/", headers={"Cookie": f"onetrace_session={session}"})[0] == 303
    status, _b, headers, _ = _press(base, session, csrf)
    assert status == 303 and headers["Location"] == "/signin", "a second press is harmless"
    session, csrf = local_sign_in(base)
    status, body, _h, _ = _get(
        base, "/search?q=x", headers={"Cookie": f"onetrace_session={session}; onetrace_csrf={csrf}"}
    )
    assert status == 200 and _token_in(_signout_form(body.decode()) or 'name="csrf_token" value=""') == csrf


@pytest.mark.parametrize("role", ["viewer", "investigator", "admin"])
def test_an_entra_session_of_each_role_sees_sign_out_and_goes_on_to_microsoft_s(entra, role, examined):  # noqa: F811
    base, fake, _root = entra
    examined(4, f"{role}: the form, the press, Microsoft's offer, a second press")
    _status, _page, _h, session, csrf = sign_in(base, fake, roles=[f"onetrace.{role}"])
    status, body, _h, _ = _get(base, "/", headers={"Cookie": f"onetrace_session={session}; onetrace_csrf={csrf}"})
    form = _signout_form(body.decode())
    assert status == 200 and form is not None and _token_in(form) == csrf
    status, body, _h, _ = _press(base, session, csrf)
    page = html.unescape(body.decode())
    assert status == 200 and "You're signed out of onetrace" in page and fake.endpoint("logout") in page
    status, _b, _h, _ = _press(base, session, csrf)
    assert status == 200, "a second press is harmless"


def test_no_session_no_sign_out(server, examined):
    """Sign-in off, as a local console runs: the menu draws no Sign out."""
    base, _root = server
    examined(1, "the Overview with sign-in off")
    page = urllib.request.urlopen(base + "/", timeout=limit(30)).read().decode()
    assert _signout_form(page) is None and 'data-frame="settings"' in page


def test_a_public_console_draws_no_sign_out(server, monkeypatch, examined):
    from onetrace_console.config import Config
    from onetrace_console.serve import Handler

    base, _root = server
    monkeypatch.setattr(Handler, "config", Config(public=True, sign_in={**Config().sign_in, "enabled": False}))
    examined(1, "the comparisons page on a public console")
    page = urllib.request.urlopen(base + "/comparisons.html", timeout=limit(30)).read().decode()
    assert _signout_form(page) is None
