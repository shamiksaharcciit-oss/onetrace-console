"""The first admin, created inside the container. The password is
read from stdin, never argv or an environment variable; the web never creates accounts.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import sys
from pathlib import Path

from onetrace_console.__main__ import main as cli_main
from onetrace_console.config import ENV_VAR
from onetrace_console.serve import ACCOUNTS_DIRNAME

REPO = Path(__file__).resolve().parent.parent


def _run_admin_create(monkeypatch, tmp_path, username: str, password: str,
                      store_root: Path | None = None) -> tuple[int, str]:
    store_root = store_root or (tmp_path / "store")
    config_path = tmp_path / "config.json"
    config_path.write_text(f'{{"store_root": "{store_root.as_posix()}"}}', encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(password + "\n"))
    rc = cli_main(["admin", "create", username])
    return rc, str(store_root)


def test_admin_create_reads_the_password_from_stdin(tmp_path, monkeypatch, examined):
    from onetrace_console.accounts import AccountStore

    rc, store_root = _run_admin_create(monkeypatch, tmp_path, "alice", "a real password")
    examined(1, "admin create runs, then the account is checked directly")
    assert rc == 0
    accounts = AccountStore(Path(store_root) / ACCOUNTS_DIRNAME)
    assert accounts.verify_password("alice", b"a real password") is True


def test_admin_create_never_accepts_the_password_as_an_argument(tmp_path, monkeypatch, examined):
    """The CLI's own usage is `admin create <username>` -- exactly one positional
    argument beside the subcommand. Passing a second one (an attempted password
    argument) is refused as a usage error, not read as a password.
    """
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))
    examined(1, "an admin create invocation with a second positional argument")
    rc = cli_main(["admin", "create", "alice", "a-password-typed-as-an-argument"])
    assert rc == 2


def test_admin_create_ignores_any_password_looking_environment_variable(
        tmp_path, monkeypatch, examined):
    """There is no environment variable this CLI reads a password from at all --
    checked by setting one with a plausible name and confirming stdin is still what
    is read, not the environment.
    """
    from onetrace_console.accounts import AccountStore

    monkeypatch.setenv("ONETRACE_CONSOLE_ADMIN_PASSWORD", "from-the-environment")
    rc, store_root = _run_admin_create(monkeypatch, tmp_path, "alice", "from-stdin-instead")
    examined(1, "an account created with an env var set to a different password")
    assert rc == 0
    accounts = AccountStore(Path(store_root) / ACCOUNTS_DIRNAME)
    assert accounts.verify_password("alice", b"from-stdin-instead") is True
    assert accounts.verify_password("alice", b"from-the-environment") is False


def test_no_route_in_serve_py_creates_an_account(examined):
    """Read the real source directly: no `do_POST` branch names anything that would
    create a user. This is what the sabotage below actually exercises.
    """
    source = (REPO / "src" / "onetrace_console" / "serve.py").read_text(encoding="utf-8")
    examined(1, "serve.py's own source, scanned for a signup route")
    assert '"/signup"' not in source
    assert "def _handle_signup" not in source


def test_sabotage_a_signup_route_added_to_a_copy_makes_the_no_route_test_fail(tmp_path, examined):
    """Never against the real `serve.py` -- copies the tree (source AND this test
    file, so `REPO` in the copy resolves to the copy's own path), adds a signup
    route, and runs `test_no_route_in_serve_py_creates_an_account` as a real pytest
    subprocess against that copy. It must fail.
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
        'elif split.path == "/signup":\n'
        '                self._handle_signup(body)  # sabotage: a web route that creates a user\n'
        '            ' + needle,
        1)
    serve_py.write_text(sabotaged, encoding="utf-8")

    examined(1, "a copy of serve.py with a signup route inserted, run through the real test")
    env = dict(__import__("os").environ, PYTHONPATH=str(copy_root / "src"))
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_admin_cli.py::test_no_route_in_serve_py_creates_an_account", "-q"],
        cwd=str(copy_root), env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0, (
        "the no-signup-route test PASSED against a tree with a signup route added -- "
        "the sabotage did not fire:\n" + result.stdout[-2000:] + result.stderr[-2000:])
