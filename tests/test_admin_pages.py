"""The admin pages: `/admin/people`,
`/admin/teams` and `/admin/audit`, each

- answering `admin` only;
- drawing nothing from run contents;
- with a row in the role table;
- drawn in both themes at 1280 and 390 px by the layout check (its kinds `admin-people`, `admin-teams`,
  `admin-audit`, served from example facts by `tools/signin_pages.py`);

and saying, each at its top, when SCIM's enforcement of sign-in is off and since when, and when the audit log is
failing; People lists Users, tokens near their expiry, the requests refused from outside `scim.allowed_sources`, the
values dropped beside a removal and the removals refused; Teams the Groups with no team and the teams naming no
provisioned Group. A directory string is drawn escaped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from onetrace_console import scim
from tests.test_entra_flow import entra, sign_in  # noqa: F401 - a fixture, requested by name
from tests.test_scim_teams import OID, TEAMS, _group, _try, _user, directory  # noqa: F401 - a fixture
from tests.test_scim_users import call

PAGES = ("people", "teams", "audit")
REPO = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("which", PAGES)
def test_each_admin_page_has_a_role_table_row_an_admin_s_in_both_sets_of_rules(which, examined):
    from onetrace_console import roles

    for oidc in (False, True):
        rel = f"admin/{which}"
        assert roles.required_role("GET", "/" + rel, rel_for_get=rel, oidc=oidc) == roles.ADMIN
        assert roles.team_rule("GET", "/" + rel, rel_for_get=rel, oidc=oidc) == roles.ADMIN_UNSCOPED
    examined(2, f"admin/{which}, both sets of rules")


@pytest.mark.parametrize("which", PAGES)
def test_each_admin_page_answers_an_admin_only(directory, which, examined):
    base, fake, _root, token, _log = directory
    _user(token, base)
    got = {}
    for role in ("onetrace.viewer", "onetrace.investigator", "onetrace.admin"):
        session = sign_in(base, fake, roles=(role,))[3]
        got[role] = _try(base, f"/admin/{which}", session)[0]
    assert got == {"onetrace.viewer": 403, "onetrace.investigator": 403, "onetrace.admin": 200}, got
    assert _try(base, f"/admin/{which}", "no-such-session")[0] == 303
    examined(4, f"admin/{which}: three roles and no session")


def test_with_local_sign_in_no_account_reaches_an_admin_page(examined):
    """A local account is a viewer; the admin pages are an admin's (with sign-in off, the machine's own user's)."""
    from onetrace_console import roles

    assert roles.required_role("GET", "/admin/people", rel_for_get="admin/people") == roles.ADMIN
    assert not roles.role_includes(roles.VIEWER, roles.ADMIN)
    examined(1, "a local viewer and an admin page")


@pytest.mark.parametrize("which", PAGES)
def test_an_admin_page_draws_nothing_from_run_contents(directory, shared_demo, monkeypatch, which, examined):
    from onetrace_console.serve import Handler
    from onetrace_console.store import Store
    from tests.conftest import demo_copy

    base, fake, root, token, _log = directory
    demo = Store(demo_copy(shared_demo, root.parent / "demo") / "store" / "store")
    runs = demo.runs()
    assert runs
    monkeypatch.setattr(Handler, "store", demo)
    _user(token, base)
    session = sign_in(base, fake, roles=("onetrace.admin",))[3]
    status, page, _h, _ = _try(base, f"/admin/{which}", session)
    assert status == 200
    text = page.decode("utf-8")
    for run in runs:
        assert run.key not in text and run.run_id not in text, run.run_id
    examined(len(runs), f"runs, none named on admin/{which}")


def test_every_admin_page_says_enforcement_is_off_and_since_when_and_that_the_log_is_failing(directory, examined):
    from onetrace_console.admin_pages import Facts, page

    facts = Facts(
        scim_on=True,
        enforcement=(False, "2026-11-14T22:05:31Z"),
        audit_on=True,
        unrecorded=[{"at": "2026-11-14T22:01:17.551Z", "event": "signout"}],
    )
    for which in PAGES:
        drawn = page(which, facts)
        assert 'data-admin="enforcement-off"' in drawn and "since 2026-11-14T22:05:31Z" in drawn, which
        assert (
            'data-admin="audit-failing"' in drawn and "1 action(s) not recorded since 2026-11-14T22:01:17.551Z" in drawn
        )
    on = Facts(scim_on=True)
    assert all('data-admin="enforcement-off"' not in page(w, on) for w in PAGES)
    examined(len(PAGES) + 1, "each page with enforcement off and the log failing; each with neither")


def test_people_lists_users_tokens_refusals_and_what_was_dropped(directory, monkeypatch, examined):
    from datetime import UTC, datetime, timedelta

    from onetrace_console.admin_pages import gather, people
    from onetrace_console.serve import Handler

    base, _fake, root, token, log = directory
    _user(token, base, name="<script>alert(1)</script>")
    scim.TokenStore(root).create(5, now=datetime.now(UTC) - timedelta(days=1))
    _s, made, _h = call(
        base,
        "POST",
        "/scim/v2/Users",
        token=token,
        body={"externalId": "00000002-0000-4000-8000-000000000000", "userName": "bo"},
    )
    call(
        base,
        "PATCH",
        f"/scim/v2/Users/{made['id']}",
        token=token,
        body={
            "Operations": [
                {"op": "replace", "path": "externalId", "value": "mailNickname"},
                {"op": "replace", "path": "active", "value": False},
            ]
        },
    )
    call(
        base,
        "PATCH",
        f"/scim/v2/Users/{made['id']}",
        token=token,
        body=b'{"Operations": [{"op": "replace", "path": "active", "value": false}',
    )
    monkeypatch.setattr(Handler, "scim_refused_sources", 2)
    facts = gather(root, Handler.config, audit_log=log, refused_sources=2, refused_writes=Handler.scim_refused_writes)
    drawn = people(facts)
    assert "&lt;script&gt;" in drawn and "<script>alert" not in drawn
    assert drawn.count('data-admin="expires-soon"') == 1, "the token made 5 days ago-plus-one, expiring within 14"
    assert "2 request(s) refused from outside" in drawn
    assert "externalId &#x27;mailNickname&#x27;" in drawn
    assert 'data-admin="refused"' in drawn and "the body is not JSON" in drawn
    examined(5, "users escaped, a token near expiry, sources refused, a value dropped, a removal refused")


def test_teams_lists_groups_with_no_team_and_teams_naming_no_group(directory, examined):
    from onetrace_console.admin_pages import gather, teams
    from onetrace_console.serve import Handler

    base, _fake, root, token, _log = directory
    _group(token, base, "0000000c-1111-4222-8333-444444444444")
    _group(token, base, TEAMS["alpha"]["scim_group"])
    drawn = teams(gather(root, Handler.config))
    assert 'data-admin="unmapped"' in drawn and "0000000c-1111-4222-8333-444444444444" in drawn
    assert '<ul data-admin="unprovisioned"><li>beta</li></ul>' in drawn
    examined(2, "a group no team names; a team naming no provisioned group")


def test_audit_says_its_head_and_where_the_heads_are_kept(directory, monkeypatch, tmp_path, examined):
    from dataclasses import replace

    from onetrace_console.admin_pages import audit_page, gather
    from onetrace_console.audit import AuditLog
    from onetrace_console.serve import Handler

    _base, _fake, root, _token, _log = directory
    heads = tmp_path / "heads-for-page.jsonl"
    config = replace(Handler.config, audit={"enabled": True, "head_location": str(heads), "max_segment_bytes": 1 << 20})
    AuditLog(root / "audit_log", head_location=heads).append("cli", "audit.checkpoint", "log", {})
    drawn = audit_page(gather(root, config))
    assert "<dt>Last seq</dt><dd>1</dd>" in drawn and str(heads) in drawn
    assert "audit-off" in audit_page(gather(root, Handler.config))
    examined(2, "the log on, and off")


def test_the_layout_check_draws_each_admin_page_in_both_themes_at_1280_and_390(examined):
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import layout_check
        import signin_pages
    finally:
        sys.path.remove(str(REPO / "tools"))
    for which in PAGES:
        kind = f"admin-{which}"
        assert kind in layout_check.KINDS and layout_check.SIGNIN_KINDS[kind] == f"admin/{which}"
        ctype, body = signin_pages.pages()[f"/admin/{which}"]
        assert ctype.startswith("text/html") and b'data-admin="nav"' in body
    src = Path(layout_check.__file__).read_text(encoding="utf-8")
    assert 'default="1280,768,390"' in src and 'choices=("light", "dark")' in src, "the gate runs it in each theme"
    examined(len(PAGES), "admin pages among the layout check's kinds, served for it")


def test_an_admin_page_is_never_answered_on_a_public_console(tmp_path, monkeypatch, examined):
    from dataclasses import replace

    from onetrace_console.config import Config
    from onetrace_console.serve import Handler
    from tests.conftest import serving
    from tests.test_signin_flow import _get

    with serving(tmp_path) as (base, _root):
        monkeypatch.setattr(
            Handler, "config", replace(Config(), public=True, sign_in={**Config().sign_in, "enabled": False})
        )
        for which in PAGES:
            try:
                status = _get(base, f"/admin/{which}")[0]
            except Exception as e:  # urllib raises on 4xx
                status = e.code
            assert status == 404, which
    examined(len(PAGES), "admin pages on a public console")
