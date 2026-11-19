"""The index from a principal to its session ids: built in memory beside the session store.

- a session is entered under its principal, a local account's name or an Entra ID key, when it is made, and leaves
  the index when it ends by each path: idle, the token's expiry, `session_max_hours` (the absolute bound), sign-out,
  and the bound on an account's sessions;
- `admin sessions end` with a local account's name, and with an Entra ID key, ends every session of that person on
  a running console at its next request, through the index, and tells the console how many it ended;
- a session made after the command's time survives it; a malformed Entra ID key is refused; with SCIM off a
  well-formed key is taken, and the command says it could not be checked against a person.
"""

from __future__ import annotations

import pytest

from onetrace_console.config import ENV_VAR, Config
from onetrace_console.sessions import SessionStore

ALICE = "alice"
#: An Entra ID key, `<tenant id>/<object id>`, as `oidc_identity.identity` makes it: lower-cased.
TENANT = "0f1e2d3c-4b5a-4968-8778-695a4b3c2d1e"
OBJECT = "11112222-3333-4444-8555-666677778888"
ENTRA = f"{TENANT}/{OBJECT}"


def _store(**kw) -> SessionStore:
    return SessionStore(idle_timeout_seconds=60, absolute_timeout_seconds=600, **kw)


@pytest.mark.parametrize("who", [ALICE, ENTRA])
def test_a_session_is_entered_under_its_principal_when_it_is_made(who, examined):
    store = _store()
    one, two = store.create(who), store.create(who)
    other = store.create("bob")
    assert store.sessions_of(who) == {one.session_id, two.session_id}
    assert store.sessions_of("bob") == {other.session_id}
    assert store.sessions_of("carol") == set()
    examined(3, f"two sessions of {who[:8]}, one of bob, none of carol")


def test_a_session_leaves_the_index_when_it_ends_by_each_path(examined):
    clock = {"wall": 1000.0}
    store = _store(max_per_account=2, wall=lambda: clock["wall"])
    ended = []

    idle = store.create("idle", now=0.0)
    assert store.get(idle.session_id, now=61.0) is None
    ended.append(("idle", store.sessions_of("idle")))

    absolute = store.create("absolute", now=0.0)
    for t in (50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0, 550.0, 600.0):
        store.get(absolute.session_id, now=t)
    assert store.get(absolute.session_id, now=601.0) is None
    ended.append(("session_max_hours", store.sessions_of("absolute")))

    expiring = store.create(ENTRA, now=0.0, expires_at=1010.0)
    clock["wall"] = 1010.0
    assert store.get(expiring.session_id, now=1.0) is None
    ended.append(("the token's expiry", store.sessions_of(ENTRA)))

    out = store.create("out")
    store.invalidate(out.session_id)
    ended.append(("sign-out", store.sessions_of("out")))

    first = store.create("bound")
    second, third = store.create("bound"), store.create("bound")
    assert store.sessions_of("bound") == {second.session_id, third.session_id}
    assert first.session_id not in store.sessions_of("bound")
    ended.append(("the bound", {first.session_id} & store.sessions_of("bound")))

    for path, left in ended:
        assert left == set(), path
    assert store.indexed() == {"bound": {second.session_id, third.session_id}}, "nothing else is held"
    examined(len(ended), "end paths: idle, session_max_hours, the token's expiry, sign-out, the bound")


def test_a_session_ended_on_a_get_leaves_the_index_without_another_get(examined):
    """Once timed out, a session is gone from the index at the get that finds it so, not only from the map."""
    store = _store()
    s = store.create(ALICE, now=0.0)
    store.get(s.session_id, now=61.0)
    assert ALICE not in store.indexed()
    examined(1, "an idle session found by its own get")


# ------------------------------------------------------------------ admin sessions end


@pytest.fixture
def console(tmp_path, monkeypatch):
    """A configuration file, an account `alice`, and the session store `serve` makes from them."""
    import json

    from onetrace_console.accounts import AccountStore
    from onetrace_console.serve import ACCOUNTS_DIRNAME, session_store_for

    root = tmp_path / "data"
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"store_root": root.as_posix(), "sign_in": {"enabled": True}}), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    accounts = AccountStore(root / ACCOUNTS_DIRNAME)
    accounts.create(ALICE, b"correct horse battery staple")
    told: list[tuple[str, int]] = []
    config = Config(sign_in={**Config().sign_in, "enabled": True}, store_root=root.as_posix())
    store = session_store_for(config, accounts, store_root=root, on_ended=lambda p, n: told.append((p, n)))
    return store, told


def _end(who) -> int:
    from onetrace_console.__main__ import main as cli_main

    return cli_main(["admin", "sessions", "end", who])


@pytest.mark.parametrize("who", [ALICE, ENTRA])
def test_admin_sessions_end_ends_every_session_of_that_person_through_the_index(console, who, capsys, examined):
    store, told = console
    mine = [store.create(who) for _ in range(3)]
    other = store.create("bob")
    assert _end(who) == 0
    out = capsys.readouterr().out
    assert store.get(mine[0].session_id) is None
    assert store.sessions_of(who) == set(), "every one of them, at the first request, not only the one asked"
    assert store.get(other.session_id) is not None, "another person's session is not ended"
    assert told == [(who, 3)], "the console is told how many it ended"
    for s in mine[1:]:
        assert store.get(s.session_id) is None
    assert told == [(who, 3)], "told once"
    if who == ENTRA:
        assert "could not be checked against a person" in out, out
    examined(4, f"{who[:8]}'s three sessions ended at one request; bob's kept")


@pytest.mark.parametrize("who", [ALICE, ENTRA])
def test_a_session_made_after_the_end_time_survives_it(console, who, examined):
    store, told = console
    before = store.create(who)
    assert _end(who) == 0
    after = store.create(who)
    assert store.get(after.session_id) is not None
    assert store.get(before.session_id) is None
    assert store.sessions_of(who) == {after.session_id}
    assert told == [(who, 1)]
    examined(2, "sessions either side of the end time")


def test_an_entra_id_key_is_read_lower_cased(console, examined):
    store, told = console
    s = store.create(ENTRA)
    assert _end(ENTRA.upper()) == 0
    assert store.get(s.session_id) is None and told == [(ENTRA, 1)]
    examined(1, "a key given in upper case")


@pytest.mark.parametrize(
    "key",
    [
        f"{TENANT}/",
        f"/{OBJECT}",
        f"{TENANT}/{OBJECT}/x",
        f"{TENANT[:-1]}/{OBJECT}",
        f"{TENANT}/not-a-guid",
        f"{TENANT}{OBJECT}",
        f"{TENANT} /{OBJECT}",
    ],
)
def test_a_malformed_entra_id_key_is_refused(console, key, capsys, examined):
    store, _told = console
    s = store.create(ENTRA)
    assert _end(key) == 1
    err = capsys.readouterr().err
    assert "two GUIDs" in err or "no account named" in err, err
    assert store.get(s.session_id) is not None, "nothing ended"
    examined(1, f"key {key[:20]}")


def test_a_name_with_no_account_is_refused_as_before(console, capsys, examined):
    assert _end("nobody") == 1
    assert "no account named 'nobody'" in capsys.readouterr().err
    examined(1, "an unknown account")
