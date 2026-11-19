"""What the audit log records, from the console's existing actions and its commands.

- an entry per event from the existing actions: upload, compare, benchmark, expectations, tokenizer keep and remove,
  explain setup save, explain send, sign-in ok and refused, sign-out (neighbours on and off: `test_neighbours.py`,
  which the neighbours environment runs);
- an entry for each event the command line adds: `token.created`, `account.created`, `sessions.ended` (the
  command's, actor `cli`, with its end time; the server's, actor `console`, with its count), `teams.changed`,
  `audit.append_failed`; and `run.assigned` (`test_team_run_assign.py`);
- no line holds any of the test's own secrets: password, session id, CSRF token, ingester token, explain key, a
  search term;
- an append failure refuses the action, except a write that removes access, `admin sessions end`, which applies and
  shows the failure (SCIM's `scim enforcement on`, and its refused grants: `test_scim_recovery.py`); `admin sessions end` against a held lock applies after the wait, and the failure is shown and
  recorded as a failed append.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from tests.http_limits import limit
from tests.keychain import keychain, keyring_lib  # noqa: F401 - fixtures, requested by name
from tests.test_audit_log import second  # noqa: F401 - a fixture, requested by name
from tests.test_explain_panel import pair  # noqa: F401 - a fixture, requested by `local`
from tests.test_explain_setup import local  # noqa: F401 - a fixture, requested by name
from tests.test_roles_enforcement import roles_enabled  # noqa: F401 - a fixture, requested by name


def _audit(log_root: Path, heads: Path):
    from onetrace_console.audit import Audit, AuditLog

    return Audit(AuditLog(log_root, head_location=heads))


@pytest.fixture
def audited(tmp_path, monkeypatch, second):  # noqa: F811 - the fixture, requested by name
    """The serving console's audit log, on: (its log)."""
    from onetrace_console.serve import Handler

    on = _audit(tmp_path / "audit_log", second / "heads.jsonl")
    monkeypatch.setattr(Handler, "audit", on)
    return on.log


def _events(log) -> list[tuple[str, str, str]]:
    return [(e["actor"], e["event"], e["object"]) for e in log.entries()]


def _post(url: str, body: bytes = b"", headers: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=limit(300)) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _broken(log) -> None:
    """The head's second location made unwritable: a folder where the file of heads should be."""
    log.head_location.unlink(missing_ok=True)
    log.head_location.mkdir()


def _mended(log) -> None:
    log.head_location.rmdir()


# ------------------------------------------------------------------ a local console's actions


@pytest.fixture
def held(server, audited):
    """The server's store holding one run checked as the expectations tests check it."""
    from onetrace_console.serve import Handler
    from tests.test_expectations_after import _stored

    base, root = server
    return base, Handler.store, _stored(Handler.store), audited


def test_an_upload_is_recorded_with_its_run_team_token_build_and_verdict(held, delivery, examined):
    base, store, _run, log = held
    status, body = _post(f"{base}/v1/runs", delivery)
    assert status == 200, body
    key = json.loads(body)["run_key"]
    (entry,) = [e for e in log.entries() if e["event"] == "run.uploaded"]
    assert entry["object"] == key and entry["actor"] == "anonymous"
    d = entry["detail"]
    assert d["run_id"] == store.get_run(key).run_id and d["team"] == "" and d["token"] is None
    assert d["verdict"] == store.get_run(key).check_verdict and d["build"]
    again = _post(f"{base}/v1/runs", delivery)
    assert again[0] == 200 and [e["event"] for e in log.entries()].count("run.uploaded") == 1, "a held run, once"
    examined(2, "a delivery, and its second, held")


def test_an_upload_the_log_cannot_record_is_refused_and_nothing_is_held(held, delivery, examined):
    base, store, _run, log = held
    before = {r.key for r in store.runs()}
    _broken(log)
    status, body = _post(f"{base}/v1/runs", delivery)
    assert status == 503 and b"Not done: the audit log could not record it" in body, body
    assert {r.key for r in store.runs()} == before, "the run taken back"
    _mended(log)
    status, body = _post(f"{base}/v1/runs", delivery)
    assert status == 200
    events = [e["event"] for e in log.entries()]
    assert events == ["audit.append_failed", "run.uploaded"], events
    failed = log.entries()[0]["detail"]
    assert failed["not_recorded"] == {"run.uploaded": 1} and failed["began"] <= failed["ended"]
    examined(2, "a refused delivery, then one recorded after the failure's own entry")


def test_a_benchmark_mark_and_its_undo_are_recorded(held, examined):
    base, store, run, log = held
    marked = _post(f"{base}/benchmark?run={run.key}&mark=yes", json.dumps({"note": "a note kept out"}).encode())
    unmarked = _post(f"{base}/benchmark?run={run.key}&mark=no")
    assert marked[0] == unmarked[0] == 200, (marked, unmarked)
    assert _events(log) == [("anonymous", "benchmark.marked", run.key), ("anonymous", "benchmark.unmarked", run.key)]
    assert log.entries()[0]["detail"] == {"team": "", "note": True}
    assert "a note kept out" not in log.head_location.read_text() + "".join(
        p.read_text(encoding="utf-8") for p in log.root.glob("*.jsonl")
    )
    examined(2, "a mark and its undo")


def test_a_mark_the_log_cannot_record_is_undone(held, examined):
    from onetrace_console import benchmarks

    base, store, run, log = held
    _broken(log)
    path = benchmarks._path(store, run.key)
    assert _post(f"{base}/benchmark?run={run.key}&mark=yes")[0] == 503
    assert not path.is_file()
    _mended(log)
    assert _post(f"{base}/benchmark?run={run.key}&mark=yes")[0] == 200
    _broken(log)
    assert _post(f"{base}/benchmark?run={run.key}&mark=no")[0] == 503
    assert path.is_file(), "the undo undone: the mark is back"
    examined(2, "a mark and an unmark, each refused and undone")


def test_an_expectations_check_is_recorded_by_its_seal_never_its_path(held, examined):
    from tests.test_expectations_after import FILE, SEAL

    base, _store, run, log = held
    status, body = _post(f"{base}/expectations?run={run.key}", json.dumps({"path": str(FILE)}).encode())
    assert status == 200, body
    (entry,) = log.entries()
    assert (entry["event"], entry["object"], entry["detail"]) == (
        "expectations.checked",
        run.key,
        {"seal": SEAL, "rows": 4},
    )
    assert str(FILE) not in json.dumps(entry) and FILE.name not in json.dumps(entry)
    examined(1, "an expectations check")


def test_a_tokenizer_kept_and_removed_is_recorded(held, examined):
    from tests.test_token_upload import TOKENIZER, _digest

    base, _store, _run, log = held
    want = _digest({"tokenizer.json": TOKENIZER})
    assert _post(f"{base}/model-tokenizers?digest={want}&name=tokenizer.json", TOKENIZER)[0] == 200
    assert _post(f"{base}/model-tokenizers?digest={want}&name=tokenizer.json", TOKENIZER)[0] == 200
    assert _post(f"{base}/model-tokenizers/remove?digest={want}")[0] == 200
    assert _post(f"{base}/model-tokenizers/remove?digest={want}")[0] == 400
    assert _events(log) == [("anonymous", "setting.changed", "tokenizer"), ("anonymous", "tokenizer.removed", want)]
    assert log.entries()[0]["detail"] == {"setting": "tokenizer kept", "digest": want}
    examined(4, "keep, keep again, remove, remove again: two changes")


# ------------------------------------------------------------------ a comparison and Explain


@pytest.fixture
def explaining(local, audited):
    return (*local, audited)


def test_a_comparison_made_is_recorded_and_one_held_is_not(explaining, examined):
    from onetrace_console.serve import Handler

    base, _root, store, comparison, _config, log = explaining
    a, b = comparison.run_a, comparison.run_b
    assert _post(f"{base}/compare?a={a}&b={b}")[0] == 200
    assert _events(log) == [], "held already: nothing made"
    Handler.store.withdraw_comparison(comparison.key)
    status, body = _post(f"{base}/compare?a={a}&b={b}")
    assert status == 200, body
    (entry,) = log.entries()
    assert (entry["event"], entry["object"]) == ("compare.made", comparison.key)
    assert entry["detail"]["a"] == a and entry["detail"]["b"] == b and entry["detail"]["build"]
    examined(2, "a pair held, then made")


def test_a_comparison_the_log_cannot_record_is_taken_back(explaining, examined):
    from onetrace_console.serve import Handler

    base, _root, store, comparison, _config, log = explaining
    Handler.store.withdraw_comparison(comparison.key)
    _broken(log)
    status, body = _post(f"{base}/compare?a={comparison.run_a}&b={comparison.run_b}")
    assert status == 503 and b"Not done" in body, body
    assert comparison.key not in Handler.store.comparison_names()
    examined(1, "a comparison refused")


def test_a_send_is_recorded_before_anything_leaves(explaining, monkeypatch, examined):
    from onetrace_console import explain

    base, _root, _store, comparison, _config, log = explaining
    started = []
    monkeypatch.setattr(explain, "command", lambda: "onetrace-explain")
    monkeypatch.setattr(explain, "start", lambda *a, **k: started.append(len(log.entries())))
    status, _body = _post(f"{base}/explain?c={comparison.key}&send=yes")
    assert status == 202 and started == [1], "the entry, then the send"
    (entry,) = log.entries()
    assert (entry["event"], entry["object"]) == ("explain.sent", comparison.key)
    assert set(entry["detail"]) == {"endpoint", "kinds", "include_text"}
    _broken(log)
    status, body = _post(f"{base}/explain?c={comparison.key}&send=yes")
    assert status == 503 and started == [1], "refused: nothing sent"
    examined(2, "a send recorded; a send refused")


def test_a_send_that_ends_is_recorded_with_its_record_s_chain_head(explaining, monkeypatch, examined):
    """`explain.sent` before the send, and `explain.completed` when it ends: the new explanation record and its
    chain head, which do not exist when the send starts; none where the send made no record."""
    from onetrace_console import explain

    base, _root, _store, comparison, _config, log = explaining
    head = "sha256:" + "a" * 64
    made = []

    def start(comp, store, *, send=False, done=None, **kwargs):
        if made:
            where = explain.folder_of(store, comp.key) / explain.REPORT / "explain" / made[-1]
            where.mkdir(parents=True)
            (where / "MANIFEST.json").write_text(json.dumps({"chain_head": head}), encoding="utf-8")
        if done is not None:
            done()

    monkeypatch.setattr(explain, "command", lambda: "onetrace-explain")
    monkeypatch.setattr(explain, "start", start)
    made.append("2026-11-15-r1")
    assert _post(f"{base}/explain?c={comparison.key}&send=yes")[0] == 202
    made.clear()
    assert _post(f"{base}/explain?c={comparison.key}&send=yes")[0] == 202
    got = [(e["event"], e["object"], e["detail"]) for e in log.entries()]
    assert [g[0] for g in got] == ["explain.sent", "explain.completed", "explain.sent", "explain.completed"]
    assert got[1][1] == comparison.key
    assert got[1][2] == {"records": [{"record": "2026-11-15-r1", "chain_head": head}]}
    assert got[3][2] == {"records": []}, "a send that made no record says so"
    examined(2, "sends ended")


@pytest.mark.usefixtures("keychain")
def test_explain_setup_saved_is_recorded_with_provider_model_and_address_never_the_key(explaining, examined):
    from tests.test_explain_setup_form import _post as post_form

    base, _root, _store, _comparison, _config, log = explaining
    key = "sk-test-0123456789abcdef-never-logged"
    fields = {"provider": "openai", "name": "small-model", "base_url": "http://127.0.0.1:9/v1", "key": ""}
    assert post_form(f"{base}/explain/setup", fields)[0] == 200
    assert post_form(f"{base}/explain/setup", {**fields, "name": ""})[0] == 400
    post_form(f"{base}/explain/setup", {"action": "replace", "key": key})
    events = [(e["event"], e["detail"]) for e in log.entries()]
    assert events[0] == (
        "setting.changed",
        {"setting": "explain setup", "provider": "openai", "model": "small-model", "address": "http://127.0.0.1:9/v1"},
    )
    assert len([e for e in events if e[1].get("setting") == "explain setup"]) == 1, "a refused save records nothing"
    assert events[-1] == ("setting.changed", {"setting": "explain key", "action": "replaced"})
    text = "".join(p.read_text(encoding="utf-8") for p in log.root.glob("*.jsonl"))
    assert key not in text
    examined(3, "a save, a refused save, a key replaced")


# ------------------------------------------------------------------ sign-in, sign-out


@pytest.fixture
def signing(roles_enabled, audited):
    return roles_enabled, audited


PASSWORD = "correct horse battery staple"


def _sign_in_as(base, username: str, password: str) -> int:
    from tests.test_signin_flow import _get_signin_form

    csrf, form_token = _get_signin_form(base)
    body = urllib.parse.urlencode({"username": username, "password": password, "csrf_token": form_token}).encode()
    headers = {"Cookie": f"onetrace_csrf={csrf}", "Content-Type": "application/x-www-form-urlencoded"}
    return _post(f"{base}/signin", body, headers)[0]


def _logged(log) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in log.root.glob("*.jsonl"))


def test_sign_in_ok_and_sign_out_are_recorded_and_keep_no_secret(signing, examined):
    from tests.test_roles_enforcement import _sign_in
    from tests.test_signout_button import _press

    (base, _token), log = signing
    session, csrf = _sign_in(base)
    _press(base, session, csrf)
    events = [(e["event"], e["object"], e["detail"]) for e in log.entries()]
    assert events[0][:2] == ("signin.ok", "alice"), events
    assert events[0][2] == {"method": "local", "roles": [], "teams": [], "differs": False}
    assert ("signout", "alice", {"how": "pressed"}) in events, events
    for secret in (PASSWORD, session, csrf):
        assert secret not in _logged(log) and secret not in log.head_location.read_text(encoding="utf-8")
    examined(2, "a sign-in and a sign-out")


def test_a_refused_sign_in_names_an_account_that_exists_and_never_a_typed_name_that_does_not(signing, examined):
    (base, _token), log = signing
    assert _sign_in_as(base, "alice", "not the password at all") == 401
    assert _sign_in_as(base, "my-password-typed-here", "x") == 401
    refused = [e for e in log.entries() if e["event"] == "signin.refused"]
    assert [(e["object"], e["detail"]["reason"]) for e in refused] == [
        ("alice", "wrong password"),
        ("unknown", "wrong password"),
    ]
    assert "my-password-typed-here" not in _logged(log) and "not the password at all" not in _logged(log)
    examined(2, "a refusal for an account, one for a name with none")


def test_a_sign_in_the_log_cannot_record_is_refused_and_makes_no_session(signing, examined):
    from onetrace_console.serve import Handler

    (base, _token), log = signing
    _broken(log)
    assert _sign_in_as(base, "alice", PASSWORD) == 503
    assert Handler.session_store.sessions_of("alice") == set()
    examined(1, "a sign-in refused")


# ------------------------------------------------------------------ the command line


@pytest.fixture
def cli_audited(tmp_path, monkeypatch, second):  # noqa: F811 - the fixture, requested by name
    from onetrace_console.audit import AuditLog
    from onetrace_console.config import ENV_VAR

    body = {
        "store_root": (tmp_path / "data").as_posix(),
        "sign_in": {"enabled": True},
        "audit": {"enabled": True, "head_location": (second / "heads.jsonl").as_posix()},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    return AuditLog(tmp_path / "data" / "audit_log", head_location=second / "heads.jsonl"), tmp_path / "data"


def _cli(*argv, stdin: str | None = None, monkeypatch=None) -> int:
    from onetrace_console.__main__ import main as cli_main

    if stdin is not None:
        import io
        import sys

        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    return cli_main(list(argv))


def test_token_created_account_created_and_sessions_ended_are_recorded_by_the_command_line(
    cli_audited, monkeypatch, capsys, examined
):
    log, _root = cli_audited
    assert _cli("token", "create", "ci-bot") == 0
    out = capsys.readouterr().out
    token_id = out.split("token id: ")[1].split()[0]
    raw = out.split("store it now): ")[1].split()[0]
    password = "correct horse battery staple, never logged"
    assert _cli("admin", "create", "alice", stdin=password + "\n", monkeypatch=monkeypatch) == 0
    assert _cli("admin", "sessions", "end", "alice") == 0
    assert _cli("token", "revoke", token_id) == 0
    entries = log.entries()
    assert [(e["actor"], e["event"], e["object"]) for e in entries] == [
        ("cli", "token.created", token_id),
        ("cli", "account.created", "alice"),
        ("cli", "sessions.ended", "alice"),
        ("cli", "token.revoked", token_id),
    ]
    assert entries[0]["detail"] == {"principal": "ci-bot", "team": None}
    assert isinstance(entries[2]["detail"]["end_time"], int)
    text = "".join(p.read_text(encoding="utf-8") for p in log.root.glob("*.jsonl"))
    assert raw not in text and password not in text
    examined(4, "four commands, each recorded")


def test_a_token_or_account_whose_making_cannot_be_recorded_is_not_made(cli_audited, monkeypatch, capsys, examined):
    from onetrace_console.accounts import AccountStore
    from onetrace_console.ingester_tokens import TokenStore

    log, root = cli_audited
    log.head_location.mkdir()
    assert _cli("token", "create", "ci-bot") == 1
    err = capsys.readouterr()
    assert "store it now" not in err.out and "could not record it" in err.err
    assert TokenStore(root / "tokens").records() == []
    assert _cli("admin", "create", "alice", stdin="correct horse battery staple\n", monkeypatch=monkeypatch) == 1
    assert not AccountStore(root / "accounts").exists("alice")
    examined(2, "a token and an account, each refused")


def test_admin_sessions_end_applies_when_its_append_fails_and_says_so(cli_audited, capsys, examined):
    from onetrace_console.session_ends import DIRNAME, EndTimes

    log, root = cli_audited
    log.head_location.mkdir()
    assert (
        _cli("admin", "sessions", "end", "0f1e2d3c-4b5a-4968-8778-695a4b3c2d1e/11112222-3333-4444-8555-666677778888")
        == 0
    )
    err = capsys.readouterr().err
    assert "sessions.ended was not recorded" in err and "applied anyway" in err, err
    assert EndTimes(root / DIRNAME).read("0f1e2d3c-4b5a-4968-8778-695a4b3c2d1e/11112222-3333-4444-8555-666677778888")
    log.head_location.rmdir()
    log.append("cli", "audit.checkpoint", "log", {})
    assert [e["event"] for e in log.entries()] == ["audit.append_failed", "audit.checkpoint"]
    assert log.entries()[0]["detail"]["not_recorded"] == {"sessions.ended": 1}
    examined(1, "a session end applied with the log failing")


def test_admin_sessions_end_against_a_held_lock_applies_after_the_wait_and_records_a_failed_append(
    cli_audited, monkeypatch, capsys, examined
):
    from onetrace_console import audit
    from onetrace_console.accounts import AccountStore
    from onetrace_console.session_ends import DIRNAME, EndTimes

    log, root = cli_audited
    AccountStore(root / "accounts").create("alice", b"correct horse battery staple")
    monkeypatch.setattr(audit, "LOCK_WAIT_SECONDS", 0.4)
    with audit._file_lock(log.root / audit.LOCK_NAME, 1.0):
        assert _cli("admin", "sessions", "end", "alice") == 0
    err = capsys.readouterr().err
    assert "held the audit log's lock for over 0.4 seconds" in err and "applied anyway" in err, err
    assert EndTimes(root / DIRNAME).read("alice") is not None, "applied"
    log.append("cli", "audit.checkpoint", "log", {})
    assert [e["event"] for e in log.entries()][0] == "audit.append_failed"
    examined(1, "a session end against a held lock")


def test_the_server_records_how_many_sessions_an_end_time_ended(cli_audited, examined):
    from onetrace_console.accounts import AccountStore
    from onetrace_console.audit import CONSOLE
    from onetrace_console.config import Config
    from onetrace_console.serve import session_store_for

    log, root = cli_audited
    on = _audit(log.root, log.head_location)
    accounts = AccountStore(root / "accounts")
    accounts.create("alice", b"correct horse battery staple")
    store = session_store_for(
        Config(sign_in={**Config().sign_in, "enabled": True}),
        accounts,
        store_root=root,
        on_ended=lambda who, n: on.record(CONSOLE, "sessions.ended", who, {"count": n}, removes_access=True),
    )
    sessions = [store.create("alice") for _ in range(2)]
    assert _cli("admin", "sessions", "end", "alice") == 0
    assert store.get(sessions[0].session_id) is None
    entries = [e for e in log.entries() if e["event"] == "sessions.ended"]
    assert [(e["actor"], e["detail"].get("count")) for e in entries] == [("cli", None), (CONSOLE, 2)]
    examined(2, "the command's entry and the server's")


def test_teams_changed_is_recorded_at_a_start_that_sees_another_mapping(cli_audited, tmp_path, monkeypatch, examined):
    from onetrace_console.config import ENV_VAR
    from tests.test_team_assignment import ENTRA_SIGN_IN, _port, _serve

    log, root = cli_audited
    path = Path(__import__("os").environ[ENV_VAR])
    body = json.loads(path.read_text(encoding="utf-8"))
    body.update(host="127.0.0.1", port=_port(), sign_in=ENTRA_SIGN_IN)
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    TokenStore(root / TOKENS_DIRNAME).create("ci", team="alpha")  # a console with teams needs a live token
    for teams in (
        {"alpha": {"role_claim": "A"}},
        {"alpha": {"role_claim": "A"}},
        {"alpha": {"role_claim": "B"}, "beta": {}},
    ):
        assert _serve(tmp_path, monkeypatch, {**body, "teams": teams}) == -1
    changed = [e["detail"]["touched"] for e in log.entries() if e["event"] == "teams.changed"]
    assert changed == [["alpha"], ["alpha", "beta"]], "the first start, then only the start that changed it"
    shas = [e["detail"]["sha256"] for e in log.entries() if e["event"] == "setting.changed"]
    assert len(shas) == 2 and len(set(shas)) == 2, "the configuration file's sha256, where it changed"
    examined(3, "three starts")


def test_a_search_term_is_never_kept(held, examined):
    base, _store, _run, log = held
    term = "verdict:FAIL secret-search-term"
    urllib.request.urlopen(f"{base}/search?q={urllib.parse.quote(term)}", timeout=limit(60)).read()
    log.append("cli", "audit.checkpoint", "log", {})
    text = "".join(p.read_text(encoding="utf-8") for p in log.root.glob("*.jsonl"))
    assert "secret-search-term" not in text
    examined(1, "a search")
