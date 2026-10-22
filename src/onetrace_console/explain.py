"""A comparison's suggested explanation: the `onetrace-explain` command, run as a person runs it.

An explanation is a suggestion about a record, never a reading of it. The console runs the
command only when a person presses Explain on a comparison's page, and only that comparison; it
never imports `onetrace_explain` (tests/test_explain_panel.py holds it to that), and nothing it
draws as a verdict, a badge, a count, a summary line or an incident reads an explanation back.

Each comparison has a folder of its own, `x/<first 16 hex of its key>/` in the store, short so
that on Windows with long paths off an explanation fits a store folder of up to `LIMIT` characters:
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
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from datetime import datetime, timezone
from pathlib import Path

#: The label every explanation is shown under, the command's own.
LABEL = "Suggested explanation — AI-generated, may be wrong"
#: The panel's own title; each explanation inside it keeps LABEL, with its model.
TITLE = "Suggested explanation"
#: The command's three words for a kept claim's kind.
KIND_WORDS = {"lead": "possible culprit", "ruled out": "ruled out", "note": "note"}
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
MEASURED = {"onetrace-explain": "0.1.0", "onetrace": "0.4.0"}
MEASURED_BELOW = len("/explain/") + 27 + len("/artifacts/_staging/post_check/checked.json") + len(".12345678.tmp")
#: The longest path Windows opens with long paths off, its NUL apart.
WINDOWS_PATH = 259
#: The longest store folder (`store_root`, the Store's own folder `store` within it) an explanation
#: fits on Windows with long paths off.
LIMIT = WINDOWS_PATH - (len("/store") + len(f"/{FOLDER}/") + KEY_HEX + len(f"/{REPORT}") + MEASURED_BELOW)
TOO_LONG = ("This store's folder is {n} characters long. On Windows with long paths off, Explain needs it "
            "to be {limit} or fewer. Turn on long paths, or move the store to a shorter folder.")


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
    """The panel's line where the store folder is longer than `LIMIT` on Windows with long paths
    off, the command then never run; None where it fits, long paths are on, or not on Windows."""
    if not _on_windows() or long_paths():
        return None
    n = len(str(Path(os.path.abspath(store.root)).parent))
    return TOO_LONG.format(n=n, limit=LIMIT) if n > LIMIT else None


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


def _keep(folder: Path, kind: str, args: list[str], proc) -> dict:
    d = folder / "attempts"
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob("*.json"))) + 1
    attempt = {"n": str(n), "kind": kind, "at": _now(), "command": "onetrace-explain " + " ".join(args),
               "exit": str(proc.returncode),
               "stdout": proc.stdout.decode("utf-8", "replace"),
               "stderr": proc.stderr.decode("utf-8", "replace")}
    (d / f"{n:06d}.json").write_text(json.dumps(attempt, indent=1, sort_keys=True), encoding="utf-8")
    return attempt


def explain(comparison, store, *, send: bool = False) -> dict:
    """One press of Explain (`send` False) or of Send (`send` True, which passes `--yes`). Refused,
    the command never run, where the store folder is too long for it (`too_long`)."""
    if too_long(store):
        raise ValueError(too_long(store))
    folder = folder_of(store, comparison.key)
    _prepare(comparison, store, folder)
    args = [REPORT, *(["--yes"] if send else [])]
    attempt = _keep(folder, "send" if send else "explain", args, _run(folder, args))
    for e in explanations(store, comparison.key):
        verified(store, comparison.key, e["record"])
    return attempt


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


def verified(store, key: str, record: str) -> str:
    """onetrace-verify's summary line of an explanation's record, kept once read."""
    from onetrace_console.checks import shipped_verifier
    from onetrace_console.child import utf8_env
    folder = folder_of(store, key)
    kept = folder / "verified" / f"{record}.txt"
    if kept.is_file():
        return kept.read_text(encoding="utf-8")
    run = folder / REPORT / "explain" / record
    #: Run in the record's folder on its manifest, as a person repeats it: the verifier reads a
    #: run's receipts relative to where it runs.
    proc = subprocess.run([sys.executable, str(shipped_verifier()), "MANIFEST.json"],
                          cwd=run, capture_output=True, timeout=TIMEOUT, env=utf8_env())
    lines = [ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]
    said = (lines[-1] if lines else "no output") + f" (exit {proc.returncode})"
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text(said, encoding="utf-8")
    return said

# ------------------------------------------------------------------ the panel
#: The panel reads what earlier presses kept; drawing it runs nothing.


def _button(path: str, words: str) -> str:
    from onetrace_console.words import escape
    return f'<button type="button" data-explain-post="{escape(path)}" hidden>{escape(words)}</button>'


def _cite(cite: str, steps: dict) -> str:
    """A cite, linked to its node's row as the page's graph links it (`steps`: node -> href); the
    field after the node stays as text. A cite of no node on this page is its words alone."""
    from onetrace_console.words import escape
    parts = cite.split("/")
    href = (steps.get(parts[1]) or steps.get(parts[1].split("#", 1)[0])) if parts[0] == "node" and len(parts) >= 2 else None
    if href:
        return f'<a href="{escape(href)}" class="mono" data-cite>{escape(cite)}</a>'
    return f'<span class="mono" data-cite>{escape(cite)}</span>'


def _format_page() -> str:
    """The explain format page, by its address in text: no page of the console links or loads
    anything outside this machine."""
    from onetrace_console.words import escape
    return f'The explain format: <span class="mono">{escape(FORMAT_PAGE)}</span>'


def _attempt_line(a: dict) -> str:
    """What the latest press got, in the command's own words where it has words."""
    from onetrace_console.words import escape
    out, err, code = a.get("stdout", ""), a.get("stderr", ""), a.get("exit", "")
    if code == "3":
        return (f'<p data-explain="unreached">{escape(UNREACHED)} '
                f'<span class="mono">{escape(err.strip().splitlines()[-1] if err.strip() else "")}</span></p>')
    if code == "2":
        line = (err.strip() or out.strip()).splitlines()[-1] if (err.strip() or out.strip()) else ""
        link = (f" {_format_page()}" if NO_MODEL_MARK in line else "")
        return f'<p data-explain="refused"><span class="mono">{escape(line)}</span>{link}</p>'
    return ""


def _asks(a: dict) -> list[str]:
    """The command's own lines before a first send, where the latest press stopped at them."""
    if a.get("exit") != "2" or a.get("kind") == "packet":
        return []
    return [ln for ln in a.get("stdout", "").splitlines() if any(m in ln for m in ASKS_MARKS)]


def panel(comparison, store, *, public: bool | None = None, steps: dict | None = None) -> str:
    """The comparison's explanation panel: its own frame, below the verdicts, apart from them."""
    from onetrace_console.words import escape
    head = (f'<section data-section="explain" class="explain"><h2>{escape(TITLE)}</h2>')
    if (_public() if public is None else public) or _NO_PRESSES.get():
        return head + f'<p data-explain="not-set-up">{escape(NOT_SET_UP_DEMO)}</p></section>'
    if command() is None:
        return head + f'<p data-explain="not-installed">{escape(NOT_INSTALLED)} {_format_page()}</p></section>'
    if too_long(store):
        return head + f'<p data-explain="too-long">{escape(too_long(store))}</p></section>'
    key = comparison.key
    try:
        tried = attempts(store, key)
    except ValueError as e:
        return head + f'<p data-explain="refused">{escape(str(e))}</p></section>'
    latest = next((a for a in reversed(tried) if a["kind"] != "packet"), None)
    body = [head, '<p data-explain="what">A suggestion about this comparison\'s record from a model you '
            "configure for <code>onetrace-explain</code>, never a reading of it. The verdicts above are "
            "what they are without it. Nothing is sent until you press Explain.</p>"]
    asks = _asks(latest) if latest else []
    buttons = [_button(f"/explain?c={key}", "Explain"), _button(f"/explain/packet?c={key}", "Show the packet")]
    if asks:
        body.append('<div data-explain="asks">' + "".join(f'<p class="mono">{escape(ln)}</p>' for ln in asks)
                    + "</div>")
        buttons.insert(0, _button(f"/explain?c={key}&send=yes", "Send"))
    elif latest is not None:
        body.append(_attempt_line(latest))
    body.append('<p data-explain="buttons">' + " ".join(buttons) + "</p>")
    pk = next((a for a in reversed(tried) if a["kind"] == "packet"), None)
    if pk is not None:
        lines = pk.get("stdout", "").splitlines()
        if pk.get("exit") == "0" and len(lines) >= 2:
            body.append('<details data-explain="packet"><summary>The packet, exactly as it would be sent: '
                        f'<span class="mono">{escape(lines[-1])}</span></summary>'
                        f'<pre><code>{escape(lines[0])}</code></pre></details>')
        else:
            body.append(_attempt_line(pk))
    for e in explanations(store, key):
        body.append(_one(e, comparison, store, steps or {}))
    if 'data-explain-post' in "".join(body):
        from onetrace_console.explain_script import EXPLAIN_SCRIPT
        body.append(EXPLAIN_SCRIPT)
    body.append("</section>")
    return "".join(body)


def _one(e: dict, comparison, store, steps: dict) -> str:
    """One explanation, as the command wrote it: kept claims by kind, the checks, the drops."""
    from onetrace_console.words import escape
    rec = e.get("record", "")
    parts = [f'<article data-explanation="{escape(rec)}"><h3>{escape(LABEL)}</h3>',
             f'<p data-explain="model">Model: <span class="mono">{escape(e.get("model", ""))}</span></p>',
             f'<p data-explain="record">Its record: <span class="mono">explain/{escape(rec)}/</span>, '
             f'onetrace-verify: <span class="mono" data-verified>{escape(verified(store, comparison.key, rec))}</span></p>']
    claims = e.get("claims") or []
    if not claims:
        parts.append(f'<p data-explain="all-dropped">{escape(ALL_DROPPED)}</p>')
    else:
        items = []
        for kind in KIND_ORDER:
            for c in (c for c in claims if c.get("kind") == kind):
                cites = ", ".join(_cite(x, steps) for x in c.get("cites", []))
                items.append(f'<li data-claim="{escape(kind)}"><span data-kind>{escape(KIND_WORDS[kind])}</span>: '
                             f'{escape(c.get("text", ""))} <span data-cites>(shown by {cites})</span></li>')
        parts.append('<ul class="plain" data-explain="claims">' + "".join(items) + "</ul>")
    shown = check_lines(e)
    checks = e.get("checks") or []
    if checks:
        rows = []
        for i, k in enumerate(checks):
            cmd = shown[i] if i < len(shown) else ""
            run = (_button(f"/explain/check?c={comparison.key}&e={rec}&i={i}", "Run")
                   if check_argv(k) is not None else '<span data-explain="not-run">needs a file or runner you name</span>')
            got = check_result(store, comparison.key, rec, i)
            out = (f'<details data-explain="check-output"><summary>What it reported: exit '
                   f'<span data-exit>{escape(got["exit"])}</span></summary><pre><code>{escape(got["output"])}'
                   "</code></pre></details>" if got else "")
            rows.append(f'<li data-check="{i}"><code>{escape(cmd)}</code> {run}{out}</li>')
        parts.append('<p data-explain="checks-lead">Checks onetrace can run. A lead is confirmed or ruled '
                     "out only by what these report.</p>"
                     '<ul class="plain" data-explain="checks">' + "".join(rows) + "</ul>")
    drops = {**(e.get("dropped") or {})}
    cdrops = e.get("checks_dropped") or {}
    if drops or cdrops:
        said = "; ".join(f"{n} {why}" for why, n in sorted(drops.items()))
        csaid = "; ".join(f"{n} {why}" for why, n in sorted(cdrops.items()))
        parts.append(f'<p data-explain="dropped">Dropped before anyone read them: '
                     f'{escape(said or "no claim")}' + (f'; checks: {escape(csaid)}' if csaid else "") + ".</p>")
    parts.append("</article>")
    return "".join(parts)
