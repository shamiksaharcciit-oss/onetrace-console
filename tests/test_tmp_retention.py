"""The suite's temporary folders: pyproject.toml sets pytest's `tmp_path_retention_policy = "failed"` and
`tmp_path_retention_count = 1`, so a passing test keeps no `tmp_path` folder, a failing one keeps its folder to be
read, and only the last run's folders are kept.

Checked by running a small suite under this repository's own pytest configuration, in a folder of its own: after a
passing run its basetemp holds no test's folder and stays small; a failing test's folder is kept, by its name; and
with the policy set back to "all", the passing run's folders are found (the sabotage).

What the policy does not clear: a folder made by `tmp_path_factory.mktemp` (the module-scoped fixtures that build
stores and demos) stays to the end of the run, as the suite's `--basetemp` is given.
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
