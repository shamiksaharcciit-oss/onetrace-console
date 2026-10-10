"""sign-in is on by default.

    Make the schema default `sign_in.enabled: true`. Local mode keeps forcing it off ... A
    file that sets `enabled: false` explicitly on a non-loopback listener keeps today's
    warning. Tests first (`{}`, and a file without `sign_in`, on `0.0.0.0`, both serve with
    sign-in).

On `0.0.0.0` with no TLS configured, "serves with sign-in" shows as the existing plain-HTTP
refusal: sign-in is on, so the console will not listen in clear text beyond
loopback. Before this change the same file started, on every interface, with no sign-in.
"""
from __future__ import annotations

import json

import pytest

from onetrace_console.config import ENV_VAR
from tests.test_local_mode import _FakeServer, _Stop, local_main  # noqa: F401  (fixture)


def _file(tmp_path, monkeypatch, body: dict) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))


def test_an_empty_config_file_serves_with_sign_in(local_main, capsys, tmp_path, monkeypatch):
    """`{}`: the defaults, on loopback, with sign-in on and its stores built."""
    serve_module, _ = local_main
    monkeypatch.chdir(tmp_path)
    _file(tmp_path, monkeypatch, {})
    with pytest.raises(_Stop):
        serve_module.main([])
    assert _FakeServer.address == ("127.0.0.1", 8080)
    assert serve_module.Handler.config.sign_in["enabled"] is True
    assert serve_module.Handler.account_store is not None
    assert "WARNING: sign_in.enabled is false" not in capsys.readouterr().err


@pytest.mark.parametrize("body", [{"host": "0.0.0.0"}, {"host": "0.0.0.0", "sign_in": {}}],
                         ids=["no-sign-in-key", "sign-in-without-enabled"])
def test_a_file_without_sign_in_on_every_interface_is_not_served_open(
        local_main, tmp_path, monkeypatch, body):
    serve_module, _ = local_main
    _file(tmp_path, monkeypatch, {**body, "store_root": (tmp_path / "s").as_posix()})
    assert serve_module.main([]) == 1, "refused in words, never a traceback"
    assert _FakeServer.address is None, "it never listened"


def test_explicitly_off_beyond_loopback_keeps_its_warning(local_main, capsys, tmp_path,
                                                         monkeypatch):
    serve_module, run = local_main
    _file(tmp_path, monkeypatch, {"host": "0.0.0.0", "store_root": (tmp_path / "s").as_posix(),
                                  "sign_in": {"enabled": False}})
    address, err, _ = run(capsys)
    assert address == ("0.0.0.0", 8080)
    assert "WARNING: sign_in.enabled is false" in err


def test_local_mode_still_has_none(local_main, capsys):
    serve_module, run = local_main
    run(capsys)
    assert serve_module.Handler.config.sign_in["enabled"] is False
