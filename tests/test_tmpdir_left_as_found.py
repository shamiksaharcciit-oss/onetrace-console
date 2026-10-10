"""The suite leaves `$TMPDIR` as it found it.

`tests/test_incidents.py` and `tests/test_staging.py` each made a store with `tempfile.mkdtemp()`
and never removed it, so every run of the suite left two folders under `$TMPDIR` -- on the
project's own machine a network volume with a quota. Both now use pytest's `tmp_path`, which
lives under the run's own basetemp. Held here by running both modules in a child pytest whose
`$TMPDIR` is a fresh, empty folder, with its basetemp elsewhere, and reading that folder
afterwards.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULES = ("tests/test_incidents.py", "tests/test_staging.py")


def test_the_two_modules_leave_tmpdir_as_they_found_it(tmp_path, examined):
    from tests.test_checks import _require_installed
    _require_installed()
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()
    env = {**os.environ, "TMPDIR": str(tmpdir), "TEMP": str(tmpdir), "TMP": str(tmpdir),
           "PYTHONPATH": os.pathsep.join([str(REPO / "src"), str(REPO)]),
           "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:randomly",
         "-p", "no:xdist", f"--basetemp={tmp_path / 'child-basetemp'}", "-q", *MODULES],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    examined(len(MODULES), "test modules run with their own TMPDIR")
    left = sorted(p.name for p in tmpdir.iterdir())
    assert left == [], f"left under TMPDIR: {left}"
