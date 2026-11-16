"""What a console answers before it asks who is asking.

`serve.py` answers a few paths before the role check (`roles.SERVED_BEFORE_ROLES`, and the routes that need no
principal). Each must hold nothing a stranger could read about the runs: no run name, no path on the server, no error
text.

- **The watched folder's state** (`GET /v1/folder`: the folder's path, the names of changed runs, how many runs it took
  in, its last error lines) is answered before roles in local mode only: no configuration file, loopback, behind the
  local guard. A folder console started with a configuration file has sign-in on, and there it is a viewer's route,
  in the role table, with local sign-in and with Entra ID: without a session it is refused as any viewer page is.
- **Every path answered before roles** is read without a session, on a folder console with sign-in on and a watcher
  holding planted values, and none of them is in its answer. A path added to the list later is held the same way.
- **The poll** that reads it stops quietly when the answer is not the state: a redirect to sign-in, or a refusal.
"""

from __future__ import annotations

import http.client
from urllib.parse import urlsplit

import pytest

from onetrace_console import roles
from onetrace_console.serve import STATIC_FILES, Handler
from tests.test_roles_enforcement import _sign_in, roles_enabled  # noqa: F401 - a fixture, used by name

#: Planted in the watcher's state: none may reach a request that has no session.
FOLDER = "/srv/planted-watched-folder"
RUN = "planted-run-name"
ERROR = "planted error line: no such file"


class _State:
    def as_json(self) -> dict:
        return {
            "folder": FOLDER,
            "interval": 2.0,
            "last_read": "2026-11-13T20:00:00+00:00",
            "taken": 7,
            "version": 3,
            "changed": {RUN: ["amber", "its files changed after intake"]},
            "errors": [ERROR],
        }


class _Watcher:
    state = _State()


@pytest.fixture
def watched(roles_enabled):  # noqa: F811 - the fixture imported above
    """A folder console with a configuration file: sign-in on, a watcher, no local guard."""
    base, _token = roles_enabled
    saved = (getattr(Handler, "watcher", None), Handler.local_port)
    Handler.watcher = _Watcher()
    Handler.local_port = None
    try:
        yield base
    finally:
        Handler.watcher, Handler.local_port = saved


def _get(base: str, path: str, cookie: str | None = None) -> tuple[int, dict, bytes]:
    u = urlsplit(base)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=30)
    conn.request("GET", path, headers={"Cookie": cookie} if cookie else {})
    r = conn.getresponse()
    body = r.read()
    headers = {k.lower(): v for k, v in r.getheaders()}
    conn.close()
    return r.status, headers, body


def _holds_none(body: bytes) -> list[str]:
    text = body.decode("utf-8", "replace")
    return [v for v in (FOLDER, RUN, ERROR, "planted") if v in text]


def test_a_folder_console_with_sign_in_refuses_the_folder_s_state_without_a_session(watched, examined):
    status, headers, body = _get(watched, "/v1/folder")
    examined(1, "request with no session")
    assert status in (303, 401), status
    assert _holds_none(body) == [], body[:200]
    assert status != 303 or "/signin" in headers.get("location", "")


def test_with_a_viewer_session_it_answers(watched, examined):
    session, _csrf = _sign_in(watched)
    status, _headers, body = _get(watched, "/v1/folder", f"onetrace_session={session}")
    examined(1, "viewer's request")
    assert status == 200, (status, body[:200])
    assert FOLDER in body.decode("utf-8") and RUN in body.decode("utf-8")


def test_the_role_table_holds_it_as_a_viewer_s_with_local_sign_in_and_with_entra_id(examined):
    examined(2, "sign-in methods")
    assert roles.required_role("GET", "/v1/folder", rel_for_get="v1/folder") == roles.VIEWER
    assert roles.required_role("GET", "/v1/folder", rel_for_get="v1/folder", oidc=True) == roles.VIEWER


def test_local_mode_is_unchanged(server, examined):
    """No configuration file: no sign-in, loopback, the local guard; the poll reads the state as before."""
    base, _store_root = server
    saved = (getattr(Handler, "watcher", None), Handler.local_port)
    Handler.watcher = _Watcher()
    Handler.local_port = urlsplit(base).port
    try:
        status, _headers, body = _get(base, "/v1/folder")
    finally:
        Handler.watcher, Handler.local_port = saved
    examined(1, "local request")
    assert status == 200 and FOLDER in body.decode("utf-8")


def _before_roles_paths() -> list[str]:
    """Every path answered before the role check: the list, each static file for `/static/`, and the routes that
    need no principal (GET)."""
    paths = []
    for p in sorted(roles.SERVED_BEFORE_ROLES):
        if p == "/static/":
            paths += sorted(STATIC_FILES) + ["/static/console.css"]
        else:
            paths.append(p or "/")
    paths += sorted(path for method, path in roles._UNAUTHENTICATED_EXACT if method == "GET")
    return sorted(set(paths))


def test_every_path_answered_before_roles_holds_no_run_name_path_or_error(watched, examined):
    paths = _before_roles_paths()
    examined(len(paths), "paths read with no session")
    assert "/v1/folder" in paths and "/health" in paths
    found = {}
    for path in paths:
        _status, _headers, body = _get(watched, path)
        if _holds_none(body):
            found[path] = _holds_none(body)
    assert found == {}, found


def test_the_poll_stops_quietly_when_the_answer_is_not_the_state(examined):
    from onetrace_console.words import WATCH_SCRIPT

    examined(1, "script")
    assert "redirect:'manual'" in WATCH_SCRIPT, "a redirect to sign-in is not followed and read as the state"
    assert "clearInterval" in WATCH_SCRIPT, "a refusal stops the poll"
    assert ".catch(" in WATCH_SCRIPT, "and nothing reaches the page as an error"


# --------------------------------------------- what the handler itself answers with no session

#: Paths no table names, asked as well, so a branch that answers any path before the role check is found.
UNKNOWN = (
    "/no-such-route",
    "/v2/folder",
    "/v1/folder/state",
    "/static/no-such.css",
    "/runs/" + "0" * 64 + "/case.html",
    "/scim/v2/Users",
    "/admin/people",
    "/t/a/home.html",
)
#: An answer with no session that may carry a planted value, each with its reason. None may: the list is empty,
#: and a path added to it must say why.
ALLOWED_TO_CARRY: dict[str, str] = {}


def _every_path() -> tuple[list[str], list[str]]:
    """Every path to ask, from the handler's own source and the tables, not from the list of what is served early:
    each path `serve.py` compares a request with, each page the role table holds, each static file, the paths
    served before roles, and paths no table names."""
    from tests.test_entra_routes import PAGES, SERVE, route_literals

    literals = route_literals(SERVE.read_text(encoding="utf-8"))
    gets = {lit if lit.startswith("/") else "/" + lit for lit in literals}
    gets |= {"/" + rel for rel in PAGES} | set(STATIC_FILES) | {"/static/console.css"}
    gets |= {p or "/" for p in roles.SERVED_BEFORE_ROLES if p != "/static/"} | set(UNKNOWN)
    posts = set(roles.post_routes()) | {"/signin", "/signout"} | set(UNKNOWN)
    return sorted(gets), sorted(posts)


def _post(base: str, path: str) -> tuple[int, bytes]:
    u = urlsplit(base)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=30)
    conn.request("POST", path, body=b"", headers={"Content-Length": "0"})
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, body


def _carriers(base: str) -> dict[str, list[str]]:
    """Each request with no session whose answer carries a planted value, and which planted values."""
    gets, posts = _every_path()
    found = {}
    for path in gets:
        _status, _headers, body = _get(base, path)
        if _holds_none(body) and path not in ALLOWED_TO_CARRY:
            found[f"GET {path}"] = _holds_none(body)
    for path in posts:
        _status, body = _post(base, path)
        if _holds_none(body) and path not in ALLOWED_TO_CARRY:
            found[f"POST {path}"] = _holds_none(body)
    return found


def test_no_answer_to_a_request_with_no_session_carries_a_planted_value(watched, examined):
    """Derived from the handler: every path it compares a request with, every page and route the role table holds,
    and paths no table names, each asked with no session on a folder console with sign-in on and a watcher."""
    gets, posts = _every_path()
    examined(len(gets) + len(posts), "requests with no session")
    assert "/v1/folder" in gets and "/health" in gets and "/v1/runs" in posts
    assert _carriers(watched) == {}


def test_sabotage_0_7_0_s_early_return_is_found(watched, monkeypatch, examined):
    """0.7.0's `_do_get` answered the watched folder's state before any role was asked for, wherever a watcher ran.
    Put back, the test above names it."""
    from onetrace_console import serve

    real = serve.Handler._do_get

    def early(self):
        self._resolve_request_identity()
        if urlsplit(self.path).path == "/v1/folder" and self.watcher is not None:
            self._respond_json(200, self.watcher.state.as_json())
            return
        real(self)

    monkeypatch.setattr(serve.Handler, "_do_get", early)
    examined(1, "early return put back")
    assert "GET /v1/folder" in _carriers(watched)
