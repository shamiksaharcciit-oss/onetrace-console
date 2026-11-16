"""Where the console looks for the `onetrace-explain` command, on each platform.

In order: the interpreter's scripts folder (`sysconfig.get_path("scripts")`), then the folder of the
Python itself; never `PATH` (console 0.8.0): the console uses only its own environment's command, and
a copy on `PATH` alone is not found. A venv's Python sits in its scripts folder beside its commands;
a base Python on Windows keeps its commands in `Scripts\\`, not beside `python.exe`, so only the
first place finds them there. The name is `onetrace-explain.exe` on Windows and `onetrace-explain`
elsewhere.

The platform and every folder are set here, so the same test runs on any machine; a folder standing
for `PATH` holds the command too, and is never searched. The Windows jobs run the real lookup as well.
"""

from __future__ import annotations

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
    """A `which` that keeps to the platform under test: the name as given, in `folder` only (the
    sabotage's PATH)."""

    def which(n: str) -> str | None:
        return str(folder / n) if (folder / n).is_file() else None

    return which


def lookup_problems(tmp: Path, windows: bool) -> list[str]:
    """Lay out a base Python (commands in Scripts, python beside neither) and a folder on `PATH`, then
    take each place away in turn: the lookup must find the first of the interpreter's places that holds
    the command, by its name on that platform, and nothing once neither does, the copy on `PATH`
    still there."""
    from onetrace_console import explain as e

    name, other = NAMES[windows], NAMES[not windows]
    scripts, home, path = tmp / "base" / "Scripts", tmp / "base", tmp / "on-path"
    python = home / ("python.exe" if windows else "python3")
    _put(home, python.name)
    for folder in (scripts, home, path):
        _put(folder, name, other)

    out = []
    for expected in (scripts / name, home / name, None):
        got = e.find(windows, str(scripts), str(python))
        if got != expected:
            out.append(f"{'windows' if windows else 'posix'}: found {got}, expected {expected}")
        if expected is not None:
            expected.unlink()
    return out


@pytest.mark.parametrize("windows", [True, False], ids=["windows", "posix"])
def test_the_lookup_takes_the_scripts_folder_then_the_python_s_and_never_path(tmp_path, windows, examined):
    examined(3, "lookups, each place taken away in turn")
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
    assert seen == [(os.name == "nt", sysconfig.get_path("scripts"), sys.executable)]


@pytest.mark.parametrize("windows", [True, False], ids=["windows", "posix"])
def test_sabotage_the_scripts_folder_taken_out_is_named(tmp_path, monkeypatch, windows, examined):
    from onetrace_console import explain as e

    places = e.places
    monkeypatch.setattr(e, "places", lambda scripts, python: places(None, python))
    examined(1, "lookup without the scripts folder")
    assert lookup_problems(tmp_path, windows) != []


@pytest.mark.parametrize("windows", [True, False], ids=["windows", "posix"])
def test_sabotage_a_path_fallback_put_back_is_named(tmp_path, monkeypatch, windows, examined):
    from onetrace_console import explain as e

    find, on_path = e.find, which_in(tmp_path / "on-path")

    def falling_back(w, scripts, python):
        found = on_path(NAMES[w])
        return find(w, scripts, python) or (Path(found) if found else None)

    monkeypatch.setattr(e, "find", falling_back)
    examined(1, "lookup with PATH put back")
    assert lookup_problems(tmp_path, windows) == [
        f"{'windows' if windows else 'posix'}: found {tmp_path / 'on-path' / NAMES[windows]}, expected None"
    ]
