"""The gate's lint stage, `tools/lint_check.py`: `ruff check`, `ruff format --check` and `mypy`, each as pyproject.toml
configures them, run in turn with the versions the test requirements pin; the stage fails on any finding of any of the
three, and its summary line names each one's result. On this tree it passes; a planted lint finding, a planted
unformatted file and a planted type error each fail it, by name. The tool writes no cache into the tree it reads.

The public export leaves the tool out: there these tests skip; here a missing one fails.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.export_tree import tool

REPO = Path(__file__).resolve().parent.parent
#: What the stage reads: the Python sources and the configuration, never the stores or the caches.
SKIP = {
    ".git",
    "store",
    ".pytest-basetemp",
    "__pycache__",
    ".wheel-cache",
    ".sdk-fixtures",
    ".ruff_cache",
    ".mypy_cache",
}


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(tool("lint_check.py")), str(root)], capture_output=True, text=True, timeout=900
    )


def _copy(dest: Path) -> Path:
    """The Python files and pyproject.toml, at their own paths."""

    def ignored(folder, names):
        return [n for n in names if n in SKIP or (Path(folder, n).is_file() and not n.endswith((".py", ".toml")))]

    shutil.copytree(REPO, dest, ignore=ignored)
    return dest


def test_this_tree_passes_and_writes_no_cache_into_it(examined):
    before = {p.name for p in REPO.iterdir()}
    got = _run(REPO)
    examined(3, "lint stages")
    assert got.returncode == 0, got.stdout + got.stderr
    assert "lint: ruff check passed; ruff format --check passed; mypy passed" in got.stdout
    assert {p.name for p in REPO.iterdir()} - before == set()


@pytest.mark.parametrize(
    "plant, stage",
    [
        (("tools/visible_text.py", "\nimport os\n"), "ruff check"),
        (("src/onetrace_console/words.py", "\nX = {  'a':1}\n"), "ruff format --check"),
        (("src/onetrace_console/words.py", '\nPLANTED: int = "not a number"\n'), "mypy"),
    ],
    ids=["a lint finding", "an unformatted line", "a type error"],
)
def test_sabotage_each_kind_of_finding_fails_the_stage_by_name(tmp_path, plant, stage, examined):
    tree = _copy(tmp_path / "tree")
    rel, text = plant
    with (tree / rel).open("a", encoding="utf-8") as f:
        f.write(text)
    got = _run(tree)
    examined(1, f"planted: {stage}")
    assert got.returncode == 1, got.stdout + got.stderr
    assert f"{stage} FAILED" in got.stdout, got.stdout
    assert rel in got.stdout, got.stdout


def test_the_linux_check_runs_the_stage_after_the_pins_and_before_the_suite(examined):
    """The private CI's Linux check runs the stage on the commit pushed, with the test tools and the console's
    pins installed (mypy reads them), before the suite; a finding fails the step, so the job. The public export
    leaves the private CI's workflows out: there this test skips."""
    from tests.export_tree import is_public_export

    if is_public_export():
        pytest.skip("the public export leaves .github/workflows/linux-check.yml out")
    text = (REPO / ".github" / "workflows" / "linux-check.yml").read_text(encoding="utf-8")
    examined(1, "the Linux check's steps")
    steps = text.split("\n      - name: ")
    lint = [i for i, s in enumerate(steps) if "python tools/lint_check.py" in s]
    assert len(lint) == 1, "the Linux check runs the lint stage once"
    (at,) = lint
    order = {
        name: next(i for i, s in enumerate(steps) if s.startswith(name))
        for name in ("The test tools", "The console's pins", "The full suite")
    }
    assert order["The test tools"] < at and order["The console's pins"] < at < order["The full suite"]
    assert "continue-on-error" not in steps[at]
