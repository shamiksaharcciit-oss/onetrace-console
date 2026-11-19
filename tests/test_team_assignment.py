"""Assignment on arrival: with `teams` configured, a run's team is its delivering token's, or its
watched folder's, and nothing the uploader writes picks it.

- a team-bound ingester token assigns its runs; a delivery with no token bound to a team is refused, nothing stored;
- `token create` without `--team` is refused with teams, and with a team the configuration does not hold, or one
  outside the name rule; `--team` is refused without teams;
- a live token bound to no team, or to a team the configuration does not hold, stops the console from starting,
  naming the token's id and the commands that replace it;
- a configuration file with a label or a run id rule is refused as holding an unknown key;
- the key team B receives for a run equals the key B would receive on an empty store, whether or not team A holds it;
- one run delivered by two teams' tokens is held once per team, each answer a first delivery, neither flagged
  "run_id reused"; a run keyed by its folder is keyed with its team too;
- a `teams` key, a `folder_team` and a token's team outside the name rule each refuse start, naming the key; a
  name of 63 characters starts; a `folder_team` naming a team the configuration does not hold refuses start;
- a held run with no team stops the console from starting, saying how many and the command that assigns them.
"""

from __future__ import annotations

import json
import re
import socket

import pytest

from onetrace_console.store import TEAM_NAME

A, B = "alpha", "beta"
TEAMS = {A: {"role_claim": "Team.Alpha"}, B: {"role_claim": "Team.Beta"}}
#: The names the team name rule refuses, and the longest it takes.
BAD_NAMES = ("Payments", "9x", "a_b", "a" * 64)
LONGEST = "a" + "b" * 62


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


#: Sign-in through Entra ID, as a console with teams needs (a local account cannot be in a team). The
#: tenant and client are invented; nothing is asked of Entra ID at start.
ENTRA_SIGN_IN = {
    "enabled": True,
    "method": "oidc",
    "public_url": "https://onetrace.example.org",
    "oidc": {
        "tenant_id": "0f1e2d3c-4b5a-4968-8778-695a4b3c2d1e",
        "client_id": "11111111-2222-4333-8444-555555555555",
        "client_secret_env": "ONETRACE_ENTRA_SECRET",
    },
}


def _body(tmp_path, **more) -> dict:
    return {
        "store_root": (tmp_path / "data").as_posix(),
        "host": "127.0.0.1",
        "port": _port(),
        "sign_in": ENTRA_SIGN_IN,
        **more,
    }


class Served(Exception):
    """The console got as far as serving."""


def _audit_on(tmp_path, monkeypatch) -> dict:
    """The audit log on, its heads in a folder read as a second volume (as `test_audit_log.second`): a console with teams
    or SCIM needs it."""
    from pathlib import Path

    from onetrace_console import audit

    folder = tmp_path / "second-volume"
    folder.mkdir(exist_ok=True)
    real = audit.device_of

    def device_of(path):
        p = Path(path).resolve()
        return -1 if p == folder or folder in p.parents else real(path)

    monkeypatch.setattr(audit, "device_of", device_of)
    return {"enabled": True, "head_location": (folder / "heads.jsonl").as_posix()}


def _serve(tmp_path, monkeypatch, body: dict, prepare=None) -> int:
    """Start the console on `body` until it would serve: -1 where it got that far, else its exit status. A body with
    teams or SCIM and no `audit` of its own gets the audit log on; a test of the log off names it off."""
    from onetrace_console import serve
    from onetrace_console.config import ENV_VAR

    if (body.get("teams") or (body.get("scim") or {}).get("enabled")) and "audit" not in body:
        body = {**body, "audit": _audit_on(tmp_path, monkeypatch)}

    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    monkeypatch.setenv("ONETRACE_ENTRA_SECRET", "not-a-real-secret")
    #: `main` sets the server's class attributes (its audit log among them); each is put back after the test, so a
    #: console started here leaves nothing behind for the next test to meet.
    for name in [n for n in vars(serve.Handler) if not n.startswith("__") and not callable(vars(serve.Handler)[n])]:
        monkeypatch.setattr(serve.Handler, name, vars(serve.Handler)[name])

    def listened(self):
        raise Served

    monkeypatch.setattr(serve.ConsoleServer, "serve_forever", listened)
    try:
        return serve.main([], prepare=prepare)
    except Served:
        return -1


def _refused(capsys) -> str:
    err = capsys.readouterr().err
    assert "refusing to start: " in err and "\nfix: " in err and "Traceback" not in err, err
    return err


# ------------------------------------------------------------------ tokens


def _cli(tmp_path, monkeypatch, body: dict, *argv: str) -> int:
    from onetrace_console.__main__ import main as cli_main
    from onetrace_console.config import ENV_VAR

    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    return cli_main(list(argv))


def test_token_create_binds_a_team_and_is_refused_without_one_where_teams_is_configured(
    tmp_path, monkeypatch, capsys, examined
):
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    body = _body(tmp_path, teams=TEAMS)
    assert _cli(tmp_path, monkeypatch, body, "token", "create", "ci", "--team", B) == 0
    out = capsys.readouterr().out
    raw = next(line.split(": ", 1)[1] for line in out.splitlines() if line.startswith("token (shown once"))
    assert "team: beta" in out
    record = TokenStore(tmp_path / "data" / TOKENS_DIRNAME).record_for(raw)
    assert record is not None and record.team == B
    for argv, said in (
        (("ci",), "teams is configured, so every ingester token is bound to one team"),
        (("ci", "--team", "gamma"), "--team is 'gamma', a team teams does not hold (it holds alpha, beta)"),
        (("ci", "--team", "Payments"), "--team is 'Payments', not a team's name"),
    ):
        assert _cli(tmp_path, monkeypatch, body, "token", "create", *argv) == 1
        assert said in capsys.readouterr().err
    assert _cli(tmp_path, monkeypatch, _body(tmp_path), "token", "create", "ci", "--team", A) == 1
    assert "teams is not configured" in capsys.readouterr().err
    assert len(TokenStore(tmp_path / "data" / TOKENS_DIRNAME).records()) == 1, "nothing made on a refusal"
    examined(5, "token create: bound, and refused four ways")


def test_a_token_made_before_teams_reads_and_writes_back_as_it_was(tmp_path, examined):
    from onetrace_console.ingester_tokens import TokenRecord, TokenStore

    tokens = TokenStore(tmp_path)
    record, _raw = tokens.create("ci")
    before = (tmp_path / f"{record.token_id}.json").read_text(encoding="utf-8")
    assert "team" not in json.loads(before) and TokenRecord.from_json(before).team == ""
    tokens.revoke(record.token_id)
    assert "team" not in json.loads((tmp_path / f"{record.token_id}.json").read_text(encoding="utf-8"))
    bound, _raw = tokens.create("ci", B)
    tokens.revoke(bound.token_id)
    assert tokens.get(bound.token_id).team == B, "a revoked token keeps its team"
    examined(3, "an unbound token's record, revoked; a bound one revoked")


@pytest.mark.parametrize("kind", ["unbound", "unheld"])
def test_a_live_token_bound_to_no_team_this_console_holds_stops_it_from_starting(
    tmp_path, monkeypatch, capsys, kind, examined
):
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    tokens = TokenStore(tmp_path / "data" / TOKENS_DIRNAME)
    bad, _raw = tokens.create("old-ci", "" if kind == "unbound" else "gamma")
    revoked, _raw = tokens.create("gone-ci")
    tokens.revoke(revoked.token_id)
    tokens.create("ci", A)
    assert _serve(tmp_path, monkeypatch, _body(tmp_path, teams=TEAMS)) == 1
    err = _refused(capsys)
    assert bad.token_id in err and revoked.token_id not in err, err
    assert f"onetrace-console token create old-ci --team <team>, then token revoke {bad.token_id}" in err
    assert ("bound to no team" if kind == "unbound" else "bound to 'gamma', a team teams does not hold") in err
    assert not list((tmp_path / "data" / "pages").rglob("*.html")), "nothing was drawn before the refusal"
    tokens.revoke(bad.token_id)
    assert _serve(tmp_path, monkeypatch, _body(tmp_path, teams=TEAMS)) == -1, capsys.readouterr().err
    examined(2, f"a live {kind} token: refused, then revoked and started")


def test_without_teams_an_unbound_token_starts_as_before(tmp_path, monkeypatch, capsys, examined):
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    TokenStore(tmp_path / "data" / TOKENS_DIRNAME).create("ci")
    assert _serve(tmp_path, monkeypatch, _body(tmp_path)) == -1, capsys.readouterr().err
    examined(1, "a console without teams, an unbound token")


# ------------------------------------------------------------------ the configuration


@pytest.mark.parametrize(
    "key",
    ["label", "labels", "run_id_prefix", "team_rules", "run_labels"],
)
def test_a_label_or_a_run_id_rule_is_refused_as_an_unknown_key(tmp_path, key, examined):
    """Revision 1's labels and rules, each written by the uploader, are not configuration: nothing the uploader
    writes picks a team."""
    from onetrace_console.config import ConfigError, load

    for data in ({key: {"x": A}, "teams": TEAMS}, {"teams": {A: {key: "x"}}}):
        path = tmp_path / "c.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ConfigError, match=re.escape(f"['{key}']")):
            load(path)
    examined(2, f"{key}: at the top and in a team's entry")


@pytest.mark.parametrize("name", BAD_NAMES)
@pytest.mark.parametrize("where", ["teams", "folder_team", "token"])
def test_a_team_name_outside_the_rule_refuses_start_naming_the_key(
    tmp_path, monkeypatch, capsys, name, where, examined
):
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    assert not TEAM_NAME.match(name)
    if where == "teams":
        body, key = _body(tmp_path, teams={**TEAMS, name: {}}), f"teams.{name} is {name!r}, not a team's name"
    elif where == "folder_team":
        body, key = _body(tmp_path, teams=TEAMS, folder_team=name), f"folder_team is {name!r}, not a team's name"
    else:
        TokenStore(tmp_path / "data" / TOKENS_DIRNAME).create("ci", name)
        body, key = _body(tmp_path, teams=TEAMS), f"is {name!r}, not a team's name"
    assert _serve(tmp_path, monkeypatch, body) == 1
    err = _refused(capsys)
    assert key in err and "a lower-case letter, then up to 62 lower-case letters, digits or hyphens" in err, err
    examined(1, f"{where} named {name[:12]}")


def test_a_team_name_of_63_characters_starts(tmp_path, monkeypatch, capsys, examined):
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    assert len(LONGEST) == 63 and TEAM_NAME.match(LONGEST)
    TokenStore(tmp_path / "data" / TOKENS_DIRNAME).create("ci", LONGEST)
    body = _body(tmp_path, teams={LONGEST: {"role_claim": "Team.Long"}}, folder_team=LONGEST)
    assert _serve(tmp_path, monkeypatch, body) == -1, capsys.readouterr().err
    examined(1, "teams, folder_team and a token's team, each 63 characters")


@pytest.mark.parametrize("teams", [TEAMS, {}])
def test_a_folder_team_naming_a_team_the_configuration_does_not_hold_refuses_start(
    tmp_path, monkeypatch, capsys, teams, examined
):
    assert _serve(tmp_path, monkeypatch, _body(tmp_path, teams=teams, folder_team="gamma")) == 1
    err = _refused(capsys)
    assert "folder_team is 'gamma', a team teams does not hold" in err, err
    examined(1, f"folder_team naming gamma, teams holding {len(teams)}")


# ------------------------------------------------------------------ keys and the delivery


def _deliver(store, data: bytes, team: str, **kw):
    from onetrace_console.ingest import Accepted, accept

    got = accept(data, store, team=team, **kw)
    assert isinstance(got, Accepted), got
    return got


def test_the_key_a_team_receives_equals_its_key_on_an_empty_store_whoever_holds_the_run(tmp_path, delivery, examined):
    from onetrace_console.store import Store, run_key

    empty = _deliver(Store(tmp_path / "empty"), delivery, B).run.key
    shared = Store(tmp_path / "shared")
    _deliver(shared, delivery, A)
    after_a = _deliver(shared, delivery, B)
    assert after_a.run.key == empty
    run = after_a.run
    assert empty == run_key(run.run_id, run.chain_head, B) != run_key(run.run_id, run.chain_head)
    assert empty != run_key(run.run_id, run.chain_head, A)
    examined(3, "B's key: on an empty store, after A's, and against the plain key")


def test_one_run_delivered_by_two_teams_is_held_once_per_team_each_a_first_delivery(tmp_path, delivery, examined):
    from onetrace_console.ingest import RUN_ID_REUSED
    from onetrace_console.store import Store

    store = Store(tmp_path / "s")
    a, b = _deliver(store, delivery, A), _deliver(store, delivery, B)
    assert a.created and b.created and a.status == b.status
    assert RUN_ID_REUSED not in a.run.flags and RUN_ID_REUSED not in b.run.flags
    assert {(r.team, r.key) for r in store.runs()} == {(A, a.run.key), (B, b.run.key)}
    again = _deliver(store, delivery, B)
    assert not again.created and again.run.key == b.run.key, "a second delivery within one team is held"
    examined(3, "two teams' first deliveries, and B's second")


def test_run_id_reused_is_read_within_the_team(tmp_path, delivery, examined):
    """A held run of another team with the same run id and another chain head flags nothing for this team."""
    from dataclasses import replace

    from onetrace_console.ingest import RUN_ID_REUSED
    from onetrace_console.store import Store

    def holding_another_chain(name: str):
        """A store holding, for team A, a run of this run's id with another chain head (and its objects)."""
        store = Store(tmp_path / name)
        held = _deliver(store, delivery, A).run
        store.put_run(replace(held, key="f" * 64, chain_head="e" * 64))
        store._run_path(held.key).unlink()
        return store

    assert RUN_ID_REUSED not in _deliver(holding_another_chain("s"), delivery, B).run.flags
    assert RUN_ID_REUSED in _deliver(holding_another_chain("s2"), delivery, A).run.flags, "within a team, a finding"
    examined(2, "another team's same id; the same team's")


def test_a_run_keyed_by_its_folder_is_keyed_with_its_team_too(tmp_path, delivery, examined):
    from onetrace_console.store import Store, folder_key

    store = Store(tmp_path / "s")
    a = _deliver(store, delivery, A, run_folder="run-1", shared_head=True).run
    b = _deliver(store, delivery, B, run_folder="run-1", shared_head=True).run
    assert a.key == folder_key(a.run_id, a.chain_head, "run-1", A)
    assert b.key == folder_key(b.run_id, b.chain_head, "run-1", B)
    assert len({a.key, b.key, folder_key(a.run_id, a.chain_head, "run-1")}) == 3
    examined(2, "one folder's run, two teams")


# ------------------------------------------------------------------ held runs with no team


def test_a_held_run_with_no_team_stops_the_console_saying_how_many_and_the_command(
    tmp_path, monkeypatch, capsys, delivery, examined
):
    from onetrace_console.store import Store

    store = Store(tmp_path / "data" / "store")
    _deliver(store, delivery, "")
    body = _body(tmp_path, teams=TEAMS)
    assert _cli(tmp_path, monkeypatch, body, "token", "create", "ci", "--team", A) == 0
    capsys.readouterr()
    assert _serve(tmp_path, monkeypatch, body) == 1
    err = _refused(capsys)
    assert "1 held run has no team" in err and "onetrace-console run assign --unassigned <team>" in err, err
    assert not list((tmp_path / "data" / "pages").rglob("*.html")), "nothing was drawn before the refusal"
    examined(1, "a held run with no team")


# ------------------------------------------------------------------ over HTTP


@pytest.fixture
def teams_console(tmp_path):
    from onetrace_console.config import Config
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME, Handler
    from tests.conftest import serving

    with serving(tmp_path) as (base, _root):
        store = Handler.store
        saved = {n: getattr(Handler, n, None) for n in ("config", "token_store")}
        Handler.config = Config(sign_in={**Config().sign_in, "enabled": True}, teams=TEAMS)
        Handler.token_store = TokenStore(tmp_path / "tokens" / TOKENS_DIRNAME)
        _rec, raw_b = Handler.token_store.create("ci-b", B)
        _rec, raw_none = Handler.token_store.create("ci-old")
        try:
            yield base, store, raw_b, raw_none
        finally:
            for n, v in saved.items():
                setattr(Handler, n, v)


def test_a_team_bound_token_assigns_the_runs_it_delivers(teams_console, delivery, examined):
    import json as _json

    from tests.test_signin_flow import _post

    base, store, raw_b, raw_none = teams_console
    status, body, _h, _ = _post(base, "/v1/runs", delivery, headers={"Authorization": f"Bearer {raw_b}"})
    assert status == 200 and _json.loads(body)["accepted"] is True
    assert [r.team for r in store.runs()] == [B]
    try:
        status, body, _h, _ = _post(base, "/v1/runs", delivery, headers={"Authorization": f"Bearer {raw_none}"})
    except Exception as e:  # urllib raises on 4xx
        status, body = e.code, e.read()
    assert status == 403 and "bound to its team" in _json.loads(body)["body"]
    assert len(store.runs()) == 1, "nothing stored for a token bound to no team"
    examined(2, "a bound token's delivery; an unbound one's")
