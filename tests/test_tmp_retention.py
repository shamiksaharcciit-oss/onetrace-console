"""The suite's temporary folders: pyproject.toml sets pytest's `tmp_path_retention_policy = "failed"` and
`tmp_path_retention_count = 1`, so a passing test keeps no `tmp_path` folder, a failing one keeps its folder to be
read, and only the last run's folders are kept.

Checked by running a small suite under this repository's own pytest configuration, in a folder of its own: after a
passing run its basetemp holds no test's folder and stays small; a failing test's folder is kept, by its name; and
with the policy set back to "all", the passing run's folders are found (the sabotage).

What the policy does not clear, a folder made by `tmp_path_factory.mktemp` (the module-scoped fixtures that build
stores and demos), `tests/basetemp_cleanup.py` does: after a run in which every test passed, the basetemp is removed
whole; after a run with a failure, everything is kept to be read.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
#: A passing run's basetemp at most this many bytes: its tests each write 100 kB into their own folder.
SMALL = 64 * 1024
SUITE = """
def test_writes(tmp_path):
    (tmp_path / "a").write_bytes(b"y" * 100_000)


def test_writes_too(tmp_path):
    (tmp_path / "b").write_bytes(b"z" * 100_000)
"""
FAILING = (
    SUITE
    + """

def test_fails(tmp_path):
    (tmp_path / "kept").write_bytes(b"k")
    assert False
"""
)


def _run(tmp: Path, suite: str, config: Path) -> tuple[subprocess.CompletedProcess, Path]:
    (tmp / "test_small_suite.py").write_text(suite, encoding="utf-8")
    basetemp = tmp / "bt"
    got = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q", "-c", str(config),
         "--rootdir", str(tmp), f"--basetemp={basetemp}", str(tmp / "test_small_suite.py")],
        capture_output=True, text=True, timeout=300, cwd=tmp,
    )  # fmt: skip
    return got, basetemp


def _size(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def test_the_suite_keeps_only_a_failed_test_s_folder_and_one_run(examined):
    ini = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    examined(2, "retention settings")
    assert ini["tmp_path_retention_policy"] == "failed"
    assert ini["tmp_path_retention_count"] == 1


def test_a_passing_run_leaves_its_basetemp_small(tmp_path, examined):
    got, basetemp = _run(tmp_path, SUITE, REPO / "pyproject.toml")
    examined(2, "tests in a passing run")
    assert got.returncode == 0, got.stdout + got.stderr
    assert not [p for p in basetemp.iterdir() if p.name.startswith("test_writes")], sorted(basetemp.iterdir())
    assert _size(basetemp) < SMALL, _size(basetemp)


def test_a_failing_test_keeps_its_folder(tmp_path, examined):
    got, basetemp = _run(tmp_path, FAILING, REPO / "pyproject.toml")
    examined(3, "tests in a run with a failure")
    assert got.returncode == 1, got.stdout + got.stderr
    kept = [p.name for p in basetemp.iterdir() if p.is_dir()]
    assert any(n.startswith("test_fails") for n in kept), kept
    assert not any(n.startswith("test_writes") for n in kept), kept
    assert (basetemp / next(n for n in kept if n.startswith("test_fails")) / "kept").is_file()


def test_sabotage_with_every_folder_kept_the_passing_run_s_are_found(tmp_path, examined):
    config = tmp_path / "all.toml"
    config.write_text('[tool.pytest.ini_options]\ntmp_path_retention_policy = "all"\n', encoding="utf-8")
    got, basetemp = _run(tmp_path, SUITE, config)
    examined(1, "a planted policy")
    assert got.returncode == 0, got.stdout + got.stderr
    assert [p for p in basetemp.iterdir() if p.name.startswith("test_writes")]
    assert _size(basetemp) >= SMALL


FACTORY = (
    SUITE
    + """

import pytest


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = tmp_path_factory.mktemp("store")
    (folder / "big").write_bytes(b"s" * 100_000)
    return folder


def test_reads_a_built_store(built):
    assert (built / "big").stat().st_size == 100_000
"""
)
#: The small suite's conftest: the repository's own hook, loaded by its path, as the suite's conftest takes it.
CLEANUP = f"""
import importlib.util

_spec = importlib.util.spec_from_file_location("basetemp_cleanup", {str(REPO / "tests" / "basetemp_cleanup.py")!r})
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
pytest_sessionfinish = _module.pytest_sessionfinish
"""


def test_a_passing_run_keeps_no_temporary_folder_a_fixture_s_among_them(tmp_path, examined):
    (tmp_path / "conftest.py").write_text(CLEANUP, encoding="utf-8")
    got, basetemp = _run(tmp_path, FACTORY, REPO / "pyproject.toml")
    examined(3, "tests in a passing run, one reading a fixture's folder")
    assert got.returncode == 0, got.stdout + got.stderr
    assert not basetemp.exists(), sorted(basetemp.rglob("*"))
    assert "basetemp removed: every test passed" in got.stdout


def test_a_run_with_a_failure_keeps_everything_to_be_read(tmp_path, examined):
    (tmp_path / "conftest.py").write_text(CLEANUP, encoding="utf-8")
    got, basetemp = _run(tmp_path, FACTORY + FAILING[len(SUITE) :], REPO / "pyproject.toml")
    examined(4, "tests in a run with a failure")
    assert got.returncode == 1, got.stdout + got.stderr
    kept = [p.name for p in basetemp.iterdir() if p.is_dir()]
    assert any(n.startswith("store") for n in kept) and any(n.startswith("test_fails") for n in kept), kept


def test_sabotage_without_the_hook_a_fixture_s_folder_is_found(tmp_path, examined):
    got, basetemp = _run(tmp_path, FACTORY, REPO / "pyproject.toml")
    examined(1, "a passing run with no hook")
    assert got.returncode == 0, got.stdout + got.stderr
    assert [p for p in basetemp.iterdir() if p.name.startswith("store")]


def test_the_suite_s_own_conftest_takes_the_hook(examined):
    from tests import basetemp_cleanup

    examined(1, "the suite's conftest")
    assert "basetemp_cleanup" in (REPO / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert callable(basetemp_cleanup.pytest_sessionfinish)
