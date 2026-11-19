"""A run folder's `.lock`, the console's part: what the `.lock` names decides whether the folder is loaded,
skipped or listed.

- A `.lock` naming a process on this host that is gone: loaded, and the run reads "not closed".
- One naming a live process on this host: skipped, as a run still being recorded.
- One naming another host: listed as locked.
- An empty `.lock`, as every onetrace before 0.9 writes it: listed on the Runs page as "locked: still
  recording, or stopped without closing". A local console offers "Load as not closed"; a public console
  only lists it.
Whether a process lives is read on POSIX by signal 0, and on Windows by OpenProcess and its exit code.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from onetrace_console import run_lock
from tests.http_limits import limit

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "examples" / "reference-demo"


@pytest.fixture(autouse=True)
def _nothing_listed():
    run_lock.LISTED.clear()
    yield
    run_lock.LISTED.clear()


def _gone_pid() -> int:
    """The id of a process that has run and been reaped."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def _lock(run_dir: Path, *, pid=None, host=None, raw: bytes | None = None) -> None:
    if raw is None:
        raw = json.dumps(
            {"pid": pid, "host": host if host is not None else run_lock.this_host(), "started": "2026-01-01T00:00:00Z"}
        ).encode()
    (run_dir / run_lock.NAME).write_bytes(raw)


def _runs(tmp_path: Path) -> Path:
    folder = tmp_path / "my-runs"
    shutil.copytree(EXAMPLE / "runs", folder)
    return folder


def _load(folder: Path, root: Path):
    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed

    _require_installed()
    store = Store(root / "store")
    return store, {r.name: r for r in load_folder(folder, store, Config()).runs}


# ---------------------------------------------------------------- what a .lock says
def test_what_each_kind_of_lock_reads_as(tmp_path, examined):
    d = tmp_path / "run"
    d.mkdir()
    seen = {"none": run_lock.state(d).kind}
    _lock(d, raw=b"")
    seen["empty"] = run_lock.state(d).kind
    _lock(d, raw=b"not json {")
    seen["not json"] = run_lock.state(d).kind
    _lock(d, raw=b'{"pid": "12", "host": "x"}')
    seen["pid not a number"] = run_lock.state(d).kind
    _lock(d, raw=b'{"pid": 12}')
    seen["no host"] = run_lock.state(d).kind
    _lock(d, raw=b"[" * 2000 + b"]" * 2000)
    seen["nested past the depth"] = run_lock.state(d).kind
    _lock(d, pid=os.getpid())
    seen["this host, live"] = run_lock.state(d).kind
    _lock(d, pid=_gone_pid())
    seen["this host, gone"] = run_lock.state(d).kind
    _lock(d, pid=os.getpid(), host="another-host.example")
    seen["another host"] = run_lock.state(d).kind
    _lock(d, pid=os.getpid(), host=run_lock.this_host().upper())
    seen["this host, other case"] = run_lock.state(d).kind
    examined(len(seen), "locks read")
    assert seen == {
        "none": "none",
        "empty": "empty",
        "not json": "empty",
        "pid not a number": "empty",
        "no host": "empty",
        "nested past the depth": "empty",
        "this host, live": "live",
        "this host, gone": "dead",
        "another host": "elsewhere",
        "this host, other case": "live",
    }


def test_whether_a_process_lives_on_this_platform(examined):
    examined(3, "process ids")
    assert run_lock.process_alive(os.getpid()) is True
    assert run_lock.process_alive(_gone_pid()) is False
    assert run_lock.process_alive(0) is False


class _Kernel32:
    """Windows' kernel32 as `_alive_on_windows` calls it, answering as told."""

    def __init__(self, *, opens=True, error=0, exit_code=259, reads=True):
        self.opens, self.error, self.exit_code, self.reads = opens, error, exit_code, reads
        self.closed = 0

    def OpenProcess(self, access, inherit, pid):
        assert access == 0x1000 and inherit is False
        return 42 if self.opens else 0

    def GetLastError(self):
        return self.error

    def GetExitCodeProcess(self, handle, code_ptr):
        assert handle == 42
        code_ptr.contents.value = self.exit_code
        return 1 if self.reads else 0

    def CloseHandle(self, handle):
        self.closed += 1
        return 1


@pytest.mark.parametrize(
    "kernel, alive",
    [
        (dict(exit_code=259), True),  # STILL_ACTIVE
        (dict(exit_code=0), False),  # exited
        (dict(opens=False, error=87), False),  # no such process
        (dict(opens=False, error=5), True),  # access denied: it runs, as another user's
        (dict(reads=False), True),  # its exit code can't be read: read as running
    ],
)
def test_whether_a_process_lives_on_windows(kernel, alive, examined):
    k = _Kernel32(**kernel)
    examined(1, f"a Windows answer: {kernel}")
    assert run_lock.process_alive(1234, windows=True, kernel32=k) is alive
    assert k.closed == (1 if k.opens else 0), "an opened handle is closed"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' own kernel32")
def test_whether_a_process_lives_on_windows_itself(examined):
    examined(2, "process ids, on Windows")
    assert run_lock.process_alive(os.getpid()) is True
    assert run_lock.process_alive(_gone_pid()) is False


# ---------------------------------------------------------------- the folder load
def test_a_lock_whose_process_is_gone_is_loaded_and_reads_not_closed(tmp_path, examined):
    from onetrace_console import closing

    folder = _runs(tmp_path)
    _lock(folder / "day-2", pid=_gone_pid())
    store, runs = _load(folder, tmp_path)
    examined(1, "a run folder whose recorder is gone")
    assert runs["day-2"].run is not None, runs["day-2"].refused
    stored = next(r for r in store.runs() if r.key == runs["day-2"].run.key)
    assert closing.state(stored.ending) == "not-closed"
    assert closing.said(stored.ending).startswith("not closed")
    assert "day-2" not in run_lock.LISTED
    #: The `.lock` is the recorder's, not the record's: it is not delivered.
    import io
    import tarfile

    from onetrace_console.folder_load import delivery

    names = tarfile.open(fileobj=io.BytesIO(delivery(folder / "day-2", skip_lock=True))).getnames()
    assert run_lock.NAME not in names


def test_a_lock_whose_process_lives_is_skipped_as_now(tmp_path, examined):
    folder = _runs(tmp_path)
    _lock(folder / "day-2", pid=os.getpid())
    _store, runs = _load(folder, tmp_path)
    examined(1, "a run folder whose recorder runs")
    assert runs["day-2"].run is None and "still being recorded" in runs["day-2"].refused
    assert "day-2" not in run_lock.LISTED


def test_a_lock_naming_another_host_is_listed(tmp_path, examined):
    folder = _runs(tmp_path)
    _lock(folder / "day-2", pid=os.getpid(), host="another-host.example")
    _store, runs = _load(folder, tmp_path)
    examined(1, "a run folder recorded on another host")
    assert runs["day-2"].run is None
    assert run_lock.LISTED["day-2"][1] == "elsewhere"


def test_an_empty_lock_is_listed_and_said(tmp_path, examined):
    folder = _runs(tmp_path)
    _lock(folder / "day-2", raw=b"")
    _store, runs = _load(folder, tmp_path)
    examined(2, "run folders, one with an empty lock")
    assert runs["day-1"].run is not None
    assert runs["day-2"].run is None and "still being recorded" in runs["day-2"].refused
    assert "stopped without closing" in runs["day-2"].refused
    assert run_lock.LISTED["day-2"] == (str(folder / "day-2"), "empty")


# ---------------------------------------------------------------- the Runs page
def _runs_page(store, *, public: bool, watched: bool, monkeypatch):
    from onetrace_console import watch
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_executions

    monkeypatch.setattr(watch, "CURRENT", object() if watched else None)
    monkeypatch.setattr("onetrace_console.render.watched_section", lambda: "")
    with rendering(onedoor=False, sign_in=False, public=public):
        return render_executions(list(store.runs()), store, generated_at="2026-01-01T00:00:00Z", every_stored=True)


def test_the_runs_page_lists_a_locked_folder_and_a_local_console_offers_the_press(tmp_path, monkeypatch, examined):
    folder = _runs(tmp_path)
    _lock(folder / "day-2", raw=b"")
    store, _ = _load(folder, tmp_path)
    page = _runs_page(store, public=False, watched=True, monkeypatch=monkeypatch)
    examined(1, "the Runs page of a local, watched console")
    assert 'data-section="locked-runs"' in page
    assert "locked: still recording, or stopped without closing" in page
    assert ">Load as not closed</button>" in page
    assert 'data-load-not-closed="/runs/load-not-closed?folder=day-2"' in page


def test_a_public_console_only_lists_it(tmp_path, monkeypatch, examined):
    folder = _runs(tmp_path)
    _lock(folder / "day-2", raw=b"")
    store, _ = _load(folder, tmp_path)
    page = _runs_page(store, public=True, watched=False, monkeypatch=monkeypatch)
    examined(1, "the Runs page of a public console")
    assert "locked: still recording, or stopped without closing" in page
    assert "Load as not closed" not in page and "data-load-not-closed" not in page


def test_another_host_s_folder_is_listed_with_no_press(tmp_path, monkeypatch, examined):
    folder = _runs(tmp_path)
    _lock(folder / "day-2", pid=os.getpid(), host="another-host.example")
    store, _ = _load(folder, tmp_path)
    page = _runs_page(store, public=False, watched=True, monkeypatch=monkeypatch)
    examined(1, "the Runs page with another host's folder")
    assert "locked: recording on another host, or stopped there without closing" in page
    assert "data-load-not-closed" not in page
    assert "another-host.example" not in page


def test_no_locked_folder_no_section(tmp_path, monkeypatch, examined):
    store, _ = _load(_runs(tmp_path), tmp_path)
    page = _runs_page(store, public=False, watched=True, monkeypatch=monkeypatch)
    examined(1, "the Runs page with nothing locked")
    assert 'data-section="locked-runs"' not in page


def test_the_press_s_script_is_named_in_the_local_content_policy(examined):
    import base64
    import hashlib

    from onetrace_console.public import content_security_policy
    from onetrace_console.run_lock_script import LOAD_NOT_CLOSED_SCRIPT

    body = LOAD_NOT_CLOSED_SCRIPT[len("<script>") : -len("</script>")]
    digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
    examined(2, "content policies")
    assert f"'sha256-{digest}'" in content_security_policy(local=True)
    assert f"'sha256-{digest}'" not in content_security_policy()


# ---------------------------------------------------------------- the watcher and the press
def _record(folder: Path, run_id: str) -> None:
    from tests.test_watch import _record as record

    record(folder, run_id)


def test_the_watcher_takes_in_a_gone_recorder_s_run_and_lists_an_empty_lock(tmp_path, examined):
    from onetrace_console import watch

    runs = tmp_path / "runs"
    _record(runs / "gone", "gone")
    _lock(runs / "gone", pid=_gone_pid())
    _record(runs / "empty", "empty")
    _lock(runs / "empty", raw=b"")
    took = []
    w = watch.Watcher(runs, lambda d: took.append(d.name) or True, interval=0.01)
    w.scan()
    w.scan()
    examined(2, "watched run folders with a lock")
    assert took == ["gone"]
    assert run_lock.LISTED["empty"][1] == "empty"
    version = w.state.version
    w.scan()
    assert w.state.version == version, "listed once, not on every pass"
    shutil.rmtree(runs / "empty")
    w.scan()
    assert "empty" not in run_lock.LISTED and w.state.version > version


def _killed(folder: Path, run_id: str) -> None:
    """A run the installed onetrace records one step of, in a process that then exits without closing it, with
    its `.lock` as onetrace before 0.9 left it: a MANIFEST.json and an empty `.lock`. onetrace 0.9 names the
    recording process in it (`dead` once the process is gone, loaded by itself); the press is for the empty one."""
    code = (
        "import os, sys\nfrom pathlib import Path\nfrom onetrace.emit import Instrument, Recorder\n"
        "rec = Recorder(sys.argv[1], run_id=sys.argv[2], declared_stages=['one', 'two'], "
        "manifest=Path(sys.argv[3]), policy='fail-closed', anchor_reason='a test record')\n"
        "rec.run_node('one', None, Instrument('w', 'tool', '1.0.0', {'k': 'v'}), "
        "lambda ctx: ctx.write('one.txt', b'1\\n', 'text/plain'))\nos._exit(0)\n"
    )
    subprocess.run([sys.executable, "-c", code, str(folder), run_id, __file__], check=True)
    assert (folder / run_lock.NAME).is_file() and (folder / "MANIFEST.json").is_file()
    (folder / run_lock.NAME).write_bytes(b"")


def test_the_press_loads_the_folder_as_not_closed(tmp_path, examined):
    from tests.test_checks import _require_installed
    from tests.test_folder_load import _Console, _free_port, _get

    _require_installed()
    runs = tmp_path / "runs"
    _record(runs / "a", "a")
    _killed(runs / "b", "b")
    port = _free_port()
    c = _Console(tmp_path, "runs", "--watch-interval", "0.5", "--port", str(port))
    base = f"http://127.0.0.1:{port}"

    def post(path, origin=None):
        headers = {"Origin": origin} if origin else {}
        try:
            req = urllib.request.Request(base + path, data=b"", method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=limit(30)) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    try:
        c.until("overview:")
        page = _get(base + "/executions-all.html")
        assert "locked: still recording, or stopped without closing" in page
        refused = {
            "a folder not listed": post("/runs/load-not-closed?folder=a"),
            "no folder": post("/runs/load-not-closed"),
            "another origin": post("/runs/load-not-closed?folder=b", origin="http://evil.example"),
        }
        status, said = post("/runs/load-not-closed?folder=b")
        deadline = time.monotonic() + 30
        while "locked: still recording" in (page := _get(base + "/executions-all.html")):
            assert time.monotonic() < deadline, "the page was never drawn again"
            time.sleep(0.5)
    finally:
        c.stop()
    examined(4, "presses: one taken, three refused")
    assert status == 200 and said["folder"] == "b" and said["closed"].startswith("not closed"), said
    assert refused["a folder not listed"][0] == 400 and refused["no folder"][0] == 400
    assert refused["another origin"][0] == 403
    assert page.count('data-ending="not-closed"') >= 1


def test_a_console_with_no_watched_folder_has_no_press_route(server, examined):
    base, _root = server
    try:
        req = urllib.request.Request(base + "/runs/load-not-closed?folder=b", data=b"", method="POST")
        urllib.request.urlopen(req, timeout=limit(10))
        answered = 200
    except urllib.error.HTTPError as e:
        answered = (e.code, e.read())
    examined(1, "the press's route on a console with no watched folder")
    assert answered == (404, b"no such route\n")
