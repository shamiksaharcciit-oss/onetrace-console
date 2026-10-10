"""The comparison runner: the SDK's own verbs, as subprocesses, with their output kept.

    Given two stored runs, call the SDK's own `diff` and, where it applies, `localize`, as
    subprocesses with a timeout, over the two stored folders. Keep each report exactly as
    produced. The runner has no comparison logic of its own: it aligns nothing, scores
    nothing, and never re-orders what the SDK returned. If the SDK refuses or cannot align
    the runs, that refusal is the result.

NO COMPARISON LOGIC, STATED AS WHAT IS ABSENT
---------------------------------------------
There is no stage alignment here, no scoring, no sorting, no merging of the two verbs'
findings, and no interpretation of a verdict. The runner materialises two stored runs,
invokes the verb, and stores the bytes it wrote. Every sentence a reader will see about a
comparison was written by the SDK.

The one judgement it makes is about **itself**: whether the subprocess finished, timed out,
or refused. A refusal is stored and shown in the SDK's own words, never retried and never
replaced -- the ladder has five closed verdicts and `COULD NOT CHECK` is one of them, so a
runner that retried until it got a nicer answer would be manufacturing one.

THE KEY CARRIES THE SDK'S BUILD IDENTITY
----------------------------------------
    The comparison key carries the SDK's build identity. Because `__version__` reads
    `0.0.1` at both pins, a version string cannot identify a build. The key becomes:
    `(sha of A's bundle, sha of B's bundle, SDK distribution version from
    importlib.metadata, SDK build digest)`. The build digest is the installed wheel's
    sha256 when installed from a wheel, or the pinned commit when loaded from a clone.
    ... A stored report whose key has no build digest is treated as unkeyed and
    recomputed.

The measurement that forced it: `onetrace.__version__` is `0.0.1` at both of this console's
pins, `c30edce` and `4c11f0e`, while the distribution metadata says `0.1.0`. The two
disagree with each other and neither moved across ten commits including a breaking
repackaging, so neither can identify a build on its own.

**The build digest is now the installed wheel's own sha256** (`wheel:<sha256>`),
because the SDK is pinned by hash from PyPI rather than loaded from a clone. Before that it
was the pinned commit (`commit:<sha>`), recorded as such so a reader could see which kind of
identity they were looking at; that labelling stays even though only the wheel case is live
today, because a source checkout on `PYTHONPATH` remains a valid, if unpinned, way to run
this console (see `sdk_build_digest()`'s own docstring).

**The distribution version was often unreadable before the SDK was installed from a pinned
wheel, and that was recorded rather than invented.** `importlib.metadata.version("onetrace")`
raises `PackageNotFoundError` when the SDK is on `PYTHONPATH` instead of installed. The key
then carried the empty string in that position, honestly, with the build digest doing the
identifying alone. Now the version is readable (`0.1.0`) and both are part of the key, which
is correct: a different version is a different build even before a byte of the wheel is
compared.

A stored comparison with **no** build digest is treated as unkeyed and recomputed, so nothing
keyed under the older three-part key is ever handed back. `sdk_source_digest` used
to stand beside the key as an additional validity check (a hit whose recorded source digest
differed from the running one was re-run even if the key matched); it was
removed as redundant, since the wheel's own hash already cannot fail to change when the
SDK's source does.
"""
from __future__ import annotations

import hashlib
import json
from onetrace_console.bounded_json import load_json_bounded
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from onetrace_console.checks import materialise
from onetrace_console.ingest import bundle
from onetrace_console.store import StoredRun, Store, digest

COMPARISON_FORMAT = "onetrace-console/comparison/0.1"

#: The verbs this slice runs. `reproduce` is deliberately absent: it re-executes stages, so
#: it is not free and the design note says it runs only when asked.
DIFF = "diff"
LOCALIZE = "localize"
VERBS = (DIFF, LOCALIZE)

#: The text diff is its own stored run of
#: `onetrace diff A B --text --json --no-follow`, beside `diff` and `localize`, whose reports stay
#: as they are. Its stdout (the `onetrace-textdiff/0.3` document) is kept byte for byte. The corpus
#: trace is not followed here; that is board 7's. "Show more" re-runs it with the larger limit
#: below, a fixed constant -- ten times the SDK's default of 200 lines per output, the most allowed
#: -- stored as a run of its own; neither changes a verdict or an earlier run.
TEXT_DIFF = "diff --text"
TEXT_DIFF_DEFAULT_LINES = 200
TEXT_DIFF_MORE_LINES = 2000

#: A wall-clock bound on each subprocess. The order asks for a timeout in as many words,
#: and a verb has been seen to hang, so this is not theoretical.
DEFAULT_TIMEOUT = 300

TIMED_OUT = "timed out"


class ComparisonError(RuntimeError):
    """The runner could not run a verb at all. Never a verdict about either run."""


@dataclass(frozen=True, slots=True)
class VerbRun:
    """One invocation of one verb, and everything it produced."""
    verb: str
    command: tuple[str, ...]        # what ran, recorded rather than reconstructed
    shown_command: str              # what a reader types to repeat it
    exit_status: str
    stdout_key: str                 # the verb's stdout, verbatim, as an object
    reports: tuple[tuple[str, str], ...] = ()   # (filename, object key), as written
    refused: bool = False
    note: str = ""                  # `timed out`, or why it could not be run

    @property
    def report_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.reports)


@dataclass(frozen=True, slots=True)
class StoredComparison:
    """One pair, compared. Content-addressed by the order's key."""
    key: str
    run_a: str
    run_b: str
    bundle_sha_a: str
    bundle_sha_b: str
    sdk_version: str
    ran_at: str
    #: `""` is a real value for the distribution version (see `sdk_distribution_version`):
    #: the SDK is on `PYTHONPATH` rather than installed, so there is no distribution to ask.
    #:
    #: An empty `sdk_build_digest` means the record predates the four-part key and
    #: is treated as **unkeyed** — recomputed rather than returned. Defaulted for exactly
    #: that reason: a record written under the old three-part key must still LOAD, so that it
    #: can be recognised as unkeyed and replaced.
    sdk_distribution_version: str = ""
    sdk_build_digest: str = ""
    #: Redundant now that `sdk_build_digest` is the installed wheel's
    #: own sha256, which cannot fail to change when the SDK's source does the way a version
    #: number could go unbumped. No longer computed, no longer checked -- kept here, defaulted
    #: to `""`, ONLY so a record written before this change still loads without a `TypeError`
    #: on an unexpected field. A record from before this change is not migrated: its stored
    #: value here is simply never read again.
    sdk_source_digest: str = ""
    verbs: tuple[VerbRun, ...] = field(default_factory=tuple)

    def verb(self, name: str) -> VerbRun | None:
        for v in self.verbs:
            if v.verb == name:
                return v
        return None

    def to_json(self) -> str:
        d = asdict(self)
        d["format"] = COMPARISON_FORMAT
        for v in d["verbs"]:
            v["command"] = list(v["command"])
            v["reports"] = [list(pair) for pair in v["reports"]]
        return json.dumps(d, indent=1, sort_keys=True, ensure_ascii=False) + "\n"

    @staticmethod
    def from_json(text: str) -> StoredComparison:
        d = load_json_bounded(text, "a stored comparison record")
        d.pop("format", None)
        d["verbs"] = tuple(
            VerbRun(**{**v,
                       "command": tuple(v["command"]),
                       "reports": tuple((n, k) for n, k in v["reports"])})
            for v in d["verbs"])
        return StoredComparison(**d)


def sdk_version() -> str:
    """The SDK's own `__version__`. Kept for the record; it cannot identify a build.

    Still recorded in every comparison, because when it finally disagrees with the
    distribution version in a NEW way that is worth being able to see.
    """
    try:
        import onetrace
    except ImportError as e:                                  # pragma: no cover
        raise ComparisonError(f"the SDK is not installed: {e}") from None
    return str(getattr(onetrace, "__version__", "unknown"))


def sdk_distribution_version() -> str:
    """The distribution version from `importlib.metadata`, or `""` when it is not readable.

    Empty is a real answer here and is recorded as such: the SDK is on `PYTHONPATH` rather
    than installed for this slice, so there is no distribution to ask. Inventing
    a version to fill the slot would put a number in the key that names nothing.
    """
    import importlib.metadata as md

    try:
        return md.version("onetrace")
    except md.PackageNotFoundError:
        return ""


def _wheel_hash_from_direct_url(dist) -> str:
    """`direct_url.json` (PEP 610), when pip wrote one.

    Only present for a "direct reference" install -- a URL, a local path, a VCS checkout --
    never for an ordinary `pip install pkg==version` resolved from an index, hash-checked or
    not. Measured directly: installing this console's own `requirements.lock` with
    `--require-hashes` alone leaves no `direct_url.json` for the index-resolved `onetrace`
    and `onetrace-verify` entries. Kept as a source because it is still correct for any
    package installed from a local path and for anyone installing a single wheel by hand;
    superseded by the install report as the primary source below.
    """
    raw = dist.read_text("direct_url.json")
    if not raw:
        return ""
    try:
        info = load_json_bounded(raw, "direct_url.json")
    except json.JSONDecodeError:
        return ""
    return ((info.get("archive_info") or {}).get("hashes") or {}).get("sha256", "")


#: The report's name and place live in `onetrace_console.install_report`, a standard-library-only
#: module the installer loads by path before anything is installed. Re-exported
#: here, so every caller that read them from `compare` still does.
from onetrace_console.install_report import (  # noqa: E402,F401
    INSTALL_REPORT_FILENAME, install_report_path)


def _wheel_hash_from_install_report(name: str) -> str:
    """`pip install --report <path>` records `download_info.archive_info.hash` for EVERY
    installed distribution, however it was resolved -- the one source that works for an
    ordinary index install as well as a direct reference. `tools/install_pinned.py` is the
    one command that produces it, at the path this reads by default.
    """
    path = install_report_path()
    if not path.is_file():
        return ""
    try:
        report = load_json_bounded(path.read_text(encoding="utf-8"), path.name)
    except json.JSONDecodeError:
        return ""
    for item in report.get("install", []):
        if item.get("metadata", {}).get("name") == name:
            archive = item.get("download_info", {}).get("archive_info", {})
            hashes = archive.get("hashes") or {}
            sha = hashes.get("sha256") or archive.get("hash", "").removeprefix("sha256=")
            if sha:
                return sha
    return ""


def record_digest(version: str, record_lines: list[str]) -> str:
    """`record:<version>:<sha256>` for an installed distribution: the sha256 of the hashed lines
    of its RECORD, sorted. Those lines are the files the wheel itself lists, so the same wheel
    gives the same identity on any Python and any machine; the lines pip adds for compiled
    files and its own bookkeeping carry no hash and are left out."""
    hashed = sorted(line.strip() for line in record_lines
                    if line.strip() and line.split(",")[1:2] and line.split(",")[1].startswith("sha256="))
    return f"record:{version}:" + hashlib.sha256("\n".join(hashed).encode("utf-8")).hexdigest()


def sdk_build_digest() -> str:
    """What identifies this SDK build: `wheel:<sha256>`, `record:<version>:<sha256>` or
    `commit:<sha>`.

    The cases are **labelled**, not collapsed into a bare hex string, because a reader of a
    stored comparison should not have to guess which kind of identity they are looking at.

    Four sources tried in order, because no single one covers every install path:
    1. the install report `tools/install_pinned.py` writes, for the pinned install;
    2. `direct_url.json`, for a direct-reference install (a local path or URL);
    3. the installed distribution's version and RECORD, for a plain `pip install` from an
       index, which leaves neither of the first two;
    4. the commit, read from git, for onetrace's own source checkout on `PYTHONPATH`: taken
       only when the repository's top level is onetrace's own (see `_own_checkout_commit`).

    Refuses rather than guessing. A build this console cannot identify is one whose reports
    it cannot safely reuse, and returning something that merely looks like an identity is how
    a stale report gets handed back.
    """
    import importlib.metadata as md

    import onetrace

    try:
        dist = md.distribution("onetrace")
    except md.PackageNotFoundError:
        dist = None

    sha = _wheel_hash_from_install_report("onetrace")
    if not sha and dist is not None:
        sha = _wheel_hash_from_direct_url(dist)
    if sha:
        return f"wheel:{sha}"

    record = dist.read_text("RECORD") if dist is not None else None
    if record:
        return record_digest(dist.version, record.splitlines())

    #: Loaded from a clone: the commit the clone is checked out at. Read from git rather
    #: than from a file this console wrote, so it is the clone's own answer.
    root = Path(onetrace.__file__).resolve().parent
    commit = _own_checkout_commit(root)
    if commit:
        return f"commit:{commit}"

    raise ComparisonError(
        f"this onetrace installation cannot be identified. Tried, in order: the install report, "
        f"direct_url.json, the installed RECORD, and git (only onetrace's own checkout counts, "
        f"and {root} is not in one). Refusing rather than keying a comparison under an identity "
        f"that names nothing, or names another project -- a report reused across two different "
        f"builds is worse than one recomputed. Reinstall onetrace with pip.")


def _own_checkout_commit(package_dir: Path) -> str:
    """The commit of onetrace's own checkout, if `package_dir` is the package folder of one;
    otherwise "".

    Git walks up to any enclosing repository, so its answer alone could be another project's
    commit (onetrace installed in a `.venv` inside that project, say). The commit is taken
    only when the repository's top level holds the package at `src/onetrace` or `onetrace`,
    and its own pyproject.toml names the project `onetrace`.
    """
    import tomllib

    def git(*args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=str(package_dir), capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else ""

    top = git("rev-parse", "--show-toplevel")
    if not top:
        return ""
    top_dir = Path(top).resolve()
    if package_dir.resolve() not in (top_dir / "src" / "onetrace", top_dir / "onetrace"):
        return ""
    try:
        meta = tomllib.loads((top_dir / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if meta.get("project", {}).get("name") != "onetrace":
        return ""
    return git("rev-parse", "HEAD")


#: `sdk_source_digest()` was removed: `sdk_build_digest()` (the
#: installed wheel's own sha256) already cannot fail to change when the SDK's source does,
#: which made a separate source digest redundant now that the build digest is a wheel hash
#: rather than a commit. `StoredComparison.sdk_source_digest` stays in the dataclass, defaulted
#: to `""`, only so a record written before this change still loads.


def comparison_key(bundle_sha_a: str, bundle_sha_b: str,
                   distribution_version: str, build_digest: str) -> str:
    """The key: A's bundle, B's bundle, distribution version, build digest, in that order.

    A is the baseline throughout. `build_digest` must be non-empty. A key without it is
    exactly the old three-part key this replaces, and such a report is treated as unkeyed and
    recomputed -- so it is refused here rather than silently produced.
    """
    if not build_digest:
        raise ComparisonError(
            "a comparison key needs the SDK's build digest. Without it the key cannot tell "
            "two builds apart, which is the whole reason the key carries it.")
    return digest("\0".join((bundle_sha_a, bundle_sha_b, distribution_version,
                             build_digest)).encode("utf-8"))


def _run_verb(verb: str, folder_a: Path, folder_b: Path, out: Path, timeout: int,
              store: Store) -> VerbRun:
    """Invoke one verb as a subprocess and keep what it wrote.

    Through `sys.executable -m onetrace`, never the name `python3`, and the exit
    status is the process's own rather than a shell pipeline's (R29).
    """
    command = (sys.executable, "-m", "onetrace", verb,
               str(folder_a), str(folder_b), "--out", str(out))
    shown = f"python -m onetrace {verb} RUN_A RUN_B --out OUT"
    try:
        proc = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # A timeout is not a verdict and is not a refusal by the SDK. It is this runner
        # failing to obtain an answer, and it says so in its own name.
        return VerbRun(verb=verb, command=command, shown_command=shown,
                       exit_status="", stdout_key=store.put(b""), refused=False,
                       note=f"{TIMED_OUT} after {timeout}s")

    stdout_key = store.put(proc.stdout)
    reports: list[tuple[str, str]] = []
    if out.is_dir():
        for path in sorted(p for p in out.rglob("*") if p.is_file()):
            reports.append((path.relative_to(out).as_posix(), store.put(path.read_bytes())))
    return VerbRun(verb=verb, command=command, shown_command=shown,
                   exit_status=str(proc.returncode), stdout_key=stdout_key,
                   reports=tuple(reports), refused=proc.returncode != 0)


def _run_text_diff(folder_a: Path, folder_b: Path, out: Path, timeout: int, store: Store,
                   max_lines: int | None = None) -> VerbRun:
    """`onetrace diff A B --text --json --no-follow`, its stdout kept byte for byte. `--out` goes
    to the scratch folder: without it the SDK writes `onetrace-report/` where it runs."""
    limit = ("--max-lines", str(max_lines)) if max_lines is not None else ()
    command = (sys.executable, "-m", "onetrace", "diff", str(folder_a), str(folder_b),
               "--text", "--json", "--no-follow", *limit, "--out", str(out))
    shown = ("python -m onetrace diff RUN_A RUN_B --text --json --no-follow"
             + (f" --max-lines {max_lines}" if max_lines is not None else ""))
    verb = TEXT_DIFF if max_lines is None else f"{TEXT_DIFF} --max-lines {max_lines}"
    try:
        proc = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return VerbRun(verb=verb, command=command, shown_command=shown, exit_status="",
                       stdout_key=store.put(b""), note=f"{TIMED_OUT} after {timeout}s")
    return VerbRun(verb=verb, command=command, shown_command=shown,
                   exit_status=str(proc.returncode), stdout_key=store.put(proc.stdout),
                   refused=proc.returncode not in (0, 1))


def show_more(comparison: "StoredComparison", store: Store, *,
              timeout: int = DEFAULT_TIMEOUT) -> "StoredComparison":
    """The text diff again, with `TEXT_DIFF_MORE_LINES` -- the one larger
    limit, never a number from a request -- stored as a run of its own beside the others, which
    are kept exactly as they were. Run once; asked again, the stored run is the answer."""
    more = f"{TEXT_DIFF} --max-lines {TEXT_DIFF_MORE_LINES}"
    if comparison.verb(more) is not None:
        return comparison
    run_a, run_b = store.get_run(comparison.run_a), store.get_run(comparison.run_b)
    if run_a is None or run_b is None:
        raise ComparisonError("a run of this comparison is no longer stored")
    with tempfile.TemporaryDirectory(prefix="onetrace-compare-") as tmp:
        root = Path(tmp)
        folder_a = materialise(run_a, store, root / "a")
        folder_b = materialise(run_b, store, root / "b")
        (root / "out-text-more").mkdir()
        run = _run_text_diff(folder_a, folder_b, root / "out-text-more", timeout, store,
                             max_lines=TEXT_DIFF_MORE_LINES)
    updated = replace(comparison, verbs=tuple(comparison.verbs) + (run,))
    store.put_comparison(updated)
    return updated


def text_diff_raw(comparison: "StoredComparison", store: Store) -> tuple[bytes, str] | None:
    """(the stored text-diff document, the run's verb name): the "Show more" run where there is
    one, else the first; None where this comparison has neither."""
    for verb in (f"{TEXT_DIFF} --max-lines {TEXT_DIFF_MORE_LINES}", TEXT_DIFF):
        run = comparison.verb(verb)
        if run is not None:
            return store.get(run.stdout_key), verb
    return None


def compare(run_a: StoredRun, run_b: StoredRun, store: Store, *,
            timeout: int = DEFAULT_TIMEOUT, verbs: tuple[str, ...] = VERBS,
            ran_at: str | None = None, force: bool = False,
            work_root: Path | None = None, text_diff: bool = True) -> StoredComparison:
    """Compare two stored runs with the SDK's verbs, or return the stored comparison.

    `run_a` is the baseline and `run_b` the candidate, in that order, always -- the SDK's
    own argument order, kept so a reader repeating the command gets the same report.

    `work_root` names where the two runs are materialised. It exists because the SDK's
    reports **record the input paths**, so "byte-identical to running `diff` by hand" is
    only a meaningful claim over the same two folders -- and a test cannot arrange that
    unless it can name them. Default: a temporary
    directory, removed afterwards.
    """
    sha_a = digest(bundle(run_a, store))
    sha_b = digest(bundle(run_b, store))
    version = sdk_version()
    distribution = sdk_distribution_version()
    build = sdk_build_digest()
    key = comparison_key(sha_a, sha_b, distribution, build)

    held = store.get_comparison(key)
    if held is not None and not force:
        #: Two ways a hit is not a hit, both "recompute rather than reuse":
        #:   * the record carries no build digest -> it predates the key change and is
        #:     unkeyed;
        #:   * its build digest is not this build -> a key collision, or a record written
        #:     under a key this console no longer computes.
        #: A third way used to be checked here -- the record's `sdk_source_digest` differing
        #: from a freshly computed one -- is no longer checked: `build` (the
        #: installed wheel's own sha256) already cannot fail to change when the SDK's source
        #: does, which is a strictly finer signal than a separate digest over the same source.
        unkeyed = not held.sdk_build_digest
        other_build = held.sdk_build_digest and held.sdk_build_digest != build
        #: A comparison stored before the text diff was kept is made
        #: again, so that comparing the pair again keeps it, as its Diff page says.
        no_text_diff = text_diff and held.verb(TEXT_DIFF) is None
        #: One whose text diff names a changed corpus link, and that holds no
        #: trace run yet, is made again, so that board 7 can be drawn (`board7.needs_trace`).
        from onetrace_console.board7 import needs_trace
        no_trace = text_diff and not no_text_diff and needs_trace(held, store)
        if not (unkeyed or other_build or no_text_diff or no_trace):
            return held

    scratch = None
    if work_root is None:
        scratch = tempfile.TemporaryDirectory(prefix="onetrace-compare-")
        root = Path(scratch.name)
    else:
        root = Path(work_root)
        root.mkdir(parents=True, exist_ok=True)
    try:
        folder_a = materialise(run_a, store, root / "a")
        folder_b = materialise(run_b, store, root / "b")
        runs = []
        for verb in verbs:
            out = root / f"out-{verb}"
            out.mkdir(parents=True, exist_ok=True)
            runs.append(_run_verb(verb, folder_a, folder_b, out, timeout, store))
        if text_diff:
            out = root / "out-text"
            out.mkdir(parents=True, exist_ok=True)
            runs.append(_run_text_diff(folder_a, folder_b, out, timeout, store))
            #: The trace's own run, only where that text diff names a changed
            #: corpus link; the text diff's run stays `--no-follow`.
            from onetrace_console.board7 import trace_run
            traced = trace_run(store, folder_a, folder_b, root, timeout, runs[-1])
            if traced is not None:
                runs.append(traced)
    finally:
        if scratch is not None:
            scratch.cleanup()

    comparison = StoredComparison(
        key=key, run_a=run_a.key, run_b=run_b.key,
        bundle_sha_a=sha_a, bundle_sha_b=sha_b,
        sdk_version=version,
        sdk_distribution_version=distribution, sdk_build_digest=build,
        ran_at=ran_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        verbs=tuple(runs))
    store.put_comparison(comparison)
    return comparison


def report_text(comparison: StoredComparison, verb: str, store: Store) -> str:
    """The verb's text report, exactly as the SDK wrote it.

    Falls back to the verb's stdout when no `<verb>.txt` was written, which is what happens
    when the SDK refuses before writing a report: the refusal is then the report, and it is
    still the SDK's words.
    """
    run = comparison.verb(verb)
    if run is None:
        raise ComparisonError(f"this comparison did not run {verb!r}")
    for name, key in run.reports:
        if name == f"{verb}.txt":
            return store.get(key).decode("utf-8", errors="replace")
    return store.get(run.stdout_key).decode("utf-8", errors="replace")


def report_json(comparison: StoredComparison, verb: str, store: Store) -> dict | None:
    """The verb's JSON report as the SDK wrote it, or None when it wrote none."""
    run = comparison.verb(verb)
    if run is None:
        return None
    for name, key in run.reports:
        if name == f"{verb}.json":
            return load_json_bounded(store.get(key).decode("utf-8"), f"{verb}.json")
    return None
