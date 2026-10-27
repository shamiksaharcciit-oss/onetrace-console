"""A comparison's suggested explanation: the `onetrace-explain` command, run as a person runs it.

An explanation is a suggestion about a record, never a reading of it. The console runs the
command only when a person presses Explain on a comparison's page, and only that comparison; it
never imports `onetrace_explain` (tests/test_explain_panel.py holds it to that), and nothing it
draws as a verdict, a badge, a count, a summary line or an incident reads an explanation back.

Each comparison has a folder of its own, `x/<first 16 hex of its key>/` in the store, short so
that on Windows with long paths off an explanation fits a store folder of up to `LIMIT` characters,
and with long paths on, every process it starts does, up to `LIMIT_LONG_PATHS`:
- `key`: the comparison's full key; a folder whose `key` names another comparison is refused;
- `a/` and `b/`: the two stored runs, laid out byte for byte (`checks.materialise`);
- `r/`: `onetrace localize a b --out r`, the folder the command reads (`diff` where localize
  refuses), run there so no path of this machine is in what is sent;
- `r/explain/<run id>/`, `<run id>.explanation.json` and `.txt`: the command's own;
- `attempts/`: each press, with the command's exit and its own lines;
- `checks/` and `verified/`: each check run from an explanation, and onetrace-verify's reading of
  each explanation's record.

Before the first send of a kind of item to an endpoint the command lists the kinds and asks; the
console runs it without `--yes` and with an empty pipe for its standard input, never NUL: a pipe is
never a terminal on any platform, and NUL, a character device, can be read as one on Windows. So the
command says what it would send and stops (exit 2, "not confirmed"). The panel shows the command's own lines and a Send
button; only that press passes `--yes`. Which endpoint has been sent which kinds is the command's own
record, so the question comes once per endpoint, as the command decides.

A public console presses nothing. It shows the explanations its build kept (`keep`), read-only, as it
shows the drift reports its build kept: the build takes them only as onetrace-explain's own records,
from the folder the command wrote `explain/` under, and keeps one only where its record verifies, its
explanation is its record's post-check with its record's model, and its evidence names the two runs
of a comparison the build holds. Anything else is refused with its reason, in `x/kept.json`, and never
shown. Without a kept record the public panel says it is not set up, as before.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

#: The label the command writes into every explanation it records (`keep` checks it is there).
LABEL = "Suggested explanation — AI-generated, may be wrong"
#: The panel's own heading, once; every explanation inside it carries AI_LINE with its model.
TITLE = "What may have happened"
AI_LINE = "AI-generated, may be wrong"
#: A kept claim's kind, as the command records it, by its badge.
KIND_WORDS = {"lead": "Lead (possible culprit)", "ruled out": "Ruled out", "note": "Note"}
KIND_ORDER = ("lead", "ruled out", "note")
#: Where the formats the panel reads are written down.
FORMAT_PAGE = "https://oneproof.dev/onetrace/explain-format.md"
NOT_INSTALLED = "onetrace-explain is not installed with this console, so no explanation can be asked for."
NOT_SET_UP_DEMO = "Explanations are not set up on this demo."
ALL_DROPPED = "No suggestion could be tied to the record"
UNREACHED = "The model couldn't be reached, or replied with nothing usable: no explanation was written."
#: The command's own line when no model is named.
NO_MODEL_MARK = "no model is configured"
#: The command's own lines before a first send, and its line when not confirmed.
ASKS_MARKS = ("never sent there before", "constants go with their values")
TIMEOUT = 300
#: A check the console runs, by the explanation's own check kind; `mask` and `reproduce` need a
#: file or a runner a person names, so they are shown and not run.
RUNNABLE = ("text", "for", "match")


#: Set while a static export draws (`export_static`): its pages are files, so nothing on them can
#: press anything, and the panel is drawn as a public console draws it -- its place only.
_NO_PRESSES: contextvars.ContextVar[bool] = contextvars.ContextVar("explain_no_presses", default=False)


@contextlib.contextmanager
def no_presses():
    token = _NO_PRESSES.set(True)
    try:
        yield
    finally:
        _NO_PRESSES.reset(token)


def _public() -> bool:
    from onetrace_console.frame import rendering_public
    return rendering_public() or _NO_PRESSES.get()


def places(scripts: str | None, python: str) -> list[Path]:
    """Where the command is looked for first, in order: the interpreter's scripts folder, then the
    folder of the Python itself. A venv's Python sits beside its commands; a base Python on
    Windows keeps them in `Scripts\\`, not beside `python.exe`."""
    return ([Path(scripts)] if scripts else []) + [Path(python).parent]


def find(windows: bool, scripts: str | None, python: str, which) -> Path | None:
    """The command by its name on the platform, in `places`, then by `which`; None where it isn't."""
    name = "onetrace-explain.exe" if windows else "onetrace-explain"
    for folder in places(scripts, python):
        if (folder / name).is_file():
            return folder / name
    found = which(name)
    return Path(found) if found else None


def command() -> Path | None:
    """The `onetrace-explain` command for this interpreter; None where it isn't."""
    return find(os.name == "nt", sysconfig.get_path("scripts"), sys.executable, shutil.which)


#: The layout's parts the console sets: `<store>/x/<KEY_HEX hex>/r`, `r` the folder handed to the
#: command, and the file in each comparison's folder holding its full key.
FOLDER, KEY_HEX, REPORT, KEY_FILE = "x", 16, "r", "key"
#: The versions whose parts below `r` were measured, and those parts: the deepest path they write
#: there is `/explain/<run id>/artifacts/_staging/post_check/checked.json.<8>.tmp`, the run id
#: onetrace-explain's (27 characters), the staging folder and temporary name the SDK's
#: (tests/test_explain_paths.py measures them, and refuses other versions).
MEASURED = {"onetrace-explain": "0.1.0", "onetrace": "0.5.0"}
#: onetrace-explain's run id, as measured with those versions.
RUN_ID = 27
MEASURED_BELOW = len("/explain/") + RUN_ID + len("/artifacts/_staging/post_check/checked.json") + len(".12345678.tmp")
#: The longest path Windows opens with long paths off, its NUL apart.
WINDOWS_PATH = 259
#: The longest store folder (`store_root`, the Store's own folder `store` within it) an explanation
#: fits on Windows with long paths off.
LIMIT = WINDOWS_PATH - (len("/store") + len(f"/{FOLDER}/") + KEY_HEX + len(f"/{REPORT}") + MEASURED_BELOW)
TOO_LONG = ("This store's folder is {n} characters long. On Windows with long paths off, Explain needs it "
            "to be {limit} or fewer. Turn on long paths, or move the store to a shorter folder.")
#: The longest working folder Windows starts a process in, long paths on or off: MAX_PATH less its NUL
#: and the trailing backslash Windows adds (tests/test_windows_working_folder.py measures it).
WORKING_FOLDER = 258
#: The longest store folder whose processes all start on Windows, long paths on or off. The deepest
#: working folder is the verifier's, the record's own folder `<store>/x/<KEY_HEX hex>/r/explain/<run id>`.
LIMIT_LONG_PATHS = WORKING_FOLDER - (len("/store") + len(f"/{FOLDER}/") + KEY_HEX + len(f"/{REPORT}")
                                     + len("/explain/") + RUN_ID)
TOO_LONG_EVEN_ON = ("This store's folder is {n} characters long. Explain needs it to be {limit} or fewer, even with "
                    "long paths on: Windows starts no program in a folder of more than {most} characters. Move the "
                    "store to a shorter folder.")


def _on_windows() -> bool:
    return os.name == "nt"


def long_paths() -> bool | None:
    """Windows' LongPathsEnabled, as the registry holds it (True or False); None elsewhere. Unreadable
    is False: the console then says what to turn on, rather than run a command that cannot write."""
    if not _on_windows():
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            return winreg.QueryValueEx(k, "LongPathsEnabled")[0] == 1
    except OSError:
        return False


def too_long(store) -> str | None:
    """The panel's line where the store folder is too long on Windows, the command then never run:
    longer than `LIMIT_LONG_PATHS`, long paths on or off, the line that says to move it; longer than
    `LIMIT` with long paths off, the line that also offers turning them on. None where it fits, or not
    on Windows."""
    if not _on_windows():
        return None
    n = len(str(Path(os.path.abspath(store.root)).parent))
    if n > LIMIT_LONG_PATHS:
        return TOO_LONG_EVEN_ON.format(n=n, limit=LIMIT_LONG_PATHS, most=WORKING_FOLDER)
    if n > LIMIT and not long_paths():
        return TOO_LONG.format(n=n, limit=LIMIT)
    return None


def folder_of(store, key: str) -> Path:
    from onetrace_console.store import _SHA256
    if not _SHA256.match(key):
        raise ValueError(f"not a comparison key: {key!r}")
    folder = Path(store.root) / FOLDER / key[:KEY_HEX]
    held = folder / KEY_FILE
    if held.is_file():
        other = held.read_text(encoding="ascii", errors="replace").strip()
        if other != key:
            raise ValueError(f"the explanations folder {FOLDER}/{key[:KEY_HEX]} holds another comparison's, "
                             f"{other!r}, whose key begins as this one's does")
    return folder


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _prepare(comparison, store, folder: Path) -> None:
    """The two runs and the report the command reads, laid out once per comparison."""
    from onetrace_console.checks import materialise
    from onetrace_console.child import utf8_env
    if (folder / REPORT).is_dir():
        return
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / KEY_FILE).is_file():
        (folder / KEY_FILE).write_bytes(comparison.key.encode("ascii") + b"\n")
    for side, key in (("a", comparison.run_a), ("b", comparison.run_b)):
        if not (folder / side).is_dir():
            run = store.get_run(key)
            if run is None:
                raise ValueError("a run of this comparison is no longer stored")
            materialise(run, store, folder / side)
    for verb in ("localize", "diff"):
        out = folder / f"report-{verb}"
        shutil.rmtree(out, ignore_errors=True)
        proc = subprocess.run([sys.executable, "-m", "onetrace", verb, "a", "b", "--out", out.name],
                              cwd=folder, capture_output=True, timeout=TIMEOUT, env=utf8_env())
        if proc.returncode in (0, 1) and (out / f"{verb}.json").is_file():
            out.rename(folder / REPORT)
            return
    raise ValueError("neither localize nor diff wrote a report this command can read")


def _run(folder: Path, args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    from onetrace_console.child import utf8_env
    return subprocess.run([str(command()), *args], cwd=folder, capture_output=True, timeout=TIMEOUT,
                          input=b"", env=utf8_env(env))


def _keep(folder: Path, kind: str, args: list[str], proc, *, note: str = "", steps: dict | None = None) -> dict:
    """An attempt, kept: the command's exit ("" where it gave none, with `note` saying why), its own
    lines, and the step times (seconds, one decimal)."""
    d = folder / "attempts"
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob("*.json"))) + 1
    code = None if proc is None else proc.returncode
    attempt = {"n": str(n), "kind": kind, "at": _now(), "command": "onetrace-explain " + " ".join(args),
               "exit": "" if code is None else str(code),
               "stdout": proc.stdout.decode("utf-8", "replace") if proc is not None else "",
               "stderr": proc.stderr.decode("utf-8", "replace") if proc is not None else ""}
    if note:
        attempt["note"] = note
    if steps is not None:
        attempt["steps"] = {k: f"{v:.1f}" for k, v in steps.items()}
    (d / f"{n:06d}.json").write_text(json.dumps(attempt, indent=1, sort_keys=True), encoding="utf-8")
    return attempt


def explain(comparison, store, *, send: bool = False) -> dict:
    """One press of Explain (`send` False) or of Send (`send` True, which passes `--yes`), run to its
    end before this returns: `start`'s work, in place. Refused as `start` refuses."""
    start(comparison, store, send=send, in_place=True)
    return attempts(store, comparison.key)[-1]


# ------------------------------------------------------------------ a press, while it runs
#: A press starts the work and returns at once (`start`); the panel reads the work's state
#: (`state`, `running.json` in the comparison's folder) and says what is happening. The step is
#: read from the command's own record as it writes it: its evidence receipt written, the packet has
#: gone to the model; its model receipt written, the reply is being checked.
RUNNING_FILE = "running.json"
STEP_WORDS = {"preparing": "Preparing the comparison",
              "waiting": "Sent to {model} and waiting for its reply",
              "checking": "Checking the reply",
              "verifying": "Verifying the explanation's record"}
#: The model as onetrace-explain's configuration names it, where the console can read it.
UNNAMED_MODEL = "the model onetrace-explain is configured with"
BUSY = "An explanation of this comparison is being made; one press at a time."
LIMIT_REACHED = "it reached its limit of {n} seconds and was stopped"
COULD_NOT_START = "it could not start: {why}"
#: Each attempt's step times, in the order the panel says them.
STEP_TIMES = (("preparing", "Preparing"), ("model", "the model's reply"), ("post_check", "the post-check"),
              ("verifying", "verifying"))
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_THREADS: dict[str, threading.Thread] = {}


class Busy(ValueError):
    """A press while another of the same comparison runs."""


def _lock(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def configured_model() -> str:
    """`provider:name` from the [model] table of onetrace-explain's configuration file, read as data
    (the command reads the same file; the console never imports it); UNNAMED_MODEL where unread."""
    import tomllib
    path = Path(os.environ.get("ONETRACE_EXPLAIN_CONFIG") or Path.home() / ".config" / "onetrace" / "explain.toml")
    try:
        m = tomllib.loads(path.read_text(encoding="utf-8")).get("model", {})
    except (OSError, ValueError, UnicodeDecodeError):
        return UNNAMED_MODEL
    return f"{m['provider']}:{m['name']}" if isinstance(m, dict) and m.get("provider") and m.get("name") else UNNAMED_MODEL


def _spawn(work) -> None:
    threading.Thread(target=work, daemon=True).start()


def start(comparison, store, *, send: bool = False, done=None, in_place: bool = False) -> dict:
    """Start one press of Explain or Send, and return at once (`in_place`: run it here). Refused
    with BUSY while one of the same comparison runs, and, the command never run, where the store
    folder is too long for it (`too_long`). `done` is called when it ends."""
    if too_long(store):
        raise ValueError(too_long(store))
    key = comparison.key
    lock = _lock(key)
    if not lock.acquire(blocking=False):
        raise Busy(BUSY)
    folder = folder_of(store, key)
    folder.mkdir(parents=True, exist_ok=True)
    _set_state(folder, {"kind": "send" if send else "explain", "started_at": _now(), "model": configured_model(),
                        "step": "preparing"})
    finished = threading.Event()

    def work():
        try:
            _press(comparison, store, folder, send)
        finally:
            (folder / RUNNING_FILE).unlink(missing_ok=True)
            lock.release()
            finished.set()
            if done is not None:
                done()
    thread = SimpleThread(finished)
    _THREADS[key] = thread
    if in_place:
        work()
    else:
        _spawn(work)
    return {"started": True}


class SimpleThread:
    """What `wait` waits on: the press's end."""
    def __init__(self, finished: threading.Event):
        self.finished = finished


def wait(key: str, timeout: float | None = None) -> bool:
    """Wait for the comparison's press to end; whether it ended in time."""
    t = _THREADS.get(key)
    return True if t is None else t.finished.wait(timeout)


def _set_state(folder: Path, s: dict) -> None:
    tmp = folder / (RUNNING_FILE + ".tmp")
    tmp.write_text(json.dumps(s, sort_keys=True), encoding="utf-8")
    os.replace(tmp, folder / RUNNING_FILE)


def state(store, key: str) -> dict:
    """The press now running on this comparison: its step, in words, when it started and how long
    ago; {"running": False} where none runs."""
    from onetrace_console.bounded_json import load_json_bounded
    path = folder_of(store, key) / RUNNING_FILE
    try:
        s = load_json_bounded(path.read_text(encoding="utf-8"), RUNNING_FILE)
    except (OSError, ValueError):
        return {"running": False}
    started = datetime.fromisoformat(s["started_at"])
    return {"running": True, "step": s["step"], "words": STEP_WORDS[s["step"]].format(model=s.get("model", UNNAMED_MODEL)),
            "started": started.strftime("%H:%M:%S UTC"),
            "elapsed": int((datetime.now(timezone.utc) - started).total_seconds())}


def _press(comparison, store, folder: Path, send: bool) -> None:
    """The work of one press: prepare, run the command (watching its record for the step), verify
    what it recorded. Keeps an attempt, with its step times, whatever happens."""
    kind = "send" if send else "explain"
    args = [REPORT, *(["--yes"] if send else [])]
    times, t0, wall0 = {}, time.monotonic(), time.time()
    from onetrace_console.bounded_json import load_json_bounded
    s = load_json_bounded((folder / RUNNING_FILE).read_text(encoding="utf-8"), RUNNING_FILE)

    def step(name: str) -> None:
        s["step"] = name
        _set_state(folder, s)
    try:
        _prepare(comparison, store, folder)
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        from onetrace_console.oserror import said
        _keep(folder, kind, args, None, note=f"preparing the comparison failed: {said(e) if isinstance(e, OSError) else e}",
              steps={"preparing": time.monotonic() - t0})
        return
    d = folder / REPORT / "explain"
    before = {p.name for p in d.iterdir()} if d.is_dir() else set()
    out, err = folder / "attempts" / ".stdout", folder / "attempts" / ".stderr"
    out.parent.mkdir(parents=True, exist_ok=True)
    from onetrace_console.child import utf8_env
    note, code = "", None
    marks = {}
    try:
        with open(out, "wb") as o, open(err, "wb") as e_:
            proc = subprocess.Popen([str(command()), *args], cwd=folder, stdin=subprocess.PIPE, stdout=o, stderr=e_,
                                    env=utf8_env(None))
            if proc.stdin is not None:
                proc.stdin.close()
            deadline = t0 + TIMEOUT
            while (code := proc.poll()) is None:
                new = [p for p in (d.iterdir() if d.is_dir() else ()) if p.is_dir() and p.name not in before]
                receipts = new[0] / "receipts" if new else None
                if receipts and "evidence" not in marks and any(receipts.glob("01-*.json")):
                    marks["evidence"] = time.monotonic()
                    step("waiting")
                if receipts and "model" not in marks and any(receipts.glob("02-*.json")):
                    marks["model"] = time.monotonic()
                    step("checking")
                if time.monotonic() > deadline:
                    proc.kill()
                    proc.wait()
                    code, note = None, LIMIT_REACHED.format(n=TIMEOUT)
                    break
                time.sleep(0.1)
    except OSError as e:
        code, note = None, COULD_NOT_START.format(why=getattr(e, "strerror", None) or type(e).__name__)
    #: The step times from the command's own receipts, each written as its stage closes: the
    #: watch above only says the step while it runs, and a quick stage can close between looks.
    ended = time.time()
    new = sorted(p for p in (d.iterdir() if d.is_dir() else ()) if p.is_dir() and p.name not in before)
    closed = [min((r.stat().st_mtime for r in (new[0] / "receipts").glob(f"0{i}-*.json")), default=None)
              if new else None for i in (1, 2)]
    times["preparing"] = (closed[0] or ended) - wall0
    if closed[0] is not None:
        times["model"] = (closed[1] or ended) - closed[0]
    if closed[1] is not None:
        times["post_check"] = ended - closed[1]
    recorded = [p.name.removesuffix(".explanation.json") for p in (d.glob("*.explanation.json") if d.is_dir() else ())
                if p.name.removesuffix(".explanation.json") not in before]
    if recorded:
        step("verifying")
        v0 = time.monotonic()
        for rid in recorded:
            verified(store, comparison.key, rid)
        times["verifying"] = time.monotonic() - v0
    got = SimpleNamespace(returncode=code, stdout=out.read_bytes() if out.is_file() else b"",
                          stderr=err.read_bytes() if err.is_file() else b"")
    _keep(folder, kind, args, got, note=note, steps=times)
    out.unlink(missing_ok=True)
    err.unlink(missing_ok=True)


def packet(comparison, store) -> dict:
    """`--dry-run`: the packet's bytes, their size and sha256, exactly as the command printed them."""
    if too_long(store):
        raise ValueError(too_long(store))
    folder = folder_of(store, comparison.key)
    _prepare(comparison, store, folder)
    return _keep(folder, "packet", [REPORT, "--dry-run"], _run(folder, [REPORT, "--dry-run"]))


def attempts(store, key: str) -> list[dict]:
    d = folder_of(store, key) / "attempts"
    from onetrace_console.bounded_json import load_json_bounded
    return ([load_json_bounded(p.read_text(encoding="utf-8"), p.name) for p in sorted(d.glob("*.json"))]
            if d.is_dir() else [])


def explanations(store, key: str) -> list[dict]:
    """Each explanation of the comparison, as the command wrote it, newest first: ordered by the
    press whose command printed `recorded: <its record>`; never merged."""
    from onetrace_console.bounded_json import load_json_bounded
    d = folder_of(store, key) / REPORT / "explain"
    order = {}
    for a in attempts(store, key):
        for ln in a.get("stdout", "").splitlines():
            if ln.startswith("recorded: "):
                order[ln[len("recorded: "):].strip().replace("\\", "/").rsplit("/", 1)[-1]] = int(a["n"])
    out = []
    for p in d.glob("*.explanation.json") if d.is_dir() else ():
        e = load_json_bounded(p.read_text(encoding="utf-8"), p.name)
        txt = p.with_name(p.name.removesuffix(".json") + ".txt")
        e["_text"] = txt.read_text(encoding="utf-8") if txt.is_file() else ""
        out.append(e)
    return sorted(out, key=lambda e: (order.get(e.get("record", ""), 0), e.get("record", "")), reverse=True)


def check_lines(e: dict) -> list[str]:
    """The checks as the command printed them, in its order."""
    lines, on = [], False
    for ln in e.get("_text", "").splitlines():
        if ln.startswith("checks onetrace can run"):
            on = True
            continue
        if on:
            if not ln.startswith("  "):
                break
            lines.append(ln.strip())
    return lines


def check_argv(check: dict) -> list[str] | None:
    """The console's own run of a check, over the laid-out runs; None for one it doesn't run."""
    c, node = check.get("check"), check.get("node", "")
    if c == "text":
        return [sys.executable, "-m", "onetrace", "diff", "a", "b", "--text", "--stage", node]
    if c == "for":
        return [sys.executable, "-m", "onetrace", "localize", "a", "b", "--for", node]
    if c == "match" and check.get("run") in ("baseline", "candidate"):
        return [sys.executable, "-m", "onetrace", "match", "a" if check["run"] == "baseline" else "b"]
    return None


def run_check(store, key: str, record: str, i: int) -> dict:
    """Check `i` of explanation `record`, rebuilt from the explanation's own checks: never a
    command from the request. Its own output and exit, kept."""
    from onetrace_console.child import utf8_env
    found = [e for e in explanations(store, key) if e.get("record") == record and record]
    if not found or not (0 <= i < len(found[0].get("checks", []))):
        raise ValueError("no such check")
    argv = check_argv(found[0]["checks"][i])
    if argv is None:
        raise ValueError("this check needs a file or a runner you name, so the console does not run it")
    folder = folder_of(store, key)
    proc = subprocess.run(argv, cwd=folder, capture_output=True, timeout=TIMEOUT, input=b"", env=utf8_env())
    out = {"record": record, "i": str(i), "at": _now(), "exit": str(proc.returncode),
           "command": (check_lines(found[0]) + [""] * (i + 1))[i],
           "output": (proc.stdout + proc.stderr).decode("utf-8", "replace")}
    d = folder / "checks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{record}-{i}.json").write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    return out


def check_result(store, key: str, record: str, i: int) -> dict | None:
    p = folder_of(store, key) / "checks" / f"{record}-{i}.json"
    from onetrace_console.bounded_json import load_json_bounded
    return load_json_bounded(p.read_text(encoding="utf-8"), p.name) if p.is_file() else None


def _chain_head(folder: Path) -> str:
    """The record's chain head, as its MANIFEST.json names it; "" where it names none."""
    try:
        from onetrace_console.bounded_json import load_json_bounded
        head = load_json_bounded((folder / "MANIFEST.json").read_text(encoding="utf-8"), "MANIFEST.json").get("chain_head")
    except (OSError, ValueError, AttributeError):
        return ""
    return head if isinstance(head, str) else ""


def verified(store, key: str, record: str) -> str:
    """onetrace-verify's summary line of an explanation's record: kept beside it, keyed by the
    record's chain head, and read again only where that head changed."""
    folder = folder_of(store, key)
    run = folder / REPORT / "explain" / record
    kept = folder / "verified" / f"{record}.json"
    head = _chain_head(run)
    try:
        from onetrace_console.bounded_json import load_json_bounded
        k = load_json_bounded(kept.read_text(encoding="utf-8"), kept.name)
        if isinstance(k, dict) and k.get("chain_head") == head and isinstance(k.get("said"), str):
            return k["said"]
    except (OSError, ValueError):
        pass
    _, said = _record_verifies(run)
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text(json.dumps({"chain_head": head, "said": said}, sort_keys=True), encoding="utf-8")
    return said

# ------------------------------------------------------------------ the panel
#: The panel reads what earlier presses kept; drawing it runs nothing.


def _button(path: str, words: str) -> str:
    from onetrace_console.words import escape
    return f'<button type="button" data-explain-post="{escape(path)}" hidden>{escape(words)}</button>'


def receipts_by_node(comparison, store) -> tuple[dict, dict]:
    """Each run's receipts by node, as onetrace-explain names a node in its cites (`name`, or
    `name#instance`): what a chip reads to say whether a cited item differs. Empty where a run's
    receipts can't be read."""
    from onetrace_console.render import _receipts_in_order

    def by_node(key: str) -> dict:
        out = {}
        for r in _receipts_in_order(key, store):
            st = r.get("stage") if isinstance(r.get("stage"), dict) else {}
            node = str(st.get("name", "")) + ("#" + str(st["instance"]) if st.get("instance") else "")
            out.setdefault(node, r)
        return out
    return by_node(comparison.run_a), by_node(comparison.run_b)


#: The instrument's fields a packet carries, and so the ones a chip compares.
_INSTRUMENT = ("id", "kind", "version", "config_digest")


def _files(r: dict | None, which: str) -> dict:
    return {i["name"]: i for i in (r or {}).get(which) or [] if isinstance(i, dict) and isinstance(i.get("name"), str)}


def chip(cite: str, facts: dict) -> tuple[list, str]:
    """A cite as its chip says it, and its node: the chip's pieces, each a list of (words, as
    code?), joined by " · " when drawn. From the comparison's record: the stage, the item, and where
    the record holds them, its two values or whether it differs, with "checked" where the console
    read that from the two runs' receipts itself. `facts`: "a" and "b", the two runs' receipts by
    node (`receipts_by_node`); "verdicts", each node's verdict in the page's words; "envelope", the
    comparison's. A cite this does not know is its words alone."""
    parts = cite.split("/")
    if parts[:2] == ["comparison", "verdict"] and facts.get("envelope"):
        return [[("comparison", False)], [("verdict ", False), (facts["envelope"], True)]], ""
    if parts[0] != "node" or len(parts) < 2:
        return [[(cite, True)]], ""
    node, rest = parts[1], parts[2:]
    a, b = facts.get("a", {}).get(node), facts.get("b", {}).get(node)
    read = a is not None and b is not None
    head = [[(node, True)]]
    checked = [[("checked", False)]]

    def pair(x: str, y: str) -> list:
        return [[(x, True), (" same", False)]] if x == y else [[(x, True), (" → ", False), (y, True)]]
    if not rest:
        word = facts.get("verdicts", {}).get(node)
        return head + [[("stage", False)]] + ([[(word, False)]] if word else []), node
    kind = rest[0]
    if kind in ("input", "output") and len(rest) >= 2:
        name = "/".join(rest[1:])
        if name.endswith("/text") and kind == "output":
            return head + [[("output ", False), (name[:-len("/text")], True), (" text", False)]], node
        out = head + [[(kind + " ", False), (name, True)]]
        if read:
            x, y = _files(a, kind + "s").get(name), _files(b, kind + "s").get(name)
            if x is not None or y is not None:
                same = (x or {}).get("digest") == (y or {}).get("digest")
                out += [[("same" if same else "differs", False)]] + checked
        return out, node
    if kind == "constant" and len(rest) >= 2:
        name = "/".join(rest[1:])
        out = head + [[(name, True)]]
        if read:
            ca = ((a.get("assertions") or {}).get("constants") or {}) if isinstance(a.get("assertions"), dict) else {}
            cb = ((b.get("assertions") or {}).get("constants") or {}) if isinstance(b.get("assertions"), dict) else {}
            if name in ca and name in cb:
                out += pair(str(ca[name]), str(cb[name])) + checked
        return out, node
    if kind == "instrument":
        out = head + [[("instrument", False)]]
        if read:
            ia = a.get("instrument") if isinstance(a.get("instrument"), dict) else {}
            ib = b.get("instrument") if isinstance(b.get("instrument"), dict) else {}
            same = all(ia.get(k) == ib.get(k) for k in _INSTRUMENT)
            out += [[("same" if same else "differs", False)]] + checked
        return out, node
    if kind == "outcome":
        out = head + [[("outcome", False)]]
        if read:
            x = str((a.get("outcome") or {}).get("class", "")) if isinstance(a.get("outcome"), dict) else ""
            y = str((b.get("outcome") or {}).get("class", "")) if isinstance(b.get("outcome"), dict) else ""
            if x and y:
                out += pair(x, y) + checked
        return out, node
    return head + [[(" / ".join(rest), False)]], node


def _cite(cite: str, steps: dict, facts: dict | None = None) -> str:
    """A cite as a chip (`chip`), linked to its node's row as the page's graph links it (`steps`:
    node -> href); the cite's own id in its title. A cite of no node on this page is not linked."""
    from onetrace_console.words import escape
    said, node = chip(cite, facts or {})
    inner = " · ".join("".join(f"<code>{escape(w)}</code>" if code else escape(w) for w, code in piece)
                       for piece in said)
    href = (steps.get(node) or steps.get(node.split("#", 1)[0])) if node else None
    tag = "a" if href else "span"
    return (f'<li><{tag} class="chip" data-cite="{escape(cite)}" title="{escape(cite)}"'
            + (f' href="{escape(href)}"' if href else "") + f">{inner}</{tag}></li>")


def _format_page() -> str:
    """The explain format page, by its address in text: no page of the console links or loads
    anything outside this machine."""
    from onetrace_console.words import escape
    return f'The explain format: <span class="mono">{escape(FORMAT_PAGE)}</span>'


FAILED = "The command failed, exit {code}: {line}"
FAILED_NO_EXIT = "The command failed with no exit: {why}."
#: A path of this machine in a line: shown as its last two parts.
_POSIX_PATH = re.compile(r"(?<![\w.])/(?:[^/\s'\"]+/)+([^/\s'\"]+/[^/\s'\"]+)")
_WINDOWS_PATH = re.compile(r"\b[A-Za-z]:\\(?:[^\\\s'\"]+\\)+([^\\\s'\"]+\\[^\\\s'\"]+)")


def shortened(line: str) -> str:
    """`line` with each path of this machine shortened to its last two parts."""
    return _WINDOWS_PATH.sub(lambda m: "…\\" + m.group(1), _POSIX_PATH.sub(lambda m: "…/" + m.group(1), line))


#: A control or bidirectional character in the command's own line: left out of what the panel says.
_UNSHOWN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]")


def _failed_line(a: dict) -> str:
    """Any exit but 0, or none: that the command failed, its exit, and its last line of error output.
    Escaped as a message is, not as a record's words: a path's backslashes are shown as written."""
    from html import escape as _h
    escape = lambda s: _h(_UNSHOWN.sub("", s))  # noqa: E731
    out, err, code = a.get("stdout", ""), a.get("stderr", ""), a.get("exit", "")
    if code == "0":
        return ""
    if code == "":
        return f'<p data-explain="failed">{escape(FAILED_NO_EXIT.format(why=a.get("note") or "it gave none"))}</p>'
    last = (err.strip() or out.strip()).splitlines()[-1].strip() if (err.strip() or out.strip()) else "no output"
    return f'<p data-explain="failed">{escape(FAILED.format(code=code, line=shortened(last)))}</p>'


def _attempt_line(a: dict) -> str:
    """What the latest press got: a failure says so (`_failed_line`), then in the command's own
    words where it has words."""
    from onetrace_console.words import escape
    out, err, code = a.get("stdout", ""), a.get("stderr", ""), a.get("exit", "")
    failed = _failed_line(a)
    if code == "3":
        return failed + f'<p data-explain="unreached">{escape(UNREACHED)}</p>'
    if code == "2":
        line = (err.strip() or out.strip()).splitlines()[-1] if (err.strip() or out.strip()) else ""
        link = (f'<p data-explain="refused">{_format_page()}</p>' if NO_MODEL_MARK in line else "")
        return failed + link
    return failed


def _running_line(s: dict) -> str:
    """The press now running: its step in words, the time it started, and how long ago."""
    from onetrace_console.words import escape
    return (f'<p data-explain="running">{escape(s["words"])}, started {escape(s["started"])} '
            f'<span data-elapsed>({s["elapsed"]} s so far)</span>.</p>')


def _steps_line(store, key: str, record: str) -> str:
    """The step times of the press that recorded `record`, as its attempt keeps them."""
    from onetrace_console.words import escape
    for a in attempts(store, key):
        if record and any(ln.startswith("recorded: ") and ln.strip().replace("\\", "/").endswith("/" + record)
                          for ln in a.get("stdout", "").splitlines()) and a.get("steps"):
            said = " · ".join(f"{words} {a['steps'][k]} s" for k, words in STEP_TIMES if k in a["steps"])
            return f'<p data-explain="steps">{escape(said)}</p>'
    return ""


def _asks(a: dict) -> list[str]:
    """The command's own lines before a first send, where the latest press stopped at them."""
    if a.get("exit") != "2" or a.get("kind") == "packet":
        return []
    return [ln for ln in a.get("stdout", "").splitlines() if any(m in ln for m in ASKS_MARKS)]


def panel(comparison, store, *, public: bool | None = None, steps: dict | None = None,
          facts: dict | None = None) -> str:
    """The comparison's explanation panel: its own frame, below the verdicts, apart from them.
    `facts`, what the page read of the comparison for the chips (`chip`): its verdicts by node and
    its envelope; the two runs' receipts are read here, only where an explanation is drawn."""
    from onetrace_console.words import escape
    head = (f'<section data-section="explain" id="explain" class="explain"><h2>{escape(TITLE)}</h2>')
    is_public = _public() if public is None else public
    held = kept_record(store) if is_public and not _NO_PRESSES.get() else None
    if held is not None:
        return head + _kept_panel(comparison, store, held, steps or {}, facts) + "</section>"
    if is_public or _NO_PRESSES.get():
        return head + f'<p data-explain="not-set-up">{escape(NOT_SET_UP_DEMO)}</p></section>'
    from onetrace_console.explain_setup import LINK, PATH
    setup = f'<p data-explain="setup"><a href="{PATH}">{escape(LINK)}</a></p>'
    if command() is None:
        return head + f'<p data-explain="not-installed">{escape(NOT_INSTALLED)} {_format_page()}</p>{setup}</section>'
    if too_long(store):
        return head + f'<p data-explain="too-long">{escape(too_long(store))}</p></section>'
    key = comparison.key
    head = head.replace('class="explain">', f'class="explain" data-c="{escape(key)}">', 1)
    try:
        tried = attempts(store, key)
    except ValueError as e:
        return head + f'<p data-explain="refused">{escape(str(e))}</p></section>'
    latest = next((a for a in reversed(tried) if a["kind"] != "packet"), None)
    now = state(store, key)
    body = [head, '<p data-explain="what">A suggestion about this comparison\'s record from a model you '
            "configure for <code>onetrace-explain</code>, never a reading of it. The verdicts above are "
            "what they are without it. Nothing is sent until you press Explain.</p>"]
    asks = _asks(latest) if latest and not now["running"] else []
    buttons = [_button(f"/explain?c={key}", "Explain"), _button(f"/explain/packet?c={key}", "Show the packet")]
    if asks:
        body.append('<div data-explain="asks">' + "".join(f'<p class="mono">{escape(ln)}</p>' for ln in asks)
                    + "</div>")
        buttons.insert(0, _button(f"/explain?c={key}&send=yes", "Send"))
    elif latest is not None and not now["running"]:
        body.append(_attempt_line(latest))
    if now["running"]:
        body.append(_running_line(now))
    body.append('<p data-explain="buttons">' + " ".join(buttons) + "</p>" + setup)
    pk = next((a for a in reversed(tried) if a["kind"] == "packet"), None)
    if pk is not None:
        lines = pk.get("stdout", "").splitlines()
        if pk.get("exit") == "0" and len(lines) >= 2:
            body.append('<details data-explain="packet"><summary>The packet, exactly as it would be sent: '
                        f'<span class="mono">{escape(lines[-1])}</span></summary>'
                        f'<pre><code>{escape(lines[0])}</code></pre></details>')
        else:
            body.append(_attempt_line(pk))
    made = explanations(store, key)
    full = {**(facts or {}), **dict(zip(("a", "b"), receipts_by_node(comparison, store)))} if made else {}
    for e in made:
        body.append(_one(e, comparison, store, steps or {}, facts=full))
    if 'data-explain-post' in "".join(body) or "data-copy=" in "".join(body):
        from onetrace_console.explain_script import EXPLAIN_SCRIPT
        body.append(EXPLAIN_SCRIPT)
    body.append("</section>")
    return "".join(body)


#: The explanation's look, in the console's stylesheet (`frame.stylesheet`): a card per claim, its
#: badge in words, its cites as chips; the footer and the record under it in the muted ink (still
#: 4.5:1 or more in both themes). "Hide the details" is a native disclosure: closed, the chips and
#: the footer are not shown, and the cards stay.
EXPLAIN_CSS = """
.cp .explain [data-explain=ai]{margin:0 0 8px;color:var(--ink-soft)}
.cp .explain [data-explain=ai] .ai{font-weight:600;color:var(--cc-ink)}
.cp .explain article+article{margin-top:22px;padding-top:14px;border-top:1px solid var(--line)}
.cp .explain details.ex-more{margin:0 0 8px}
.cp .explain details.ex-more>summary{cursor:pointer;color:var(--accent);font-size:var(--fs-small)}
.cp .explain details.ex-more[open] .when-closed,.cp .explain details.ex-more:not([open]) .when-open{display:none}
.cp .explain details.ex-more:not([open])~.cards [data-cites],
.cp .explain details.ex-more:not([open])~.ex-foot{display:none}
.cp .explain .cards{display:flex;flex-direction:column;gap:10px}
.cp .explain .claim{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-ctl);
  padding:10px 12px;min-width:0}
.cp .explain .claim>p{margin:6px 0}
.cp .explain .badge{display:inline-block;font-size:var(--fs-small);font-weight:600;padding:2px 8px;
  border-radius:var(--r-ctl);background:var(--neu-bg);color:var(--neu-ink)}
.cp .explain .badge[data-kind=lead]{background:var(--cc-bg);color:var(--cc-ink)}
.cp .explain .chips{display:flex;flex-wrap:wrap;gap:6px;list-style:none;margin:6px 0 0;padding:0}
.cp .explain .chip{display:inline-block;max-width:100%;font-size:var(--fs-small);padding:2px 8px;
  border:1px solid var(--line-strong);border-radius:var(--r-ctl);color:var(--ink);overflow-wrap:anywhere}
.cp .explain a.chip{color:var(--accent)}
.cp .explain .checks h3{margin:16px 0 4px;font-size:14px}
.cp .explain .checks li{margin:4px 0}
.cp .explain button[data-copy]{font:inherit;font-size:var(--fs-small);color:var(--ink);background:var(--surface);
  border:1px solid var(--line-strong);border-radius:var(--r-ctl);padding:2px 8px;cursor:pointer}
.cp .explain button[data-copy][hidden]{display:none}
.cp .explain .ex-foot{margin-top:12px;font-size:var(--fs-small);color:var(--ink-muted)}
.cp .explain .ex-foot summary{cursor:pointer}
.cp .explain .ex-foot .meta p{margin:4px 0;overflow-wrap:anywhere}
"""
#: The checks' heading and its lead; on a public console, KEPT_CHECKS follows the lead.
CHECKS = "Checks"
CHECKS_LEAD = "onetrace can run these. A lead is confirmed or ruled out only by what they report."
COPY = "Copy the command"
#: The footer: every claim the post-check read, and those it left out, with their reasons.
FOOTER = "{n} claims checked against the record · {m} left out"
HIDE, SHOW = "Hide the details", "Show the details"


def merged_checks(e: dict) -> list[tuple[int, str]]:
    """The explanation's checks, each command once, in its first place: (its first index, the
    command as the command printed it). A check with no printed command is kept under its index."""
    shown, seen, out = check_lines(e), set(), []
    for i, _ in enumerate(e.get("checks") or []):
        cmd = shown[i] if i < len(shown) else ""
        if cmd and cmd in seen:
            continue
        seen.add(cmd)
        out.append((i, cmd))
    return out


def _dropped(e: dict) -> int:
    """How many claims the post-check left out: the sum of its counts by reason."""
    total = 0
    for n in (e.get("dropped") or {}).values():
        try:
            total += int(n)
        except (TypeError, ValueError):
            continue
    return total


def _one(e: dict, comparison, store, steps: dict, read_only: bool = False, facts: dict | None = None) -> str:
    """One explanation, as the command wrote it: the AI line with its model; a card per kept claim,
    its kind as a badge, its text, its cites as chips; the checks, each command once; the footer,
    what was checked and left out; then its record, dimmed. `read_only`, as a public console draws
    a kept one: the checks are named and none is offered. "Hide the details" folds the chips and
    the footer, with no script: the cards stay."""
    from onetrace_console.words import escape, verbatim
    rec = e.get("record", "")
    facts = facts if facts is not None else {}
    parts = [f'<article data-explanation="{escape(rec)}">',
             f'<p data-explain="ai"><span class="ai">{escape(AI_LINE)}</span> · model '
             f'<span class="mono" data-explain="model">{escape(e.get("model", ""))}</span></p>',
             f'<details class="ex-more" open data-explain="toggle"><summary><span class="when-open">{escape(HIDE)}'
             f'</span><span class="when-closed">{escape(SHOW)}</span></summary></details>']
    claims = e.get("claims") or []
    if not claims:
        parts.append(f'<p data-explain="all-dropped">{escape(ALL_DROPPED)}</p>')
    else:
        cards = []
        for kind in KIND_ORDER:
            for c in (c for c in claims if c.get("kind") == kind):
                chips = "".join(_cite(x, steps, facts) for x in c.get("cites", []))
                cards.append(f'<div class="card claim" data-claim="{escape(kind)}">'
                             f'<span class="badge" data-kind="{escape(kind)}">{escape(KIND_WORDS[kind])}</span>'
                             f'<p data-claim-text>{escape(c.get("text", ""))}</p>'
                             f'<ul class="chips" data-cites aria-label="What it cites">{chips}</ul></div>')
        parts.append('<div class="cards" data-explain="claims">' + "".join(cards) + "</div>")
    merged = merged_checks(e)
    checks = e.get("checks") or []
    if merged:
        rows = []
        for i, cmd in merged:
            if read_only:
                rows.append(f'<li data-check="{i}"><code>{escape(cmd)}</code></li>')
                continue
            run = (_button(f"/explain/check?c={comparison.key}&e={rec}&i={i}", "Run")
                   if check_argv(checks[i]) is not None else
                   f'<button type="button" data-copy="{escape(cmd)}" hidden>{escape(COPY)}</button>')
            got = check_result(store, comparison.key, rec, i)
            out = (f'<details data-explain="check-output"><summary>What it reported: exit '
                   f'<span data-exit>{escape(got["exit"])}</span></summary><pre><code>{verbatim(got["output"])}'
                   "</code></pre></details>" if got else "")
            rows.append(f'<li data-check="{i}"><code>{escape(cmd)}</code> {run}{out}</li>')
        parts.append(f'<div class="checks" data-explain="checks-block"><h3>{escape(CHECKS)}</h3>'
                     f'<p data-explain="checks-lead">{escape(CHECKS_LEAD)}'
                     + (f" {escape(KEPT_CHECKS)}" if read_only else "") + "</p>"
                     '<ul class="plain" data-explain="checks">' + "".join(rows) + "</ul></div>")
    drops = e.get("dropped") or {}
    cdrops = e.get("checks_dropped") or {}
    left = _dropped(e)
    said = escape(FOOTER.format(n=len(claims) + left, m=left))
    reasons = [f"<li>{escape(str(n))} {escape(why)}</li>" for why, n in sorted(drops.items())]
    reasons += [f"<li>checks: {escape(str(n))} {escape(why)}</li>" for why, n in sorted(cdrops.items())]
    from onetrace_console.info_mark import claims_note, mark
    count = mark(claims_note(len(claims), {why: n for why, n in drops.items()}))
    foot = (f'<details data-explain="left-out"><summary>{said}</summary><ul class="plain">{"".join(reasons)}</ul></details>{count}'
            if reasons else f'<p data-explain="left-out">{said}{count}</p>')
    meta = [f'<p data-explain="record">Its record: <span class="mono">explain/{escape(rec)}/</span>, '
            f'onetrace-verify: <span class="mono" data-verified>{escape(verified(store, comparison.key, rec))}</span></p>',
            "" if read_only else _steps_line(store, comparison.key, rec)]
    parts.append(f'<div class="ex-foot" data-explain="footer">{foot}<div class="meta">{"".join(meta)}</div></div>')
    parts.append("</article>")
    return "".join(parts)


# ------------------------------------------------------------------ kept explanations
#: What a public console's build kept, and what it refused, with the reasons: `x/kept.json`.
KEPT_FILE = "kept.json"
KEPT_FORMAT = "onetrace-console/kept-explanations/0.1"
#: A public page whose comparison has none kept, on a build that kept some.
KEPT_NONE = "This demo kept no explanation of this comparison."
#: On a kept explanation: the checks are named, and a public console runs none.
KEPT_CHECKS = "This demo runs none of them."
#: The reasons the build refuses a file, the first that holds.
NOT_ITS_FILE = "not a file onetrace-explain writes in explain/"
NO_EXPLANATION = "a record with no explanation beside it"
NOT_AN_EXPLANATION = "not an explanation as onetrace-explain writes one"
NO_RECORD = "its record is missing"
LINKED = "its record holds a link"
NOT_VERIFIED = "its record does not verify"
NOT_ITS_RECORD = "it is not its record's post-check"
NOT_ITS_MODEL = "its model is not its record's"
NOT_HELD = "it explains a comparison this build does not hold"
#: The fields onetrace-explain adds to its record's post-check, in its `.explanation.json`.
_ADDED = ("label", "model", "record")


def kept_record(store) -> dict | None:
    """What the build kept (`keep`); None where it kept nothing, or kept no record this reads."""
    from onetrace_console.bounded_json import load_json_bounded
    path = Path(store.root) / FOLDER / KEPT_FILE
    if not path.is_file():
        return None
    record = load_json_bounded(path.read_text(encoding="utf-8"), KEPT_FILE)
    return record if isinstance(record, dict) and record.get("format") == KEPT_FORMAT else None


def _held_pairs(store) -> dict[tuple[str, str], object]:
    """Each comparison the store holds, by its two runs' MANIFEST.json digests (baseline, candidate)."""
    out = {}
    for c in store.comparisons():
        a, b = store.get_run(c.run_a), store.get_run(c.run_b)
        ma = dict(a.listing).get("MANIFEST.json") if a is not None else None
        mb = dict(b.listing).get("MANIFEST.json") if b is not None else None
        if ma and mb:
            out[(ma, mb)] = c
    return out


def _receipt(folder: Path, stage: str) -> dict:
    """A record's receipt of `stage`, by its MANIFEST.json's chain."""
    from onetrace_console.bounded_json import load_json_bounded
    man = load_json_bounded((folder / "MANIFEST.json").read_text(encoding="utf-8"), "MANIFEST.json")
    entry = next(e for e in man["chain"] if e["stage"] == stage)
    return load_json_bounded((folder / entry["file"]).read_text(encoding="utf-8"), entry["file"])


def _held_comparison(held: dict, folder: Path):
    """The comparison whose two runs the record's evidence names, by their MANIFEST.json digests;
    None where the build holds no such comparison."""
    inputs = {i["name"]: i["digest"] for i in _receipt(folder, "evidence").get("inputs", [])}
    pair = tuple(inputs.get(f"{side}/MANIFEST.json", "").removeprefix("sha256:") for side in ("baseline", "candidate"))
    return held.get(pair)


def _record_verifies(folder: Path) -> tuple[bool, str]:
    """onetrace-verify on the record, in its folder, as a person repeats it: (exit 0, its last line)."""
    from onetrace_console.checks import shipped_verifier
    from onetrace_console.child import utf8_env
    proc = subprocess.run([sys.executable, str(shipped_verifier()), "MANIFEST.json"],
                          cwd=folder, capture_output=True, timeout=TIMEOUT, env=utf8_env())
    lines = [ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]
    return proc.returncode == 0, (lines[-1] if lines else "no output") + f" (exit {proc.returncode})"


def _why_not(d: Path, rid: str, held: dict):
    """(None, the comparison) where the explanation `rid` reads as onetrace-explain wrote it and
    belongs to a comparison held; otherwise (the reason, None)."""
    from onetrace_console.bounded_json import load_json_bounded
    folder, side, text = d / rid, d / f"{rid}.explanation.json", d / f"{rid}.explanation.txt"
    try:
        e = load_json_bounded(side.read_text(encoding="utf-8"), side.name)
        if (not isinstance(e, dict) or e.get("label") != LABEL or e.get("record") != rid
                or not isinstance(e.get("model"), str) or not isinstance(e.get("claims"), list)
                or not text.is_file()):
            raise ValueError
    except (OSError, ValueError, UnicodeDecodeError):
        return NOT_AN_EXPLANATION, None
    if not (folder / "MANIFEST.json").is_file():
        return NO_RECORD, None
    if any(p.is_symlink() for p in [folder, *folder.rglob("*")]):
        return LINKED, None
    ok, said = _record_verifies(folder)
    if not ok:
        return f"{NOT_VERIFIED}: {said}", None
    try:
        checked = load_json_bounded((folder / "artifacts" / "03-post-check" / "checked.json").read_text(encoding="utf-8"),
                                    "checked.json")
        model = _receipt(folder, "model").get("instrument", {})
        held_cmp = _held_comparison(held, folder)
    except (OSError, ValueError, KeyError, StopIteration, TypeError, AttributeError, UnicodeDecodeError):
        return NOT_AN_EXPLANATION, None
    if {k: v for k, v in e.items() if k not in _ADDED} != checked:
        return NOT_ITS_RECORD, None
    if e["model"] != f"{model.get('id', '')}:{model.get('version', '')}":
        return NOT_ITS_MODEL, None
    if held_cmp is None:
        return NOT_HELD, None
    return None, held_cmp


def keep(source: Path, store) -> dict:
    """A public build's step: take onetrace-explain's own records from `source`, the folder the
    command wrote `explain/` under, into the store, each beside its comparison as a press keeps
    one; refuse every other file with its reason. Writes and returns `x/kept.json`. Runs no model:
    the command is not run, only the verifier on each record."""
    source = Path(source)
    d = source / "explain"
    if not d.is_dir() or d.is_symlink():
        raise ValueError(f"{source} holds no explain/ folder, as onetrace-explain writes under the folder "
                         "it is given")
    held = _held_pairs(store)
    names = sorted(p.name for p in d.iterdir())
    explained = {n.removesuffix(".explanation.json") for n in names if n.endswith(".explanation.json")}
    kept, refused = [], []
    for name in names:
        p = d / name
        if p.is_dir() and not p.is_symlink():
            if name not in explained:
                refused.append({"file": f"explain/{name}", "reason": NO_EXPLANATION})
            continue
        if name.endswith(".explanation.txt") and name.removesuffix(".explanation.txt") in explained:
            continue
        if not name.endswith(".explanation.json") or p.is_symlink():
            refused.append({"file": f"explain/{name}", "reason": NOT_ITS_FILE})
            continue
        rid = name.removesuffix(".explanation.json")
        why, c = _why_not(d, rid, held)
        if why is not None:
            refused.append({"file": f"explain/{name}", "reason": why})
            continue
        dest = folder_of(store, c.key)
        dest.mkdir(parents=True, exist_ok=True)
        if not (dest / KEY_FILE).is_file():
            (dest / KEY_FILE).write_bytes(c.key.encode("ascii") + b"\n")
        into = dest / REPORT / "explain"
        into.mkdir(parents=True, exist_ok=True)
        shutil.copytree(d / rid, into / rid)
        for suffix in (".explanation.json", ".explanation.txt"):
            shutil.copyfile(d / f"{rid}{suffix}", into / f"{rid}{suffix}")
        verified(store, c.key, rid)
        kept.append({"record": rid, "comparison": c.key})
    record = {"format": KEPT_FORMAT, "kept": kept, "refused": refused}
    out = Path(store.root) / FOLDER / KEPT_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return record


def _kept_panel(comparison, store, held: dict, steps: dict, facts: dict | None = None) -> str:
    """The kept explanations of this comparison, read-only; only those the build's record lists."""
    from onetrace_console.words import escape
    mine = {k["record"] for k in held.get("kept", []) if k.get("comparison") == comparison.key}
    shown = [e for e in explanations(store, comparison.key) if e.get("record") in mine] if mine else []
    if not shown:
        return f'<p data-explain="none-kept">{escape(KEPT_NONE)}</p>'
    full = {**(facts or {}), **dict(zip(("a", "b"), receipts_by_node(comparison, store)))}
    return "".join(_one(e, comparison, store, steps, read_only=True, facts=full) for e in shown)
