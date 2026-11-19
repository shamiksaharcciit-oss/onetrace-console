"""Groups, teams from SCIM, deprovisioning, through the fake Entra ID:

- Group create, and members PATCH add and remove, as Entra ID sends them;
- a mapped group grants its team on the next request; an unmapped group grants nothing and is listed; with SCIM on, a
  role claim grants no team;
- `active: false` (boolean and string) and DELETE each end every live session of that person before the response,
  and refuse the next request;
- a sign-in whose object id matches no active User is refused and recorded; with `required_for_sign_in` false, an
  inactive or deleted object id is refused, and one SCIM never named is admitted with no team from SCIM;
- a PATCH with Entra ID's capitalised `op`, an unkept `path` beside `active` false, and a members remove naming an
  unknown User beside a real one: each removes access, none is refused; a deprovisioning while the audit log cannot
  be appended to removes access and says the failure;
- `scim user activate` and `scim enforcement off` and `on` (`test_scim_recovery.py`);
- the provisioning-cycle double's second cycle writes nothing.
"""

from __future__ import annotations

import time

import pytest

from onetrace_console import scim
from tests.fake_entra import TENANT
from tests.test_entra_flow import entra, sign_in  # noqa: F401 - a fixture, requested by name
from tests.test_scim_users import call
from tests.test_signin_flow import _get

OID = "99999999-8888-7777-6666-555555555555"
OTHER = "aaaaaaaa-8888-7777-6666-555555555555"
GROUP_A = "0000000a-1111-4222-8333-444444444444"
GROUP_B = "0000000b-1111-4222-8333-444444444444"
TEAMS = {"alpha": {"scim_group": GROUP_A}, "beta": {"scim_group": GROUP_B, "role_claim": "onetrace.viewer"}}


@pytest.fixture
def directory(entra, monkeypatch, tmp_path):
    """The fake's console with SCIM on and two teams mapped to groups, a SCIM token, and an audit log: (base, fake,
    store root, token, log)."""
    from dataclasses import replace

    from onetrace_console import scim
    from onetrace_console.audit import Audit, AuditLog
    from onetrace_console.serve import Handler

    base, fake, root = entra
    config = Handler.config
    monkeypatch.setattr(
        Handler, "config", replace(config, teams=TEAMS, scim={**scim.DEFAULTS, "enabled": True, "tenant_id": TENANT})
    )
    log = AuditLog(tmp_path / "audit_log", head_location=tmp_path / "heads.jsonl")
    monkeypatch.setattr(Handler, "audit", Audit(log))
    monkeypatch.setattr(Handler, "scim_directory", None)
    from onetrace_console.serve import _render_all_pages

    _render_all_pages(Handler.store, root, Handler.config)
    _r, token = scim.TokenStore(root).create(90)
    return base, fake, root, token, log


def _user(token, base, oid=OID, *, name="ada@example.org", active=True) -> dict:
    status, made, _h = call(
        base,
        "POST",
        "/scim/v2/Users",
        token=token,
        body={
            "schemas": [scim.USER],
            "externalId": oid,
            "userName": name,
            "active": active,
        },
    )
    assert status == 201, made
    return made


def _group(token, base, ext, members=()) -> dict:
    body = {
        "schemas": [scim.GROUP],
        "externalId": ext,
        "displayName": f"group {ext[:8]}",
        "members": [{"value": m} for m in members],
    }
    status, made, _h = call(base, "POST", "/scim/v2/Groups", token=token, body=body)
    assert status == 201, made
    return made


def _members(token, base, group_id, op, ids, *, by_filter=False):
    if op.lower() == "remove" and by_filter:
        ops = [{"op": op, "path": f'members[value eq "{i}"]'} for i in ids]
    else:
        ops = [{"op": op, "path": "members", "value": [{"value": i} for i in ids]}]
    return call(
        base,
        "PATCH",
        f"/scim/v2/Groups/{group_id}",
        token=token,
        body={"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"], "Operations": ops},
    )


def _teams_now(base, session) -> list[str]:
    """The teams a request is served: those whose prefix, `/t/<team>/`, answers it."""
    out = []
    for team in TEAMS:
        status, _b, _h, _ = _try(base, f"/t/{team}/home.html", session)
        if status == 200:
            out.append(team)
    return out


def _try(base, path, session):
    try:
        return _get(base, path, headers={"Cookie": f"onetrace_session={session}"})
    except Exception as e:  # urllib raises on 4xx
        return e.code, b"", {}, None


# ------------------------------------------------------------------ groups


def test_group_create_and_members_add_and_remove_as_entra_id_sends_them(directory, examined):
    base, _fake, _root, token, _log = directory
    a, b = _user(token, base)["id"], _user(token, base, OTHER, name="bo@example.org")["id"]
    group = _group(token, base, GROUP_A, [a])
    assert [m["value"] for m in group["members"]] == [a]
    status, got, _h = _members(token, base, group["id"], "Add", [b])
    assert status == 200 and sorted(m["value"] for m in got["members"]) == sorted([a, b])
    status, got, _h = _members(token, base, group["id"], "Remove", [a], by_filter=True)
    assert status == 200 and [m["value"] for m in got["members"]] == [b]
    status, got, _h = _members(token, base, group["id"], "remove", [b])
    assert status == 200 and got["members"] == []
    _s, listed, _h = call(
        base,
        "GET",
        f"/scim/v2/Groups?filter=displayName+eq+%22group+{GROUP_A[:8]}%22&excludedAttributes=members",
        token=token,
    )
    assert listed["totalResults"] == 1 and "members" not in listed["Resources"][0]
    examined(4, "a group made, a member added, two removed, the group matched")


def test_a_second_group_with_one_external_id_is_409_and_an_unknown_id_404(directory, examined):
    base, _fake, _root, token, _log = directory
    _group(token, base, GROUP_A)
    status, body, _h = call(
        base, "POST", "/scim/v2/Groups", token=token, body={"externalId": GROUP_A.upper(), "displayName": "again"}
    )
    assert status == 409 and body["scimType"] == "uniqueness"
    assert call(base, "GET", "/scim/v2/Groups/" + "f" * 32, token=token)[0] == 404
    examined(2, "a group's externalId twice; an id never issued")


def test_a_member_naming_no_user_is_dropped_from_an_add_and_recorded(directory, examined):
    base, _fake, _root, token, log = directory
    a = _user(token, base)["id"]
    group = _group(token, base, GROUP_A)
    status, got, _h = _members(token, base, group["id"], "Add", [a, "e" * 32])
    assert status == 200 and [m["value"] for m in got["members"]] == [a]
    (entry,) = [
        e
        for e in log.entries()
        if e["event"] == "scim.write" and e["detail"].get("resource") == "Group" and e["detail"]["method"] == "PATCH"
    ]
    assert entry["detail"]["dropped"] == [f"member {'e' * 32!r}"] and entry["detail"]["members"] == [a]
    examined(1, "an add naming a User never issued")


# ------------------------------------------------------------------ teams from SCIM


def test_a_mapped_group_grants_its_team_on_the_next_request_and_a_role_claim_grants_none(directory, examined):
    base, fake, _root, token, _log = directory
    me = _user(token, base)["id"]
    group = _group(token, base, GROUP_A)
    _status, _page, _h, session, _csrf = sign_in(base, fake, roles=("onetrace.viewer",))
    assert session
    assert _teams_now(base, session) == [], "beta's role claim grants nothing with SCIM on; alpha has no member yet"
    _members(token, base, group["id"], "Add", [me])
    assert _teams_now(base, session) == ["alpha"], "on the next request, no new sign-in"
    _members(token, base, group["id"], "Remove", [me], by_filter=True)
    assert _teams_now(base, session) == []
    examined(3, "before the group holds the person, after the add, after the remove")


def test_an_unmapped_group_grants_nothing_and_is_listed(directory, examined):
    from onetrace_console import scim
    from onetrace_console.serve import Handler

    base, fake, root, token, _log = directory
    me = _user(token, base)["id"]
    stray = _group(token, base, "0000000c-1111-4222-8333-444444444444", [me])
    _s, _p, _h, session, _c = sign_in(base, fake)
    assert _teams_now(base, session) == []
    assert [g["id"] for g in scim.unmapped_groups(root, Handler.config.teams)] == [stray["id"]]
    assert scim.unprovisioned_mappings(root, Handler.config.teams) == ["alpha", "beta"]
    examined(2, "a group no team names; teams naming no group")


# ------------------------------------------------------------------ the join


def test_a_sign_in_whose_object_id_matches_no_active_user_is_refused_and_recorded(directory, examined):
    base, fake, _root, token, log = directory
    status, page, _h, session, _c = sign_in(base, fake)
    assert status == 403 and "not provisioned for this console" in page and not session
    _user(token, base, active=False)
    status, page, _h, session, _c = sign_in(base, fake)
    assert status == 403 and not session
    refused = [(e["object"], e["detail"]["reason"]) for e in log.entries() if e["event"] == "signin.refused"]
    assert refused == [(f"{TENANT}/{OID}", "not provisioned"), (f"{TENANT}/{OID}", "inactive")]
    examined(2, "never provisioned; inactive")


def test_with_required_for_sign_in_false_an_inactive_or_deleted_object_id_is_refused_and_one_never_named_admitted(
    directory, monkeypatch, examined
):
    from dataclasses import replace

    from onetrace_console.serve import Handler

    base, fake, _root, token, _log = directory
    monkeypatch.setattr(
        Handler, "config", replace(Handler.config, scim={**Handler.config.scim, "required_for_sign_in": False})
    )
    status, _page, _h, session, _c = sign_in(base, fake)
    assert status == 200 and session, "never named: admitted on its app roles"
    assert _teams_now(base, session) == [], "with no team from SCIM"
    made = _user(token, base, active=False)
    assert sign_in(base, fake)[0] == 403
    call(base, "DELETE", f"/scim/v2/Users/{made['id']}", token=token)
    assert sign_in(base, fake)[0] == 403, "a tombstone refuses"
    examined(3, "never named, inactive, deleted")


@pytest.mark.parametrize(
    "how",
    ["active false", "active False", "DELETE", "Replace beside an unkept path"],
)
def test_a_deprovisioning_ends_every_live_session_before_the_response_and_refuses_the_next_request(
    directory, how, examined
):
    from onetrace_console.serve import Handler

    base, fake, _root, token, log = directory
    me = _user(token, base)
    first = sign_in(base, fake)[3]
    second = sign_in(base, fake)[3]
    principal = f"{TENANT}/{OID}"
    assert len(Handler.session_store.sessions_of(principal)) == 2
    if how == "DELETE":
        status, _b, _h = call(base, "DELETE", f"/scim/v2/Users/{me['id']}", token=token)
    else:
        value = "False" if how == "active False" else False
        ops = [{"op": "replace" if how == "active false" else "Replace", "path": "active", "value": value}]
        if how.startswith("Replace beside"):
            ops.insert(0, {"op": "Replace", "path": "name.givenName", "value": "x"})
        status, _b, _h = call(base, "PATCH", f"/scim/v2/Users/{me['id']}", token=token, body={"Operations": ops})
    assert status in (200, 204)
    assert Handler.session_store.sessions_of(principal) == set(), "ended before the answer"
    for session in (first, second):
        got = _try(base, "/home.html", session)
        assert got[0] == 303, how
    ended = [e for e in log.entries() if e["event"] == "sessions.ended"]
    assert ended and ended[0]["detail"] == {"count": 2, "by": "deprovisioning"} and ended[0]["actor"] == "console"
    examined(2, f"two sessions, ended by {how}")


def test_a_members_remove_naming_an_unknown_user_beside_a_real_one_removes_the_real_one(directory, examined):
    base, fake, _root, token, _log = directory
    me = _user(token, base)["id"]
    group = _group(token, base, GROUP_A, [me])
    session = sign_in(base, fake)[3]
    assert _teams_now(base, session) == ["alpha"]
    status, got, _h = _members(token, base, group["id"], "Remove", ["d" * 32, me], by_filter=True)
    assert status == 200 and got["members"] == []
    assert _teams_now(base, session) == []
    examined(1, "a remove naming one unknown User and one real")


def test_a_user_whose_active_check_fails_is_refused_at_its_next_request(directory, examined):
    """The per-request check that a User is active: one set inactive by another writer, here the file itself, ends the
    session at its next request."""
    import json as _json

    from onetrace_console import scim

    base, fake, root, token, _log = directory
    me = _user(token, base)
    session = sign_in(base, fake)[3]
    assert _try(base, "/home.html", session)[0] != 303
    path = scim.Users(root).root / f"{me['id']}.json"
    record = _json.loads(path.read_text(encoding="utf-8"))
    time.sleep(0.01)
    scim.Users(root).put({**record, "active": False})
    assert _try(base, "/home.html", session)[0] == 303
    examined(1, "a session after its User was set inactive")


def test_a_deprovisioning_while_the_audit_log_cannot_be_appended_to_removes_access_and_says_so(
    directory, capsys, examined
):
    from onetrace_console.serve import Handler

    base, fake, _root, token, log = directory
    me = _user(token, base)
    session = sign_in(base, fake)[3]
    log.head_location.unlink()
    log.head_location.mkdir()
    status, body, _h = call(
        base,
        "PATCH",
        f"/scim/v2/Users/{me['id']}",
        token=token,
        body={"Operations": [{"op": "Replace", "path": "active", "value": "False"}]},
    )
    assert status == 200 and body["active"] is False
    assert Handler.session_store.sessions_of(f"{TENANT}/{OID}") == set()
    assert _try(base, "/home.html", session)[0] == 303
    err = capsys.readouterr().err
    assert "scim.write was not recorded" in err and "applied anyway" in err
    log.head_location.rmdir()
    log.append("cli", "audit.checkpoint", "log", {})
    (failed,) = [e for e in log.entries() if e["event"] == "audit.append_failed"]
    assert failed["detail"]["not_recorded"] == {"scim.write": 1, "sessions.ended": 1}
    examined(1, "a deprovisioning with the log failing")


# ------------------------------------------------------------------ the provisioning-cycle double


class Cycle:
    """A small client running a provisioning cycle in Entra ID's order: match each person by userName, create or
    update; match each group by displayName without members, create; then members, added where not held."""

    def __init__(self, base, token):
        self.base, self.token, self.writes = base, token, 0

    def _call(self, method, path, body=None):
        got = call(self.base, method, "/scim/v2" + path, token=self.token, body=body)
        if method != "GET":
            self.writes += 1
        return got

    def run(self, people: list[dict], groups: list[dict]) -> None:
        from urllib.parse import quote

        ids = {}
        for p in people:
            _s, found, _h = self._call("GET", "/Users?filter=" + quote(f'userName eq "{p["userName"]}"'))
            if found["totalResults"] == 0:
                _s, made, _h = self._call("POST", "/Users", {"schemas": [scim.USER], **p})
                ids[p["externalId"]] = made["id"]
                continue
            held = found["Resources"][0]
            ids[p["externalId"]] = held["id"]
            changed = [{"op": "Replace", "path": k, "value": v} for k, v in p.items() if held.get(k) != v]
            if changed:
                self._call("PATCH", f"/Users/{held['id']}", {"Operations": changed})
        for g in groups:
            q = quote(f'displayName eq "{g["displayName"]}"')
            _s, found, _h = self._call("GET", f"/Groups?filter={q}&excludedAttributes=members")
            if found["totalResults"] == 0:
                _s, made, _h = self._call(
                    "POST", "/Groups", {"externalId": g["externalId"], "displayName": g["displayName"]}
                )
                gid = made["id"]
            else:
                gid = found["Resources"][0]["id"]
            _s, now, _h = self._call("GET", f"/Groups/{gid}")
            have = {m["value"] for m in now.get("members", [])}
            want = [ids[m] for m in g["members"] if ids[m] not in have]
            if want:
                self._call(
                    "PATCH",
                    f"/Groups/{gid}",
                    {"Operations": [{"op": "Add", "path": "members", "value": [{"value": i} for i in want]}]},
                )


def test_the_provisioning_cycle_double_s_second_cycle_writes_nothing(directory, examined):
    base, _fake, root, token, log = directory
    people = [
        {"externalId": OID, "userName": "ada@example.org", "displayName": "Ada", "active": True},
        {"externalId": OTHER, "userName": "bo@example.org", "displayName": "Bo", "active": True},
    ]
    groups = [{"externalId": GROUP_A, "displayName": "Team Alpha", "members": [OID, OTHER]}]
    first = Cycle(base, token)
    first.run(people, groups)
    assert first.writes == 4, "two Users, a Group, its members"
    entries = len(log.entries())
    files = sorted(p.stat().st_mtime_ns for p in (root / "scim").rglob("*.json") if "tokens" not in p.parts)
    second = Cycle(base, token)
    second.run(people, groups)
    assert second.writes == 0 and len(log.entries()) == entries, "nothing written, nothing recorded"
    assert sorted(p.stat().st_mtime_ns for p in (root / "scim").rglob("*.json") if "tokens" not in p.parts) == files
    examined(2, "a first cycle, then a second that changes nothing")
