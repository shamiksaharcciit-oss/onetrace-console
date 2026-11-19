"""`run assign`: runs held before `teams` was configured are given one, and a run is moved
between teams, each keyed with its team.

On a copy of the public demo, whose runs have no team:

- `run assign --unassigned <team>` gives every run with no team that team, keys each with it, keeps the map from old
  key to new, and the console then starts; what was kept by a run's key, and the comparisons naming it, follow it;
- it is refused without teams, for a team the configuration does not hold, and while the console is listening;
- `run assign <run key> <team>` moves a run's pages from one team's set to the other's;
- a run's old page address redirects for a person in its team, and answers anyone else with the bytes a run that
  does not exist gets;
- every assignment produces one `run.assigned` entry, actor `cli`, with both keys, the teams and the rule; where
  the entry cannot be appended, the run is not moved.
"""

from __future__ import annotations

import json
import socket
import time

import pytest

from tests.test_audit_log import second  # noqa: F401 - a fixture, requested by name
from tests.test_team_assignment import TEAMS, A, B, _port

_HEX64 = r"[0-9a-f]{64}"


def _configure(monkeypatch, tmp_path, store_root, **more) -> dict:
    from onetrace_console.config import ENV_VAR

    body = {"store_root": store_root.as_posix(), "host": "127.0.0.1", "port": _port(), "teams": TEAMS, **more}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    return body


def _cli(*argv) -> int:
    from onetrace_console.__main__ import main as cli_main

    return cli_main(["run", "assign", *argv])


@pytest.fixture
def unassigned(shared_demo, tmp_path):
    """A copy of the demo, every run with no team: (its store root, its store)."""
    from onetrace_console.store import Store
    from tests.conftest import demo_copy

    folder = demo_copy(shared_demo, tmp_path / "demo")
    store = Store(folder / "store" / "store")
    assert store.runs() and not any(r.team for r in store.runs())
    return folder / "store", store


def test_run_assign_unassigned_gives_every_run_the_team_keyed_with_it(
    unassigned, tmp_path, monkeypatch, capsys, examined
):
    from onetrace_console.store import Store, folder_key, run_key

    root, store = unassigned
    before = {r.key: r for r in store.runs()}
    _configure(monkeypatch, tmp_path, root)
    assert _cli("--unassigned", B) == 0
    out = capsys.readouterr().out
    after = Store(root / "store")
    runs = after.runs()
    assert len(runs) == len(before) and all(r.team == B for r in runs)
    for old, run in before.items():
        plain = run.key == run_key(run.run_id, run.chain_head)
        want = (
            run_key(run.run_id, run.chain_head, B) if plain else folder_key(run.run_id, run.chain_head, run.folder, B)
        )
        assert after.get_run(want) is not None and after.get_run(old) is None
        assert after.moved_to(old) == want, "the map keeps the old key and the new"
        assert f"{old} -> {want}: no team -> beta" in out
    assert f"{len(before)} runs given to beta" in out
    examined(len(before), "the demo's runs, each given beta and keyed with it")


def test_what_is_kept_by_a_run_s_key_and_the_comparisons_naming_it_follow_it(
    unassigned, tmp_path, monkeypatch, examined
):
    from onetrace_console.store import Store

    root, store = unassigned
    data = root / "store"
    owned = {
        f: sorted(p.name.split(".", 1)[0] for p in (data / f).iterdir())
        for f, whose in Store.OWNED_FOLDERS.items()
        if whose == "run" and (data / f).is_dir()
    }
    compared = [(c.key, c.run_a, c.run_b) for c in store.comparisons()]
    assert compared and any(owned.values()), "the demo keeps something by a run's key, and compares"
    _configure(monkeypatch, tmp_path, root)
    assert _cli("--unassigned", A) == 0
    after = Store(data)
    for folder, keys in owned.items():
        now = sorted(p.name.split(".", 1)[0] for p in (data / folder).iterdir())
        assert now == sorted(after.moved_to(k) for k in keys), folder
    for key, a, b in compared:
        c = after.get_comparison(key)
        assert (c.run_a, c.run_b) == (after.moved_to(a), after.moved_to(b))
    for folder in ("comparisons", "drift", *Store.KEPT_KINDS):
        for p in (data / folder).glob("*.json") if (data / folder).is_dir() else ():
            assert not any(k in p.read_text(encoding="utf-8") for k in after_keys_before(owned, compared)), p
    examined(len(compared) + sum(map(len, owned.values())), "comparisons and kept files, each following its run")


def after_keys_before(owned, compared) -> set[str]:
    return {k for keys in owned.values() for k in keys} | {k for _c, a, b in compared for k in (a, b)}


def test_after_run_assign_the_console_starts_and_draws_each_run_in_its_team_s_set(
    unassigned, tmp_path, monkeypatch, capsys, examined
):
    from onetrace_console.serve import PAGES_DIRNAME, team_set
    from onetrace_console.store import Store
    from tests.test_team_assignment import _serve

    root, _store = unassigned
    body = _configure(monkeypatch, tmp_path, root)
    assert _cli("--unassigned", A) == 0
    capsys.readouterr()
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    TokenStore(root / TOKENS_DIRNAME).create("ci", team=A)  # a console with teams needs a live token
    assert _serve(tmp_path, monkeypatch, {**body, "sign_in": {"enabled": False}}) == -1, capsys.readouterr().err
    keys = {r.key for r in Store(root / "store").runs()}
    drawn = (
        {p.name for p in (team_set(root, A).pages / "runs").iterdir()}
        if (team_set(root, A).pages / "runs").is_dir()
        else set()
    )
    assert keys <= drawn, "every run drawn under its new key in its team's set"
    old = {p.stem for p in (root / "store" / "moved").glob("*.json")}
    assert not old & {p.name for p in (root / PAGES_DIRNAME / "runs").iterdir()}, "no page under an old key"
    examined(len(keys), "each run's pages in alpha's set, none under an old key")


def test_run_assign_is_refused_without_teams_for_a_team_not_held_and_while_the_console_listens(
    unassigned, tmp_path, monkeypatch, capsys, examined
):
    root, store = unassigned
    before = sorted(r.key for r in store.runs())
    _configure(monkeypatch, tmp_path, root, teams={})
    assert _cli("--unassigned", A) == 1
    assert "teams is not configured" in capsys.readouterr().err
    _configure(monkeypatch, tmp_path, root)
    assert _cli("--unassigned", "gamma") == 1
    assert "'gamma' is a team teams does not hold" in capsys.readouterr().err
    assert _cli("--unassigned", "Payments") == 1
    assert "not a team's name" in capsys.readouterr().err
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        _configure(monkeypatch, tmp_path, root, port=listener.getsockname()[1])
        assert _cli("--unassigned", A) == 1
        assert "Stop the console" in capsys.readouterr().err
    assert _cli("assign-nothing") == 2
    from onetrace_console.store import Store

    assert sorted(r.key for r in Store(root / "store").runs()) == before, "nothing changed on a refusal"
    examined(4, "run assign refused: no teams, a team not held, a bad name, the console listening")


@pytest.fixture
def two_teams(shared_demo, tmp_path):
    """The demo split between the two teams (`test_team_pages.split_demo`), drawn."""
    from onetrace_console.config import Config
    from onetrace_console.serve import _render_startup_pages
    from tests.test_team_pages import split_demo

    root, store = split_demo(shared_demo, tmp_path / "demo")
    config = Config(sign_in={**Config().sign_in, "enabled": False}, teams=TEAMS)
    _render_startup_pages(store, root, config)
    return root, store, config


def test_run_assign_moves_a_run_s_pages_from_one_team_s_set_to_the_other_s(
    two_teams, tmp_path, monkeypatch, capsys, examined
):
    from onetrace_console.serve import _render_startup_pages, team_set
    from onetrace_console.store import Store

    root, store, config = two_teams
    run = next(r for r in store.runs() if r.team == A)
    assert (team_set(root, A).pages / "runs" / run.key / "case.html").is_file()
    _configure(monkeypatch, tmp_path, root)
    assert _cli(run.key, B) == 0
    capsys.readouterr()
    after = Store(root / "store")
    new = after.moved_to(run.key)
    assert new and after.get_run(new).team == B
    _render_startup_pages(after, root, config)
    assert (team_set(root, B).pages / "runs" / new / "case.html").is_file()
    for team in (A, B):
        assert not (team_set(root, team).pages / "runs" / run.key).exists()
    assert not (team_set(root, A).pages / "runs" / new).exists()
    assert _cli(new, B) == 0 and "already" in capsys.readouterr().out
    examined(3, "a run moved: drawn in beta's set, gone from alpha's, under neither key there")


def test_a_run_s_old_address_redirects_for_its_team_and_reads_as_no_run_for_anyone_else(
    two_teams, tmp_path, monkeypatch, capsys, examined
):
    from onetrace_console.serve import Handler, _render_startup_pages
    from onetrace_console.sessions import SessionStore
    from onetrace_console.store import Store
    from tests.conftest import serving
    from tests.test_team_folder import _get

    root, store, config = two_teams
    run = next(r for r in store.runs() if r.team == A)
    _configure(monkeypatch, tmp_path, root)
    assert _cli(run.key, B) == 0
    after = Store(root / "store")
    new = after.moved_to(run.key)
    signed = type(config)(
        sign_in={**config.sign_in, "enabled": True, "insecure_cookie_for_local_dev": True}, teams=TEAMS
    )
    _render_startup_pages(after, root, signed)
    (tmp_path / "serving").mkdir()
    with serving(tmp_path / "serving") as (base, _root):
        names = ("store", "store_root", "config", "session_store")
        saved = {n: getattr(Handler, n, None) for n in names}
        Handler.store, Handler.store_root, Handler.config = after, root, signed
        Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)

        def person(teams, role=None):
            s = Handler.session_store.create(
                f"p-{'-'.join(teams)}-{role}", role=role, expires_at=time.time() + 600, teams=tuple(teams)
            )
            return {"Cookie": f"onetrace_session={s.session_id}"}

        try:
            beta, alpha, admin = person((B,)), person((A,)), person((), "admin")
            for who, prefix in ((beta, ""), (beta, "t/beta/"), (admin, "")):
                status, _body, headers = _redirect(base, f"/{prefix}runs/{run.key}/case.html", who)
                assert status == 302 and headers["Location"] == f"/{prefix}runs/{new}/case.html", (prefix, headers)
            unknown = "0" * 64
            for path in (f"runs/{run.key}/case.html", f"t/alpha/runs/{run.key}/case.html"):
                asked = _get(base, "/" + path, alpha)
                none = _get(base, "/" + path.replace(run.key, unknown), alpha)
                assert asked[0] == none[0] == 404
                assert asked[1] == none[1].replace(unknown.encode(), run.key.encode()), path
        finally:
            for n, v in saved.items():
                setattr(Handler, n, v)
    examined(5, "the old address: beta twice and an admin redirected; alpha twice told no such run")


def _redirect(base, path, headers):
    import http.client
    from urllib.parse import urlsplit

    u = urlsplit(base)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=10)
    try:
        conn.request("GET", path, headers=headers)
        r = conn.getresponse()
        return r.status, r.read(), dict(r.getheaders())
    finally:
        conn.close()


def test_every_assignment_writes_one_run_assigned_entry_with_both_keys(
    unassigned, tmp_path, monkeypatch, second, examined
):
    from onetrace_console.audit import AuditLog
    from onetrace_console.store import Store

    root, store = unassigned
    heads = second / "heads.jsonl"
    _configure(monkeypatch, tmp_path, root, audit={"enabled": True, "head_location": heads.as_posix()})
    old = sorted(r.key for r in store.runs())
    assert _cli("--unassigned", A) == 0
    after = Store(root / "store")
    entries = [e for e in AuditLog(root / "audit_log", head_location=heads).entries() if e["event"] == "run.assigned"]
    assert sorted(e["object"] for e in entries) == old
    for e in entries:
        d = e["detail"]
        assert e["actor"] == "cli" and d["old_key"] == e["object"] and d["new_key"] == after.moved_to(d["old_key"])
        assert (d["from"], d["to"], d["rule"]) == (None, A, "run assign --unassigned")
    run = after.get_run(entries[0]["detail"]["new_key"])
    assert _cli(run.key, B) == 0
    moved = [e for e in AuditLog(root / "audit_log", head_location=heads).entries() if e["event"] == "run.assigned"][-1]
    assert moved["detail"] == {
        "from": A,
        "to": B,
        "rule": "run assign",
        "old_key": run.key,
        "new_key": Store(root / "store").moved_to(run.key),
    }
    examined(len(old) + 1, "one run.assigned entry per run, with both keys; and one move")


def test_a_run_assign_the_log_cannot_record_moves_no_run(unassigned, tmp_path, monkeypatch, second, capsys, examined):
    from onetrace_console.store import Store

    root, store = unassigned
    heads = second / "heads.jsonl"
    heads.mkdir()
    _configure(monkeypatch, tmp_path, root, audit={"enabled": True, "head_location": heads.as_posix()})
    before = sorted(r.key for r in store.runs())
    assert _cli("--unassigned", A) == 1
    assert "could not record it" in capsys.readouterr().err
    assert sorted(r.key for r in Store(root / "store").runs()) == before
    examined(1, "run assign with the log failing")
