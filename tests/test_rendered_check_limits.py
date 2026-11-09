"""The rendered checks stop at a limit of their own, and say so on their summary line.

`tools/layout_check.py` and `tools/explain_look_check.py` each start consoles and a browser and wait on
them. A wait that never ends -- a browser that stalls, a console that never starts -- once held a gate for
over an hour, with nothing on the check's output. Each check now takes `--timeout` seconds for the whole
run (each step it waits on gets what is left), and any way it stops short -- its limit, a console that did
not start, a step that failed -- is said on its summary line, on its output, and it ends with exit 2.

Held with a stand-in for the console's Python that never starts a console (a POSIX shell script, so
these run where there is one).
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in is a POSIX shell script")


@pytest.fixture
def never_starts(tmp_path) -> Path:
    """A 'Python' that, run as anything, waits ten minutes and does nothing."""
    p = tmp_path / "never-starts"
    p.write_text("#!/bin/sh\nexec sleep 600\n", encoding="utf-8")
    p.chmod(0o755)
    return p


def _run(tool: str, *args: str) -> tuple[subprocess.CompletedProcess, float]:
    start = time.monotonic()
    done = subprocess.run([sys.executable, "-B", f"tools/{tool}", *args], cwd=REPO, capture_output=True, text=True,
                          timeout=180)
    return done, time.monotonic() - start


@pytest.mark.parametrize("tool, name, extra", [
    ("layout_check.py", "layout check", []),
    ("explain_look_check.py", "explain look check", ["--local-python"]),
])
def test_a_check_stops_at_its_own_limit_and_says_so_on_its_summary_line(never_starts, tool, name, extra, examined):
    args = ["--console-python", str(never_starts), "--browser-python", str(never_starts), "--theme", "dark",
            "--timeout", "5"] + ([extra[0], str(never_starts)] if extra else [])
    done, took = _run(tool, *args)
    examined(1, f"{name} run against a console that never starts")
    assert done.returncode == 2, (done.returncode, done.stdout[-1500:], done.stderr[-1500:])
    last = done.stdout.strip().splitlines()[-1]
    assert last.startswith(f"{name} (dark): no page views judged, FAILED: "), done.stdout[-1500:]
    assert "5 s" in last, last
    assert took < 120, took
