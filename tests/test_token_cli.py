"""Token create/revoke, CLI-only -- the same shape as `admin
create`. The raw token is printed exactly once, never persisted.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from onetrace_console.__main__ import main as cli_main
from onetrace_console.config import ENV_VAR
from onetrace_console.serve import TOKENS_DIRNAME

REPO = Path(__file__).resolve().parent.parent


def _configured(monkeypatch, tmp_path, store_root: Path | None = None) -> Path:
    store_root = store_root or (tmp_path / "store")
    config_path = tmp_path / "config.json"
    config_path.write_text(f'{{"store_root": "{store_root.as_posix()}"}}', encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config_path))
    return store_root


def test_token_create_prints_the_raw_token_once_and_stores_only_a_hash(
        tmp_path, monkeypatch, capsys, examined):
    from onetrace_console.ingester_tokens import TokenStore

    store_root = _configured(monkeypatch, tmp_path)
    examined(2, "the CLI's own stdout, and the persisted token record")
    rc = cli_main(["token", "create", "ci-pipeline"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "token id:" in out
    assert "token (shown once" in out

    token_id = out.splitlines()[0].split(": ", 1)[1]
    raw = out.splitlines()[1].split(": ", 1)[1]

    tokens = TokenStore(store_root / TOKENS_DIRNAME)
    assert tokens.principal_for(raw) == "ci-pipeline"
    on_disk = (store_root / TOKENS_DIRNAME / f"{token_id}.json").read_text(encoding="utf-8")
    assert raw not in on_disk


def test_token_revoke_makes_it_stop_resolving(tmp_path, monkeypatch, capsys, examined):
    from onetrace_console.ingester_tokens import TokenStore

    store_root = _configured(monkeypatch, tmp_path)
    cli_main(["token", "create", "ci-pipeline"])
    out = capsys.readouterr().out
    token_id = out.splitlines()[0].split(": ", 1)[1]
    raw = out.splitlines()[1].split(": ", 1)[1]

    examined(2, "the token, before and after revoke")
    tokens = TokenStore(store_root / TOKENS_DIRNAME)
    assert tokens.principal_for(raw) == "ci-pipeline"
    rc = cli_main(["token", "revoke", token_id])
    assert rc == 0
    tokens = TokenStore(store_root / TOKENS_DIRNAME)  # re-read from disk
    assert tokens.principal_for(raw) is None


def test_token_revoke_of_an_unknown_id_is_a_usage_failure(tmp_path, monkeypatch, examined):
    _configured(monkeypatch, tmp_path)
    examined(1, "a revoke against an id that was never created")
    rc = cli_main(["token", "revoke", "does-not-exist"])
    assert rc == 1


def test_no_route_in_serve_py_creates_or_revokes_a_token(examined):
    """Same shape as `test_admin_cli.py`'s own check: read the real source, scan
    for anything that would create or revoke a token over HTTP.
    """
    source = (REPO / "src" / "onetrace_console" / "serve.py").read_text(encoding="utf-8")
    examined(1, "serve.py's own source, scanned for a token route")
    assert '"/token' not in source
    assert "def _handle_token" not in source


def test_sabotage_a_token_route_added_to_a_copy_makes_the_no_route_test_fail(tmp_path, examined):
    """Same discipline as `test_admin_cli.py`'s own sabotage: never against the
    real tree, a copy with a token-creating web route added, the real check run
    as a subprocess against it, must fail.
    """
    copy_root = tmp_path / "console-copy"
    shutil.copytree(REPO / "src", copy_root / "src")
    shutil.copytree(REPO / "tests", copy_root / "tests")
    shutil.copy(REPO / "pyproject.toml", copy_root / "pyproject.toml")

    serve_py = copy_root / "src" / "onetrace_console" / "serve.py"
    text = serve_py.read_text(encoding="utf-8")
    needle = 'elif split.path == "/signin" and self.config.sign_in.get("enabled"):'
    assert needle in text, "the anchor this sabotage inserts beside has moved or been reworded"
    sabotaged = text.replace(
        needle,
        'elif split.path == "/token-create":\n'
        '                self._handle_token_create(body)  # sabotage: a web route for tokens\n'
        '            ' + needle,
        1)
    serve_py.write_text(sabotaged, encoding="utf-8")

    examined(1, "a copy of serve.py with a token route inserted, run through the real test")
    env = dict(__import__("os").environ, PYTHONPATH=str(copy_root / "src"))
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_token_cli.py::test_no_route_in_serve_py_creates_or_revokes_a_token", "-q"],
        cwd=str(copy_root), env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0, (
        "the no-token-route test PASSED against a tree with a token route added -- "
        "the sabotage did not fire:\n" + result.stdout[-2000:] + result.stderr[-2000:])
