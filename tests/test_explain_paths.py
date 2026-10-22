"""Where an explanation is kept, and how long its paths are: Windows' limit, held by measurement.

On Windows with long paths off a path can be 259 characters at most, and a folder 247 (room for an 8.3
name). Long paths on or off, a process cannot start in a working folder of more than 258. The console
keeps each comparison's explanations in `<store>/x/<first 16 hex of its key>/`, and hands the command
`r` there. `explain.LIMIT` is the longest store folder that layout fits, from the parts the console
sets and the parts onetrace-explain and its SDK set below `r`, as measured.

The measurement here runs a real explanation with the `fake:` provider under a store folder padded
to exactly `LIMIT`, and records every path opened, made, renamed or replaced under it, in this
process and in every Python process it starts (the command, and the console's onetrace and verifier
runs), through an audit hook, with the working folder of every process each of them starts. It asks
nothing of the operating system's own limit, so it holds on any platform; on Windows with long paths
off it is also a real run at the limit.
"""
from __future__ import annotations

import importlib.metadata
import os
import sys
from pathlib import Path

import pytest

from tests.test_explain_panel import RAN_AT, _diff, _fake, _make, _panel, _text, tried

#: Windows' longest file path and longest folder path, long paths off, NUL apart.
FILE_MOST, FOLDER_MOST = 259, 247
#: Every Python process the command or the console starts imports this first, from the import path.
_HOOK = '''import os, sys
_LOG = os.environ.get("EXPLAIN_PATHS_LOG")
if _LOG:
    def _hook(event, args, _open=open):
        if event == "subprocess.Popen" and args[2] is not None:
            with _open(_LOG, "a", encoding="utf-8") as f:
                f.write("start\\t" + os.path.abspath(os.fsdecode(args[2])) + "\\n")
        if event in ("open", "os.mkdir", "os.rename", "os.replace"):
            for a in (args[:2] if event in ("os.rename", "os.replace") else args[:1]):
                if isinstance(a, (str, bytes, os.PathLike)) and not os.fsdecode(a) == _LOG:
                    with _open(_LOG, "a", encoding="utf-8") as f:
                        f.write(event + "\\t" + os.path.abspath(os.fsdecode(a)) + "\\n")
    sys.addaudithook(_hook)
'''
#: This process's own hook, added once (an audit hook cannot be removed) and on only while a
#: measurement runs.
_SEEN: list[tuple[str, str]] | None = None
_HOOKED = False


#: The working folder of each process this process starts, while `caught` runs a measurement.
_STARTED: list[str] | None = None


def _hook(event, args):
    if event == "subprocess.Popen" and args[2] is not None:
        folder = os.path.abspath(os.fsdecode(args[2]))
        if _STARTED is not None:
            _STARTED.append(folder)
        if _SEEN is not None:
            _SEEN.append(("start", folder))
    if _SEEN is not None and event in ("open", "os.mkdir", "os.rename", "os.replace"):
        for a in (args[:2] if event in ("os.rename", "os.replace") else args[:1]):
            if isinstance(a, (str, bytes, os.PathLike)):
                _SEEN.append((event, os.path.abspath(os.fsdecode(a))))


def _hooked() -> None:
    """This process's hook, added once."""
    global _HOOKED
    if not _HOOKED:
        sys.addaudithook(_hook)
        _HOOKED = True


def padded(tmp_path: Path, length: int) -> Path:
    """A folder whose path is exactly `length` characters."""
    room = length - len(str(tmp_path)) - 1
    if room < 1:
        pytest.fail(f"the test's temporary folder is {len(str(tmp_path))} characters, too long to pad "
                    f"a store folder to {length}: run the suite from a shorter folder")
    root = tmp_path / ("p" * room)
    root.mkdir()
    assert len(str(root)) == length
    return root


def pair_at(root: Path, monkeypatch):
    """The panel tests' pair, in a store at `root/store`, and a config naming no model yet."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    from tests.test_compare import _deliver
    _require_installed()
    store = Store(root / "store")
    made = root.parent / "made"
    a, b = (run_and_record(_deliver(f, store, outputs=True), store, ran_at=RAN_AT) for f in _make(made))
    comparison = compare(a, b, store)
    config = root.parent / "config" / "explain.toml"
    config.parent.mkdir()
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("ONETRACE_EXPLAIN_CONFIG", str(config))
    return store, comparison, config


def versions(explain_command) -> dict[str, str]:
    """The versions installed: onetrace-explain where the tests installed it, onetrace here."""
    _, lib = explain_command
    found = [d.version for d in importlib.metadata.distributions(path=[str(lib)])
             if d.metadata["Name"].lower().replace("_", "-") == "onetrace-explain"]
    return {"onetrace-explain": found[0] if len(found) == 1 else repr(found),
            "onetrace": importlib.metadata.version("onetrace")}


def measured(tmp_path: Path, monkeypatch, explain_command, length: int | None = None) -> dict:
    """An explanation, its packet and a check, run under a store folder of exactly `length` (`LIMIT`
    unless given): every path each process touched under it and every working folder a process
    started in there, the deepest path, and the problems against Windows' limits."""
    global _SEEN
    from onetrace_console import explain
    root = padded(tmp_path, explain.LIMIT if length is None else length)
    store, comparison, config = pair_at(root, monkeypatch)
    hook = tmp_path / "hook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(_HOOK, encoding="utf-8")
    log = tmp_path / "paths.log"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(hook), os.environ.get("PYTHONPATH", "")]))
    monkeypatch.setenv("EXPLAIN_PATHS_LOG", str(log))
    _hooked()
    _fake(config, "mixed.json")
    _SEEN = []
    try:
        got = explain.explain(comparison, store)
        shown = explain.packet(comparison, store)
        record = next(iter(explain.explanations(store, comparison.key)), {}).get("record", "")
        check = explain.run_check(store, comparison.key, record, 0) if record else {}
    finally:
        seen, _SEEN = _SEEN, None
    seen += [tuple(ln.split("\t", 1)) for ln in log.read_text(encoding="utf-8").splitlines()]
    under = sorted({(event, p) for event, p in seen if p.startswith(str(root) + os.sep)},
                   key=lambda e: -len(e[1]))
    problems = []
    if got.get("exit") != "0" or shown.get("exit") != "0" or check.get("exit") is None:
        problems.append(f"the explanation, its packet or its check did not run: {tried(store, comparison)}")
    problems += [f"{len(p)} characters: {p}" for e, p in under if e != "start" and len(p) > FILE_MOST]
    problems += [f"a folder of {len(p)} characters: {p}" for e, p in under
                 if e == "os.mkdir" and len(p) > FOLDER_MOST]
    problems += [f"a working folder of {len(p)} characters: {p}" for e, p in under
                 if e == "start" and len(p) > WORKING_FOLDER_MOST]
    staging = [p for _, p in under if "_staging" in p and ".tmp" in p]
    if not staging:
        problems.append("no staged temporary file was seen: the measurement missed the command's deepest writes")
    starts = [p for e, p in under if e == "start"]
    paths = [p for e, p in under if e != "start"]
    return {"root": root, "under": under, "deepest": len(paths[0]) if paths else 0, "problems": problems,
            "starts": starts, "deepest_start": max((len(p) for p in starts), default=0)}


def test_every_path_an_explanation_writes_fits_windows_limit_at_the_store_folder_limit(
        tmp_path, monkeypatch, explain_command, explain_installed, examined):
    from onetrace_console import explain
    assert versions(explain_command) == explain.MEASURED, (
        f"measured with {explain.MEASURED}; installed {versions(explain_command)}: measure the new "
        f"versions' parts below `{explain.REPORT}`, and set explain.MEASURED_BELOW from them")
    got = measured(tmp_path, monkeypatch, explain_command)
    examined(len(got["under"]) - len(got["starts"]), "paths under a store folder at the limit")
    examined(len(got["starts"]), "working folders a process started in, under a store folder at the limit")
    assert got["problems"] == [], "\n".join(got["problems"])
    #: At the limit the deepest path is the limit's own: the layout and the measured parts agree.
    assert got["deepest"] == FILE_MOST, (got["deepest"], got["under"][:3])


#: onetrace-explain's run id, measured with `explain.MEASURED`'s versions.
RUN_ID = 27


def limit_long_paths() -> int:
    """The longest store folder whose deepest working folder fits `WORKING_FOLDER_MOST`: the
    verifier's, in the record's folder `<store>/<FOLDER>/<KEY_HEX hex>/<REPORT>/explain/<run id>`, from
    the layout's parts and the run id's measured length."""
    from onetrace_console import explain
    return WORKING_FOLDER_MOST - (len("/store") + len(f"/{explain.FOLDER}/") + explain.KEY_HEX
                                  + len(f"/{explain.REPORT}") + len("/explain/") + RUN_ID)


def _deeper_verifier(monkeypatch):
    """The sabotage: the verifier started one folder below the record's."""
    from onetrace_console import explain
    run = explain.subprocess.run

    def deeper(argv, *args, cwd=None, **kwargs):
        if cwd is not None and Path(cwd).parent.name == "explain" and "MANIFEST.json" in argv:
            cwd = Path(cwd) / "d"
            cwd.mkdir(exist_ok=True)
        return run(argv, *args, cwd=cwd, **kwargs)
    monkeypatch.setattr(explain.subprocess, "run", deeper)


def working_folder_problems(got: dict) -> list[str]:
    return [p for p in got["problems"] if p.startswith(("a working folder", "the explanation, its packet",
                                                         "no staged"))]


def _long_paths_on_here():
    """Skip where Windows says long paths are off: at `limit_long_paths()` and over, the store's own
    files and the explanation's pass `FILE_MOST`."""
    from onetrace_console import explain
    if explain.long_paths() is False:
        pytest.skip(f"at {limit_long_paths()} characters and over, the store's own files and the explanation's "
                    f"pass {FILE_MOST}, which Windows with long paths off refuses; this runs where they are on")


def test_with_long_paths_on_every_process_starts_within_windows_limit_at_its_store_folder_limit(
        tmp_path, monkeypatch, explain_command, explain_installed, examined):
    from onetrace_console import explain
    _long_paths_on_here()
    assert (explain.LIMIT_LONG_PATHS, explain.WORKING_FOLDER) == (limit_long_paths(), WORKING_FOLDER_MOST)
    got = measured(tmp_path, monkeypatch, explain_command, limit_long_paths())
    examined(len(got["starts"]), f"working folders a process started in, under a store folder of {limit_long_paths()}")
    assert working_folder_problems(got) == [], "\n".join(got["problems"])
    #: At the bound the deepest working folder is the limit's own: the layout and the run id agree.
    assert got["deepest_start"] == WORKING_FOLDER_MOST, (got["deepest_start"], got["starts"])


def test_sabotage_the_verifier_started_one_folder_deeper_is_named(tmp_path, monkeypatch, explain_command,
                                                                  explain_installed, examined):
    _long_paths_on_here()
    _deeper_verifier(monkeypatch)
    outcome, named = caught(lambda: measured(tmp_path, monkeypatch, explain_command, limit_long_paths()))
    folders = [ln for ln in named.splitlines() if ln.startswith("a working folder")]
    examined(len(folders), f"working folders past the limit named, the verifier one folder deeper, {outcome}")
    #: Measured where nothing refuses the start; refused, with error 267, on Windows.
    assert outcome in ("measured", "refused") and folders, named
    assert all(f"of {WORKING_FOLDER_MOST + 2} characters" in ln for ln in folders), named


#: Windows' error for a path past its limit (ERROR_FILENAME_EXCED_RANGE), which Python raises as
#: FileNotFoundError.
TOO_LONG = 206
#: Windows' error when a process cannot start in the working folder it is given (ERROR_DIRECTORY),
#: which Python raises as NotADirectoryError, with no filename: long paths on or off, CreateProcess
#: refuses a working folder over `WORKING_FOLDER_MOST` characters.
ERROR_DIRECTORY = 267
#: The longest working folder a process starts in: MAX_PATH less its NUL and the trailing backslash
#: Windows adds (SetCurrentDirectory's own documentation), measured by
#: tests/test_windows_working_folder.py.
WORKING_FOLDER_MOST = 258


def _making_a_folder(e: BaseException) -> bool:
    """Whether `e` was raised while a folder was being made: a mkdir or makedirs frame in its
    traceback."""
    tb = e.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_name in ("mkdir", "makedirs"):
            return True
        tb = tb.tb_next
    return False


def caught(measure) -> tuple[str, str]:
    """How a layout too deep for Windows was caught, and what was named: "measured" where the
    measurement completes and names paths over the limit; "refused" where the operating system
    refuses an over-long path first, with Windows' own error. For a process start refused with
    error 267, which names no path, the path is the working folder this process was seen to pass to
    that start. Anything else is "not caught", with why: another error, or a run with no over-long
    path."""
    global _STARTED
    _STARTED = started = []
    try:
        got = measure()
    except OSError as e:
        if getattr(e, "winerror", None) == ERROR_DIRECTORY and e.filename is None:
            folder = started[-1] if started else ""
            if len(folder) > WORKING_FOLDER_MOST:
                return "refused", f"a working folder of {len(folder)} characters refused: {folder}"
            return "not caught", (f"{type(e).__name__}, winerror {ERROR_DIRECTORY}, the last process start's "
                                  f"working folder {len(folder)} characters: {folder or 'no process was started'}")
        path = os.fsdecode(e.filename) if e.filename is not None else ""
        windows = getattr(e, "winerror", None) == TOO_LONG or (os.name == "nt" and isinstance(e, FileNotFoundError))
        folder = _making_a_folder(e)
        if windows and len(path) > (FOLDER_MOST if folder else FILE_MOST):
            return "refused", f"{'a folder' if folder else 'a path'} of {len(path)} characters refused: {path}"
        return "not caught", f"{type(e).__name__}, winerror {getattr(e, 'winerror', None)}, {len(path)} characters: {e}"
    finally:
        _STARTED = None
    over = [p for p in got["problems"] if " characters: " in p]
    return ("measured", "\n".join(over)) if over else ("not caught", f"no over-long path: {got['problems']}")


def test_sabotage_the_old_layout_is_named(tmp_path, monkeypatch, explain_command, explain_installed, examined):
    from onetrace_console import explain
    monkeypatch.setattr(explain, "FOLDER", "explanations")
    monkeypatch.setattr(explain, "KEY_HEX", 64)
    monkeypatch.setattr(explain, "REPORT", "report")
    outcome, named = caught(lambda: measured(tmp_path, monkeypatch, explain_command))
    examined(len(named.splitlines()), f"over-long paths named, the old layout, caught by {outcome}")
    print(f"the old layout, caught by {outcome}:\n{named}")
    assert outcome in ("measured", "refused"), named


def _windows_error(path: str) -> OSError:
    """The error Windows raises for a path past its limit, as Python raises it there."""
    if os.name == "nt":
        return OSError(2, "The filename or extension is too long", path, TOO_LONG)
    e = FileNotFoundError(2, "The filename or extension is too long", path)
    e.winerror = TOO_LONG
    return e


def _mkdir(error):
    def mkdir():
        raise error
    return mkdir


def _open(error):
    def open_file():
        raise error
    return open_file


def _directory_error() -> OSError:
    """The error CreateProcess gives for a working folder past its limit, as Python raises it there."""
    if os.name == "nt":
        return OSError(0, "The directory name is invalid", None, ERROR_DIRECTORY)
    e = NotADirectoryError(20, "The directory name is invalid")
    e.winerror = ERROR_DIRECTORY
    return e


def _start(folder: str | None):
    """A process start in `folder`, refused as Windows refuses it: the start is seen (its audit
    event, as subprocess raises it before CreateProcess), then error 267 with no filename."""
    def start():
        _hooked()
        if folder is not None:
            sys.audit("subprocess.Popen", sys.executable, [sys.executable], folder, None)
        raise _directory_error()
    return start


_DEEP = "C:\\" + "d" * 300
#: An absolute folder of any length up to 300 on this platform (`/ddd...` or `C:\\ddd...`), as a
#: working folder is passed.
_ROOTED = os.path.abspath(os.sep) + "d" * 300
PLANTED = {
    "a folder past 247, refused": (lambda: _mkdir(_windows_error(_DEEP[:248]))(), "refused"),
    "a file past 259, refused": (lambda: _open(_windows_error(_DEEP[:260]))(), "refused"),
    "over-long paths, measured": (lambda: {"problems": ["260 characters: " + _DEEP[:260]]}, "measured"),
    "another kind of error": (lambda: _mkdir(PermissionError(13, "Access is denied", _DEEP[:260]))(), "not caught"),
    "Windows' error on a short folder": (lambda: _mkdir(_windows_error(_DEEP[:247]))(), "not caught"),
    "Windows' error on a file of 248": (lambda: _open(_windows_error(_DEEP[:248]))(), "not caught"),
    "no over-long path": (lambda: {"problems": []}, "not caught"),
    "Windows' error 267 on a working folder past 258, refused": (lambda: _start(_ROOTED[:259])(), "refused"),
    "Windows' error 267 on a working folder of 258": (lambda: _start(_ROOTED[:258])(), "not caught"),
    "Windows' error 267 with no process started": (lambda: _start(None)(), "not caught"),
}


@pytest.mark.parametrize("planted", list(PLANTED))
def test_sabotage_of_the_sabotage_only_the_two_outcomes_count_as_caught(planted, examined):
    measure, want = PLANTED[planted]
    outcome, named = caught(measure)
    examined(1, "planted outcome")
    assert outcome == want, (planted, outcome, named)
    if want == "not caught":
        assert named, planted


# ------------------------------------------------------------------ one folder, one comparison

def refused_problems(store, comparison, config) -> list[str]:
    """The layout, then a comparison folder whose `key` names another comparison: refused in words
    by every reader and every press, and nothing written into it."""
    from onetrace_console import explain
    out = []
    _fake(config, "mixed.json")
    got = explain.explain(comparison, store)
    folder = Path(store.root) / explain.FOLDER / comparison.key[:explain.KEY_HEX]
    if got.get("exit") != "0" or not (folder / explain.REPORT / "explain").is_dir():
        out.append(f"the explanation is not under {explain.FOLDER}/<16 hex>/{explain.REPORT}: "
                   f"{tried(store, comparison)}")
    if (folder / explain.KEY_FILE).read_text(encoding="ascii").strip() != comparison.key:
        out.append("the folder's key file does not hold the comparison's full key")
    other = comparison.key[:explain.KEY_HEX] + "0" * (64 - explain.KEY_HEX)
    other = other if other != comparison.key else comparison.key[:explain.KEY_HEX] + "1" * (64 - explain.KEY_HEX)
    (folder / explain.KEY_FILE).write_text(other + "\n", encoding="ascii")
    before = sorted(str(p) for p in folder.rglob("*"))
    for name, press in (("Explain", lambda: explain.explain(comparison, store)),
                        ("Show the packet", lambda: explain.packet(comparison, store)),
                        ("the attempts", lambda: explain.attempts(store, comparison.key))):
        try:
            press()
            out.append(f"{name}: not refused")
        except ValueError as e:
            if "holds another comparison's" not in str(e) or other not in str(e):
                out.append(f"{name}: refused, but not in words naming the other key: {e}")
    panel = _text(_panel(_diff(store, comparison)))
    if "holds another comparison's" not in panel:
        out.append(f"the panel does not say so: {panel[:200]}")
    if sorted(str(p) for p in folder.rglob("*")) != before:
        out.append("something was written into the other comparison's folder")
    return out


def test_a_folder_holding_another_comparison_s_key_is_refused_in_words(tmp_path, monkeypatch,
                                                                        explain_installed, examined):
    store, comparison, config = pair_at(padded(tmp_path, len(str(tmp_path)) + 2), monkeypatch)
    examined(1, "comparison folder")
    assert refused_problems(store, comparison, config) == []


def test_sabotage_the_key_check_skipped_is_named(tmp_path, monkeypatch, explain_installed, examined):
    from onetrace_console import explain
    store, comparison, config = pair_at(padded(tmp_path, len(str(tmp_path)) + 2), monkeypatch)
    monkeypatch.setattr(explain, "folder_of",
                        lambda store, key: Path(store.root) / explain.FOLDER / key[:explain.KEY_HEX])
    examined(1, "comparison folder, the check skipped")
    assert refused_problems(store, comparison, config) != []


# ------------------------------------------------------------------ the line before the command runs

#: The panel's line, word for word as ruled; N and the limit filled in.
RULED = ("This store's folder is {n} characters long. On Windows with long paths off, Explain needs it "
         "to be {limit} or fewer. Turn on long paths, or move the store to a shorter folder.")


def line_problems(store, comparison, config, monkeypatch, *, enabled: bool) -> list[str]:
    """On Windows (as the console is told it is), a store folder one character over the limit: with
    long paths off, the ruled line, word for word, and the command never run; with them on, no line
    and the buttons."""
    from onetrace_console import explain
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(explain, "long_paths", lambda: enabled)
    out = []
    n = len(str(Path(store.root).parent))
    if n != explain.LIMIT + 1:
        out.append(f"the store folder is {n} characters, not the limit and one")
    panel = _panel(_diff(store, comparison))
    want = RULED.format(n=n, limit=explain.LIMIT)
    if enabled:
        if "data-explain=\"too-long\"" in panel or "Explain</button>" not in panel:
            out.append("long paths on: the line is shown, or Explain is not")
        return out
    if _text(panel).removeprefix(explain.TITLE).strip() != want:
        out.append(f"the panel: {_text(panel)!r}, not {want!r}")
    for name, press in (("Explain", lambda: explain.explain(comparison, store)),
                        ("Show the packet", lambda: explain.packet(comparison, store))):
        try:
            press()
            out.append(f"{name}: the command was run")
        except ValueError as e:
            if str(e) != want:
                out.append(f"{name}: refused with {e}")
    if (Path(store.root) / explain.FOLDER).exists():
        out.append("an explanation folder was made")
    return out


@pytest.mark.parametrize("enabled", [False, True], ids=["long paths off", "long paths on"])
def test_over_the_limit_on_windows_the_panel_says_so_before_the_command_runs(
        tmp_path, monkeypatch, explain_installed, examined, enabled):
    from onetrace_console import explain
    store, comparison, config = pair_at(padded(tmp_path, explain.LIMIT + 1), monkeypatch)
    examined(1, "comparison page")
    assert line_problems(store, comparison, config, monkeypatch, enabled=enabled) == []


def test_at_the_limit_the_panel_offers_explain(tmp_path, monkeypatch, explain_installed, examined):
    from onetrace_console import explain
    store, comparison, _ = pair_at(padded(tmp_path, explain.LIMIT), monkeypatch)
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(explain, "long_paths", lambda: False)
    examined(1, "comparison page")
    panel = _panel(_diff(store, comparison))
    assert explain.too_long(store) is None and "Explain</button>" in panel, _text(panel)


def test_sabotage_the_line_s_words_changed_is_named(tmp_path, monkeypatch, explain_installed, examined):
    from onetrace_console import explain
    store, comparison, config = pair_at(padded(tmp_path, explain.LIMIT + 1), monkeypatch)
    monkeypatch.setattr(explain, "TOO_LONG", explain.TOO_LONG.replace("Turn on long paths", "Enable long paths"))
    examined(1, "comparison page")
    assert line_problems(store, comparison, config, monkeypatch, enabled=False) != []


#: The panel's line past the working-folder bound, word for word as ruled; N and the limits filled in.
RULED_EVEN_ON = ("This store's folder is {n} characters long. Explain needs it to be {limit} or fewer, even with "
                 "long paths on: Windows starts no program in a folder of more than {most} characters. Move the "
                 "store to a shorter folder.")


def even_on_problems(store, comparison, monkeypatch, *, enabled: bool) -> list[str]:
    """On Windows (as the console is told it is), long paths on or off: a store folder over
    `limit_long_paths()` has the ruled line, word for word, and the command never runs; at it, with
    long paths on, Explain is offered."""
    from onetrace_console import explain
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(explain, "long_paths", lambda: enabled)
    n = len(str(Path(store.root).parent))
    panel = _panel(_diff(store, comparison))
    out = []
    if n <= limit_long_paths():
        if "data-explain=\"too-long\"" in panel or "Explain</button>" not in panel:
            out.append(f"at {n}, long paths {'on' if enabled else 'off'}: Explain is not offered: {_text(panel)!r}")
        return out
    want = RULED_EVEN_ON.format(n=n, limit=limit_long_paths(), most=WORKING_FOLDER_MOST)
    if _text(panel).removeprefix(explain.TITLE).strip() != want:
        out.append(f"the panel: {_text(panel)!r}, not {want!r}")
    for name, press in (("Explain", lambda: explain.explain(comparison, store)),
                        ("Show the packet", lambda: explain.packet(comparison, store))):
        try:
            press()
            out.append(f"{name}: the command was run")
        except ValueError as e:
            if str(e) != want:
                out.append(f"{name}: refused with {e}")
        except OSError as e:
            out.append(f"{name}: the command was run, and failed: {e}")
    if (Path(store.root) / explain.FOLDER).exists():
        out.append("an explanation folder was made")
    return out


@pytest.mark.parametrize("length, enabled", [(0, True), (1, True), (1, False)],
                         ids=["at the bound, long paths on", "one over, long paths on", "one over, long paths off"])
def test_past_the_working_folder_bound_the_panel_says_so_long_paths_on_or_off(
        tmp_path, monkeypatch, explain_installed, examined, length, enabled):
    _long_paths_on_here()
    store, comparison, config = pair_at(padded(tmp_path, limit_long_paths() + length), monkeypatch)
    examined(1, "comparison page")
    assert even_on_problems(store, comparison, monkeypatch, enabled=enabled) == []


def test_sabotage_the_bound_s_line_words_changed_is_named(tmp_path, monkeypatch, explain_installed, examined):
    from onetrace_console import explain
    _long_paths_on_here()
    store, comparison, config = pair_at(padded(tmp_path, limit_long_paths() + 1), monkeypatch)
    monkeypatch.setattr(explain, "TOO_LONG_EVEN_ON", explain.TOO_LONG_EVEN_ON.replace("Move the store", "Move your store"))
    examined(1, "comparison page")
    assert even_on_problems(store, comparison, monkeypatch, enabled=True) != []


def test_long_paths_is_read_from_the_registry_on_windows_only(examined):
    from onetrace_console import explain
    examined(1, "setting")
    if os.name != "nt":
        assert explain.long_paths() is None
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
        held = winreg.QueryValueEx(k, "LongPathsEnabled")[0]
    assert explain.long_paths() is (held == 1)
