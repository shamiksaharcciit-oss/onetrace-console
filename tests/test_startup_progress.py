"""Console 0.6.1 item 5: progress while the console starts.

One line per phase on stderr, flushed as it happens, each with its count and time: recording the
demo's runs, checking runs, comparing pairs, drawing pages, then the address. A count line updates in
place on a terminal and is one line per step otherwise. The first line is said at once; a later demo
start that reuses `onetrace-console-demo/` says so. `--quiet` keeps the old silence.
"""
from __future__ import annotations

import io
import sys
import re
from pathlib import Path

import pytest

from onetrace_console import startup_progress as sp

SPECS = ("p4-29-reply-30-days", "p4-30-reply-14-days", "p7-39-cold-chain-baseline")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_not_a_terminal_each_step_is_a_line_and_the_end_says_the_time():
    out, clock = io.StringIO(), Clock()
    p = sp.Progress(out, tty=False, clock=clock)
    p.say("starting: here")
    with p.phase("checking runs", 3) as step:
        for _ in range(3):
            step()
        clock.t = 12.4
    assert out.getvalue().splitlines() == [
        "starting: here", "checking runs: 0 of 3", "checking runs: 1 of 3", "checking runs: 2 of 3",
        "checking runs: 3 of 3", "checking runs: 3 of 3, 12 s"]
    assert "\r" not in out.getvalue()


def test_on_a_terminal_the_count_updates_in_place_and_ends_its_line():
    out, clock = io.StringIO(), Clock()
    p = sp.Progress(out, tty=True, clock=clock)
    with p.phase("comparing pairs", 2) as step:
        step()
        step()
        clock.t = 0.3
    p.say("next")
    text = out.getvalue()
    assert text == ("\rcomparing pairs: 0 of 2\x1b[K\rcomparing pairs: 1 of 2\x1b[K\rcomparing pairs: 2 of 2\x1b[K"
                    "\rcomparing pairs: 2 of 2, under 1 s\x1b[K\nnext\n")


def test_a_line_said_mid_phase_on_a_terminal_starts_on_its_own_line():
    out = io.StringIO()
    p = sp.Progress(out, tty=True, clock=Clock())
    with p.phase("drawing pages", 5) as step:
        step()
        p.say("onetrace-console: took in a run")
    assert "\x1b[K\nonetrace-console: took in a run\n" in out.getvalue()


def test_with_nothing_set_up_the_phases_say_nothing(capsys):
    with sp.phase("checking runs", 2) as step:
        step()
    sp.say("x")
    assert capsys.readouterr().err == ""


def test_the_demos_record_phase_counts_pipelines_and_runs(tmp_path, monkeypatch):
    from onetrace_console import demo_store
    out, clock = io.StringIO(), Clock()
    specs = [s for s in demo_store.runs() if s.folder in SPECS]
    monkeypatch.setattr(demo_store, "runs", lambda: specs)
    for name in ("write_traces", "write_build_record"):
        monkeypatch.setattr(demo_store, name, lambda *a, **k: None)
    monkeypatch.setattr(demo_store.app_traces, "write", lambda *a, **k: None)
    with sp.using(sp.Progress(out, tty=False, clock=clock)):
        demo_store.build(tmp_path / "demo")
    lines = out.getvalue().splitlines()
    assert lines[0] == "recording the demo's runs: 0 of 3"
    assert lines[-1] == "recording the demo's runs: 2 pipelines … 3 runs, under 1 s"


# ------------------------------------------------------------------ the command, start to address

@pytest.fixture
def runs_folder(tmp_path_factory) -> Path:
    from tests.test_checks import _require_installed
    from tests.test_neighbours import _record
    _require_installed()
    folder = tmp_path_factory.mktemp("progress-runs")
    _record(SPECS, folder)
    return folder


@pytest.fixture
def served(monkeypatch, tmp_path):
    """`serve.main` as far as its address: prepare, draw the pages, print the address; no listening."""
    import onetrace_console.serve as serve
    from onetrace_console.config import Config
    from onetrace_console.store import Store
    seen = {}

    def main(argv, *, overrides=None, prepare=None, open_browser=False, watch=None, **_):
        root = Path((overrides or {}).get("store_root") or tmp_path / "store")
        root.mkdir(parents=True, exist_ok=True)
        store = Store(root / "store")
        config = Config(sign_in={**Config().sign_in, "enabled": False})
        ready = prepare(store, config) if prepare else ([], "")
        serve._render_startup_pages(store, root, config)
        print("onetrace-console: listening on http://127.0.0.1:0", flush=True)
        seen["ready"] = ready
        return 0
    monkeypatch.setattr(serve, "main", main)
    monkeypatch.chdir(tmp_path)
    return seen


def test_a_runs_folder_says_its_phases_in_order_with_counts(runs_folder, served, capsys):
    from onetrace_console.folder_load import main
    assert main([str(runs_folder), "--no-watch", "--compare", SPECS[0], SPECS[1]], demo=False) == 0
    err = capsys.readouterr().err
    phases = [line.split(":")[0] for line in err.splitlines() if not line.startswith("onetrace-console")]
    assert phases[0] == "starting" and err.splitlines()[0] == f"starting: loading the runs in {runs_folder}"
    order = [p for i, p in enumerate(phases) if p != "starting" and (i == 0 or phases[i - 1] != p)]
    assert order == ["checking runs", "comparing pairs", "drawing pages"], order
    assert re.search(r"^checking runs: 3 of 3, (under 1 s|\d+ s)$", err, re.M)
    assert re.search(r"^comparing pairs: 1 of 1, (under 1 s|\d+ s)$", err, re.M)
    #: Three runs, one comparison, and the pages over them all.
    assert re.search(r"^drawing pages: 5 of 5, (under 1 s|\d+ s)$", err, re.M)


def test_quiet_keeps_the_silence(runs_folder, served, capsys):
    from onetrace_console.folder_load import main
    assert main([str(runs_folder), "--no-watch", "--quiet"], demo=False) == 0
    err = capsys.readouterr().err
    assert not re.search(r"^(starting|checking runs|comparing pairs|drawing pages):", err, re.M), err


def test_the_demos_first_line_is_said_at_once_and_a_later_start_says_it_reuses(served, capsys, monkeypatch, tmp_path):
    from onetrace_console import folder_load
    from onetrace_console.folder_load import DEMO_FOLDER
    said_before_build = []

    def demo_folder(cwd):
        said_before_build.append(capsys.readouterr().err)
        (cwd / DEMO_FOLDER / "runs").mkdir(parents=True, exist_ok=True)
        return cwd / DEMO_FOLDER
    monkeypatch.setattr(folder_load, "demo_folder", demo_folder)
    monkeypatch.setattr("onetrace_console.demo_store.deliver",
                        lambda folder, store, config: folder_load.Loaded((), None, ""))
    monkeypatch.setattr(folder_load, "announce", lambda *a: ([], ""))
    monkeypatch.delenv("ONETRACE_CONSOLE_CONFIG", raising=False)
    assert folder_load.main([], demo=True) == 0
    assert said_before_build[0] == sp.FIRST_DEMO + "\n"
    assert folder_load.main([], demo=True) == 0
    #: What the first start said after its build is read here too: the later start's line is the last.
    assert said_before_build[1].splitlines()[-1] == sp.LATER_DEMO.format(folder=DEMO_FOLDER)
    assert "onetrace-console-demo/" in said_before_build[1]


# ---------------------------------------------------------------- a console that takes no escape codes


def test_without_vt_mode_a_count_updates_in_place_with_no_escape_byte():
    """Windows PowerShell 5.1's classic console prints `ESC[K` as it is: where VT mode was not accepted,
    a count line is redrawn with `\\r` and padded with spaces over the longer line before it."""
    out, clock = io.StringIO(), Clock()
    p = sp.Progress(out, tty=True, vt=False, clock=clock)
    with p.phase("checking runs", 54) as step:
        for _ in range(54):
            step()
    with p.phase("drawing pages", 2, done=lambda n, took: "pages: drawn") as step:
        step()
    text = out.getvalue()
    assert "\x1b" not in text
    assert "\rchecking runs: 49 of 54\rchecking runs: 50 of 54" in text
    assert text.endswith("\rpages: drawn" + " " * (len("drawing pages: 1 of 2") - len("pages: drawn")) + "\n")


@pytest.fixture
def a_file_stream(tmp_path):
    with open(tmp_path / "stderr.txt", "w", encoding="utf-8", newline="") as f:
        yield f


def test_on_windows_a_console_that_refuses_vt_mode_gets_no_escape_byte(a_file_stream, monkeypatch):
    asked = []
    monkeypatch.setattr(sp.sys, "platform", "win32")
    monkeypatch.setattr(sp, "windows_vt", lambda stream: asked.append(stream) or False)
    p = sp.Progress(a_file_stream, tty=True, clock=Clock())
    with p.phase("checking runs", 2) as step:
        step()
    a_file_stream.flush()
    text = open(a_file_stream.name, encoding="utf-8", newline="").read()
    assert asked == [a_file_stream] and "\x1b" not in text and text.startswith("\rchecking runs: 0 of 2")


def test_on_windows_a_console_that_takes_vt_mode_is_asked_before_the_first_line(a_file_stream, monkeypatch):
    said = []
    monkeypatch.setattr(sp.sys, "platform", "win32")
    monkeypatch.setattr(sp, "windows_vt", lambda stream: said.append(open(stream.name).read()) or True)
    p = sp.Progress(a_file_stream, tty=True, clock=Clock())
    with p.phase("checking runs", 1) as step:
        step()
    a_file_stream.flush()
    assert said == [""] and "\x1b[K" in open(a_file_stream.name, encoding="utf-8", newline="").read()


@pytest.mark.skipif(sys.platform != "win32", reason="SetConsoleMode is Windows' own")
def test_on_windows_a_stream_that_is_no_console_does_not_take_vt_mode(a_file_stream):
    """The real call: a file is no console, so GetConsoleMode fails and no escape code is written."""
    assert sp.windows_vt(a_file_stream) is False
