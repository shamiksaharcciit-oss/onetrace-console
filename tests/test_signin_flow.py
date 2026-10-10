"""End to end over real HTTP: the sign-in form, CSRF, rate limiting, sessions,
sign-out, and the access log recording the real principal with no secrets.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request

import pytest

from onetrace_console.accounts import AccountStore
from onetrace_console.config import Config
from onetrace_console.rate_limit import ConcurrencyLimiter, RateLimiter
from onetrace_console.serve import ACCOUNTS_DIRNAME, Handler
from onetrace_console.sessions import SessionStore


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    """A sign-in POST's own 303 (or the sign-out route's own redirect) must be
    observed directly -- its `Set-Cookie` headers are on THAT response, not
    whatever `urllib` would otherwise silently follow it to.
    """
    def http_response(self, request, response):
        return response
    https_response = http_response


_no_redirect_opener = urllib.request.build_opener(_NoRedirect)


def _headers_dict(message) -> dict:
    """`dict(message)` silently keeps only the LAST occurrence of a repeated
    header -- `email.message.Message`'s own iteration yields every `(name,
    value)` pair, but a plain `dict()` over that just overwrites. A response
    with two `Set-Cookie` headers (now routine, since sign-in sets both the
    session and the post-auth CSRF cookie) needs `get_all`.
    """
    out = {}
    for key in message.keys():
        values = message.get_all(key)
        out[key] = values if len(values) > 1 else values[0]
    return out


def _get(base, path, headers=None):
    req = urllib.request.Request(base + path, headers=headers or {})
    resp = _no_redirect_opener.open(req, timeout=10)
    return resp.status, resp.read(), _headers_dict(resp.headers), resp


def _post(base, path, body, headers=None):
    req = urllib.request.Request(base + path, data=body, method="POST",
                                 headers=headers or {})
    resp = _no_redirect_opener.open(req, timeout=10)
    return resp.status, resp.read(), _headers_dict(resp.headers), resp


def _cookie_value(set_cookie_headers, name):
    """`http.client`'s response headers fold repeated `Set-Cookie` lines into commas
    sometimes and not others depending on platform; parse whichever we got.
    """
    if isinstance(set_cookie_headers, list):
        raw = "; ".join(set_cookie_headers)
    else:
        raw = set_cookie_headers or ""
    m = re.search(rf"{name}=([^;,]+)", raw)
    return m.group(1) if m else None


@pytest.fixture
def signin_enabled(server, tmp_path):
    """Flips the shared `server` fixture's Handler over to a sign-in-enabled
    configuration, with one real account, and restores the disabled state after.
    """
    base, store_root = server
    old_config = Handler.config
    old_accounts = Handler.account_store
    old_sessions = Handler.session_store
    old_rl_account = Handler.rate_limit_per_account
    old_rl_client = Handler.rate_limit_per_client
    old_rl_concurrent = Handler.rate_limit_concurrent_hashes
    old_tokens = Handler.token_store

    Handler.config = Config(sign_in={"enabled": True})
    Handler.account_store = AccountStore(store_root / ACCOUNTS_DIRNAME)
    Handler.account_store.create("alice", b"correct horse battery staple")
    Handler.session_store = SessionStore(idle_timeout_seconds=1800,
                                         absolute_timeout_seconds=43200)
    Handler.rate_limit_per_account = RateLimiter(max_attempts=100, window_seconds=60)
    Handler.rate_limit_per_client = RateLimiter(max_attempts=100, window_seconds=60)
    Handler.rate_limit_concurrent_hashes = ConcurrencyLimiter(max_concurrent=100)
    Handler.token_store = None
    try:
        yield base
    finally:
        Handler.config = old_config
        Handler.account_store = old_accounts
        Handler.session_store = old_sessions
        Handler.rate_limit_per_account = old_rl_account
        Handler.rate_limit_per_client = old_rl_client
        Handler.rate_limit_concurrent_hashes = old_rl_concurrent
        Handler.token_store = old_tokens


def _get_signin_form(base):
    status, body, headers, _ = _get(base, "/signin")
    assert status == 200
    csrf = _cookie_value(headers.get("Set-Cookie"), "onetrace_csrf")
    m = re.search(rb'name="csrf_token" value="([^"]+)"', body)
    form_token = m.group(1).decode()
    return csrf, form_token


def test_the_happy_path_signs_in_and_the_access_log_names_the_real_principal(
        signin_enabled, examined):
    base = signin_enabled
    csrf, form_token = _get_signin_form(base)
    assert csrf == form_token

    examined(1, "a correct sign-in submission")
    status, body, headers, _ = _post(
        base, "/signin",
        f"username=alice&password=correct+horse+battery+staple&csrf_token={form_token}".encode(),
        headers={"Cookie": f"onetrace_csrf={csrf}",
                "Content-Type": "application/x-www-form-urlencoded"})
    assert status == 303
    session_cookie = _cookie_value(headers.get("Set-Cookie"), "onetrace_session")
    assert session_cookie

    #: A page fetched with that session cookie is recorded under the real username.
    _get(base, "/health", headers={"Cookie": f"onetrace_session={session_cookie}"})
    entries = Handler.access_log.read_all_entries()
    assert entries[-1]["principal"] == "alice"


def test_a_wrong_password_is_refused(signin_enabled, examined):
    base = signin_enabled
    csrf, form_token = _get_signin_form(base)
    examined(1, "an incorrect password submission")
    status, body, headers, _ = _post(
        base, "/signin",
        f"username=alice&password=wrong&csrf_token={form_token}".encode(),
        headers={"Cookie": f"onetrace_csrf={csrf}",
                "Content-Type": "application/x-www-form-urlencoded"})
    assert status == 401
    assert b"wrong username or password" in body


def test_a_sign_in_post_without_the_csrf_token_is_refused(signin_enabled, examined):
    """A sign-in POST without the CSRF token is refused."""
    base = signin_enabled
    csrf, _form_token = _get_signin_form(base)
    examined(1, "a sign-in submission missing the CSRF field")
    status, body, headers, _ = _post(
        base, "/signin", b"username=alice&password=correct+horse+battery+staple",
        headers={"Cookie": f"onetrace_csrf={csrf}",
                "Content-Type": "application/x-www-form-urlencoded"})
    assert status == 403


def test_a_mismatched_csrf_token_is_refused(signin_enabled, examined):
    base = signin_enabled
    csrf, _form_token = _get_signin_form(base)
    examined(1, "a sign-in submission whose form token disagrees with its cookie")
    status, body, headers, _ = _post(
        base, "/signin",
        b"username=alice&password=correct+horse+battery+staple&csrf_token=not-the-real-one",
        headers={"Cookie": f"onetrace_csrf={csrf}",
                "Content-Type": "application/x-www-form-urlencoded"})
    assert status == 403


def test_sign_out_invalidates_the_session_on_the_server(signin_enabled, examined):
    base = signin_enabled
    csrf, form_token = _get_signin_form(base)
    _status, _body, headers, _ = _post(
        base, "/signin",
        f"username=alice&password=correct+horse+battery+staple&csrf_token={form_token}".encode(),
        headers={"Cookie": f"onetrace_csrf={csrf}",
                "Content-Type": "application/x-www-form-urlencoded"})
    session_cookie = _cookie_value(headers.get("Set-Cookie"), "onetrace_session")
    #: sign-out is itself CSRF-checked now -- the post-auth CSRF
    #: cookie sign-in just set (the session's own token) must be echoed back.
    action_csrf = _cookie_value(headers.get("Set-Cookie"), "onetrace_csrf")

    status, _body, _h, _ = _post(
        base, "/signout", b"",
        headers={"Cookie": f"onetrace_session={session_cookie}; onetrace_csrf={action_csrf}",
                "X-CSRF-Token": action_csrf})
    assert status == 303

    #: The SAME cookie, presented again after sign-out, must no longer resolve to
    #: alice -- the session is gone server-side, not merely told to the client to
    #: forget it. Checked via the access log's own recorded principal, since no
    #: route is role-gated yet (that is step 3) to give a literal 401/redirect here.
    examined(1, "a request bearing the now-signed-out session cookie")
    _get(base, "/health", headers={"Cookie": f"onetrace_session={session_cookie}"})
    entries = Handler.access_log.read_all_entries()
    assert entries[-1]["principal"] == "anonymous"


def test_sign_out_itself_is_logged_under_the_signing_out_principal(signin_enabled, examined):
    """The principal is resolved BEFORE the handler runs, so the
    `/signout` request's own access-log entry names who signed out, not
    `anonymous` -- which is what the session looks like the instant AFTER
    `_handle_signout` invalidates it. Previously `_principal()` was called
    inside `_respond`, after the handler had already run.
    """
    base = signin_enabled
    csrf, form_token = _get_signin_form(base)
    _status, _body, headers, _ = _post(
        base, "/signin",
        f"username=alice&password=correct+horse+battery+staple&csrf_token={form_token}".encode(),
        headers={"Cookie": f"onetrace_csrf={csrf}",
                "Content-Type": "application/x-www-form-urlencoded"})
    session_cookie = _cookie_value(headers.get("Set-Cookie"), "onetrace_session")
    action_csrf = _cookie_value(headers.get("Set-Cookie"), "onetrace_csrf")

    examined(1, "the access log's own entry for the /signout request itself")
    status, _body, _h, _ = _post(
        base, "/signout", b"",
        headers={"Cookie": f"onetrace_session={session_cookie}; onetrace_csrf={action_csrf}",
                "X-CSRF-Token": action_csrf})
    assert status == 303
    entries = Handler.access_log.read_all_entries()
    signout_entries = [e for e in entries if e["path"] == "/signout"]
    assert signout_entries[-1]["principal"] == "alice"


def test_sign_out_without_a_valid_csrf_token_is_refused(signin_enabled, examined):
    """The sign-out form is CSRF-checked too now."""
    base = signin_enabled
    csrf, form_token = _get_signin_form(base)
    _status, _body, headers, _ = _post(
        base, "/signin",
        f"username=alice&password=correct+horse+battery+staple&csrf_token={form_token}".encode(),
        headers={"Cookie": f"onetrace_csrf={csrf}",
                "Content-Type": "application/x-www-form-urlencoded"})
    session_cookie = _cookie_value(headers.get("Set-Cookie"), "onetrace_session")
    action_csrf = _cookie_value(headers.get("Set-Cookie"), "onetrace_csrf")

    examined(1, "a sign-out POST with no CSRF token at all")
    status, _body, _h, _ = _post(
        base, "/signout", b"",
        headers={"Cookie": f"onetrace_session={session_cookie}; onetrace_csrf={action_csrf}"})
    assert status == 403

    #: The session must still be alive -- a refused sign-out must not have
    #: invalidated it as a side effect.
    _get(base, "/health", headers={"Cookie": f"onetrace_session={session_cookie}"})
    entries = Handler.access_log.read_all_entries()
    assert entries[-1]["principal"] == "alice"


def test_rate_limiting_per_account_blocks_further_attempts(server, tmp_path, examined):
    base, store_root = server
    old_config, old_accounts, old_sessions = Handler.config, Handler.account_store, Handler.session_store
    old_rl_account, old_rl_client = Handler.rate_limit_per_account, Handler.rate_limit_per_client
    old_rl_concurrent = Handler.rate_limit_concurrent_hashes
    Handler.config = Config(sign_in={"enabled": True})
    Handler.account_store = AccountStore(store_root / ACCOUNTS_DIRNAME)
    Handler.account_store.create("bob", b"a-real-password")
    Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    Handler.rate_limit_per_account = RateLimiter(max_attempts=2, window_seconds=60)
    Handler.rate_limit_per_client = RateLimiter(max_attempts=100, window_seconds=60)
    Handler.rate_limit_concurrent_hashes = ConcurrencyLimiter(max_concurrent=100)
    try:
        examined(3, "sign-in attempts against a per-account limit of 2")
        statuses = []
        for _ in range(3):
            csrf, form_token = _get_signin_form(base)
            status, _body, _headers, _ = _post(
                base, "/signin",
                f"username=bob&password=wrong&csrf_token={form_token}".encode(),
                headers={"Cookie": f"onetrace_csrf={csrf}",
                        "Content-Type": "application/x-www-form-urlencoded"})
            statuses.append(status)
        assert statuses == [401, 401, 429]
    finally:
        Handler.config, Handler.account_store, Handler.session_store = old_config, old_accounts, old_sessions
        Handler.rate_limit_per_account, Handler.rate_limit_per_client = old_rl_account, old_rl_client
        Handler.rate_limit_concurrent_hashes = old_rl_concurrent


def test_the_access_log_never_contains_a_password_hash_session_id_or_csrf_token(
        signin_enabled, examined):
    """Extends step 1's own access-log test: search the whole log,
    across a real sign-in, for all four secrets.
    """
    base = signin_enabled
    csrf, form_token = _get_signin_form(base)
    password = "correct horse battery staple"
    status, body, headers, _ = _post(
        base, "/signin",
        f"username=alice&password={password.replace(' ', '+')}&csrf_token={form_token}".encode(),
        headers={"Cookie": f"onetrace_csrf={csrf}",
                "Content-Type": "application/x-www-form-urlencoded"})
    session_cookie = _cookie_value(headers.get("Set-Cookie"), "onetrace_session")
    account = Handler.account_store.get("alice")

    log_text = "\n".join(str(e) for e in Handler.access_log.read_all_entries())
    examined(4, "secrets searched for in the access log")
    assert password not in log_text
    assert account.hash_hex not in log_text
    assert session_cookie not in log_text
    assert form_token not in log_text
