"""Sign-in through Entra ID: every route declares the role it needs, denied by default (`roles`).

viewer reads runs and comparisons; investigator also starts a comparison, Explain, an expectations
check, the tokenizer upload and the bisect form; admin also the settings (Set up Explain, the
neighbours setup) and the admin routes. With `local`, every route needs what it needed before.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

from onetrace_console import roles
from tests.fake_entra import CLIENT, TENANT

SERVE = Path(roles.__file__).with_name("serve.py")
V, I, A, ING = roles.VIEWER, roles.INVESTIGATOR, roles.ADMIN, roles.INGESTER

#: Every POST route: (role with local sign-in, as before; role with sign-in through Entra ID).
POST = {
    "/v1/runs": (ING, ING),
    "/v1/decisions": (ING, ING),
    "/compare": (V, I),
    "/text-diff/more": (V, I),
    "/explain": (V, I),
    "/explain/packet": (V, I),
    "/explain/check": (V, I),
    "/explain/cancel": (V, I),
    "/explain/text": (V, I),
    "/benchmark": (V, I),
    "/expectations": (V, I),
    "/runs/load-not-closed": (V, I),
    "/model-tokenizers": (A, I),
    "/model-tokenizers/remove": (A, A),
    "/neighbours/on": (A, A),
    "/neighbours/off": (A, A),
    "/explain/setup": (A, A),
}
#: The pages that need more than viewer with Entra ID: rendered path -> role.
GET_ABOVE_VIEWER = {"explain/setup": A, "neighbours/setup": A, "bisect": I}
#: A sample of the rendered page shapes, each viewer either way.
PAGES = [
    "home.html",
    "counts.html",
    "executions-all.html",
    "incidents.html",
    "monitor.html",
    "runs/" + "ab" * 32 + "/answer.html",
    "runs/" + "ab" * 32 + "/receipt.html",
    "runs/" + "ab" * 32 + "/record.tar",
    "diff/x.html",
    "comparisons.html",
    "pipeline-p1.html",
    "drift-p1.html",
    "bisect-p1.html",
    "choose-p1.html",
    "explain/state",
    "search",
    "model-tokenizers",
    "policy.html",
]


@pytest.mark.parametrize("path", sorted(POST))
def test_each_post_route_s_role_with_local_sign_in_and_with_entra_id(path, examined):
    examined(2, f"POST {path}: local and oidc")
    local, entra = POST[path]
    assert roles.required_role("POST", path) == local
    assert roles.required_role("POST", path, oidc=True) == entra


@pytest.mark.parametrize("rel", PAGES + sorted(GET_ABOVE_VIEWER))
def test_each_page_s_role_with_local_sign_in_and_with_entra_id(rel, examined):
    examined(2, f"GET {rel}: local and oidc")
    assert roles.required_role("GET", "/" + rel, rel_for_get=rel) == V
    assert roles.required_role("GET", "/" + rel, rel_for_get=rel, oidc=True) == GET_ABOVE_VIEWER.get(rel, V)


def test_with_entra_id_the_flow_s_routes_need_no_one_and_local_sign_in_is_gone(examined):
    examined(6, "the start, the callback, health, sign-out; POST /signin; the flow's routes on a local console")
    for path in ("/signin", "/signin/oidc/start", "/signin/oidc/callback", "/health"):
        assert roles.required_role("GET", path, oidc=True) is None
    assert roles.required_role("POST", "/signout", oidc=True) is None
    with pytest.raises(roles.NoRouteTableEntry):
        roles.required_role("POST", "/signin", oidc=True)
    for path in ("/signin/oidc/start", "/signin/oidc/callback"):
        with pytest.raises(roles.NoRouteTableEntry):
            roles.required_role("GET", path)


def test_a_route_or_page_with_no_row_is_refused_with_entra_id_too(examined):
    examined(2, "an unknown POST and an unknown page shape")
    with pytest.raises(roles.NoRouteTableEntry):
        roles.required_role("POST", "/v1/new-thing", oidc=True)
    with pytest.raises(roles.NoRouteTableEntry):
        roles.required_role("GET", "/admin.html", rel_for_get="admin.html", oidc=True)


# ------------------------------------------------------------------ the inventory, from the code


_ROUTE_NAMES = {"path", "rel"}


def _subject(node) -> bool:
    """`path`, `rel`, `split.path` or `urlsplit(self.path).path`: what a route is matched against."""
    if isinstance(node, ast.Name):
        return node.id in _ROUTE_NAMES
    if isinstance(node, ast.Attribute) and node.attr == "path":
        return isinstance(node.value, (ast.Name, ast.Call))
    return False


def route_literals(source: str) -> set[str]:
    """Every string a request's path is compared with in `serve.py`: `==`, `in (...)`, and `.startswith`."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare) and _subject(node.left):
            for comp in node.comparators:
                items = comp.elts if isinstance(comp, (ast.Tuple, ast.List, ast.Set)) else [comp]
                found |= {c.value for c in items if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "startswith"
            and _subject(node.func.value)
        ):
            found |= {a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    return found


def undeclared(source: str) -> list[str]:
    """The route literals with no role in either method, nor a place among the routes served
    before the role check (`roles.SERVED_BEFORE_ROLES`)."""
    out = []
    for lit in sorted(route_literals(source)):
        if lit in roles.SERVED_BEFORE_ROLES:
            continue
        url = lit if lit.startswith("/") else "/" + lit
        rel = None if lit.startswith("/") else lit
        declared = False
        for method in ("GET", "POST"):
            for oidc in (False, True):
                try:
                    roles.required_role(method, url, rel_for_get=rel, oidc=oidc)
                    declared = True
                except roles.NoRouteTableEntry:
                    pass
        if not declared:
            out.append(lit)
    return out


def test_every_route_the_console_serves_declares_a_role(examined):
    source = SERVE.read_text(encoding="utf-8")
    found = route_literals(source)
    examined(len(found), "route literals in serve.py")
    assert len(found) >= 25, sorted(found)
    assert undeclared(source) == []


def test_sabotage_a_route_with_no_role_is_named(examined):
    examined(1, "a planted POST route with no row")
    source = (
        SERVE.read_text(encoding="utf-8")
        + '\n\ndef planted(split):\n    if split.path == "/v1/planted":\n        pass\n'
    )
    assert undeclared(source) == ["/v1/planted"]


def test_every_post_row_is_a_route_the_console_serves(examined):
    """No row for a route that no longer exists: the table and the code say the same."""
    found = route_literals(SERVE.read_text(encoding="utf-8"))
    examined(len(POST), "POST rows")
    assert sorted(set(POST) - found) == []
    assert sorted(roles.post_routes()) == sorted(POST)


# ------------------------------------------------------------------ over HTTP, a session of each role


@pytest.fixture
def entra_console(server):
    from onetrace_console.config import Config
    from onetrace_console.serve import Handler
    from onetrace_console.sessions import SessionStore

    base, _root = server
    saved = {n: getattr(Handler, n, None) for n in ("config", "session_store")}
    Handler.config = Config(
        sign_in={
            "enabled": True,
            "method": "oidc",
            "public_url": base,
            "insecure_cookie_for_local_dev": True,
            "oidc": {"tenant_id": TENANT, "client_id": CLIENT, "client_secret_env": "X", "session_max_hours": 8},
        }
    )
    Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    try:
        yield base
    finally:
        for n, v in saved.items():
            setattr(Handler, n, v)


REFUSED = b"this credential does not grant the required role"
#: Routes this test server does not serve at all (a folder watcher, the neighbours extra): their
#: rows are held by the table tests above.
NOT_HERE = {"/runs/load-not-closed", "/neighbours/on", "/neighbours/off"}


def _session(role: str):
    from onetrace_console.serve import Handler

    oid = {"viewer": "1", "investigator": "2", "admin": "3"}[role] * 8 + "-0000-0000-0000-000000000000"
    s = Handler.session_store.create(f"{TENANT}/{oid}", role=role, display_name=role, expires_at=time.time() + 600)
    return {"Cookie": f"onetrace_session={s.session_id}; onetrace_csrf={s.csrf_token}", "X-CSRF-Token": s.csrf_token}


@pytest.mark.parametrize("role", ["viewer", "investigator", "admin"])
def test_the_route_matrix_for_each_role(entra_console, role, examined):
    """Each POST route and each page above viewer, with a session of the role: refused for the role
    (403, in those words) exactly where the role does not include the route's."""
    from tests.test_signin_flow import _get, _post

    base = entra_console
    headers = {**_session(role), "Origin": base, "Content-Type": "application/x-www-form-urlencoded"}
    checked = 0
    for path, (_local, needed) in POST.items():
        if path in NOT_HERE or needed == ING:
            continue
        status, body, _h, _ = _post(base, path, b"", headers=headers)
        refused = status == 403 and REFUSED in body
        assert refused is not roles.role_includes(role, needed), (role, path, status, body[:120])
        checked += 1
    for rel, needed in GET_ABOVE_VIEWER.items():
        status, body, _h, _ = _get(base, "/" + rel, headers=headers)
        refused = status == 403 and REFUSED in body
        assert refused is not roles.role_includes(role, needed), (role, rel, status, body[:120])
        checked += 1
    status, _b, _h, _ = _get(base, "/", headers=headers)
    assert status == 200
    examined(checked + 1, f"routes for {role}")


def test_an_ingester_route_refuses_every_entra_session(entra_console, examined):
    from tests.test_signin_flow import _post

    examined(3, "POST /v1/runs with a viewer's, an investigator's and an admin's session")
    for role in ("viewer", "investigator", "admin"):
        headers = {**_session(role), "Origin": entra_console}
        status, body, _h, _ = _post(entra_console, "/v1/runs", b"", headers=headers)
        assert status == 403 and REFUSED in body, (role, status, body[:120])
