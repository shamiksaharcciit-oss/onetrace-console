"""A press's work with the command's report folder and its output files, whatever the file system does.

- **The run a press watches is the first new one by name.** While the command runs, the press looks for the run it is
  making, to say its step; after, it takes its step times from that run's receipts. Both take the same run: the first
  of the new runs by name, never the first a listing gives, since a file system may list a folder in any order.
- **A press ends, and keeps its attempt, even where its output files cannot be removed.** On Windows a file another
  process still holds cannot be removed: a child the command started can still hold its output after it stops.
  Removing them is tidying only; the next press writes them again.

The command is a stand-in for `subprocess.Popen` that makes the report's runs as the command would; nothing is started
and no model is called.
"""

from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

import pytest

KEY = "e" * 64


def _press(tmp_path, monkeypatch, made: dict[str, list[str]]):
    """One press, the stand-in command making `made`'s runs (a run's name to its receipts' names) as it starts; the
    steps it said, and the folder."""
    from onetrace_console import explain
    from onetrace_console.store import Store

    store = Store(tmp_path / "store")
    folder = explain.folder_of(store, KEY)
    folder.mkdir(parents=True)
    explain._set_state(folder, {"kind": "explain", "step": "preparing"})
    said: list[str] = []
    real_set_state = explain._set_state

    def set_state(f, s):
        said.append(s["step"])
        real_set_state(f, s)

    class Command:
        """The command: its runs made, running for one look, then ended with exit 0."""

        def __init__(self, args, *, cwd, stdout, **_kw):
            self.stdin, self.returncode, self.looks = None, None, 0
            for run, receipts in made.items():
                (pathlib.Path(cwd) / explain.REPORT / "explain" / run / "receipts").mkdir(parents=True)
                for name in receipts:
                    (pathlib.Path(cwd) / explain.REPORT / "explain" / run / "receipts" / name).write_text("{}")
            stdout.write(b"done\n")

        def poll(self):
            self.looks += 1
            self.returncode = None if self.looks == 1 else 0
            return self.returncode

    monkeypatch.setattr(explain, "_prepare", lambda comparison, store, folder: None)
    monkeypatch.setattr(explain, "_set_state", set_state)
    monkeypatch.setattr(explain, "command", lambda: pathlib.Path("onetrace-explain"))
    monkeypatch.setattr(explain.subprocess, "Popen", Command)
    explain._press(SimpleNamespace(key=KEY), store, folder, False)
    return said, folder


@pytest.mark.parametrize("order", ["as listed", "reversed"])
def test_the_run_a_press_watches_is_the_first_new_one_by_name(tmp_path, monkeypatch, order, examined):
    #: Two new runs: the first by name holds the evidence's receipt, the other none. Listed either way, the press
    #: watches the first by name and says the step its receipt shows.
    listing = pathlib.Path.iterdir
    if order == "reversed":
        monkeypatch.setattr(pathlib.Path, "iterdir", lambda self: iter(sorted(listing(self), reverse=True)))
    else:
        monkeypatch.setattr(pathlib.Path, "iterdir", lambda self: iter(sorted(listing(self))))
    said, _folder = _press(
        tmp_path, monkeypatch, {"20260101T000000Z-a": ["01-evidence.json"], "20260101T000000Z-b": []}
    )
    examined(1, f"press, its runs listed {order}")
    assert "waiting" in said, said


def test_a_press_ends_and_keeps_its_attempt_where_its_output_files_cannot_be_removed(tmp_path, monkeypatch, examined):
    removed: list[str] = []
    unlink = pathlib.Path.unlink

    def held(self, missing_ok=False):
        if self.name in (".stdout", ".stderr"):
            removed.append(self.name)
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(pathlib.Path, "unlink", held)
    _said, folder = _press(tmp_path, monkeypatch, {"20260101T000000Z-a": ["01-evidence.json"]})
    examined(1, "press whose output files are held")
    attempt = json.loads((folder / "attempts" / "000001.json").read_text(encoding="utf-8"))
    assert attempt["exit"] == "0" and attempt["stdout"] == "done\n"
    #: Each file is tried, the second though the first could not be removed.
    assert removed == [".stdout", ".stderr"]
