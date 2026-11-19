"""The SCIM token and SCIM's start:

- `scim token create` prints the token once and stores a hash; its id shares no bits with its value; it expires at
  its stated day and then reads as unknown; `--days` over `scim.token_max_days` is refused; at most two are live; it is
  recorded as `scim.token.created` with its expiry, and its revoke as `scim.token.revoked`;
- the console refuses to start with `scim.token_max_days` over 365, naming the key and the limit;
- SCIM refuses to turn on in local or public mode, without TLS on a non-loopback host, with `sign_in.method` `local`
  (naming both keys), and with `sign_in.enabled` false; and `/scim/v2/*` refuses a request with no SCIM token on a
  console whose role check lets everything through;
- with SCIM on, `admin sessions end` refuses an Entra ID key SCIM's records do not hold, and takes one they hold.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from tests.test_audit_log import second  # noqa: F401 - a fixture, requested by name
from tests.test_scim_users import TENANT, call, scim_config

CLIENT = "11111111-2222-4333-8444-555555555555"


def _file(tmp_path, monkeypatch, **top) -> dict:
    from onetrace_console.config import ENV_VAR

    body = {
        "store_root": (tmp_path / "data").as_posix(),
        "sign_in": {
            "enabled": True,
            "method": "oidc",
            "public_url": "https://onetrace.example.org",
            "oidc": {"tenant_id": TENANT, "client_id": CLIENT, "client_secret_env": "ONETRACE_ENTRA_SECRET"},
        },
        "scim": {"enabled": True},
        **top,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    monkeypatch.setenv("ONETRACE_ENTRA_SECRET", "not-a-real-secret")
    return body


def _cli(*argv) -> int:
    from onetrace_console.__main__ import main as cli_main

    return cli_main(list(argv))


def test_scim_token_create_prints_once_and_stores_a_hash(tmp_path, monkeypatch, capsys, examined):
    import hashlib

    from onetrace_console import scim

    _file(tmp_path, monkeypatch)
    assert _cli("scim", "token", "create") == 0
    out = capsys.readouterr().out
    token_id = out.split("SCIM token id: ")[1].split()[0]
    raw = out.split("Secret Token field now): ")[1].split()[0]
    folder = tmp_path / "data" / "scim" / "tokens"
    (kept,) = list(folder.iterdir())
    text = kept.read_text(encoding="utf-8")
    assert raw not in text and json.loads(text)["sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert kept.name == f"{token_id}.json"
    assert scim.TokenStore(tmp_path / "data").find(raw).token_id == token_id
    assert len(raw) >= 43, "256 random bits"
    examined(1, "a SCIM token made")


def test_a_token_s_id_shares_no_bits_with_its_value(tmp_path, examined):
    from onetrace_console import scim

    tokens = scim.TokenStore(tmp_path)
    made = [tokens.create(90) for _ in range(20)]
    for token, raw in made:
        assert token.token_id not in raw and raw[:8] not in token.token_id
        assert token.token_id != __import__("hashlib").sha256(raw.encode()).hexdigest()[:32]
    examined(len(made), "tokens made, each id apart from its value")


def test_a_token_expires_at_its_stated_day_and_then_reads_as_unknown(tmp_path, examined):
    from onetrace_console import scim

    tokens = scim.TokenStore(tmp_path)
    made_at = datetime(2026, 1, 1, tzinfo=UTC)
    token, raw = tokens.create(30, now=made_at)
    assert token.expires_at == "2026-01-31T00:00:00Z"
    assert token.live(made_at + timedelta(days=29, hours=23))
    assert not token.live(made_at + timedelta(days=30))
    assert tokens.find(raw) is None, "made in the past, so expired now: it reads as unknown"
    examined(3, "a token before, at and after its expiry")


def test_days_over_token_max_days_are_refused_and_at_most_two_are_live(tmp_path, monkeypatch, capsys, examined):
    _file(tmp_path, monkeypatch, scim={"enabled": True, "token_max_days": 30})
    assert _cli("scim", "token", "create", "--days", "31") == 1
    assert "over scim.token_max_days (30)" in capsys.readouterr().err
    assert _cli("scim", "token", "create", "--days", "0") == 1
    assert _cli("scim", "token", "create", "--days", "30") == 0
    assert _cli("scim", "token", "create", "--days", "7") == 0
    assert _cli("scim", "token", "create", "--days", "7") == 1
    assert "2 SCIM tokens are live already" in capsys.readouterr().err
    examined(5, "31 days, 0 days, 30, 7, and a third")


def test_scim_token_created_and_revoked_are_recorded_by_id_never_by_value(
    tmp_path,
    monkeypatch,
    capsys,
    second,
    examined,  # noqa: F811
):
    from onetrace_console.audit import AuditLog

    heads = second / "heads.jsonl"
    _file(tmp_path, monkeypatch, audit={"enabled": True, "head_location": heads.as_posix()})
    assert _cli("scim", "token", "create", "--days", "14") == 0
    out = capsys.readouterr().out
    token_id = out.split("SCIM token id: ")[1].split()[0]
    raw = out.split("Secret Token field now): ")[1].split()[0]
    assert _cli("scim", "token", "revoke", token_id) == 0
    log = AuditLog(tmp_path / "data" / "audit_log", head_location=heads)
    entries = [(e["actor"], e["event"], e["object"]) for e in log.entries()]
    assert entries == [("cli", "scim.token.created", token_id), ("cli", "scim.token.revoked", token_id)]
    assert log.entries()[0]["detail"]["days"] == 14 and log.entries()[0]["detail"]["expires"].endswith("Z")
    assert raw not in "".join(p.read_text(encoding="utf-8") for p in log.root.glob("*.jsonl"))
    examined(2, "a SCIM token made and revoked")


def test_scim_token_create_is_refused_with_scim_off(tmp_path, monkeypatch, capsys, examined):
    _file(tmp_path, monkeypatch, scim={"enabled": False})
    assert _cli("scim", "token", "create") == 1
    assert "scim.enabled is false" in capsys.readouterr().err
    examined(1, "scim off")


# ------------------------------------------------------------------ the start


@pytest.mark.parametrize("days", [366, 1000, 0, "90"])
def test_the_console_refuses_to_start_with_token_max_days_over_365_naming_the_key_and_the_limit(
    tmp_path, days, examined
):
    from onetrace_console.config import ConfigError, load

    path = tmp_path / "c.json"
    path.write_text(json.dumps({"scim": {"token_max_days": days}}), encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        load(path)
    assert "scim.token_max_days" in str(e.value) and "at most 365" in str(e.value), str(e.value)
    examined(1, f"token_max_days {days!r}")


def test_token_max_days_of_365_loads(tmp_path, examined):
    from onetrace_console.config import load

    path = tmp_path / "c.json"
    path.write_text(json.dumps({"scim": {"token_max_days": 365}}), encoding="utf-8")
    assert load(path).scim["token_max_days"] == 365
    examined(1, "token_max_days 365")


def _serve(tmp_path, monkeypatch, body: dict, capsys) -> tuple[int, str]:
    from tests.test_team_assignment import _serve as serve

    got = serve(tmp_path, monkeypatch, body)
    return got, capsys.readouterr().err


def test_scim_refuses_to_start_with_local_sign_in_naming_both_keys(tmp_path, monkeypatch, capsys, examined):
    body = {
        "store_root": (tmp_path / "data").as_posix(),
        "host": "127.0.0.1",
        "sign_in": {"enabled": True},
        "scim": {"enabled": True},
    }
    got, err = _serve(tmp_path, monkeypatch, body, capsys)
    assert got == 1 and "scim.enabled is true and sign_in.method is local" in err, err
    examined(1, "scim on, local sign-in")


def test_scim_refuses_to_start_with_sign_in_off(tmp_path, monkeypatch, capsys, examined):
    body = {
        "store_root": (tmp_path / "data").as_posix(),
        "host": "127.0.0.1",
        "sign_in": {"enabled": False},
        "scim": {"enabled": True},
    }
    got, err = _serve(tmp_path, monkeypatch, body, capsys)
    assert got == 1 and "scim.enabled is true and sign_in.enabled is false" in err, err
    examined(1, "scim on, sign-in off")


def test_scim_refuses_to_start_on_a_public_console(tmp_path, examined):
    from dataclasses import replace

    from onetrace_console import scim

    refused = scim.start_refusal(replace(scim_config(), public=True), local=False)
    assert refused is not None and "public is true" in refused[0]
    examined(1, "scim on, public")


def test_scim_refuses_to_start_in_local_mode(tmp_path, examined):
    from onetrace_console import scim

    refused = scim.start_refusal(scim_config(), local=True)
    assert refused is not None and "local mode" in refused[0]
    examined(1, "scim on, local mode")


def test_scim_refuses_to_start_without_tls_on_a_non_loopback_host(tmp_path, monkeypatch, capsys, examined):
    body = _file(tmp_path, monkeypatch)
    got, err = _serve(tmp_path, monkeypatch, {**body, "host": "0.0.0.0"}, capsys)
    assert got == 1 and "refusing to start" in err and ("TLS" in err or "tls" in err), err
    examined(1, "scim on, 0.0.0.0 without TLS")


def test_scim_refuses_another_tenant_than_sign_in_s(tmp_path, examined):
    from onetrace_console import scim

    refused = scim.start_refusal(scim_config(tenant_id="99999999-2222-4333-8444-555555555555"), local=False)
    assert refused is not None and "scim.tenant_id" in refused[0] and "sign_in.oidc.tenant_id" in refused[0]
    assert scim.start_refusal(scim_config(tenant_id=TENANT.upper()), local=False) is None
    examined(2, "another tenant, the same one in capitals")


def test_scim_s_own_token_check_stands_before_a_role_check_that_lets_everything_through(
    tmp_path, monkeypatch, examined
):
    """A console with sign-in off lets every route through its role check; `/scim/v2/*` still asks for its token."""
    from dataclasses import replace

    from onetrace_console.serve import Handler
    from tests.conftest import serving

    with serving(tmp_path) as (base, _root):
        open_config = replace(scim_config(), sign_in={**scim_config().sign_in, "enabled": False})
        monkeypatch.setattr(Handler, "config", open_config)
        assert call(base, "GET", "/home.html")[0] == 200, "the role check lets a page through"
        assert call(base, "GET", "/scim/v2/Users")[0] == 401
    examined(2, "a page, and SCIM, on a console with sign-in off")


# ------------------------------------------------------------------ admin sessions end, with SCIM on


def test_with_scim_on_admin_sessions_end_refuses_a_key_scim_does_not_hold(tmp_path, monkeypatch, capsys, examined):
    from onetrace_console import scim

    _file(tmp_path, monkeypatch)
    held = "00000001-0000-4000-8000-000000000000"
    users = scim.Users(tmp_path / "data")
    users.put(scim.user_from({"userName": "ana", "externalId": held, "active": False}, user_id="a" * 32))
    gone = "00000002-0000-4000-8000-000000000000"
    users.put(scim.user_from({"userName": "bo", "externalId": gone}, user_id="b" * 32))
    users.delete(users.get("b" * 32), "t" * 32)
    assert _cli("admin", "sessions", "end", f"{TENANT}/{held}") == 0, "an inactive User's"
    assert _cli("admin", "sessions", "end", f"{TENANT}/{gone.upper()}") == 0, "a deleted User's"
    capsys.readouterr()
    assert _cli("admin", "sessions", "end", f"{TENANT}/00000003-0000-4000-8000-000000000000") == 1
    assert "SCIM's records hold no User" in capsys.readouterr().err
    examined(3, "an inactive User's key, a deleted one's, one never held")
