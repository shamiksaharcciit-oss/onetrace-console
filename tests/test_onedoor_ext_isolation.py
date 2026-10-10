"""Two checks: a disabled console never imports the extension, and nothing under
`onetrace_console` -- the extension included -- imports `onedoor` itself.

onedoor is headless; the extension is separable and off by default. The hard constraint:
onetrace never depends on onedoor, and the console doesn't either. The extension reads
onedoor's export format. It never imports the onedoor package, at runtime or in tests.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "onetrace_console"

_ONEDOOR_IMPORT = re.compile(r"^\s*(import onedoor\b|from onedoor\b)", re.MULTILINE)


def _post(base: str, path: str, body: bytes = b"") -> tuple[int, bytes]:
    req = urllib.request.Request(base + path, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _files_importing_onedoor(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if _ONEDOOR_IMPORT.search(
        p.read_text(encoding="utf-8")))


# ------------------------------------------------------- check 1: the disabled route

def test_a_disabled_console_never_imports_the_extension(server, examined):
    """`server`'s fixture uses `Config()` -- extensions off by default -- unmodified."""
    base, _ = server
    for name in ("onetrace_console.onedoor_ext", "onetrace_console.onedoor_ext.decisions"):
        sys.modules.pop(name, None)

    examined(1, "POST /v1/decisions sent to a console with the extension disabled")
    status, body = _post(base, "/v1/decisions", b"anything at all")

    assert status == 404, (status, body)
    assert "onetrace_console.onedoor_ext" not in sys.modules, (
        "the disabled route imported the extension package anyway")
    assert "onetrace_console.onedoor_ext.decisions" not in sys.modules, (
        "the disabled route imported the extension's decisions module anyway")


def test_an_enabled_console_does_reach_the_route(server, examined):
    """The other half of the same fact: the gate is a real gate, not a route that
    never existed. Flips `Handler.config` on the SAME running server, calls it once,
    and puts the default config back -- so this test cannot leak into another.
    """
    from onetrace_console.config import Config
    from onetrace_console.serve import Handler

    base, _ = server
    old_config = Handler.config
    Handler.config = Config(extensions={"onedoor": True}, sign_in={**Config().sign_in, "enabled": False})
    try:
        examined(1, "POST /v1/decisions sent to a console with the extension enabled")
        status, _ = _post(base, "/v1/decisions", b"not a real archive")
        assert status == 422, (
            "an enabled console should reach the handler and reject this body as "
            "malformed, not 404 -- 404 would mean the gate is not wired to the config "
            f"at all (got {status})")
    finally:
        Handler.config = old_config


# ------------------------------------------------------------ check 2: no dependency

def test_no_source_file_imports_onedoor(examined):
    files = sorted(SRC.rglob("*.py"))
    examined(len(files), "source files scanned for an onedoor import")
    hits = _files_importing_onedoor(SRC)
    assert hits == [], f"these files import onedoor directly: {hits}"


def test_the_onedoor_import_scan_actually_catches_one(tmp_path, examined):
    """Sabotage of the check above: a planted file that DOES import onedoor, fed to
    the identical scanning function. Proves the scan is not vacuously passing --
    an accidentally-empty `rglob` would pass the real test too, silently.
    """
    bad = tmp_path / "sneaky.py"
    bad.write_text("import onedoor  # noqa\n", encoding="utf-8")
    examined(1, "a planted file importing onedoor")
    hits = _files_importing_onedoor(tmp_path)
    assert hits == [bad], hits


def test_importing_every_module_under_the_console_never_pulls_in_onedoor(examined):
    """The dynamic counterpart to the static scan: actually import every module this
    package has -- the extension included -- and confirm `onedoor` never lands in
    `sys.modules` as a side effect of doing so.
    """
    import onetrace_console

    names = [onetrace_console.__name__]
    for _finder, name, _ispkg in pkgutil.walk_packages(
            onetrace_console.__path__, prefix="onetrace_console."):
        names.append(name)

    examined(len(names), "modules imported under onetrace_console")
    for name in names:
        importlib.import_module(name)

    assert "onedoor" not in sys.modules, (
        "importing every module under onetrace_console pulled onedoor into "
        "sys.modules -- something here depends on it directly")


# ------------------------------------------------------------------------
# The sabotages above must actually RUN, never
# just be argued for. Never against the real gate -- against a temporary copy
# of the tree, broken there, with the real repository's own pinned SDK
# packages (already installed in THIS interpreter) reused rather than
# reinstalled, so this stays fast enough to run on every suite.
# ------------------------------------------------------------------------

def _copy_console_tree(tmp_path: Path) -> Path:
    """`src/`, `tests/` and `pyproject.toml` only -- enough to run one test file
    against a broken copy, reusing this interpreter's already-installed pinned
    packages (`onetrace`, `onetrace-verify`, `canary-viewer`) rather than
    reinstalling them into a throwaway venv per sabotage, which the standing
    rule does not require and would make this check too slow to keep running.
    """
    dst = tmp_path / "console-copy"
    shutil.copytree(REPO / "src", dst / "src")
    shutil.copytree(REPO / "tests", dst / "tests")
    shutil.copy(REPO / "pyproject.toml", dst / "pyproject.toml")
    return dst


def _run_pytest_in_copy(copy_root: Path, node_id: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(copy_root / "src"))
    return subprocess.run(
        [sys.executable, "-m", "pytest", node_id, "-q"],
        cwd=str(copy_root), env=env, capture_output=True, text=True, timeout=120)


def test_sabotage_the_isolation_gate_actually_breaks_the_disabled_import_test(
        tmp_path, examined):
    """Never edits the real `serve.py` -- copies the tree, breaks the COPY's gate
    (the `and self.config.extensions...` clause dropped, so `/v1/decisions`
    always dispatches), and runs the real isolation test against that copy,
    asserting it FAILS. A guard whose sabotage never runs is exactly what the
    standing rule forbids.
    """
    copy_root = _copy_console_tree(tmp_path)
    serve_py = copy_root / "src" / "onetrace_console" / "serve.py"
    text = serve_py.read_text(encoding="utf-8")
    needle = 'elif split.path == "/v1/decisions" and self.config.extensions.get("onedoor"):'
    assert needle in text, "the gate this sabotage targets has moved or been reworded"
    serve_py.write_text(text.replace(needle, 'elif split.path == "/v1/decisions" and True:', 1),
                       encoding="utf-8")

    examined(1, "a broken copy of the console tree, run through its own isolation test")
    result = _run_pytest_in_copy(
        copy_root,
        "tests/test_onedoor_ext_isolation.py::test_a_disabled_console_never_imports_the_extension")

    assert result.returncode != 0, (
        "the isolation test PASSED against a tree whose gate was broken -- the "
        "sabotage did not fire:\n" + result.stdout[-2000:] + result.stderr[-2000:])


def test_sabotage_an_injected_onedoor_import_actually_fails_the_dependency_test(
        tmp_path, examined):
    """Same shape, for the other check: inject a real `import onedoor` line into
    the COPY's extension package and run the static scan against that copy.
    """
    copy_root = _copy_console_tree(tmp_path)
    init_py = copy_root / "src" / "onetrace_console" / "onedoor_ext" / "__init__.py"
    init_py.write_text(init_py.read_text(encoding="utf-8") + "\nimport onedoor  # sabotage\n",
                       encoding="utf-8")

    examined(1, "a copy of the console tree with a real onedoor import injected")
    result = _run_pytest_in_copy(
        copy_root, "tests/test_onedoor_ext_isolation.py::test_no_source_file_imports_onedoor")

    assert result.returncode != 0, (
        "the static-scan test PASSED against a tree with an injected onedoor import -- "
        "the sabotage did not fire:\n" + result.stdout[-2000:] + result.stderr[-2000:])
