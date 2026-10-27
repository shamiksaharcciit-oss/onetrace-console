"""`onetrace-console <runs folder>` and `onetrace-console demo`: a first run with something to show.

1. A folder load delivers every run folder in it through the same path `POST /v1/runs` takes
   (the folder as a delivery with its SHA256SUMS, accepted, then checked), and compares nothing
   unless `--compare A B` names two of them.
2. A run folder that cannot be delivered is said, with why, and the others still load: one still
   being recorded (onetrace's `.lock` is in it), one holding a link, one whose own SHA256SUMS does
   not match it.
3. `demo` copies the reference demo's two runs and its trust file into `onetrace-console-demo/`,
   loads both, compares them, and prints the pages' addresses. It ships inside the package, as
   the reference demo's own bytes.
4. Both listen on 127.0.0.1 only; a browser is opened only with `--open`.
"""
from __future__ import annotations

import hashlib
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import urllib.request
from html import unescape
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "examples" / "reference-demo"
SHIPPED = REPO / "src" / "onetrace_console" / "demo_store"


def _runs(tmp_path: Path) -> Path:
    folder = tmp_path / "my-runs"
    shutil.copytree(EXAMPLE / "runs", folder)
    return folder


def _load(folder: Path, root: Path, compare=None, trust_file=None):
    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    store = Store(root / "store")
    return store, load_folder(folder, store, Config(trust_file=trust_file), compare=compare)


# ------------------------------------------------------------------ 1. the load itself

def test_every_run_folder_is_loaded_and_nothing_is_compared(tmp_path, examined):
    store, loaded = _load(_runs(tmp_path), tmp_path)
    examined(len(loaded.runs), "run folders loaded")
    assert sorted(r.name for r in loaded.runs) == ["day-1", "day-2"]
    assert all(r.run is not None and not r.refused for r in loaded.runs), loaded.runs
    assert sorted(r.run_id for r in store.runs()) == ["demo-run-1", "demo-run-2"]
    assert loaded.comparison is None
    assert list(store.comparisons()) == []


def test_compare_a_b_compares_the_two_it_names_a_as_the_baseline(tmp_path, examined):
    store, loaded = _load(_runs(tmp_path), tmp_path, compare=("day-1", "day-2"))
    examined(1, "comparison asked for")
    cmp = loaded.comparison
    assert cmp is not None
    by_name = {r.name: r.run for r in loaded.runs}
    assert (cmp.run_a, cmp.run_b) == (by_name["day-1"].key, by_name["day-2"].key)
    assert [c.key for c in store.comparisons()] == [cmp.key]


def test_a_comparison_naming_a_folder_not_there_is_refused_before_anything_loads(tmp_path, examined):
    from onetrace_console.folder_load import LoadRefused
    examined(1, "comparison naming a missing folder")
    with pytest.raises(LoadRefused) as refused:
        _load(_runs(tmp_path), tmp_path, compare=("day-1", "day-3"))
    assert "day-3" in str(refused.value)
    assert not (tmp_path / "store").exists() or not list((tmp_path / "store").rglob("*.json"))


def test_a_folder_with_no_run_folders_is_said(tmp_path, examined):
    from onetrace_console.folder_load import LoadRefused
    (tmp_path / "empty").mkdir()
    examined(1, "empty folder")
    with pytest.raises(LoadRefused) as refused:
        _load(tmp_path / "empty", tmp_path)
    assert "MANIFEST.json" in str(refused.value)


# ------------------------------------------------------------------ 2. runs that cannot be delivered

def test_a_run_still_being_recorded_is_skipped_and_said(tmp_path, examined):
    folder = _runs(tmp_path)
    (folder / "day-2" / ".lock").write_bytes(b"")
    _store, loaded = _load(folder, tmp_path)
    by_name = {r.name: r for r in loaded.runs}
    examined(2, "run folders")
    assert by_name["day-1"].run is not None
    assert by_name["day-2"].run is None and "still being recorded" in by_name["day-2"].refused


def test_a_run_whose_own_sums_do_not_match_is_refused_with_the_consoles_rows(tmp_path, examined):
    folder = _runs(tmp_path)
    (folder / "day-2" / "SHA256SUMS").write_text(f"{'0' * 64}  MANIFEST.json\n", encoding="utf-8")
    _store, loaded = _load(folder, tmp_path)
    day2 = {r.name: r for r in loaded.runs}["day-2"]
    examined(1, "run folder with its own sums")
    assert day2.run is None and "does not match" in day2.refused, day2.refused


def test_a_run_whose_own_sums_match_is_delivered_with_them(tmp_path, examined):
    folder = _runs(tmp_path)
    run = folder / "day-1"
    files = sorted(p for p in run.rglob("*") if p.is_file())
    (run / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(run).as_posix()}\n"
        for p in files), encoding="utf-8")
    _store, loaded = _load(folder, tmp_path)
    examined(1, "run folder with its own sums")
    assert {r.name: r for r in loaded.runs}["day-1"].run is not None


def _make_link(link: Path, target: Path) -> None:
    """Make `link` point at `target`. On Windows, making a link needs a privilege few accounts hold:
    if it cannot be made there, the test is skipped with the error itself. Anywhere else a link can
    always be made, so a failure is the test's failure, never a skip."""
    try:
        link.symlink_to(target)
    except OSError as e:
        if os.name == "nt":
            pytest.skip(f"skipped on Windows: the runner cannot create links ({e})")
        raise


def test_a_run_holding_a_link_is_refused(tmp_path, examined):
    folder = _runs(tmp_path)
    (tmp_path / "outside.txt").write_text("not part of the run", encoding="utf-8")
    _make_link(folder / "day-2" / "notes.txt", tmp_path / "outside.txt")
    _store, loaded = _load(folder, tmp_path)
    day2 = {r.name: r for r in loaded.runs}["day-2"]
    examined(1, "run folder holding a link")
    assert day2.run is None and "link" in day2.refused, day2.refused


# ------------------------------------------------------------------ 3. the demo's builder ships in the package
#: 0.1.1: the package ships the demo store's builder and its trust file,
#: not runs. The reference demo's committed runs stay in examples/, outside the store.

def test_the_package_ships_the_builders_trust_file_and_the_reference_pipeline_as_is(examined):
    from onetrace_console.demo_store import keys
    examined(2, "files the builder ships")
    assert (SHIPPED / "trust.json").read_bytes() == keys.trust_file_bytes(), \
        "the packaged trust file is the builder's, byte for byte"
    assert (SHIPPED / "reference_pipeline.py").read_bytes() == (EXAMPLE / "demo.py").read_bytes(), \
        "P2 runs the reference demo's pipeline unchanged"
    assert not (REPO / "src" / "onetrace_console" / "reference_demo").exists(), \
        "no committed runs ship in the package"


def test_the_package_data_names_the_demo(examined):
    import tomllib
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    globs = data["tool"]["setuptools"]["package-data"]["onetrace_console"]
    examined(len(globs), "package-data globs")
    from fnmatch import fnmatch
    shipped = [p.relative_to(SHIPPED.parent).as_posix() for p in SHIPPED.rglob("*")
               if p.is_file() and p.suffix != ".py" and "__pycache__" not in p.parts]
    assert shipped == ["demo_store/trust.json"], shipped
    assert all(any(fnmatch(p, g) for g in globs) for p in shipped), shipped


# ------------------------------------------------------------------ 4. the commands, as a user runs them

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Console:
    """`python -m onetrace_console ...` in a folder, read until it has printed its overview line."""

    def __init__(self, cwd: Path, *args: str, env: dict | None = None):
        clean = {k: v for k, v in os.environ.items() if k != "ONETRACE_CONSOLE_CONFIG"}
        clean["PYTHONPATH"] = str(REPO / "src")
        self.proc = subprocess.Popen([sys.executable, "-B", "-m", "onetrace_console", *args], cwd=cwd,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     env={**clean, **(env or {})})
        self.lines: list[str] = []
        lines: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: [lines.put(l) for l in self.proc.stdout] and lines.put(None),
                         daemon=True).start()
        self._queue = lines

    def until(self, prefix: str, timeout: float = 600) -> str:
        while True:
            line = self._queue.get(timeout=timeout)
            if line is None:
                raise AssertionError("the console exited:\n" + "".join(self.lines))
            self.lines.append(line)
            if line.strip().startswith(prefix):
                return line.strip()

    def exited(self, timeout: float = 120) -> tuple[int, str]:
        """For a start that must refuse: it says why and exits within seconds, never serving."""
        code = self.proc.wait(timeout=timeout)
        while (line := self._queue.get(timeout=timeout)) is not None:
            self.lines.append(line)
        return code, "".join(self.lines)

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def _url(line: str) -> str:
    return line.split()[-1]


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=120) as r:
        assert r.status == 200, url
        return r.read().decode("utf-8")


@pytest.fixture
def console():
    started: list[_Console] = []

    def start(*args, **kw) -> _Console:
        c = _Console(*args, **kw)
        started.append(c)
        return c
    yield start
    for c in started:
        c.stop()


def test_a_folder_load_serves_the_runs_and_the_comparison_it_was_asked_for(tmp_path, console, examined):
    folder = _runs(tmp_path)
    port = _free_port()
    c = console(tmp_path, str(folder), "--compare", "day-1", "day-2", "--port", str(port))
    overview = c.until("overview:")
    out = "".join(c.lines)
    examined(1, "folder load")
    base = f"http://127.0.0.1:{port}/"
    assert _url(overview) == base
    compared = next(l for l in c.lines if l.strip().startswith("compared"))
    assert "day-1" in compared and "day-2" in compared and f"{base}diff/" in compared
    assert "day-1" in out and "day-2" in out and "Records agree" in out, out
    assert "Verified" not in out, "the start-up list counts the verifier's word, not the run's own page's"
    assert "demo-run-1" in _get(base)
    assert "Where the change started" in _get(_url(compared)) or "model" in _get(_url(compared))
    assert (tmp_path / "store").is_dir(), "the store is ./store under the folder it is started from"


def _demo_runs() -> list[str]:
    """What the demo's `runs/` holds: its run folders, and what the builder writes beside them."""
    from onetrace_console.demo_store import BESIDE_RUNS, runs
    return sorted([r.folder for r in runs()] + list(BESIDE_RUNS))


def test_the_demo_builds_loads_compares_and_reads_the_signatures_with_its_trust_file(tmp_path, console,
                                                                                   examined):
    from onetrace_console.demo_store import COMPARISONS, keys
    port = _free_port()
    c = console(tmp_path, "demo", "--port", str(port))
    overview = c.until("overview:")
    examined(1, "demo")
    demo = tmp_path / "onetrace-console-demo"
    assert sorted(p.name for p in (demo / "runs").iterdir()) == _demo_runs()
    assert (demo / "trust.json").read_bytes() == (SHIPPED / "trust.json").read_bytes()
    assert (demo / "store").is_dir() and not (tmp_path / "store").exists()
    compared = next(l for l in c.lines if l.strip().startswith("compared"))
    assert "/diff/" in compared and COMPARISONS[0][0] in compared and COMPARISONS[0][1] in compared
    first = next(l for l in c.lines if l.strip().startswith(COMPARISONS[0][0]))
    receipt = _get(_url(first).replace("case.html", "receipt.html"))
    assert keys.TRUSTED_LABEL in unescape(receipt), \
        "the signatures were not read with the demo's trust file"
    assert _url(overview) == f"http://127.0.0.1:{port}/"


def test_the_demo_runs_again_in_the_same_folder(tmp_path, console, examined):
    records = []
    for _ in range(2):
        port = _free_port()
        c = console(tmp_path, "demo", "--port", str(port))
        c.until("overview:")
        c.stop()
        records.append((tmp_path / "onetrace-console-demo" / "BUILD_RECORD.json").read_bytes())
    examined(2, "demo starts in one folder")
    assert sorted(p.name for p in (tmp_path / "onetrace-console-demo" / "runs").iterdir()) == _demo_runs()
    assert records[0] == records[1], "the second start re-used the runs the first built"


def test_the_demo_refuses_a_folder_whose_runs_were_changed(tmp_path, console, examined):
    """A hand edit after the build -- one byte of one recorded output -- is named and refused."""
    c = console(tmp_path, "demo", "--port", str(_free_port()))
    c.until("overview:")
    c.stop()
    runs = tmp_path / "onetrace-console-demo" / "runs"
    (edited,) = sorted(runs.glob("p1-01-*/artifacts/*-answer/answers.json"))
    data = bytearray(edited.read_bytes())
    data[-3] ^= 0x01
    edited.write_bytes(bytes(data))
    c = console(tmp_path, "demo", "--port", str(_free_port()))
    code, out = c.exited()
    examined(1, "changed demo folder")
    assert code == 1, out
    rel = edited.relative_to(runs.parent).as_posix()
    assert f"{rel} was changed" in out and "onetrace-console-demo" in out, out


def test_the_demo_refuses_when_a_configuration_file_is_named(tmp_path, console, examined):
    c = console(tmp_path, "demo", "--port", str(_free_port()),
                env={"ONETRACE_CONSOLE_CONFIG": str(tmp_path / "config.json")})
    code, out = c.exited()
    examined(1, "demo with a configuration file named")
    assert code == 1 and "ONETRACE_CONSOLE_CONFIG" in out, out
    assert not (tmp_path / "onetrace-console-demo").exists()


def _browser(tmp_path: Path) -> tuple[dict, Path]:
    """A stand-in browser: `webbrowser` runs $BROWSER with the address, and this one writes it down."""
    opened = tmp_path / "opened.txt"
    script = tmp_path / "browser.py"
    script.write_text("import sys, pathlib\npathlib.Path(sys.argv[1]).write_text(sys.argv[2])\n",
                      encoding="utf-8")
    return {"BROWSER": f'"{sys.executable}" "{script}" "{opened}" %s'}, opened


@pytest.mark.parametrize("asked", [False, True], ids=["without --open", "with --open"])
def test_a_browser_is_opened_only_when_asked(tmp_path, console, examined, asked):
    env, opened = _browser(tmp_path)
    port = _free_port()
    args = [str(_runs(tmp_path)), "--compare", "day-1", "day-2", "--port", str(port)]
    c = console(tmp_path, *args, *(["--open"] if asked else []), env=env)
    c.until("overview:")
    compared = _url(next(l for l in c.lines if l.strip().startswith("compared")))
    said = [l.strip() for l in c.lines if l.strip().startswith("opening")]
    examined(1, "start")
    #: The console says it is opening a browser before its last line, so by now it has said so
    #: or it will not.
    assert bool(said) == asked, c.lines
    if asked:
        assert said == [f"opening {compared} in your browser"], "opens the comparison it made"
        for _ in range(150):
            if opened.exists():
                break
            threading.Event().wait(0.2)
        assert opened.read_text(encoding="utf-8").strip() == compared, "the browser was not asked"
    else:
        assert not opened.exists()


def test_the_usage_names_both_commands(examined):
    from onetrace_console.__main__ import USAGE
    examined(1, "usage text")
    assert "onetrace-console demo" in USAGE
    assert "onetrace-console <runs folder>" in USAGE and "--compare" in USAGE and "--open" in USAGE


def test_a_mistyped_command_says_so_and_shows_the_usage(tmp_path, examined):
    """A first word that is neither a command nor an existing path is a mistyped command, not a
    folder problem: it is said as that, then the usage, and the exit is 2."""
    out = subprocess.run([sys.executable, "-B", "-m", "onetrace_console", "srve"], cwd=tmp_path,
                         capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(REPO / "src")})
    examined(1, "mistyped command")
    assert out.returncode == 2, (out.returncode, out.stderr)
    assert out.stderr.splitlines()[0] == "onetrace-console: 'srve' is not a command or a folder", out.stderr
    assert "onetrace-console serve" in out.stderr and "onetrace-console demo" in out.stderr, "no usage"
    assert not (tmp_path / "store").exists(), "a mistyped command started something"
