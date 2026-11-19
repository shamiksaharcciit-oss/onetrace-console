"""SCIM discovery and Users:

- `/ServiceProviderConfig`, `/Schemas` and `/ResourceTypes` answer as the console declares them;
- User create, get, filter `eq`, replace, PATCH and delete, replayed from the Entra-shaped conversations in
  `tests/scim_entra/users.json`;
- every negative test for Users: a missing or wrong token (`401`, `WWW-Authenticate`), a revoked and an
  expired one, a token in the query string or a form body, a SCIM token on a page route and a session or ingester
  token on a SCIM route, `or` and other filter operators, a body over the limit, an `id` with a path in it, two Users
  with one `userName` or one `externalId` in two letter cases, an `externalId` not shaped like a GUID, `/Me`,
  `/.search` and `/Bulk`; and the writes that remove access, never refused: a PATCH path the console does not keep
  beside `active` false, and a removal while the audit log cannot be appended to;
- with `scim.enabled` false, `/scim/v2/*` answers as a route the console does not have.
"""

from __future__ import annotations

import http.client
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from onetrace_console import scim
from tests.http_limits import limit

FIXTURES = Path(__file__).parent / "scim_entra"
TENANT = "0f1e2d3c-4b5a-4968-8778-695a4b3c2d1e"
PUBLIC_URL = "https://onetrace.example.org"


def scim_config(**scim_over):
    from onetrace_console.config import Config
    from onetrace_console.scim import DEFAULTS

    sign_in = {
        **Config().sign_in,
        "enabled": True,
        "method": "oidc",
        "public_url": PUBLIC_URL,
        "oidc": {**Config().sign_in["oidc"], "tenant_id": TENANT, "client_id": "11111111-2222-4333-8444-555555555555"},
    }
    return Config(sign_in=sign_in, scim={**DEFAULTS, "enabled": True, **scim_over})


@pytest.fixture
def scim_console(tmp_path, monkeypatch):
    """A console with SCIM on, sign-in through Entra ID named, and one live SCIM token: (base, store root, token)."""
    from onetrace_console import scim
    from onetrace_console.serve import Handler
    from onetrace_console.sessions import SessionStore
    from tests.conftest import serving

    with serving(tmp_path) as (base, root):
        monkeypatch.setattr(Handler, "config", scim_config())
        monkeypatch.setattr(
            Handler, "session_store", SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
        )
        monkeypatch.setattr(Handler, "token_store", None)
        _record, raw = scim.TokenStore(root).create(90)
        yield base, root, raw


def call(base: str, method: str, path: str, *, token: str | None = None, body=None, headers=None):
    """(status, the parsed body or None, the headers) of one request, over HTTP."""
    u = urlsplit(base)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=limit(60))
    hs = {"Content-Type": "application/scim+json", **(headers or {})}
    if token is not None:
        hs["Authorization"] = f"Bearer {token}"
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    try:
        conn.request(method, path, body=data, headers=hs)
        r = conn.getresponse()
        raw = r.read()
        parsed = json.loads(raw) if raw and r.getheader("Content-Type", "").startswith("application/scim+json") else raw
        return r.status, parsed, {k.lower(): v for k, v in r.getheaders()}
    finally:
        conn.close()


def _user(n: int, **over) -> dict:
    body = {
        "schemas": [scim.USER],
        "externalId": f"{n:08x}-0000-4000-8000-000000000000",
        "userName": f"person{n}@example.org",
        "active": True,
    }
    body.update(over)
    return body


# ------------------------------------------------------------------ discovery


def test_service_provider_config_declares_what_is_served_and_what_is_left_out(scim_console, examined):
    base, _root, token = scim_console
    status, spc, headers = call(base, "GET", "/scim/v2/ServiceProviderConfig", token=token)
    assert status == 200 and headers["content-type"].startswith("application/scim+json")
    assert spc["schemas"] == [scim.SPC]
    assert spc["patch"] == {"supported": True}
    assert spc["bulk"]["supported"] is False and spc["sort"] == {"supported": False}
    assert spc["etag"] == {"supported": False} and spc["changePassword"] == {"supported": False}
    assert spc["filter"] == {"supported": True, "maxResults": 200}
    assert [s["type"] for s in spc["authenticationSchemes"]] == ["oauthbearertoken"]
    examined(1, "the service provider's configuration")


def test_schemas_and_resource_types_are_user_and_group_cut_to_what_is_kept(scim_console, examined):
    base, _root, token = scim_console
    _s, schemas, _h = call(base, "GET", "/scim/v2/Schemas", token=token)
    by_id = {s["id"]: s for s in schemas["Resources"]}
    user = by_id[scim.USER]
    assert [a["name"] for a in user["attributes"]] == ["userName", "externalId", "displayName", "active", "emails"]
    group = by_id[scim.GROUP]
    assert [a["name"] for a in group["attributes"]] == ["displayName", "externalId", "members"]
    status, one, _h = call(base, "GET", "/scim/v2/Schemas/" + scim.USER, token=token)
    assert status == 200 and one == user
    _s, types, _h = call(base, "GET", "/scim/v2/ResourceTypes", token=token)
    assert [(t["name"], t["endpoint"]) for t in types["Resources"]] == [("User", "/Users"), ("Group", "/Groups")]
    assert call(base, "GET", "/scim/v2/ResourceTypes/User", token=token)[0] == 200
    assert call(base, "GET", "/scim/v2/ResourceTypes/Nobody", token=token)[0] == 404
    examined(4, "the schemas list, one schema, the resource types, one type")


# ------------------------------------------------------------------ the Entra-shaped conversations


def _conversations():
    data = json.loads((FIXTURES / "users.json").read_text(encoding="utf-8"))
    assert data["written"] and data["source"].startswith("Microsoft Learn")
    return data["conversations"]


@pytest.mark.parametrize("conversation", _conversations(), ids=lambda c: c["name"])
def test_an_entra_shaped_conversation_is_answered_as_scim_says(scim_console, conversation, examined):
    base, _root, token = scim_console
    kept: dict[str, str] = {}
    for step in conversation["steps"]:
        path = "/scim/v2" + step["path"].replace("{id}", kept.get("id", ""))
        status, body, headers = call(base, step["method"], path, token=token, body=step.get("body"))
        where = f"{step['method']} {step['path']}"
        assert status == step["status"], (where, status, body)
        if status == 201:
            assert headers["location"] == f"{PUBLIC_URL}/scim/v2/Users/{body['id']}"
            assert set(body["meta"]) == {"resourceType", "created", "lastModified", "location"}
        if "keep" in step:
            kept[step["keep"]] = body[step["keep"]]
        if "list" in step:
            assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:ListResponse"]
            assert body["totalResults"] == step["list"] == len(body["Resources"]), where
        for k, v in step.get("shows", {}).items():
            assert body[k] == v, (where, k, body)
        for k in step.get("hides", ()):
            assert k not in body, (where, k)
        if "error" in step:
            assert (
                body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"] and body["status"] == step["error"]
            )
        if status == 204:
            assert body in (b"", None)
    examined(len(conversation["steps"]), conversation["name"])


def test_a_user_s_id_is_the_console_s_own_32_hex_never_the_directory_s(scim_console, examined):
    import re

    base, _root, token = scim_console
    _s, made, _h = call(base, "POST", "/scim/v2/Users", token=token, body=_user(1))
    assert re.fullmatch(r"[0-9a-f]{32}", made["id"]) and made["id"] not in json.dumps(_user(1))
    examined(1, "a created User's id")


# ------------------------------------------------------------------ the token


def test_a_missing_or_wrong_token_is_401_with_www_authenticate(scim_console, examined):
    base, _root, _token = scim_console
    for token, given in ((None, False), ("not-a-token", True)):
        status, body, headers = call(base, "GET", "/scim/v2/Users", token=token)
        assert status == 401
        want = 'Bearer realm="scim"' + (', error="invalid_token"' if given else "")
        assert headers["www-authenticate"] == want
        assert body == {"schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"], "status": "401"}
    examined(2, "no token, a wrong one")


def test_a_revoked_or_expired_token_answers_as_an_unknown_one(scim_console, examined):
    from datetime import UTC, datetime, timedelta

    from onetrace_console import scim

    base, root, _token = scim_console
    tokens = scim.TokenStore(root)
    revoked, raw_revoked = tokens.create(90)
    tokens.revoke(revoked.token_id)
    _expired, raw_expired = tokens.create(1, now=datetime.now(UTC) - timedelta(days=2))
    unknown = call(base, "GET", "/scim/v2/Users", token="x" * 43)
    for raw in (raw_revoked, raw_expired):
        assert call(base, "GET", "/scim/v2/Users", token=raw) == unknown
    examined(2, "a revoked token, an expired one")


def test_a_token_in_the_query_string_or_a_form_body_is_refused_even_where_it_is_live(scim_console, examined):
    base, _root, token = scim_console
    in_query = call(base, "GET", f"/scim/v2/Users?access_token={token}")
    both = call(base, "GET", f"/scim/v2/Users?access_token={token}", token=token)
    form = call(
        base,
        "POST",
        "/scim/v2/Users",
        body=f"access_token={token}".encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        token=token,
    )
    assert in_query[0] == both[0] == form[0] == 401
    examined(3, "a token in the query, beside a header, in a form body")


def test_a_session_or_an_ingester_token_is_refused_on_scim_and_a_scim_token_on_every_other_route(
    scim_console, tmp_path, monkeypatch, examined
):
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import Handler

    base, root, token = scim_console
    session = Handler.session_store.create("t/o", role="admin", expires_at=time.time() + 600)
    ingester = TokenStore(tmp_path / "tokens")
    monkeypatch.setattr(Handler, "token_store", ingester)
    _rec, raw_ingester = ingester.create("ci")
    cookie = {"Cookie": f"onetrace_session={session.session_id}"}
    assert call(base, "GET", "/scim/v2/Users", headers=cookie)[0] == 401
    assert call(base, "GET", "/scim/v2/Users", token=raw_ingester)[0] == 401
    with_cookie = call(base, "GET", "/scim/v2/Users", token=token, headers=cookie)
    assert with_cookie[:2] == call(base, "GET", "/scim/v2/Users", token=token)[:2], "a cookie changes nothing"
    for method, path in (
        ("GET", "/home.html"),
        ("GET", "/"),
        ("POST", "/v1/runs"),
        ("GET", "/runs/" + "0" * 64 + "/case.html"),
    ):
        status = call(base, method, path, token=token, body=b"" if method == "POST" else None)[0]
        assert status in (303, 401, 403, 404), (method, path, status)
    examined(6, "a session and an ingester token on SCIM; a SCIM token on four other routes")


def test_with_scim_off_every_scim_path_answers_as_a_route_the_console_does_not_have(
    scim_console, monkeypatch, examined
):
    from onetrace_console.serve import Handler

    base, _root, token = scim_console
    monkeypatch.setattr(Handler, "config", scim_config(enabled=False))
    unknown = call(base, "GET", "/no-such-route")
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        got = call(base, method, "/scim/v2/Users", token=token, body={} if method in ("POST", "PUT", "PATCH") else None)
        assert got[:2] == (404, b"no such route\n") == unknown[:2], method
    examined(5, "each method with SCIM off")


@pytest.mark.parametrize("enabled", [True, False], ids=["scim on", "scim off"])
def test_put_patch_and_delete_outside_scim_are_answered_as_before_by_the_standard_server(
    scim_console, monkeypatch, enabled, examined
):
    """Outside `/scim/v2` the console serves no PUT, PATCH or DELETE: each is the standard server's own `501`, as it
    was before SCIM, and as a method the console has no handler for is answered."""
    from onetrace_console.serve import Handler

    base, _root, token = scim_console
    monkeypatch.setattr(Handler, "config", scim_config(enabled=enabled))
    unserved = call(base, "BREW", "/")
    assert unserved[0] == 501
    for method in ("PUT", "PATCH", "DELETE"):
        for path in ("/", "/v1/runs", "/home.html", "/scim", "/scim/v2x"):
            for given in (None, token):
                status, body, _hs = call(base, method, path, token=given, body=b"" if method != "DELETE" else None)
                assert status == 501, (method, path, status)
                assert body == unserved[1].replace(b"'BREW'", repr(method).encode()), (method, path, body)
    examined(30, "PUT, PATCH and DELETE on five paths outside SCIM, with and without its token")


def test_authentication_comes_before_a_404_or_a_501(scim_console, examined):
    base, _root, _token = scim_console
    for path in ("/scim/v2/Nowhere", "/scim/v2/Me", "/scim/v2/Users/" + "0" * 32):
        assert call(base, "GET", path)[0] == 401, path
    examined(3, "an unknown resource, /Me, an unknown User, without a token")


# ------------------------------------------------------------------ the negative tests


@pytest.mark.parametrize(
    "filter_, word",
    [
        ('userName eq "a" or userName eq "b"', "'or'"),
        ('userName ne "a"', "'ne'"),
        ('userName co "a"', "'co'"),
        ('userName sw "a"', "'sw'"),
        ('not (userName eq "a")', "'not'"),
        ('emails[type eq "work"]', "grouped"),
        ('displayName eq "a"', "'displayName'"),
    ],
)
def test_a_filter_it_does_not_serve_is_invalid_filter_naming_it(scim_console, filter_, word, examined):
    from urllib.parse import quote

    base, _root, token = scim_console
    status, body, _h = call(base, "GET", "/scim/v2/Users?filter=" + quote(filter_), token=token)
    assert status == 400 and body["scimType"] == "invalidFilter" and word in body["detail"], body
    examined(1, filter_)


def test_and_combines_two_eq_terms_and_a_quoted_and_is_a_value(scim_console, examined):
    from urllib.parse import quote

    base, _root, token = scim_console
    call(base, "POST", "/scim/v2/Users", token=token, body=_user(1, userName="rock and roll"))
    call(base, "POST", "/scim/v2/Users", token=token, body=_user(2))
    both = 'userName eq "rock and roll" and externalId eq "00000001-0000-4000-8000-000000000000"'
    _s, got, _h = call(base, "GET", "/scim/v2/Users?filter=" + quote(both), token=token)
    assert got["totalResults"] == 1
    _s, none, _h = call(base, "GET", "/scim/v2/Users?filter=" + quote('userName eq "rock"'), token=token)
    assert none["totalResults"] == 0
    examined(2, "two terms; a value holding and")


def test_a_body_over_the_limit_is_refused_before_it_is_read(scim_console, monkeypatch, examined):
    from onetrace_console.serve import Handler

    base, _root, token = scim_console
    monkeypatch.setattr(Handler, "config", scim_config(max_body_bytes=2048))
    status, body, _h = call(base, "POST", "/scim/v2/Users", token=token, body=_user(1, displayName="x" * 4000))
    assert status == 413 and body["scimType"] == "invalidSyntax"
    examined(1, "a body over 2048 bytes")


@pytest.mark.parametrize(
    "path",
    [
        "/scim/v2/Users/../ServiceProviderConfig",
        "/scim/v2/Users/a%2F..%2Fb",
        "/scim/v2/Users/x/y",
        "/scim/v2/Users/%2e%2e",
    ],
)
def test_an_id_with_a_path_in_it_is_no_such_user(scim_console, path, examined):
    base, _root, token = scim_console
    status, body, _h = call(base, "GET", path, token=token)
    assert status == 404 and body["status"] == "404", (path, body)
    examined(1, path)


def test_two_users_with_one_user_name_or_one_external_id_in_two_cases_are_409_uniqueness(scim_console, examined):
    base, _root, token = scim_console
    assert call(base, "POST", "/scim/v2/Users", token=token, body=_user(1, userName="Ana@Example.org"))[0] == 201
    same_name = call(base, "POST", "/scim/v2/Users", token=token, body=_user(2, userName="ana@example.ORG"))
    upper = _user(3, externalId="00000001-0000-4000-8000-000000000000".upper())
    same_ext = call(base, "POST", "/scim/v2/Users", token=token, body=upper)
    for status, body, _h in (same_name, same_ext):
        assert status == 409 and body["scimType"] == "uniqueness", body
    examined(2, "a userName in another case, an externalId in another case")


@pytest.mark.parametrize("ext", ["mailNickname", "0a21f0f2-8d2a-4f8e-bf98", "", 42])
def test_an_external_id_not_shaped_like_a_guid_is_invalid_value(scim_console, ext, examined):
    base, _root, token = scim_console
    status, body, _h = call(base, "POST", "/scim/v2/Users", token=token, body=_user(1, externalId=ext))
    assert status == 400 and body["scimType"] == "invalidValue", body
    examined(1, repr(ext))


@pytest.mark.parametrize("path", ["/scim/v2/Me", "/scim/v2/.search", "/scim/v2/Users/.search", "/scim/v2/Bulk"])
def test_me_search_and_bulk_are_501(scim_console, path, examined):
    base, _root, token = scim_console
    for method in ("GET", "POST"):
        status, body, _h = call(base, method, path, token=token, body={} if method == "POST" else None)
        assert status == 501 and body["status"] == "501", (method, path)
    examined(2, path)


def test_an_error_s_detail_never_echoes_a_token_a_header_or_a_body(scim_console, examined):
    base, _root, token = scim_console
    planted = "planted-value-zz9"
    answers = [
        call(base, "POST", "/scim/v2/Users", token=token, body=_user(1, externalId=planted)),
        call(base, "GET", f'/scim/v2/Users?filter=userName+co+"{planted}"', token=token),
        call(base, "PATCH", "/scim/v2/Users/" + "0" * 32, token=token, body={"Operations": planted}),
        call(base, "GET", "/scim/v2/Users", token=planted, headers={"X-Planted": planted}),
    ]
    for _status, body, _h in answers:
        assert planted not in json.dumps(body) and token not in json.dumps(body)
    examined(len(answers), "four refusals")


# ------------------------------------------------------------------ the writes that remove access


def test_a_patch_path_it_does_not_keep_beside_active_false_is_dropped_and_the_person_is_inactive(
    scim_console, examined
):
    base, root, token = scim_console
    _s, made, _h = call(base, "POST", "/scim/v2/Users", token=token, body=_user(1))
    ops = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [
            {
                "op": "Replace",
                "path": "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:manager",
                "value": "x",
            },
            {"op": "Replace", "path": "active", "value": "False"},
            {"op": "Add", "path": "name.givenName", "value": "Ana"},
        ],
    }
    status, body, _h = call(base, "PATCH", f"/scim/v2/Users/{made['id']}", token=token, body=ops)
    assert status == 200 and body["active"] is False and "name" not in body
    examined(1, "a PATCH with two unkept paths beside active false")


@pytest.mark.parametrize("ext", ["not-a-guid", "held-by-another"])
def test_inside_a_removal_a_bad_or_held_external_id_is_dropped_and_audited_not_refused(
    scim_console, tmp_path, monkeypatch, ext, examined
):
    from onetrace_console.audit import Audit, AuditLog
    from onetrace_console.serve import Handler

    base, _root, token = scim_console
    heads = tmp_path / "heads.jsonl"
    log = AuditLog(tmp_path / "audit_log", head_location=heads)
    monkeypatch.setattr(Handler, "audit", Audit(log))
    _s, a, _h = call(base, "POST", "/scim/v2/Users", token=token, body=_user(1))
    call(base, "POST", "/scim/v2/Users", token=token, body=_user(2))
    value = "00000002-0000-4000-8000-000000000000" if ext == "held-by-another" else ext
    ops = {
        "Operations": [
            {"op": "replace", "path": "externalId", "value": value},
            {"op": "replace", "path": "active", "value": False},
        ]
    }
    status, body, _h = call(base, "PATCH", f"/scim/v2/Users/{a['id']}", token=token, body=ops)
    assert status == 200 and body["active"] is False and body["externalId"] == "00000001-0000-4000-8000-000000000000"
    (entry,) = [e for e in log.entries() if e["event"] == "scim.write" and e["detail"]["method"] == "PATCH"]
    assert entry["detail"]["dropped"] == [f"externalId {value!r}"] and entry["detail"]["active"] is False
    examined(1, f"a removal beside {ext}")


def test_a_removal_while_the_audit_log_cannot_be_appended_to_applies_and_a_grant_does_not(
    scim_console, tmp_path, monkeypatch, capsys, examined
):
    from onetrace_console.audit import Audit, AuditLog
    from onetrace_console.serve import Handler

    base, _root, token = scim_console
    heads = tmp_path / "heads.jsonl"
    log = AuditLog(tmp_path / "audit_log", head_location=heads)
    monkeypatch.setattr(Handler, "audit", Audit(log))
    _s, a, _h = call(base, "POST", "/scim/v2/Users", token=token, body=_user(1))
    heads.unlink()
    heads.mkdir()
    off = {"Operations": [{"op": "Replace", "path": "active", "value": "False"}]}
    status, body, _h = call(base, "PATCH", f"/scim/v2/Users/{a['id']}", token=token, body=off)
    assert status == 200 and body["active"] is False, "the removal applies"
    assert "scim.write was not recorded" in capsys.readouterr().err
    on = {"Operations": [{"op": "Replace", "path": "active", "value": "True"}]}
    status, body, _h = call(base, "PATCH", f"/scim/v2/Users/{a['id']}", token=token, body=on)
    assert status == 503, "a grant is refused"
    assert call(base, "GET", f"/scim/v2/Users/{a['id']}", token=token)[1]["active"] is False, "and taken back"
    made = call(base, "POST", "/scim/v2/Users", token=token, body=_user(2))
    assert made[0] == 503
    _s, listed, _h = call(base, "GET", "/scim/v2/Users", token=token)
    assert listed["totalResults"] == 1, "the User refused is not kept"
    examined(3, "a removal applied, a reactivation and a create refused")


def test_every_write_is_recorded_as_scim_write_by_its_token_s_id_never_its_value(
    scim_console, tmp_path, monkeypatch, examined
):
    from onetrace_console import scim
    from onetrace_console.audit import Audit, AuditLog
    from onetrace_console.serve import Handler

    base, root, token = scim_console
    log = AuditLog(tmp_path / "audit_log", head_location=tmp_path / "heads.jsonl")
    monkeypatch.setattr(Handler, "audit", Audit(log))
    (live,) = scim.TokenStore(root).live()
    _s, a, _h = call(base, "POST", "/scim/v2/Users", token=token, body=_user(1, displayName="Ana"))
    call(
        base,
        "PATCH",
        f"/scim/v2/Users/{a['id']}",
        token=token,
        body={"Operations": [{"op": "replace", "path": "displayName", "value": "Ana B"}]},
    )
    call(base, "DELETE", f"/scim/v2/Users/{a['id']}", token=token)
    entries = [
        (e["actor"], e["event"], e["object"], e["detail"]["method"])
        for e in log.entries()
        if e["event"] == "scim.write"
    ]
    assert entries == [(f"scim:{live.token_id}", "scim.write", a["id"], m) for m in ("POST", "PATCH", "DELETE")]
    assert [e for e in log.entries() if e["event"] == "scim.write"][1]["detail"]["changed"] == ["displayName"]
    text = "".join(p.read_text(encoding="utf-8") for p in log.root.glob("*.jsonl"))
    assert token not in text and "Ana B" not in text, "attribute names and active alone, never other values"
    examined(3, "a create, a change, a delete")


def test_a_deleted_user_leaves_a_tombstone_with_its_external_id_and_the_token(scim_console, examined):
    from onetrace_console import scim

    base, root, token = scim_console
    _s, a, _h = call(base, "POST", "/scim/v2/Users", token=token, body=_user(1))
    call(base, "DELETE", f"/scim/v2/Users/{a['id']}", token=token)
    (live,) = scim.TokenStore(root).live()
    stone = scim.Users(root).tombstone("00000001-0000-4000-8000-000000000000")
    assert stone is not None and stone["token"] == live.token_id and stone["id"] == a["id"]
    examined(1, "a tombstone")


def test_a_list_s_count_is_capped_at_max_results(scim_console, monkeypatch, examined):
    from onetrace_console.serve import Handler

    base, _root, token = scim_console
    monkeypatch.setattr(Handler, "config", scim_config(max_results=2))
    for n in range(1, 4):
        call(base, "POST", "/scim/v2/Users", token=token, body=_user(n))
    _s, page, _h = call(base, "GET", "/scim/v2/Users?count=50", token=token)
    assert page["totalResults"] == 3 and page["itemsPerPage"] == 2
    _s, second, _h = call(base, "GET", "/scim/v2/Users?startIndex=3&count=2", token=token)
    assert second["startIndex"] == 3 and second["itemsPerPage"] == 1
    examined(2, "a capped page, the last page")


def test_a_request_from_outside_allowed_sources_answers_as_an_unknown_route(scim_console, monkeypatch, examined):
    from onetrace_console.serve import Handler

    base, _root, token = scim_console
    monkeypatch.setattr(Handler, "config", scim_config(allowed_sources=["192.0.2.0/24"]))
    before = Handler.scim_refused_sources
    assert call(base, "GET", "/scim/v2/Users", token=token)[:2] == (404, b"no such route\n")
    assert Handler.scim_refused_sources == before + 1
    monkeypatch.setattr(Handler, "config", scim_config(allowed_sources=["127.0.0.0/8"]))
    assert call(base, "GET", "/scim/v2/Users", token=token)[0] == 200
    examined(2, "outside the list, inside it")
