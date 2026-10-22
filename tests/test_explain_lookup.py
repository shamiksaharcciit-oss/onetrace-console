"""Where the console looks for the `onetrace-explain` command, on each platform.

In order: the interpreter's scripts folder (`sysconfig.get_path("scripts")`), the folder of the
Python itself, then `shutil.which`. A venv's Python sits in its scripts folder beside its commands;
a base Python on Windows keeps its commands in `Scripts\\`, not beside `python.exe`, so only the
first place finds them there. The name is `onetrace-explain.exe` on Windows and `onetrace-explain`
elsewhere.

The platform and every folder are set here, and so is `which`: the test's own, keeping to the
platform under test, so the same test runs on any machine. The host's `shutil.which` would not: on
Windows it tries PATHEXT, and finds `onetrace-explain.exe` for the POSIX name. The Windows jobs run
the real lookup as well.
"""
from __future__ import annotations

import shutil
import stat
from pathlib import Path

import pytest

NAMES = {True: "onetrace-explain.exe", False: "onetrace-explain"}


def _put(folder: Path, *names: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        p = folder / name
        p.write_bytes(b"")
        p.chmod(p.stat().st_mode | stat.S_IXUSR)


def which_in(folder: Path):
    """A `which` that keeps to the platform under test: the name as given, in `folder` only."""
    def which(n: str) -> str | None:
        return str(folder / n) if (folder / n).is_file() else None
    return which


def pathext_which_in(folder: Path):
    """A `which` as Windows' is: each PATHEXT extension tried on the name, then the name itself."""
    def which(n: str) -> str | None:
        return next((str(folder / c) for c in (n + ".exe", n) if (folder / c).is_file()), None)
    return which


def lookup_problems(tmp: Path, windows: bool, which_for=which_in) -> list[str]:
    """Lay out a base Python (commands in Scripts, python beside neither), then take each place
    away in turn: the lookup must find the first place that holds the command, by its name on that
    platform, and nothing once none does."""
    from onetrace_console import explain as e
    name, other = NAMES[windows], NAMES[not windows]
    scripts, home, path = tmp / "base" / "Scripts", tmp / "base", tmp / "on-path"
    python = home / ("python.exe" if windows else "python3")
    _put(home, python.name)
    for folder in (scripts, home, path):
        _put(folder, name, other)

    which = which_for(path)
    out = []
    for expected in (scripts / name, home / name, path / name, None):
        got = e.find(windows, str(scripts), str(python), which)
        if got != expected:
            out.append(f"{'windows' if windows else 'posix'}: found {got}, expected {expected}")
        if expected is not None:
            expected.unlink()
    return out


@pytest.mark.parametrize("windows", [True, False], ids=["windows", "posix"])
def test_the_lookup_takes_the_scripts_folder_then_the_python_s_then_path(tmp_path, windows, examined):
    examined(4, "lookups, each place taken away in turn")
    assert lookup_problems(tmp_path, windows) == []


def test_the_real_lookup_reads_this_interpreter_s_folders(monkeypatch, examined):
    """`command()` hands `find` this platform, this interpreter's scripts folder and its Python."""
    import os
    import sys
    import sysconfig
    from onetrace_console import explain as e
    seen = []
    monkeypatch.setattr(e, "find", lambda *a: seen.append(a))
    e.command()
    examined(1, "call of find")
    assert seen == [(os.name == "nt", sysconfig.get_path("scripts"), sys.executable, shutil.which)]


@pytest.mark.parametrize("windows", [True, False], ids=["windows", "posix"])
def test_sabotage_the_scripts_folder_taken_out_is_named(tmp_path, monkeypatch, windows, examined):
    from onetrace_console import explain as e
    places = e.places
    monkeypatch.setattr(e, "places", lambda scripts, python: places(None, python))
    examined(1, "lookup without the scripts folder")
    assert lookup_problems(tmp_path, windows) != []


def test_sabotage_a_pathext_which_in_the_posix_case_is_named(tmp_path, examined):
    examined(4, "lookups with a PATHEXT-style which")
    assert lookup_problems(tmp_path, False, pathext_which_in) == [
        f"posix: found {tmp_path / 'on-path' / 'onetrace-explain.exe'}, expected {tmp_path / 'on-path' / 'onetrace-explain'}",
        f"posix: found {tmp_path / 'on-path' / 'onetrace-explain.exe'}, expected None"]
