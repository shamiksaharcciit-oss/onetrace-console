"""The command a page prints to regenerate itself works as printed.

A run's answer and case pages end with the command that regenerates them. The viewer is
`onetrace_console.viewer`, so the command must name that module: run as the page prints it, with the
two placeholders filled in, it writes the same two pages again.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from html import unescape
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
#: The reference demo's day-1 run. Since 0.1.1 the package ships no runs (the demo store builds
#: them), so the committed copy in examples/ is read: the same bytes the package carried.
RUN = REPO / "examples" / "reference-demo" / "runs" / "day-1"


def _generate(cwd: Path, argv: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-B", *argv], cwd=cwd, capture_output=True, text=True, env=env)


def test_the_printed_command_regenerates_the_pages(tmp_path, examined):
    shutil.copytree(RUN, tmp_path / "run")
    first = _generate(tmp_path, ["-m", "onetrace_console.viewer", "generate", "run", "--cli", "--out", "first"])
    assert first.returncode == 0, first.stderr[-2000:]
    page = unescape((tmp_path / "first" / "answer.html").read_text(encoding="utf-8"))
    printed = re.findall(r"python -m \S+ generate RUN_FOLDER [^<]*?OUT_FOLDER", page)
    examined(len(printed), "regenerate commands printed on the page")
    assert printed, "the page prints no regenerate command"
    for command in set(printed):
        assert command.startswith("python -m onetrace_console.viewer "), command
        argv = command.split()[1:]
        argv = ["run" if a == "RUN_FOLDER" else "again" if a == "OUT_FOLDER" else a for a in argv]
        again = _generate(tmp_path, argv)
        assert again.returncode == 0, (command, again.stderr[-2000:])
        assert (tmp_path / "again" / "answer.html").is_file() and (tmp_path / "again" / "case.html").is_file()


def test_the_viewer_s_help_names_its_module(examined):
    out = _generate(REPO, ["-m", "onetrace_console.viewer", "--help"])
    examined(1, "help text")
    assert out.returncode == 0 and out.stdout.startswith("usage: python -m onetrace_console.viewer "), out.stdout[:200]
