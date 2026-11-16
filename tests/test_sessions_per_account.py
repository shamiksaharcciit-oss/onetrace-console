"""Sessions per account: `sign_in.max_sessions_per_account` (default 3) bounds an account's live sessions, and a
sign-in beyond it ends that account's oldest; `onetrace-console admin sessions end <account>` ends all of an
account's sessions, the running console's included, by a time the console reads from the accounts folder. A
cookie whose session is ended gets the sign-in page. Over real HTTP where a cookie is presented.
"""

from __future__ import annotations

import io
import sys

import pytest

from onetrace_console.config import ENV_VAR, Config, ConfigError
from onetrace_console.serve import ACCOUNTS_DIRNAME, Handler
from onetrace_console.sessions import SessionStore
from tests.test_roles_enforcement import _sign_in, roles_enabled  # noqa: F401
from tests.test_signin_flow import _get


@pytest.fixture
def per_account(roles_enabled, monkeypatch):
    """The console's own session store, as `serve` makes it from the configuration."""
    from onetrace_console.serve import session_store_for

    base, _ = roles_enabled
    monkeypatch.setattr(
        Handler,
        "session_store",
        session_store_for(
            Config(
                sign_in={
                    "enabled": True,
                    "session_idle_timeout_seconds": 1800,
                    "session_absolute_timeout_seconds": 43200,
                    "max_sessions_per_account": 3,
                }
            ),
            Handler.account_store,
        ),
    )
    return base


def _page(base, session) -> tuple[int, str]:
    status, _, headers, _ = _get(base, "/home.html", headers={"Cookie": f"onetrace_session={session}"})
    return status, headers.get("Location", "")


def test_the_default_is_three_sessions_per_account(examined):
    examined(1, "the default configuration")
    assert Config().sign_in["max_sessions_per_account"] == 3


def test_the_fourth_sign_in_ends_the_first(per_account, examined):
    base = per_account
    sessions = [_sign_in(base)[0] for _ in range(4)]
    seen = [_page(base, s) for s in sessions]
    examined(len(seen), "sessions, one page each")
    assert seen[0] == (303, "/signin")
    assert [s for s, _ in seen[1:]] == [200, 200, 200]


def test_another_account_s_sessions_are_not_counted(per_account, examined):
    base = per_account
    Handler.account_store.create("bob", b"another long passphrase")
    alice = _sign_in(base)[0]
    for _ in range(3):
        Handler.session_store.create("bob")
    examined(1, "alice's session beside three of bob's")
    assert _page(base, alice)[0] == 200


def test_admin_sessions_end_ends_all_of_an_account_s_sessions(per_account, tmp_path, monkeypatch, examined):
    from onetrace_console.__main__ import main as cli_main

    base = per_account
    store_root = Handler.account_store.root.parent
    alice = [_sign_in(base)[0] for _ in range(2)]
    config = tmp_path / "config.json"
    config.write_text(f'{{"store_root": "{store_root.as_posix()}"}}', encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    rc = cli_main(["admin", "sessions", "end", "alice"])
    examined(len(alice), "alice's sessions after the command")
    assert rc == 0
    assert [_page(base, s) for s in alice] == [(303, "/signin")] * 2
    #: A sign-in after the command makes a session that lives.
    assert _page(base, _sign_in(base)[0])[0] == 200


def test_admin_sessions_end_leaves_other_accounts_alone(per_account, tmp_path, monkeypatch, examined):
    from onetrace_console.__main__ import main as cli_main

    Handler.account_store.create("bob", b"another long passphrase")
    bob = Handler.session_store.create("bob")
    config = tmp_path / "config.json"
    config.write_text(f'{{"store_root": "{Handler.account_store.root.parent.as_posix()}"}}', encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config))
    assert cli_main(["admin", "sessions", "end", "alice"]) == 0
    examined(1, "bob's session")
    assert Handler.session_store.get(bob.session_id) is not None


def test_admin_sessions_end_refuses_an_account_that_does_not_exist(tmp_path, monkeypatch, capsys, examined):
    from onetrace_console.__main__ import main as cli_main

    config = tmp_path / "config.json"
    config.write_text(f'{{"store_root": "{(tmp_path / "store").as_posix()}"}}', encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config))
    rc = cli_main(["admin", "sessions", "end", "nobody"])
    examined(1, "the command for no such account")
    assert rc == 1 and "no account named 'nobody'" in capsys.readouterr().err
    assert not (tmp_path / "store" / ACCOUNTS_DIRNAME / "nobody.ended").exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["admin", "sessions"],
        ["admin", "sessions", "end"],
        ["admin", "sessions", "end", "a", "b"],
        ["admin", "sessions", "list", "a"],
    ],
)
def test_admin_sessions_usage(argv, capsys, examined):
    from onetrace_console.__main__ import main as cli_main

    examined(1, f"argv {argv}")
    assert cli_main(argv) == 2
    assert "admin sessions end <account>" in capsys.readouterr().err


def test_a_session_made_before_the_end_time_is_gone_and_one_after_lives(tmp_path, examined):
    from onetrace_console.accounts import AccountStore

    accounts = AccountStore(tmp_path / ACCOUNTS_DIRNAME)
    accounts.create("alice", b"correct horse battery staple")
    store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200, ended=accounts.sessions_ended_at)
    before = store.create("alice")
    accounts.end_sessions("alice")
    after = store.create("alice")
    examined(2, "sessions either side of the end time")
    assert store.get(before.session_id) is None and store.get(after.session_id) is not None


@pytest.mark.parametrize("value", [0, -1, True, "3"])
def test_a_bound_that_is_not_a_positive_integer_is_refused(tmp_path, value, examined):
    import json

    from onetrace_console.config import load

    p = tmp_path / "config.json"
    p.write_text(json.dumps({"sign_in": {"max_sessions_per_account": value}}), encoding="utf-8")
    examined(1, f"max_sessions_per_account {value!r}")
    with pytest.raises(ConfigError, match=r"sign_in\.max_sessions_per_account must be"):
        load(p)
