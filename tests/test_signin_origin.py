"""With sign-in on, a state-changing request carried by a session cookie is refused with 403 where its
`Origin` (else its `Referer`) names another origin than the console's own. The console's own origin is
`sign_in.public_url` where it is set (behind a TLS-terminating proxy), else the request's own scheme and
`Host`. A request with neither header goes on to the CSRF check, as before; a bearer-token request is not
checked by origin at all. Over real HTTP, on `POST /signout`, whose 303 says the request was taken.
"""

from __future__ import annotations

import urllib.error

import pytest

from onetrace_console.config import Config
from onetrace_console.serve import Handler
from tests.test_roles_enforcement import _sign_in, roles_enabled  # noqa: F401
from tests.test_signin_flow import _get, _post

REFUSED = b"refused: this request comes from another origin than this console's\n"


def _signout(base, session, csrf, **headers):
    try:
        status, body, _, _ = _post(
            base,
            "/signout",
            b"",
            headers={"Cookie": f"onetrace_session={session}; onetrace_csrf={csrf}", "X-CSRF-Token": csrf, **headers},
        )
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read()
    return status, body


def _alive(base, session) -> bool:
    _get(base, "/health", headers={"Cookie": f"onetrace_session={session}"})
    return Handler.access_log.read_all_entries()[-1]["principal"] == "alice"


@pytest.mark.parametrize(
    "header, value",
    [
        ("Origin", "https://evil.example"),
        ("Origin", "null"),
        ("Origin", "http://127.0.0.1:1"),
        ("Referer", "https://evil.example/page.html"),
    ],
)
def test_a_foreign_origin_with_the_right_token_is_refused(roles_enabled, header, value, examined):
    base, _ = roles_enabled
    session, csrf = _sign_in(base)
    status, body = _signout(base, session, csrf, **{header: value})
    examined(1, f"a sign-out with {header}: {value}")
    assert (status, body) == (403, REFUSED)
    assert _alive(base, session)


@pytest.mark.parametrize("header", ["Origin", "Referer"])
def test_the_console_s_own_origin_is_allowed(roles_enabled, header, examined):
    base, _ = roles_enabled
    session, csrf = _sign_in(base)
    status, _ = _signout(base, session, csrf, **{header: base + ("/runs.html" if header == "Referer" else "")})
    examined(1, f"a sign-out with its own {header}")
    assert status == 303 and not _alive(base, session)


def test_no_origin_and_no_referer_with_the_right_token_is_allowed(roles_enabled, examined):
    base, _ = roles_enabled
    session, csrf = _sign_in(base)
    status, _ = _signout(base, session, csrf)
    examined(1, "a sign-out with neither header")
    assert status == 303 and not _alive(base, session)


def test_no_origin_and_the_wrong_token_is_still_refused_by_the_csrf_check(roles_enabled, examined):
    base, _ = roles_enabled
    session, csrf = _sign_in(base)
    status, body = _signout(base, session, csrf, **{"X-CSRF-Token": "wrong"})
    examined(1, "a sign-out with neither header and the wrong token")
    assert status == 403 and body != REFUSED and _alive(base, session)


def test_the_configured_public_url_is_the_console_s_own_origin(roles_enabled, monkeypatch, examined):
    base, _ = roles_enabled
    monkeypatch.setattr(Handler, "config", Config(sign_in={"enabled": True, "public_url": "https://console.example"}))
    session, csrf = _sign_in(base)
    refused = _signout(base, session, csrf, Origin=base)
    taken = _signout(base, session, csrf, Origin="https://console.example")
    examined(2, "sign-outs behind a public URL")
    assert refused == (403, REFUSED) and taken[0] == 303


def test_a_bearer_token_request_is_not_checked_by_origin(roles_enabled, examined):
    base, token = roles_enabled
    seen = []
    for headers in ({}, {"Origin": "https://evil.example"}):
        try:
            status, body, _, _ = _post(
                base, "/v1/runs", b"not-a-real-tar", headers={"Authorization": f"Bearer {token}", **headers}
            )
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        seen.append((status, body))
    examined(2, "ingests with and without a foreign Origin")
    assert seen[0] == seen[1] and seen[1][1] != REFUSED


@pytest.mark.parametrize("url", ["console.example", "https://", "https://console.example/path", "ftp://x.example"])
def test_a_public_url_that_is_not_an_origin_is_refused_at_start(url, examined):
    from onetrace_console.config import ConfigError, validate_sign_in_public_url

    examined(1, f"public_url {url!r}")
    with pytest.raises(ConfigError, match="public_url"):
        validate_sign_in_public_url(url)
