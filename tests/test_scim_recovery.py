"""The way back in, on the console's machine:

- `scim user activate <externalId>` sets that User active, writes `scim.user.activated` with actor `cli`, and is
  refused when its append fails, saying so;
- `scim enforcement off` admits an Entra ID sign-in on 0.8.0's rule with no team from SCIM; the start-up line says it
  is off and since when; `scim enforcement on` restores the join; each writes `scim.enforcement.changed` with actor
  `cli`; with every User inactive, a session admitted while it is off survives its first request and its second; a
  deprovisioning while it is off still ends that person's sessions;
- `scim enforcement on` while the audit log cannot be appended to applies: the join and the per-request check are
  back at the next request, the failure is said on the error stream and the start-up line, and recorded by
  `audit.append_failed` once appends work again.
"""

from __future__ import annotations

import json

import pytest

from tests.fake_entra import TENANT
from tests.test_audit_log import second  # noqa: F401 - a fixture, requested by name
from tests.test_entra_flow import entra, sign_in  # noqa: F401 - a fixture, requested by name
from tests.test_scim_teams import OID, _try, _user, directory  # noqa: F401 - a fixture, requested by name
from tests.test_scim_users import call


@pytest.fixture
def machine(directory, monkeypatch, tmp_path, second):  # noqa: F811
    """`directory`'s console, with a configuration file naming its store and an audit log on a second volume, for the
    commands run on the machine: (base, fake, store root, token, the console's log)."""
    from onetrace_console.audit import Audit, AuditLog
    from onetrace_console.config import ENV_VAR
    from onetrace_console.serve import Handler

    base, fake, root, token, _log = directory
    heads = second / "heads.jsonl"
    body = {
        "store_root": str(root),
        "sign_in": {
            "enabled": True,
            "method": "oidc",
            "public_url": base,
            "oidc": {
                "tenant_id": TENANT,
                "client_id": "22222222-3333-4444-5555-666666666666",
                "client_secret_env": "X",
            },
        },
        "scim": {"enabled": True},
        "audit": {"enabled": True, "head_location": heads.as_posix()},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    log = AuditLog(root / "audit_log", head_location=heads)
    monkeypatch.setattr(Handler, "audit", Audit(log))
    return base, fake, root, token, log


def _cli(*argv) -> int:
    from onetrace_console.__main__ import main as cli_main

    return cli_main(list(argv))


def test_scim_user_activate_sets_the_user_active_and_is_recorded_by_the_command_line(machine, capsys, examined):
    from onetrace_console import scim

    base, fake, root, token, log = machine
    me = _user(token, base, active=False)
    assert sign_in(base, fake)[0] == 403
    assert _cli("scim", "user", "activate", OID.upper()) == 0
    assert scim.Users(root).get(me["id"])["active"] is True
    assert sign_in(base, fake)[0] == 200
    (entry,) = [e for e in log.entries() if e["event"] == "scim.user.activated"]
    assert entry["actor"] == "cli" and entry["object"] == me["id"]
    assert entry["detail"] == {"externalId": OID, "was_inactive": True}
    assert _cli("scim", "user", "activate", "00000000-0000-4000-8000-000000000000") == 1
    examined(2, "an inactive User activated; one not held")


def test_scim_user_activate_is_refused_when_its_append_fails(machine, capsys, examined):
    from onetrace_console import scim

    base, _fake, root, token, log = machine
    me = _user(token, base, active=False)
    log.head_location.unlink(missing_ok=True)
    log.head_location.mkdir()
    assert _cli("scim", "user", "activate", OID) == 1
    assert "could not record it" in capsys.readouterr().err
    assert scim.Users(root).get(me["id"])["active"] is False, "a grant is never made unrecorded"
    examined(1, "an activate with the log failing")


def test_enforcement_off_admits_on_the_app_roles_alone_with_no_team_and_on_restores_the_join(machine, capsys, examined):
    from tests.test_scim_teams import _teams_now

    base, fake, _root, token, log = machine
    assert sign_in(base, fake)[0] == 403, "the join: never provisioned"
    assert _cli("scim", "enforcement", "off") == 0
    status, _page, _h, session, _c = sign_in(base, fake)
    assert status == 200 and session
    assert _teams_now(base, session) == [], "no team from SCIM, and a role claim grants none"
    assert _cli("scim", "enforcement", "on") == 0
    assert sign_in(base, fake)[0] == 403, "the join again"
    changes = [(e["actor"], e["detail"]) for e in log.entries() if e["event"] == "scim.enforcement.changed"]
    assert changes == [("cli", {"enforcement": "off"}), ("cli", {"enforcement": "on"})]
    examined(3, "refused, admitted while off, refused again")


def test_with_every_user_inactive_a_session_admitted_while_off_survives_its_first_and_second_request(machine, examined):
    base, fake, _root, token, _log = machine
    _user(token, base, active=False)
    assert _cli("scim", "enforcement", "off") == 0
    session = sign_in(base, fake)[3]
    assert _try(base, "/home.html", session)[0] != 303
    assert _try(base, "/home.html", session)[0] != 303, "the active check is suspended too: still signed in"
    assert _cli("scim", "enforcement", "on") == 0
    assert _try(base, "/home.html", session)[0] == 303, "and back at the next request once on"
    examined(3, "two requests while off; one after on")


def test_a_deprovisioning_while_enforcement_is_off_still_ends_that_person_s_sessions(machine, examined):
    from onetrace_console.serve import Handler

    base, fake, _root, token, _log = machine
    me = _user(token, base)
    assert _cli("scim", "enforcement", "off") == 0
    session = sign_in(base, fake)[3]
    call(
        base,
        "PATCH",
        f"/scim/v2/Users/{me['id']}",
        token=token,
        body={"Operations": [{"op": "Replace", "path": "active", "value": "False"}]},
    )
    assert Handler.session_store.sessions_of(f"{TENANT}/{OID}") == set()
    assert _try(base, "/home.html", session)[0] == 303
    examined(1, "a deprovisioning while off")


def test_the_start_up_line_says_enforcement_is_off_and_since_when(machine, tmp_path, monkeypatch, capsys, examined):
    from onetrace_console import scim

    base, _fake, root, _token, _log = machine
    assert _cli("scim", "enforcement", "off") == 0
    _on, since = scim.enforcement(root)
    from tests.test_team_assignment import _serve

    body = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    body.update(host="127.0.0.1", port=__import__("tests.test_team_assignment", fromlist=["_port"])._port())
    body["sign_in"] = {**body["sign_in"], "public_url": "https://onetrace.example.org"}
    monkeypatch.setenv("X", "not-a-real-secret")
    capsys.readouterr()
    _serve(tmp_path, monkeypatch, body)
    err = capsys.readouterr().err
    assert f"SCIM's enforcement of sign-in is off, since {since}" in err, err
    examined(1, "a start with enforcement off")


def test_enforcement_on_while_the_audit_log_cannot_be_appended_to_applies_and_is_recorded_after(
    machine, capsys, examined
):
    base, fake, _root, token, log = machine
    assert _cli("scim", "enforcement", "off") == 0
    session = sign_in(base, fake)[3]
    assert _try(base, "/home.html", session)[0] != 303
    log.head_location.unlink()
    log.head_location.mkdir()
    assert _cli("scim", "enforcement", "on") == 0
    err = capsys.readouterr().err
    assert "scim.enforcement.changed was not recorded" in err and "applied anyway" in err, err
    assert _try(base, "/home.html", session)[0] == 303, "the active check is back at the next request"
    assert sign_in(base, fake)[0] == 403, "and the join"
    from onetrace_console.audit import Audit, start_line

    assert "not recorded since" in start_line(Audit(log))
    log.head_location.rmdir()
    log.append("cli", "audit.checkpoint", "log", {})
    failed = [e for e in log.entries() if e["event"] == "audit.append_failed"]
    assert failed and failed[-1]["detail"]["not_recorded"].get("scim.enforcement.changed") == 1
    examined(1, "enforcement on with the log failing")


def test_enforcement_off_is_refused_when_its_append_fails(machine, capsys, examined):
    from onetrace_console import scim

    base, _fake, root, _token, log = machine
    log.head_location.unlink(missing_ok=True)
    log.head_location.mkdir()
    assert _cli("scim", "enforcement", "off") == 1
    assert "could not record it" in capsys.readouterr().err
    assert scim.enforcement(root)[0] is True
    examined(1, "enforcement off with the log failing")
