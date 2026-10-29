"""Live folder pickup (watch.py): a run written into a watched folder is taken in on its own.

Each rule, on a real folder and real runs:
1. a run still being written is never taken in -- written slowly, stage by stage with the
   recorder's lock file, and written with its MANIFEST.json first and the rest after;
2. a finished run is taken in once its file list and sizes are the same on two reads in a row;
3. taken in once: a run changed after intake keeps its stored copy, and is noted, amber or red
   by what its own check now reads; a run deleted from the folder stays stored, noted neutral;
4. bounded: 200 runs arriving at once are taken in at most 50 a pass;
5. end to end: the console started on an empty folder shows a run recorded into it afterwards on
   its Overview, with no restart.

The sabotage of rule 2 (a run taken in on its first sight) is tools/sabotage_watch.py's.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest

from onetrace_console import watch


def _record(folder: Path, run_id: str, *, between=None) -> None:
    from onetrace.emit import Instrument, Recorder
    rec = Recorder(str(folder), run_id=run_id, declared_stages=["one", "two"], manifest=Path(__file__),
                   policy="fail-closed", anchor_reason="a test record")
    rec.run_node("one", None, Instrument("w", "tool", "1.0.0", {"k": "v"}),
                 lambda ctx: ctx.write("one.txt", b"1\n", "text/plain"))
    if between is not None:
        between()
    rec.run_node("two", None, Instrument("w", "tool", "1.0.0", {"k": "v"}),
                 lambda ctx: ctx.write("two.txt", b"2\n", "text/plain"))
    rec.close()


class _Intake:
    """What the watcher took in, without a store: the folder names, in order."""

    def __init__(self):
        self.names: list[str] = []

    def __call__(self, run_dir: Path) -> bool:
        self.names.append(run_dir.name)
        return True


def test_a_run_written_stage_by_stage_is_taken_only_once_finished(tmp_path, examined):
    runs = tmp_path / "runs"
    runs.mkdir()
    took = _Intake()
    w = watch.Watcher(runs, took, interval=0.01)
    seen_while_writing = []

    def mid_run():
        seen_while_writing.extend([w.scan(), w.scan()])     # two reads while it's being written
    _record(runs / "slow", "slow", between=mid_run)
    examined(1, "run written slowly")
    assert seen_while_writing == [[], []] and took.names == [], "never while being written"
    assert w.scan() == [], "first read of the finished run: not yet"
    assert w.scan() == ["slow"] and took.names == ["slow"]


def test_a_manifest_written_first_waits_until_the_folder_stops_changing(tmp_path, examined):
    runs = tmp_path / "runs"
    _record(tmp_path / "source", "first")
    target = runs / "first"
    target.mkdir(parents=True)
    shutil.copy2(tmp_path / "source" / "MANIFEST.json", target / "MANIFEST.json")
    took = _Intake()
    w = watch.Watcher(runs, took, interval=0.01)
    examined(1, "run written manifest first")
    #: Read once with only the manifest there; then every file that follows changes the folder
    #: before the next read, so no two reads agree until the last file is in. (The rule's limit,
    #: stated in the hand-over: a writer that pauses for two reads after its manifest would be
    #: taken in part-written. onetrace itself writes the manifest last, under its lock file.)
    assert w.scan() == []
    for p in sorted((tmp_path / "source").rglob("*")):
        if p.is_file() and p.name != "MANIFEST.json":
            (target / p.relative_to(tmp_path / "source")).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target / p.relative_to(tmp_path / "source"))
            assert w.scan() == [], "the folder changed since the last read: not yet"
    assert w.scan() == ["first"]


def test_taken_in_once_a_changed_run_is_noted_and_a_deleted_one_noted_neutral(tmp_path, examined):
    runs = tmp_path / "runs"
    _record(runs / "a", "a")
    _record(runs / "b", "b")
    took = _Intake()
    w = watch.Watcher(runs, took, interval=0.01, examine=lambda d: ("bad", f"{d.name} now contradicts"))
    w.scan(); w.scan()
    assert took.names == ["a", "b"]
    (runs / "a" / "artifacts" / "01-one" / "one.txt").write_bytes(b"changed\n")
    shutil.rmtree(runs / "b")
    w.scan(); w.scan()
    examined(2, "runs changed after intake")
    assert took.names == ["a", "b"], "never taken in a second time"
    assert w.state.changed == {"a": ("bad", "a now contradicts"), "b": watch.GONE}
    assert watch.GONE[0] == "neu"


def test_two_hundred_runs_at_once_are_taken_fifty_a_pass(tmp_path, examined):
    runs = tmp_path / "runs"
    _record(tmp_path / "one", "one")
    for i in range(200):
        shutil.copytree(tmp_path / "one", runs / f"r{i:03d}")
    took = _Intake()
    w = watch.Watcher(runs, took, interval=0.01)
    w.scan()
    passes = [len(w.scan()) for _ in range(5)]
    examined(200, "runs")
    assert passes == [50, 50, 50, 50, 0] and len(took.names) == 200


def test_an_error_in_one_intake_is_kept_and_the_pass_goes_on(tmp_path, examined):
    runs = tmp_path / "runs"
    _record(runs / "a", "a")
    _record(runs / "b", "b")

    def intake(run_dir: Path) -> bool:
        if run_dir.name == "a":
            raise RuntimeError("the store is full")
        return True
    w = watch.Watcher(runs, intake, interval=0.01)
    w.scan()
    examined(1, "pass")
    assert w.scan() == ["b"] and w.state.errors == ["a: RuntimeError: the store is full"]


def test_the_console_shows_a_run_recorded_into_its_folder_after_it_started(tmp_path, examined):
    from tests.test_checks import _require_installed
    from tests.test_folder_load import _Console, _free_port, _get
    _require_installed()
    (tmp_path / "runs").mkdir()
    port = _free_port()
    c = _Console(tmp_path, "runs", "--watch-interval", "0.5", "--port", str(port))
    try:
        c.until("overview:")
        base = f"http://127.0.0.1:{port}"
        assert "late-run" not in _get(base + "/home.html")
        _record(tmp_path / "runs" / "late", "late-run")
        deadline = time.monotonic() + 60
        while "late-run" not in _get(base + "/home.html"):
            assert time.monotonic() < deadline, "the run never appeared"
            time.sleep(0.5)
        state = json.loads(_get(base + "/v1/folder"))
        page = _get(base + "/home.html")
    finally:
        c.stop()
    examined(1, "run recorded while serving")
    assert state["taken"] == 1 and state["errors"] == []
    assert 'data-section="watched"' in page and "Show them" in page


def test_no_watch_reads_once_and_compare_waits_when_watched(tmp_path, examined):
    from tests.test_checks import _require_installed
    from tests.test_folder_load import _Console, _free_port
    _require_installed()
    (tmp_path / "runs").mkdir()
    c = _Console(tmp_path, "runs", "--no-watch", "--port", str(_free_port()))
    code, out = c.exited()
    examined(2, "starts")
    assert code == 1 and "no run folders" in out, "unwatched, an empty folder is refused as before"
    _record(tmp_path / "runs" / "a", "a")
    c = _Console(tmp_path, "runs", "--compare", "a", "b", "--port", str(_free_port()))
    try:
        c.until("overview:")
        out = "".join(c.lines)
    finally:
        c.stop()
    assert "waiting for b: the comparison is made when both run folders have arrived" in out, out


def test_a_watched_console_has_no_form_and_no_read_now_route(tmp_path, examined):
    """No "Read the folder now" button: the console's no-form rule stands, and the folder is read
    by its poll alone. A watched local console's pages carry no form and no button, and the POST
    route that would have read the folder at once does not exist: it answers "no such route", not
    a refusal of its token."""
    import re
    import urllib.error
    import urllib.request

    from tests.test_checks import _require_installed
    from tests.test_folder_load import _Console, _free_port, _get
    _require_installed()
    _record(tmp_path / "runs" / "a", "a")
    port = _free_port()
    c = _Console(tmp_path, "runs", "--watch-interval", "0.5", "--port", str(port))
    try:
        c.until("overview:")
        base = f"http://127.0.0.1:{port}"
        #: What stays: the line saying the folder is watched, once it has been read.
        deadline = time.monotonic() + 30
        while 'data-section="watched"' not in _get(base + "/home.html"):
            assert time.monotonic() < deadline, "the watched line never appeared"
            time.sleep(0.5)
        pages = {name: _get(f"{base}/{name}") for name in ("home.html", "executions-all.html")}
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    base + "/v1/folder/read", data=b"", method="POST"), timeout=10) as r:
                answered = (r.status, r.read())
        except urllib.error.HTTPError as e:
            answered = (e.code, e.read())
    finally:
        c.stop()
    examined(len(pages) + 1, "pages and the route")
    for name, page in pages.items():
        assert 'data-section="watched"' in page, name
        from tests.run_tools import without_run_tools
        from tests.test_theme_switch import without_the_console_s_own
        #: The index's search box (console 0.5.0) reads; it is no "read now", and is taken out by its
        #: exact markup.
        assert not re.search(r"<(form|button)\b", without_the_console_s_own(without_run_tools(page)), re.I), name
    assert answered == (404, b"no such route\n"), answered


def test_the_watched_line_shows_the_folder_as_written_not_with_doubled_backslashes(tmp_path, monkeypatch,
                                                                                    examined):
    """The watched-folder line shows the folder's path as written. On Windows every separator is a
    backslash, and the page's record-word escape doubled each one (`C:\\\\Users\\\\...`). Here the
    folder's own name holds a backslash, so the same line is checked on every platform; on Windows
    its whole path is backslashes."""
    import html
    import re

    from onetrace_console.render import watched_section
    folder = tmp_path / "my\\runs"
    folder.mkdir(parents=True)
    monkeypatch.setattr(watch, "CURRENT", watch.Watcher(folder, lambda run_dir: True, interval=1.0))
    shown = re.search(r"<p>Watching <code>(.*?)</code>", watched_section()).group(1)
    examined(1, "watched lines")
    assert html.unescape(shown) == str(folder.resolve()), shown
    assert "\\\\" not in shown


def test_a_watched_path_s_control_characters_are_still_shown_as_escapes(examined):
    from onetrace_console.words import path_text
    shown = path_text("C:\\Users\\a\x07b\u202e<c>")
    examined(1, "paths")
    assert shown == "C:\\Users\\a\\u0007b\\u202e&lt;c&gt;", shown
