"""Role enforcement (item 7), ingester bearer tokens (item 8), and
CSRF on `POST /compare` (item 9), all over real HTTP.

The pure mapping -- every route in `docs/design/signin-and-roles.md` §3's own
table -- is checked exhaustively, one sub-case per row, in `tests/test_roles.py`
against `roles.required_role` directly. This file is the live-HTTP half: a
representative case per credential kind (none, viewer session, ingester token),
proving the mapping is actually WIRED to `serve.py`, not just correct in the
abstract.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from onetrace_console.accounts import AccountStore
from onetrace_console.config import Config
from onetrace_console.rate_limit import ConcurrencyLimiter, RateLimiter
from onetrace_console.serve import ACCOUNTS_DIRNAME, TOKENS_DIRNAME, Handler
from onetrace_console.sessions import SessionStore
from onetrace_console.ingester_tokens import TokenStore
from tests.test_signin_flow import _cookie_value, _get, _get_signin_form, _post

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def roles_enabled(server, tmp_path):
    """Sign-in AND role enforcement on, one real viewer account, one real
    ingester token. Restores every swapped Handler attribute afterward, the
    same discipline `test_signin_flow.py`'s own fixture uses.
    """
    base, store_root = server
    saved = {
        name: getattr(Handler, name)
        for name in ("config", "account_store", "session_store", "token_store",
                     "rate_limit_per_account", "rate_limit_per_client",
                     "rate_limit_concurrent_hashes")
    }

    Handler.config = Config(sign_in={"enabled": True})
    Handler.account_store = AccountStore(store_root / ACCOUNTS_DIRNAME)
    Handler.account_store.create("alice", b"correct horse battery staple")
    Handler.token_store = TokenStore(store_root / TOKENS_DIRNAME)
    _record, raw_token = Handler.token_store.create("ci-pipeline")
    Handler.session_store = SessionStore(idle_timeout_seconds=1800,
                                         absolute_timeout_seconds=43200)
    Handler.rate_limit_per_account = RateLimiter(max_attempts=100, window_seconds=60)
    Handler.rate_limit_per_client = RateLimiter(max_attempts=100, window_seconds=60)
    Handler.rate_limit_concurrent_hashes = ConcurrencyLimiter(max_concurrent=100)
    try:
        yield base, raw_token
    finally:
        for name, value in saved.items():
            setattr(Handler, name, value)


def _sign_in(base) -> tuple[str, str]:
    """Returns `(session_cookie, action_csrf)` for a real, signed-in `alice`."""
    csrf, form_token = _get_signin_form(base)
    _status, _body, headers, _ = _post(
        base, "/signin",
        f"username=alice&password=correct+horse+battery+staple&csrf_token={form_token}".encode(),
        headers={"Cookie": f"onetrace_csrf={csrf}",
                "Content-Type": "application/x-www-form-urlencoded"})
    session_cookie = _cookie_value(headers.get("Set-Cookie"), "onetrace_session")
    action_csrf = _cookie_value(headers.get("Set-Cookie"), "onetrace_csrf")
    return session_cookie, action_csrf


# ------------------------------------------------------------ item 7: role enforcement

def test_an_unauthenticated_get_redirects_to_signin(roles_enabled, examined):
    base, _token = roles_enabled
    examined(1, "GET / with no credential at all")
    status, _body, headers, _ = _get(base, "/")
    assert status == 303
    assert headers.get("Location") == "/signin"


def test_an_unauthenticated_post_to_v1_runs_gets_401(roles_enabled, examined):
    base, _token = roles_enabled
    examined(1, "POST /v1/runs with no credential at all")
    status, _body, _headers, _ = _post(base, "/v1/runs", b"not-a-real-tar")
    assert status == 401


def test_a_signed_in_session_can_reach_a_viewer_page(roles_enabled, examined):
    base, _token = roles_enabled
    session_cookie, _csrf = _sign_in(base)
    examined(1, "GET /home.html with a real viewer session")
    status, _body, _headers, _ = _get(
        base, "/home.html", headers={"Cookie": f"onetrace_session={session_cookie}"})
    assert status == 200


def test_a_session_on_an_ingester_route_gets_403(roles_enabled, examined):
    """A session on `POST /v1/runs` gets 403."""
    base, _token = roles_enabled
    session_cookie, _csrf = _sign_in(base)
    examined(1, "POST /v1/runs with a real viewer session, no token")
    status, _body, _headers, _ = _post(
        base, "/v1/runs", b"not-a-real-tar",
        headers={"Cookie": f"onetrace_session={session_cookie}"})
    assert status == 403


def test_a_token_on_a_viewer_page_gets_403(roles_enabled, examined):
    """A token on `GET /home.html` gets 403."""
    base, raw_token = roles_enabled
    examined(1, "GET /home.html with a valid ingester token")
    status, _body, _headers, _ = _get(
        base, "/home.html", headers={"Authorization": f"Bearer {raw_token}"})
    assert status == 403


def test_a_revoked_token_gets_401(roles_enabled, examined):
    """A revoked token gets 401."""
    base, raw_token = roles_enabled
    Handler.token_store.revoke(next(iter(
        p.stem for p in (Handler.token_store.root).glob("*.json"))))
    examined(1, "POST /v1/runs with a now-revoked token")
    status, _body, _headers, _ = _post(
        base, "/v1/runs", b"not-a-real-tar", headers={"Authorization": f"Bearer {raw_token}"})
    assert status == 401


def test_an_ingest_with_a_valid_token_succeeds(roles_enabled, delivery, examined):
    base, raw_token = roles_enabled
    examined(1, "POST /v1/runs with a valid ingester token and a real delivery")
    status, _body, _headers, _ = _post(
        base, "/v1/runs", delivery, headers={"Authorization": f"Bearer {raw_token}"})
    assert status == 200


def test_a_runs_authorization_page_is_a_viewer_page_over_http(roles_enabled, delivery,
                                                              examined):
    """The run's authorization page shape, wired: no credential is sent to sign in, a viewer
    session reads it, and an ingester token -- which delivered the run -- may not."""
    import json

    base, raw_token = roles_enabled
    status, body, _headers, _ = _post(
        base, "/v1/runs", delivery, headers={"Authorization": f"Bearer {raw_token}"})
    assert status == 200, body
    page = json.loads(body)["pages"]["authorization"]
    session_cookie, _csrf = _sign_in(base)
    examined(3, f"GET {page} with no credential, a viewer session and an ingester token")

    status, _body, headers, _ = _get(base, page)
    assert (status, headers.get("Location")) == (303, "/signin")
    status, body, _headers, _ = _get(
        base, page, headers={"Cookie": f"onetrace_session={session_cookie}"})
    assert status == 200 and b"No authorization records for this run" in body
    status, _body, _headers, _ = _get(base, page, headers={"Authorization": f"Bearer {raw_token}"})
    assert status == 403


def test_no_log_line_contains_the_token(roles_enabled, delivery, examined):
    base, raw_token = roles_enabled
    _post(base, "/v1/runs", delivery, headers={"Authorization": f"Bearer {raw_token}"})
    log_text = "\n".join(str(e) for e in Handler.access_log.read_all_entries())
    examined(1, "the access log, searched for the raw token")
    assert raw_token not in log_text


def test_the_ingest_access_log_entry_names_the_tokens_own_principal(roles_enabled, delivery,
                                                                     examined):
    base, raw_token = roles_enabled
    _post(base, "/v1/runs", delivery, headers={"Authorization": f"Bearer {raw_token}"})
    entries = Handler.access_log.read_all_entries()
    ingest_entries = [e for e in entries if e["path"] == "/v1/runs"]
    examined(1, "the access log's own entry for the token-authenticated ingest")
    assert ingest_entries[-1]["principal"] == "ci-pipeline"


# ---------------------------------------------------------------- item 9: CSRF on /compare

def _two_run_keys(base: str, raw_token: str) -> tuple[str, str]:
    """Two DISTINCT, real SDK bench runs (the same `ingest-r1/run_C` /
    `run_C_poppler24` pair `tests/test_serve.py::test_compare_after_two_ingests…`
    uses) -- comparing a run against itself hits an unrelated pre-existing edge
    case in the diff verb's own report reader, nothing to do with CSRF/roles.
    """
    import json

    from tests.test_serve import _real_delivery

    exam = REPO / ".sdk-fixtures" / "exam" / "fixtures" / "ingest-r1"
    run_c, run_c_poppler24 = exam / "run_C", exam / "run_C_poppler24"
    if not (run_c.is_dir() and run_c_poppler24.is_dir()):
        pytest.fail(f"the SDK's exam fixtures are not there under {exam}\n"
                   f"    python tools/fetch_sdk_fixtures.py")
    headers = {"Authorization": f"Bearer {raw_token}"}
    _s1, b1, _h1, _ = _post(base, "/v1/runs", _real_delivery(run_c), headers=headers)
    _s2, b2, _h2, _ = _post(base, "/v1/runs", _real_delivery(run_c_poppler24), headers=headers)
    return json.loads(b1)["run_key"], json.loads(b2)["run_key"]


#: Its uploads are the exam's preview-format ingest-r1 runs, stored
#: directly (a new preview delivery is refused since 0.2.0): what the console does with runs it holds.
@pytest.mark.usefixtures("preview_stored_directly")
def test_compare_without_a_csrf_token_is_refused(roles_enabled, examined):
    base, raw_token = roles_enabled
    key_a, key_b = _two_run_keys(base, raw_token)

    session_cookie, _csrf = _sign_in(base)
    examined(1, "POST /compare with a real viewer session but no CSRF token")
    status, _body, _headers, _ = _post(
        base, f"/compare?a={key_a}&b={key_b}", b"",
        headers={"Cookie": f"onetrace_session={session_cookie}"})
    assert status == 403


#: Its uploads are the exam's preview-format ingest-r1 runs, stored
#: directly (a new preview delivery is refused since 0.2.0): what the console does with runs it holds.
@pytest.mark.usefixtures("preview_stored_directly")
def test_compare_with_a_valid_csrf_token_succeeds(roles_enabled, examined):
    base, raw_token = roles_enabled
    key_a, key_b = _two_run_keys(base, raw_token)

    session_cookie, action_csrf = _sign_in(base)
    examined(1, "POST /compare with a real viewer session and its own CSRF token")
    status, _body, _headers, _ = _post(
        base, f"/compare?a={key_a}&b={key_b}&csrf_token={action_csrf}", b"",
        headers={"Cookie": f"onetrace_session={session_cookie}; onetrace_csrf={action_csrf}"})
    assert status == 200


#: Its uploads are the exam's preview-format ingest-r1 runs, stored
#: directly (a new preview delivery is refused since 0.2.0): what the console does with runs it holds.
@pytest.mark.usefixtures("preview_stored_directly")
def test_an_ingester_token_on_compare_gets_403(roles_enabled, examined):
    """`/compare` is `viewer` (design note §3's own judgement call) -- an
    ingester credential must not satisfy it, CSRF question aside.
    """
    base, raw_token = roles_enabled
    key_a, key_b = _two_run_keys(base, raw_token)
    examined(1, "POST /compare with a valid ingester token")
    status, _body, _headers, _ = _post(
        base, f"/compare?a={key_a}&b={key_b}", b"",
        headers={"Authorization": f"Bearer {raw_token}"})
    assert status == 403


# ---------------------------------------------------------------- item 7's own sabotage

def test_sabotage_a_new_route_with_no_role_table_entry_is_caught(tmp_path, examined):
    """Item 7's own named sabotage: add a route to `serve.py` with no matching
    entry in `roles.py`'s table, calling `_respond` directly WITHOUT going
    through `_enforce_role` first -- the exact mistake a future change could
    make. A real test (written into the copy, run for real as a subprocess)
    expects the new route to be refused for an unauthenticated request, the
    same as every other route; against the sabotaged copy it must FAIL,
    because the sabotaged route answers 200 instead.
    """
    copy_root = tmp_path / "console-copy"
    shutil.copytree(REPO / "src", copy_root / "src")
    shutil.copytree(REPO / "tests", copy_root / "tests")
    shutil.copy(REPO / "pyproject.toml", copy_root / "pyproject.toml")

    serve_py = copy_root / "src" / "onetrace_console" / "serve.py"
    text = serve_py.read_text(encoding="utf-8")
    needle = '            else:\n                self._respond(404, b"no such route\\n", "text/plain")'
    assert needle in text, "the else-branch this sabotage inserts beside has moved or been reworded"
    sabotaged = text.replace(
        needle,
        '            elif split.path == "/unwired-new-route":\n'
        '                #: sabotage: answers directly, skipping _enforce_role entirely --\n'
        '                #: exactly the shape item 7 exists to catch.\n'
        '                self._respond(200, b"should never be reachable\\n", "text/plain")\n'
        + needle,
        1)
    assert sabotaged != text, "the sabotage's own replacement did not apply"
    serve_py.write_text(sabotaged, encoding="utf-8")

    probe_test = copy_root / "tests" / "test_unwired_route_probe.py"
    probe_test.write_text(
        'from onetrace_console.config import Config\n'
        'from onetrace_console.serve import Handler\n'
        '\n'
        '\n'
        'def test_the_new_route_is_refused_like_every_other_one(server):\n'
        '    base, _store_root = server\n'
        '    old_config = Handler.config\n'
        '    Handler.config = Config(sign_in={"enabled": True})\n'
        '    try:\n'
        '        import urllib.error\n'
        '        import urllib.request\n'
        '        req = urllib.request.Request(base + "/unwired-new-route", data=b"", method="POST")\n'
        '        try:\n'
        '            resp = urllib.request.urlopen(req, timeout=5)\n'
        '            status = resp.status\n'
        '        except urllib.error.HTTPError as e:\n'
        '            status = e.code\n'
        '        assert status in (401, 403, 404), (\n'
        '            f"an unauthenticated request to an unwired route answered {status}, "\n'
        '            f"not a refusal -- it bypassed role enforcement entirely")\n'
        '    finally:\n'
        '        Handler.config = old_config\n',
        encoding="utf-8")

    examined(1, "the probe test, run for real against the sabotaged copy")
    import os
    env = dict(os.environ, PYTHONPATH=str(copy_root / "src"))
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_unwired_route_probe.py", "-q"],
        cwd=str(copy_root), env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0, (
        "the unwired-route probe PASSED against a tree with an unrouted, unenforced "
        "path added -- the sabotage did not fire:\n"
        + result.stdout[-2000:] + result.stderr[-2000:])
