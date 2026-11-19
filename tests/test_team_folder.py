"""A folder console with teams: `onetrace-console <runs folder>` started with a configuration
file that names teams refuses to start unless `folder_team` binds the watched folder to one team, naming the key;
every run it takes in is that team's; and `GET /v1/folder` answers that team's people, and anyone else as a route the
console does not have.
"""

from __future__ import annotations

import json
import time

import pytest

from tests.test_team_assignment import TEAMS, A, B, _body, _refused, _serve


def test_a_folder_console_with_teams_and_no_folder_team_refuses_to_start_naming_the_key(
    tmp_path, monkeypatch, capsys, examined
):
    def prepare(store, config):
        raise AssertionError("it loaded the folder")

    assert _serve(tmp_path, monkeypatch, _body(tmp_path, teams=TEAMS), prepare=prepare) == 1
    err = _refused(capsys)
    assert "teams is configured and folder_team is not" in err and "set folder_team" in err, err
    examined(1, "a folder console, teams and no folder_team")


def test_every_run_a_folder_console_takes_in_is_its_folder_team_s(tmp_path, run_folder, examined):
    import shutil

    from onetrace_console.config import Config
    from onetrace_console.folder_load import deliver_one
    from onetrace_console.store import Store, run_key

    runs = tmp_path / "runs"
    shutil.copytree(run_folder, runs / "run-1")
    store = Store(tmp_path / "store")
    got = deliver_one(runs / "run-1", store, Config(teams=TEAMS, folder_team=B))
    assert got.run is not None, got.refused
    assert got.run.team == B and got.run.key == run_key(got.run.run_id, got.run.chain_head, B)
    plain = deliver_one(runs / "run-1", Store(tmp_path / "plain"), Config())
    assert (
        plain.run is not None
        and plain.run.team == ""
        and plain.run.key == run_key(plain.run.run_id, plain.run.chain_head)
    )
    examined(2, "a folder run with folder_team, and without teams")


class _Watcher:
    class state:  # noqa: N801 - the watcher's own attribute name
        @staticmethod
        def as_json():
            return {"folder": "runs", "taken": ["run-1"]}


@pytest.fixture
def folder_console(tmp_path):
    from onetrace_console.config import Config
    from onetrace_console.serve import Handler
    from onetrace_console.sessions import SessionStore
    from tests.conftest import serving

    with serving(tmp_path) as (base, _root):
        names = ("config", "watcher", "local_port", "session_store")
        saved = {n: getattr(Handler, n, None) for n in names}
        Handler.config = Config(
            sign_in={**Config().sign_in, "enabled": True, "insecure_cookie_for_local_dev": True},
            teams=TEAMS,
            folder_team=A,
        )
        Handler.watcher, Handler.local_port = _Watcher(), None
        Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
        try:
            yield base
        finally:
            for n, v in saved.items():
                setattr(Handler, n, v)


def _session(teams, role=None) -> dict:
    from onetrace_console.serve import Handler

    s = Handler.session_store.create(
        f"person-{'-'.join(teams) or 'none'}-{role}", role=role, expires_at=time.time() + 600, teams=tuple(teams)
    )
    return {"Cookie": f"onetrace_session={s.session_id}"}


def _get(base, path, headers):
    from tests.test_signin_flow import _get as get

    try:
        status, body, _h, _ = get(base, path, headers=headers)
    except Exception as e:  # urllib raises on 4xx
        status, body = e.code, e.read()
    return status, body


def test_the_folder_s_state_answers_its_team_and_anyone_else_as_a_route_not_there(folder_console, examined):
    base = folder_console
    status, body = _get(base, "/v1/folder", _session((A,)))
    assert status == 200 and json.loads(body)["taken"] == ["run-1"]
    assert _get(base, "/v1/folder", _session((A, B)))[0] == 200
    assert _get(base, "/v1/folder", _session((), "admin"))[0] == 200
    beta = _session((B,))
    unknown = _get(base, "/v1/folders", beta)
    assert unknown == (404, b"no such route\n")
    assert _get(base, "/v1/folder", beta) == unknown, "byte for byte"
    assert _get(base, "/t/beta/v1/folder", beta) == _get(base, "/t/beta/v1/folders", beta)
    examined(5, "the folder's state: its team, two teams, an admin, the other team, the other's prefix")
