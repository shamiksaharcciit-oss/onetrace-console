"""Every row of the role table carries a team rule, in both sets of rules: a team rule for every
route.

A rule is one of three: scoped by run (the route reads or writes a run or a comparison, and answers an outside key as
an unknown one), `admin`, unscoped (a console-wide setting), or draws nothing from runs. A row with no rule is refused,
as a row with no role is, so a route added later cannot go unscoped by being forgotten. The routes that need no
principal draw nothing from runs: `/health`, the sign-in page and sign-out answer the same bytes on an empty store and a
full one.
"""

from __future__ import annotations

import re

import pytest

from onetrace_console import roles

RULES = {roles.SCOPED_BY_RUN, roles.ADMIN_UNSCOPED, roles.DRAWS_NOTHING}


def _get_rows() -> list[str]:
    return [p.pattern for p in roles._VIEWER_GET_PATTERNS]


def _sample(pattern: str) -> str:
    """A rendered path the pattern matches, for asking the table about it."""
    samples = {
        r"^runs/[^/]+/answer\.html$": "runs/" + "a" * 64 + "/answer.html",
        r"^runs/[^/]+/case\.html$": "runs/" + "a" * 64 + "/case.html",
        r"^runs/[0-9a-f]{64}/authorization\.html$": "runs/" + "a" * 64 + "/authorization.html",
        r"^runs/[0-9a-f]{64}/proof\.html$": "runs/" + "a" * 64 + "/proof.html",
        r"^runs/[0-9a-f]{64}/stage-[0-9]+\.html$": "runs/" + "a" * 64 + "/stage-0.html",
        r"^runs/[0-9a-f]{64}/receipt\.html$": "runs/" + "a" * 64 + "/receipt.html",
        r"^runs/[0-9a-f]{64}/record\.tar$": "runs/" + "a" * 64 + "/record.tar",
        r"^executions-[\w-]+\.html$": "executions-all.html",
        r"^incidents-[\w.-]+\.html$": "incidents-x.html",
        r"^diff/[^/]+\.html$": "diff/x.html",
        r"^pipeline-p[0-9]+(-agree|-attention)?\.html$": "pipeline-p1.html",
        r"^drift-p[0-9]+(-previous)?\.html$": "drift-p1.html",
        r"^bisect-p[0-9]+\.html$": "bisect-p1.html",
        r"^choose-p[0-9]+\.html$": "choose-p1.html",
        r"^pipelines/p[0-9]+/noise$": "pipelines/p1/noise",
        r"^choose-p[0-9]+-[0-9a-f]{64}\.html$": "choose-p1-" + "a" * 64 + ".html",
        r"^policy/[^/]+\.html$": "policy/x.html",
        r"^policy-verdict-[\w-]+\.html$": "policy-verdict-x.html",
        r"^policy-issuer-[\w.-]+\.html$": "policy-issuer-x.html",
    }
    if pattern in samples:
        return samples[pattern]
    plain = pattern.strip("^$").replace("\\.", ".")
    assert all(c not in plain for c in "[](){}+*?|\\"), f"no sample for {pattern!r}"
    return plain


@pytest.mark.parametrize("oidc", [False, True], ids=["local sign-in", "Entra ID"])
def test_every_row_carries_a_team_rule_in_both_sets_of_rules(oidc, examined):
    rows = 0
    for pattern in _get_rows():
        rel = _sample(pattern)
        assert roles.team_rule("GET", "/" + rel, rel_for_get=rel, oidc=oidc) in RULES, pattern
        rows += 1
    for path in roles.post_routes():
        assert roles.team_rule("POST", path, oidc=oidc) in RULES, path
        rows += 1
    for method, path in roles._OIDC_UNAUTHENTICATED_EXACT if oidc else roles._UNAUTHENTICATED_EXACT:
        assert roles.team_rule(method, path, oidc=oidc) == roles.DRAWS_NOTHING, (method, path)
        rows += 1
    examined(rows, "role table rows, each with its team rule")


@pytest.mark.parametrize("oidc", [False, True], ids=["local sign-in", "Entra ID"])
@pytest.mark.parametrize("kind", ["GET", "POST", "no principal"])
def test_a_row_with_no_team_rule_is_refused_in_both_sets(monkeypatch, oidc, kind, examined):
    if kind == "GET":
        pattern = r"^comparisons\.html$"
        rules = {k: v for k, v in roles._GET_TEAM_RULES.items() if k != pattern}
        monkeypatch.setattr(roles, "_GET_TEAM_RULES", rules)
        ask = ("GET", "/comparisons.html", {"rel_for_get": "comparisons.html"})
    elif kind == "POST":
        rules = {k: v for k, v in roles._POST_TEAM_RULES.items() if k != "/compare"}
        monkeypatch.setattr(roles, "_POST_TEAM_RULES", rules)
        ask = ("POST", "/compare", {})
    else:
        rules = {k: v for k, v in roles._NO_PRINCIPAL_TEAM_RULES.items() if k != ("GET", "/health")}
        monkeypatch.setattr(roles, "_NO_PRINCIPAL_TEAM_RULES", rules)
        ask = ("GET", "/health", {})
    method, path, extra = ask
    with pytest.raises(roles.NoRouteTableEntry, match="no team rule"):
        roles.required_role(method, path, oidc=oidc, **extra)
    with pytest.raises(roles.NoRouteTableEntry, match="no team rule"):
        roles.team_rule(method, path, oidc=oidc, **extra)
    examined(1, f"a {kind} row without its team rule")


def test_the_rules_the_note_names(examined):
    """The role table's rows its first version left out, each with the rule it gives."""
    named = {
        ("POST", "/v1/runs"): roles.SCOPED_BY_RUN,
        ("POST", "/v1/decisions"): roles.SCOPED_BY_RUN,
        ("POST", "/explain/setup"): roles.ADMIN_UNSCOPED,
        ("POST", "/model-tokenizers"): roles.ADMIN_UNSCOPED,
        ("POST", "/model-tokenizers/remove"): roles.ADMIN_UNSCOPED,
        ("POST", "/signout"): roles.DRAWS_NOTHING,
        ("GET", "/health"): roles.DRAWS_NOTHING,
        ("GET", "/runs/" + "a" * 64 + "/authorization.html"): roles.SCOPED_BY_RUN,
        ("GET", "/v1/folder"): roles.SCOPED_BY_RUN,
    }
    for oidc in (False, True):
        for (method, path), rule in named.items():
            assert roles.team_rule(method, path, oidc=oidc) == rule, (oidc, method, path)
    examined(2 * len(named), "rows the note's table names, in both sets")


def test_the_routes_that_need_no_principal_draw_nothing_from_runs(shared_demo, tmp_path, examined):
    """`/health`, the sign-in page and sign-out answer the same bytes on an empty store and on the demo's."""
    from onetrace_console.config import Config
    from onetrace_console.serve import Handler
    from onetrace_console.store import Store
    from tests.conftest import serving
    from tests.test_signin_flow import _get, _post

    answers = {}
    for name in ("empty", "demo"):
        (tmp_path / name).mkdir()
        with serving(tmp_path / name) as (base, _root):
            saved = (Handler.config, Handler.store, Handler.store_root, Handler.session_store)
            from onetrace_console.sessions import SessionStore

            if name == "demo":
                Handler.store_root = shared_demo["folder"] / "store"
                Handler.store = Store(Handler.store_root / "store")
            Handler.config = Config(
                sign_in={**Config().sign_in, "enabled": True, "insecure_cookie_for_local_dev": True}
            )
            Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
            try:
                if name == "demo":
                    assert len(Handler.store.runs()) > 10
                got = []
                for path in ("/health", "/signin"):
                    status, body, headers, _ = _get(base, path)
                    #: The sign-in form's CSRF token is new at each request; the rest of the page is compared.
                    token = re.search(r"onetrace_csrf=([^;]+)", str(headers.get("Set-Cookie", "")))
                    if token:
                        body = body.replace(token.group(1).encode(), b"<token>")
                    got.append((path, status, body))
                status, body, _h, _ = _post(base, "/signout", b"", headers={"Origin": base})
                got.append(("/signout", status, body))
                answers[name] = got
            finally:
                Handler.config, Handler.store, Handler.store_root, Handler.session_store = saved
    assert answers["empty"] == answers["demo"]
    examined(len(answers["demo"]), "no-principal routes, on an empty store and the demo's")
