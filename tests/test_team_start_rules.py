"""What a console with `teams` needs at start:

- with the console's own accounts (`sign_in.method` `local`) it refuses to start, naming both keys: a local account
  cannot be in a team;
- with sign-in off it starts, and the start-up line says teams scope nothing while sign-in is off: this machine's user
  reads every team;
- with no live ingester token, delivery is open to any caller and no token names a team, so it refuses to start,
  naming both; a folder console names its team by `folder_team` instead, and starts.

Each configuration here also holds what the other rules ask (the audit log on, a token bound to a team), so each test
holds one rule at a time.
"""

from __future__ import annotations

import pytest

from tests.test_audit_log import second  # noqa: F401 - a fixture, requested by name
from tests.test_scim_token import CLIENT
from tests.test_scim_users import TENANT
from tests.test_team_assignment import TEAMS, A, _body, _cli, _refused, _serve


@pytest.fixture
def audit_on(second):  # noqa: F811
    return {"enabled": True, "head_location": (second / "heads.jsonl").as_posix()}


def _oidc() -> dict:
    return {
        "enabled": True,
        "method": "oidc",
        "public_url": "https://onetrace.example.org",
        "oidc": {"tenant_id": TENANT, "client_id": CLIENT, "client_secret_env": "ONETRACE_ENTRA_SECRET"},
    }


def _with_token(tmp_path, monkeypatch, body: dict) -> None:
    assert _cli(tmp_path, monkeypatch, body, "token", "create", "ci", "--team", A) == 0


def test_teams_with_the_console_s_own_accounts_refuses_to_start_naming_both_keys(
    tmp_path, monkeypatch, capsys, audit_on, examined
):
    body = _body(
        tmp_path, teams=TEAMS, audit=audit_on, sign_in={"enabled": True, "insecure_cookie_for_local_dev": True}
    )
    _with_token(tmp_path, monkeypatch, body)
    capsys.readouterr()
    assert _serve(tmp_path, monkeypatch, body) == 1
    err = _refused(capsys)
    assert "teams" in err and "sign_in.method" in err and "local" in err
    examined(1, "start refused")


def test_teams_with_entra_id_sign_in_starts(tmp_path, monkeypatch, capsys, audit_on, examined):
    monkeypatch.setenv("ONETRACE_ENTRA_SECRET", "not-a-real-secret")
    body = _body(tmp_path, teams=TEAMS, audit=audit_on, sign_in=_oidc())
    _with_token(tmp_path, monkeypatch, body)
    assert _serve(tmp_path, monkeypatch, body) == -1, capsys.readouterr().err
    examined(1, "start")


def test_teams_with_sign_in_off_starts_and_says_teams_scope_nothing(tmp_path, monkeypatch, capsys, audit_on, examined):
    from onetrace_console.team_assign import SIGN_IN_OFF

    body = _body(tmp_path, teams=TEAMS, audit=audit_on, sign_in={"enabled": False})
    _with_token(tmp_path, monkeypatch, body)
    capsys.readouterr()
    assert _serve(tmp_path, monkeypatch, body) == -1
    err = capsys.readouterr().err
    assert SIGN_IN_OFF in err and "teams scope nothing" in SIGN_IN_OFF and "every team" in SIGN_IN_OFF
    examined(1, "start-up line")


def test_teams_with_no_live_ingester_token_refuses_to_start_naming_both(
    tmp_path, monkeypatch, capsys, audit_on, examined
):
    monkeypatch.setenv("ONETRACE_ENTRA_SECRET", "not-a-real-secret")
    body = _body(tmp_path, teams=TEAMS, audit=audit_on, sign_in=_oidc())
    assert _serve(tmp_path, monkeypatch, body) == 1
    err = _refused(capsys)
    assert "teams" in err and "ingester token" in err and "token create" in err and "folder_team" in err
    #: A token made, then revoked: none live, refused the same.
    _with_token(tmp_path, monkeypatch, body)
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    store = TokenStore(tmp_path / "data" / TOKENS_DIRNAME)
    for r in store.records():
        store.revoke(r.token_id)
    capsys.readouterr()
    assert _serve(tmp_path, monkeypatch, body) == 1
    assert "ingester token" in _refused(capsys)
    examined(2, "starts refused")
