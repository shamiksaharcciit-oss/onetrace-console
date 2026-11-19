"""Serving a team's pages: a request reads its person's team's set, and nothing of another
team's, which answers as what does not exist, byte for byte.

On a copy of the public demo with P1's runs split between two teams (`test_team_pages.split_demo`), a console with
both teams and Entra ID sign-in serves sessions in one team, the other, both, none, and an `admin`'s:

- a page of another team's run, comparison or pipeline answers the bytes of a page not drawn, the path echoed as
  asked; another team's prefix (`/t/<team>/`) answers as a team that does not exist;
- `record.tar` of another team's run answers as an unknown key; `/search?q=verdict:FAIL` returns the team's runs only;
  `/bisect?p=P1` resolves within the team; `POST /compare` of another team's key answers as an unknown key;
- every row of the role table scoped by run, walked with another team's key, answers as with an unknown key, with
  local sign-in's rules and with Entra ID's;
- a person's teams come from the ID token's app roles at sign-in, through the whole flow.
"""

from __future__ import annotations

import re
import time

import pytest

from onetrace_console import roles
from tests.test_entra_flow import entra  # noqa: F401 - the fake Entra ID's console, for the sign-in test
from tests.test_team_pages import TEAMS, A, B, split_demo

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT = "22222222-2222-2222-2222-222222222222"
UNKNOWN = "0" * 64


@pytest.fixture(scope="module")
def console(shared_demo, tmp_path_factory):
    from dataclasses import replace

    from onetrace_console.config import Config
    from onetrace_console.serve import Handler, _render_startup_pages
    from onetrace_console.sessions import SessionStore
    from onetrace_console.team_view import TeamView
    from tests.conftest import serving

    root, store = split_demo(shared_demo, tmp_path_factory.mktemp("team-serving") / "demo")
    oidc = Config(
        sign_in={
            "enabled": True,
            "method": "oidc",
            "public_url": "http://127.0.0.1",
            "insecure_cookie_for_local_dev": True,
            "oidc": {"tenant_id": TENANT, "client_id": CLIENT, "client_secret_env": "X", "session_max_hours": 8},
        },
        teams=TEAMS,
    )
    _render_startup_pages(store, root, oidc)
    with serving(tmp_path_factory.mktemp("team-serving-root")) as (base, _empty):
        names = ("store", "store_root", "config", "session_store")
        saved = {n: getattr(Handler, n, None) for n in names}
        #: Its own address, so the origin check passes a POST through to its handler.
        oidc = replace(oidc, sign_in={**oidc.sign_in, "public_url": base})
        Handler.store, Handler.store_root, Handler.config = store, root, oidc
        Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
        try:
            views = {t: TeamView(store, t) for t in (A, B)}
            yield base, store, views, oidc
        finally:
            for n, v in saved.items():
                setattr(Handler, n, v)


def session(role: str = "investigator", teams=(B,)) -> dict:
    from onetrace_console.serve import Handler

    oid = f"{abs(hash((role, teams))) % 10**8:08d}-0000-0000-0000-000000000000"
    s = Handler.session_store.create(
        f"{TENANT}/{oid}", role=role, display_name=role, expires_at=time.time() + 600, teams=tuple(teams)
    )
    return {"Cookie": f"onetrace_session={s.session_id}; onetrace_csrf={s.csrf_token}", "X-CSRF-Token": s.csrf_token}


def get(base, path, headers):
    from tests.test_signin_flow import _get

    try:
        status, body, h, _ = _get(base, path, headers=headers)
    except Exception as e:  # urllib raises on 4xx
        status, body, h = e.code, e.read(), dict(e.headers)
    return status, body, h.get("Content-Type")


def post(base, path, headers, body=b""):
    from tests.test_signin_flow import _post

    headers = {**headers, "Origin": base, "Content-Type": "application/x-www-form-urlencoded"}
    try:
        status, got, h, _ = _post(base, path, body, headers=headers)
    except Exception as e:
        status, got, h = e.code, e.read(), dict(e.headers)
    return status, got, h.get("Content-Type")


def same_as_unknown(asked, unknown, outside_key, unknown_key):
    """The two answers equal, once the key asked is read as the other."""
    return (
        asked[0] == unknown[0]
        and asked[2] == unknown[2]
        and asked[1].replace(outside_key.encode(), b"K") == unknown[1].replace(unknown_key.encode(), b"K")
    )


def _alpha_only_pipeline(views):
    from onetrace_console.overview import pipelines

    a = {p.label for p in pipelines(views[A])}
    b = {p.label for p in pipelines(views[B])}
    return sorted(a - b, key=lambda x: int(x[1:]))[0]


def test_a_page_of_another_team_answers_the_bytes_of_a_page_not_drawn(console, examined):
    base, _store, views, _config = console
    beta = session("viewer", (B,))
    asked = 0
    a_key = views[A].runs()[0].key
    for page in ("case.html", "answer.html", "proof.html", "receipt.html", "authorization.html", "stage-1.html"):
        outside = get(base, f"/runs/{a_key}/{page}", beta)
        unknown = get(base, f"/runs/{UNKNOWN}/{page}", beta)
        assert outside[0] == 404 and outside[1] == f"not rendered: runs/{a_key}/{page}\n".encode()
        assert same_as_unknown(outside, unknown, a_key, UNKNOWN), page
        asked += 1
    comparison = views[A].comparisons()[0].key
    outside = get(base, f"/diff/{comparison}.html", beta)
    assert same_as_unknown(outside, get(base, f"/diff/{UNKNOWN}.html", beta), comparison, UNKNOWN)
    label = _alpha_only_pipeline(views).lower()
    outside = get(base, f"/pipeline-{label}.html", beta)
    unknown = get(base, "/pipeline-p999.html", beta)
    assert same_as_unknown(outside, unknown, label, "p999")
    #: The team's own pages are served, from its set.
    b_key = views[B].runs()[0].key
    assert get(base, f"/runs/{b_key}/case.html", beta)[0] == 200
    assert get(base, f"/runs/{b_key}/case.html", session("viewer", (A,)))[0] == 404
    examined(asked + 4, "pages asked for by another team, and by the run's own")


def test_another_team_s_prefix_answers_as_a_team_that_does_not_exist(console, examined):
    base, _store, views, _config = console
    beta, admin = session("viewer", (B,)), session("admin", ())
    outside = get(base, "/t/alpha/home.html", beta)
    unknown = get(base, "/t/gamma/home.html", beta)
    assert outside[0] == 404 and same_as_unknown(outside, unknown, "alpha", "gamma")
    b_key = views[B].runs()[0].key
    assert get(base, f"/t/beta/runs/{b_key}/case.html", beta)[0] == 200
    assert get(base, "/t/beta/", beta)[0] == 200
    #: An admin reads the all-teams set, and each team's through its prefix.
    a_key = views[A].runs()[0].key
    assert get(base, f"/runs/{a_key}/case.html", admin)[0] == 200
    assert get(base, f"/t/alpha/runs/{a_key}/case.html", admin)[0] == 200
    assert get(base, f"/t/beta/runs/{a_key}/case.html", admin)[0] == 404
    examined(7, "prefixed requests")


def test_a_person_in_no_team_reads_nothing_and_a_person_in_two_reads_each(console, examined):
    base, _store, views, _config = console
    nobody, both = session("viewer", ()), session("viewer", (A, B))
    from onetrace_console.team_assign import NO_TEAM

    status, body, ctype = get(base, "/", nobody)
    assert status == 403 and NO_TEAM.encode() in body and ctype.startswith("text/html"), "the page for no team"
    a_key, b_key = views[A].runs()[0].key, views[B].runs()[0].key
    assert get(base, f"/runs/{a_key}/case.html", both)[0] == 200
    assert get(base, f"/t/beta/runs/{b_key}/case.html", both)[0] == 200
    assert get(base, f"/runs/{b_key}/case.html", both)[0] == 404, "the first team's set, without a prefix"
    examined(4, "requests by a person in no team and in two")


def test_record_tar_of_another_team_s_run_answers_as_an_unknown_key(console, examined):
    base, _store, views, _config = console
    beta = session("viewer", (B,))
    a_key, b_key = views[A].runs()[0].key, views[B].runs()[0].key
    outside = get(base, f"/runs/{a_key}/record.tar", beta)
    assert outside == get(base, f"/runs/{UNKNOWN}/record.tar", beta) == (404, b"no such run\n", "text/plain")
    assert get(base, f"/runs/{b_key}/record.tar", beta)[0] == 200
    examined(3, "record.tar asked for")


def test_search_reads_the_team_s_index_only(console, examined):
    base, _store, views, _config = console
    keys = {t: {r.key for r in views[t].runs()} for t in (A, B)}

    def found(headers):
        status, body, _ = get(base, "/search?q=verdict%3AFAIL", headers)
        assert status == 200
        return set(re.findall(r"runs/([0-9a-f]{64})/", body.decode())) & (keys[A] | keys[B])

    every = found(session("admin", ()))
    assert every & keys[A] and every & keys[B], "the query finds runs of both teams in the all-teams index"
    alpha = found(session("viewer", (A,)))
    assert alpha and alpha <= keys[A]
    examined(len(every), "runs the query finds across teams")


def test_bisect_resolves_p1_within_the_team(console, examined):
    base, _store, views, _config = console
    beta = session("investigator", (B,))
    status, body, _ = get(base, "/bisect?p=P1", beta)
    assert status == 200
    named = set(re.findall(r"runs/([0-9a-f]{64})/", body.decode()))
    assert named and named <= {r.key for r in views[B].runs()}
    label = _alpha_only_pipeline(views)
    assert (
        get(base, f"/bisect?p={label}", beta)
        == get(base, "/bisect?p=P999", beta)
        == (
            404,
            b"no such pipeline\n",
            "text/plain",
        )
    )
    examined(len(named) + 1, "runs the team's bisect names, and another team's pipeline")


def test_compare_of_another_team_s_key_answers_as_an_unknown_key(console, examined):
    base, _store, views, _config = console
    beta = session("investigator", (B,))
    b1, b2 = (r.key for r in views[B].runs()[:2])
    a_key = views[A].runs()[0].key
    outside = post(base, f"/compare?a={b1}&b={a_key}", beta)
    unknown = post(base, f"/compare?a={b1}&b={UNKNOWN}", beta)
    assert outside[0] == 400 and same_as_unknown(outside, unknown, a_key, UNKNOWN), outside
    assert b"unknown or malformed run key" in outside[1]
    outside = post(base, f"/compare?a={a_key}&b={b2}", beta)
    unknown = post(base, f"/compare?a={UNKNOWN}&b={b2}", beta)
    assert same_as_unknown(outside, unknown, a_key, UNKNOWN)
    examined(2, "comparisons asked with another team's key")


#: Each POST row scoped by run that takes a key: the query naming it, `{k}` for the key.
POST_KEYS = {
    "/compare": ("run", "a={k}&b={own}"),
    "/compare/check": ("comparison", "key={k}&check=text"),
    "/text-diff/more": ("comparison", "c={k}"),
    "/explain": ("comparison", "c={k}"),
    "/explain/packet": ("comparison", "c={k}"),
    "/explain/check": ("comparison", "c={k}&e=0&i=0"),
    "/explain/cancel": ("comparison", "c={k}"),
    "/explain/text": ("comparison", "c={k}&on=yes"),
    "/benchmark": ("run", "run={k}"),
    "/expectations": ("run", "run={k}"),
}
#: The scoped POST rows that take no run or comparison key: a delivery and a decision export are scoped by the
#: delivering token's team (a run is assigned on arrival); the folder's "Load as not closed" names a run folder.
POST_WITHOUT_A_KEY = {"/v1/runs", "/v1/decisions", "/runs/load-not-closed"}


@pytest.mark.parametrize("oidc", [True, False], ids=["Entra ID", "local sign-in"])
def test_every_scoped_row_walked_with_another_team_s_key_answers_as_an_unknown_one(console, oidc, examined):
    """Every row of the role table that is scoped by run, in the set of rules named, asked with the other team's key
    and with an unknown one: the two answers are the same. With local sign-in a session is in no team, so every key
    is another team's."""
    from dataclasses import replace

    from onetrace_console.serve import Handler

    base, _store, views, config = console
    if not oidc:
        Handler.config = replace(config, sign_in={**config.sign_in, "method": "local"})
    try:
        headers = session("investigator" if oidc else None, (B,) if oidc else ())
        a_run, a_comparison = views[A].runs()[0].key, views[A].comparisons()[0].key
        own = views[B].runs()[0].key
        walked = 0
        for pattern in roles._VIEWER_GET_PATTERNS:
            if roles._GET_TEAM_RULES[pattern.pattern] != roles.SCOPED_BY_RUN or not re.search(
                r"\^(runs|diff)/|choose-p.*64", pattern.pattern
            ):
                continue
            path = re.sub(r"\[0-9a-f\]\{64\}|\[\^/\]\+", "K", pattern.pattern.strip("^$")).replace("\\.", ".")
            path = path.replace("[0-9]+", "1")
            key = a_comparison if path.startswith("diff/") else a_run
            outside = get(base, "/" + path.replace("K", key), headers)
            unknown = get(base, "/" + path.replace("K", UNKNOWN), headers)
            #: 403 where the session is in no team (local sign-in): the one page for no team, the same for every path.
            assert outside[0] in (404, 303, 403) and same_as_unknown(outside, unknown, key, UNKNOWN), (
                path,
                outside[:2],
            )
            walked += 1
        for path in roles.post_routes():
            if roles._POST_TEAM_RULES[path] != roles.SCOPED_BY_RUN or path in POST_WITHOUT_A_KEY:
                continue
            kind, query = POST_KEYS[path]
            key = a_run if kind == "run" else a_comparison
            outside = post(base, f"{path}?{query.format(k=key, own=own)}", headers)
            unknown = post(base, f"{path}?{query.format(k=UNKNOWN, own=own)}", headers)
            assert outside[0] != 403, (path, outside[:2], "refused before its handler")
            assert same_as_unknown(outside, unknown, key, UNKNOWN), (path, outside[:2], unknown[:2])
            walked += 1
    finally:
        Handler.config = config
    assert set(POST_KEYS) | POST_WITHOUT_A_KEY == {
        p for p in roles.post_routes() if roles._POST_TEAM_RULES[p] == roles.SCOPED_BY_RUN
    }
    examined(walked, "scoped rows walked with another team's key")


def test_a_person_s_teams_come_from_the_id_token_s_app_roles_at_sign_in(entra, examined):
    from dataclasses import replace

    from onetrace_console.serve import Handler
    from tests.test_entra_flow import sign_in

    base, fake, _root = entra
    Handler.config = replace(Handler.config, teams=TEAMS)
    got = {}
    for asked in (
        ("onetrace.viewer", "Team.Beta"),
        ("onetrace.viewer", "Team.Alpha", "Team.Beta"),
        ("onetrace.viewer",),
    ):
        status, _page, _h, cookie, _csrf = sign_in(base, fake, roles=asked)
        assert status == 200
        got[asked] = Handler.session_store.get(cookie).teams
    assert list(got.values()) == [(B,), (A, B), ()]
    examined(len(got), "sign-ins with app roles naming teams")
