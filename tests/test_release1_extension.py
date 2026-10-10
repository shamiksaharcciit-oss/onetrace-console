"""The authorization extension cannot be switched on in release 1.

    The onedoor extension: in release 1 it can't be switched on. The setting is refused at
    start with a clear message ("the authorization extension is not part of this release").
    That removes the "records shown while pages say none" contradiction until release 2
    wires the join.

The extension's code stays, and its own tests still drive it directly; only the console's
start refuses the setting.
"""
from __future__ import annotations

import json

import pytest

from onetrace_console.config import ENV_VAR
from tests.test_local_mode import _FakeServer, _Stop, local_main  # noqa: F401  (fixture)


def _file(tmp_path, monkeypatch, body: dict) -> None:
    path = tmp_path / "config.json"
    body = {"store_root": (tmp_path / "s").as_posix(), **body}
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))


def test_switching_the_extension_on_is_refused_at_start(local_main, capsys, tmp_path,
                                                         monkeypatch):
    serve_module, _ = local_main
    _file(tmp_path, monkeypatch, {"extensions": {"onedoor": True}})
    assert serve_module.main([]) == 1
    assert "the authorization extension is not part of this release" in capsys.readouterr().err
    assert _FakeServer.address is None, "it never listened"


def test_the_extension_left_off_starts_as_before(local_main, capsys, tmp_path, monkeypatch):
    serve_module, _ = local_main
    _file(tmp_path, monkeypatch, {"extensions": {"onedoor": False}})
    with pytest.raises(_Stop):
        serve_module.main([])
    assert _FakeServer.address == ("127.0.0.1", 8080)
