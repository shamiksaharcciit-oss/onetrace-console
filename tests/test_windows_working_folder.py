"""Windows' longest working folder for a new process, measured on this machine.

The console starts each process it runs in a working folder it names (`subprocess.run(...,
cwd=...)`), and CreateProcess refuses a working folder past its limit with error 267
(ERROR_DIRECTORY), long paths on or off. tests/test_explain_paths.py holds the explanation layout
to `WORKING_FOLDER_MOST`; this test measures the limit itself, a process started in each working
folder from ten characters under it to ten over. The folders are made through the `\\\\?\\` prefix, so
long paths off does not stop their making; the starts are given them as the console gives them,
with no prefix.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tests.test_explain_paths import ERROR_DIRECTORY, WORKING_FOLDER_MOST

TRIED = range(WORKING_FOLDER_MOST - 10, WORKING_FOLDER_MOST + 11)


def _long_paths() -> str:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            return str(winreg.QueryValueEx(k, "LongPathsEnabled")[0])
    except OSError as e:
        return f"unreadable ({e})"


@pytest.mark.skipif(os.name != "nt", reason="CreateProcess's limit is Windows' own; nothing to measure elsewhere")
def test_a_process_starts_in_a_working_folder_up_to_the_limit_and_not_past_it(tmp_path, examined):
    base = str(tmp_path)
    if TRIED[-1] - len(base) - 1 > 255:
        pytest.fail(f"the test's temporary folder is {len(base)} characters, too short for one folder name "
                    f"to reach {TRIED[-1]}")
    if TRIED[0] - len(base) - 1 < 1:
        pytest.fail(f"the test's temporary folder is {len(base)} characters, too long to try {TRIED[0]}")
    started, refused = [], {}
    made = []
    try:
        for n in TRIED:
            folder = base + "\\" + "w" * (n - len(base) - 1)
            assert len(folder) == n
            os.mkdir("\\\\?\\" + folder)
            made.append(folder)
            try:
                subprocess.run([sys.executable, "-c", "pass"], cwd=folder, check=True, timeout=120,
                               capture_output=True)
                started.append(n)
            except OSError as e:
                refused[n] = f"{type(e).__name__}, winerror {getattr(e, 'winerror', None)}"
    finally:
        for folder in made:
            os.rmdir("\\\\?\\" + folder)
    longest = max(started) if started else None
    said = (f"LongPathsEnabled {_long_paths()}: started in {started}; refused {refused}; the longest "
            f"working folder a process started in, {longest} characters")
    print(said)
    examined(len(TRIED), f"working folder lengths tried, LongPathsEnabled {_long_paths()}")
    assert started == [n for n in TRIED if n <= WORKING_FOLDER_MOST], said
    assert set(refused) == {n for n in TRIED if n > WORKING_FOLDER_MOST}, said
    assert all(f"winerror {ERROR_DIRECTORY}" in r for r in refused.values()), said
