"""The check runner: the verifier as shipped, called with paths, with no logic of its own.

    The runner is the verifier and the verbs as shipped, in a container, called with
    paths. It has no logic of its own.      -- the store and console design note, §4

NO VERDICT LOGIC OF ITS OWN
---------------------------
The verdict is the verifier's own summary line, read by the viewer's strict reader --
`viewer.report.parse`, the same parser the reader-session page uses, reused and not
reimplemented. It refuses a report it cannot read rather than guessing, and an unreadable
report becomes `could_not_check`, never `contradicts`. That is the three-outcome rule: a
report that cannot be read is an access problem, not evidence about the record.

Mapping the verifier's `PASS`/`FAIL` onto the design note's
`holds`/`contradicts`/`could_not_check` is reading, not deciding. Nothing here inspects a
receipt, counts anything the verifier did not count, or forms an opinion.

WHAT IS STORED
--------------
The verifier's stdout, **verbatim**, as a content-addressed object, plus the exit status
it returned. The requirement is that this is byte-identical to running
`onetrace-verify` by hand on the same folder, and `tests/test_checks.py` runs the console
script itself to compare -- the claim is not made by the code that produces the bytes.

THE LINKS BETWEEN STAGES: THE VERIFIER'S OWN EDGE ROWS
------------------------------------------------------
Since onetrace 0.2.0 the verifier checks a run's recorded links itself: its report carries edge
rows ("edges equal the edges derived from the receipts", and against a declared plan where there
is one). The console runs no separate topology check of its own, and raises nothing for one it
does not run. Where a run declares links and the verifier's report has no edge row at all, the
run's page says so in one line (`TOPOLOGY_NO_EDGE_ROWS`): a note about what was not checked, not
an incident, because nothing happened that someone must act on.
"""
from __future__ import annotations

import importlib.util
import re
from onetrace_console.bounded_json import load_json_bounded
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from onetrace_console.store import (SameFileError, StoredRun, Store, StoreError,
                                    create_exclusively)

#: The design note's `checks.verdict`, closed.
HOLDS = "holds"
CONTRADICTS = "contradicts"
COULD_NOT_CHECK = "could_not_check"
VERDICTS = (HOLDS, CONTRADICTS, COULD_NOT_CHECK)

#: What a reader types to repeat the check without us. The console script the pinned
#: `onetrace-verify` distribution installs.
REPEAT_COMMAND = "onetrace-verify ."

#: The run page's one line where a run declares links between its stages and the verifier's report
#: has no row that checks them. Never an incident.
TOPOLOGY_NO_EDGE_ROWS = ("This run declares links between its stages, and the verifier's report has "
                         "no row that checks them.")
_EDGE_ROW = re.compile(r"^\[[A-Z -]+\]\s+edges\b", re.M)


def topology_note(*, declares_edges: bool, output: str) -> str:
    """The note for a run, or "" where the run declares no links or the verifier checked them."""
    return TOPOLOGY_NO_EDGE_ROWS if declares_edges and not _EDGE_ROW.search(output) else ""


class CheckRunnerError(RuntimeError):
    """The runner could not run the verifier at all. Never a verdict about the record."""


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One invocation of the verifier over one stored run."""
    envelope: dict            # onetrace-viewer/check-report/0.1, as the viewer reads it
    verdict: str
    exit_status: str
    output: bytes             # the verifier's stdout, verbatim
    n_pass: int
    n_fail: int
    n_not_run: int
    unreadable: str = ""      # why the report could not be read, when it could not
    declares_edges: bool = False
    topology_run: bool = False
    topology_note: str = ""


#: Where the shipped verifier's module lives, newest layout first.
#:
#: `onetrace_verify.verify` is the layout from the SDK's `4c11f0e`: `verify.py` and
#: `canonicalize.py` moved INSIDE the package so `importlib.resources` can find them once
#: installed. Before that they were top-level `py-modules`, so `import verify` worked and
#: now does not -- a breaking change between our two pins, recorded in PINS.md.
#:
#: Both are tried, newest first, so this console reads either pin rather than only the one
#: it was written against. Running the file as a script still resolves `verify.py`'s own
#: bare `from canonicalize import canonicalize`, because a script's directory goes on
#: `sys.path` and its sibling is right there.
VERIFIER_MODULES = ("onetrace_verify.verify", "verify")


def shipped_verifier() -> Path:
    """Ask the installed distribution where its verifier is; never hardcode a path.

    Locating it by import rather than by a relative path is what makes this a dependency
    rather than a copy -- and it means a reinstall at a different commit moves the verifier
    without editing anything here.
    """
    tried = []
    for name in VERIFIER_MODULES:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError) as e:            # a parent package that is absent
            tried.append(f"{name}: {type(e).__name__}")
            continue
        if spec is not None and spec.origin:
            return Path(spec.origin)
        tried.append(f"{name}: not found")
    raise CheckRunnerError(
        "the verifier is not installed; none of its module names resolved. Tried:\n  "
        + "\n  ".join(tried)
        + "\nInstall the pinned onetrace-verify distribution (see PINS.md). This refuses "
          "rather than falling back to a copy, because a console that checked runs with "
          "bytes nobody pinned would be worth less than one that did not check them.")


def materialise(run: StoredRun, store: Store, dest: Path) -> Path:
    """Write a stored run back to disk, byte for byte, so the verifier can read it.

    The verifier opens chain files relative to the working directory, so it needs a real
    folder. The bytes come from the store's objects, verified on the way out by `get`.
    """
    dest = Path(dest)
    for path, key in run.listing:
        target = dest / path
        #: Never outside the run's own folder, whatever the listing says: a
        #: record is checked when it is read, and this checks again where it is used.
        if not target.resolve().is_relative_to(dest.resolve()):
            raise StoreError(f"the stored path {path!r} leads outside the run's folder")
        target.parent.mkdir(parents=True, exist_ok=True)
        #: Never over a file already written: a stored run whose two paths name
        #: one file here -- written on another host, or edited -- raises `SameFileError`.
        create_exclusively(target, store.get(key), named=path)
    return dest


#: How long the check may take. At least as long as staging's own verifier call (180 s,
#: `staging.ask_the_verifier`), twice over for a loaded machine: a verifier that passed staging
#: and then outran a shorter check left a run stored with no report (the second confirmation
#: review, B2). A check that still does not finish is recorded as unfinished -- could not
#: check, with that note -- never raised.
CHECK_TIMEOUT_SECONDS = 360


#: Each exit status a check gives with the result its summary states, and the verdict for them
#: `onetrace-verify` exits 2, and `sdk_verify` 4, for NOT VERIFIED: a receipt
#: names a format the check does not implement, so its content was not read. Those are never
#: holds and never contradicts. Reachable end to end since the 0.2.0 verifier: it reads a
#: preview-format run, which ingest accepts, as NOT VERIFIED.
_VERDICTS = {("0", "pass"): HOLDS, ("1", "fail"): CONTRADICTS}
NOT_VERIFIED_EXITS = ("2", "4")

#: A preview-format run, checked with the pinned verifier, is "Couldn't check", never "doesn't
#: hold", and says why in these words: the format, not a verifier version, so they stay true for
#: any version. The run stays stored and viewable.
PREVIEW_CHAIN_FORMAT = "stage-receipt-chain/0.0-preview"
PREVIEW_REASON = ("This run is in the preview record format (stage-receipt/0.0-preview), and "
                  "onetrace-verify does not check that format, so its receipts couldn't be checked.")
#: The reason runs checked before were stored with, which named a verifier version. Still
#: recognised on a stored run; never stored again, and never shown: a page shows PREVIEW_REASON.
PREVIEW_REASON_STORED_BEFORE = ("This run uses the preview record format, which the 0.2.0 verifier "
                                "doesn't check. It was recorded before onetrace 0.1.")
PREVIEW_REASONS = (PREVIEW_REASON, PREVIEW_REASON_STORED_BEFORE)


def is_preview_not_verified(run) -> bool:
    """A stored preview-format run whose check said NOT VERIFIED for that
    format -- a known, permanent state, not an event. Exactly this, and nothing wider: the format,
    the verdict, a NOT VERIFIED exit and the fixed reason (either one), all four."""
    return (run.format == PREVIEW_CHAIN_FORMAT and run.check_verdict == COULD_NOT_CHECK
            and run.check_exit in NOT_VERIFIED_EXITS and run.check_note in PREVIEW_REASONS)


def shown_note(run) -> str:
    """A stored run's check note as a page shows it: the current reason for a preview run, whichever
    of the two fixed reasons it was stored with; any other note as stored."""
    return PREVIEW_REASON if is_preview_not_verified(run) else run.check_note


#: The Overview's one line, shown only where such runs exist; and its singular.
PREVIEW_OVERVIEW_LINE = ("{n} runs are in the preview record format (stage-receipt/0.0-preview), and "
                         "onetrace-verify does not check that format, so their receipts couldn't be "
                         "checked.")
PREVIEW_OVERVIEW_LINE_ONE = ("1 run is in the preview record format (stage-receipt/0.0-preview), and "
                             "onetrace-verify does not check that format, so its receipts couldn't be "
                             "checked.")


def preview_overview_line(n: int) -> str:
    """The Overview's line for `n` (at least 1) stored preview runs: the singular for one."""
    return PREVIEW_OVERVIEW_LINE_ONE if n == 1 else PREVIEW_OVERVIEW_LINE.format(n=n)


def not_verified_reason(run_format: str, output: str) -> str:
    """The stated reason for a NOT VERIFIED check (exit 2): the fixed sentence for a preview-format
    run; otherwise the check's own summary line, quoted -- it names what it did not implement."""
    if run_format == PREVIEW_CHAIN_FORMAT:
        return PREVIEW_REASON
    lines = [line for line in output.splitlines() if line.strip()]
    return f"not verified; the check says: {lines[-1] if lines else '(no summary line)'}"


def verdict_for(exit_status: str, overall: str) -> str:
    """The verdict from the check's exit status and its summary's result, never from its rows."""
    if exit_status in NOT_VERIFIED_EXITS:
        return COULD_NOT_CHECK
    return _VERDICTS.get((exit_status, overall), COULD_NOT_CHECK)


#: What a stored check records of the trust file it ran with: the file's sha256,
#: "none" where no trust file was set -- and for a report stored before this, which ran without
#: `--trust` -- or "unreadable" where the console could not read the file to hash it (the verifier
#: then says why, in its own `--trust` row).
NO_TRUST_FILE = "none"
TRUST_UNREADABLE = "unreadable"


def trust_record(trust_file: str | None) -> str:
    if not trust_file:
        return NO_TRUST_FILE
    import hashlib
    try:
        return "sha256:" + hashlib.sha256(Path(trust_file).read_bytes()).hexdigest()
    except OSError:
        return TRUST_UNREADABLE


#: What a stored check records of the time-stamp authority it ran with: "none" where none was
#: given (and for a report stored before this), or the sha256 of its certificate and of each root,
#: "sha256:<cert>;sha256:<root>,...", or "unreadable" where a file could not be read to hash it.
NO_TSA = "none"


def tsa_record(tsa_cert: str | None, tsa_roots=()) -> str:
    if not tsa_cert:
        return NO_TSA
    import hashlib
    try:
        cert = "sha256:" + hashlib.sha256(Path(tsa_cert).read_bytes()).hexdigest()
        roots = ",".join("sha256:" + hashlib.sha256(Path(r).read_bytes()).hexdigest() for r in tsa_roots)
    except OSError:
        return TRUST_UNREADABLE
    return f"{cert};{roots}"


def check_options(config) -> dict:
    """What every check runs with, from the console's configuration: the trust file, and the
    time-stamp authority's certificate and roots."""
    return {"trust_file": getattr(config, "trust_file", None) if config is not None else None,
            "tsa_cert": getattr(config, "tsa_cert", None) if config is not None else None,
            "tsa_roots": tuple(getattr(config, "tsa_roots", ()) or ()) if config is not None else ()}


def stored_tsa_record(run: StoredRun, store: Store) -> str | None:
    """The time-stamp authority the run's stored check ran with, or None where it has no
    readable report. A report stored before the record was kept ran with none."""
    from onetrace_console.home import _envelope
    envelope = _envelope(run, store)
    if envelope is None:
        return None
    recorded = envelope.get("tsa", NO_TSA)
    return recorded if isinstance(recorded, str) else None


def stored_trust_record(run: StoredRun, store: Store) -> str | None:
    """The trust file the run's stored check ran with, or None where it has no readable report."""
    from onetrace_console.home import _envelope
    envelope = _envelope(run, store)
    if envelope is None:
        return None
    recorded = envelope.get("trust_file", NO_TRUST_FILE)
    return recorded if isinstance(recorded, str) else None


def check(run_dir: Path, *, ran_at: str | None = None, trust_file: str | None = None,
          tsa_cert: str | None = None, tsa_roots=(), extra: tuple[str, ...] = ()) -> CheckResult:
    """Run the verifier over a run folder and read its own summary. No opinions added.
    `trust_file`: the console's configured trust file, passed as `--trust`; `tsa_cert` and
    `tsa_roots`: the time-stamp authority's certificate and roots, as `--tsa-cert`/`--tsa-root`."""
    from onetrace_console.viewer.report import ReportUnreadable, capture_cli, parse

    run_dir = Path(run_dir)
    manifest_path = run_dir / "MANIFEST.json"
    if not manifest_path.is_file():
        raise CheckRunnerError(f"no MANIFEST.json in {run_dir}")

    #: The installed CLI -- not the bench `verify.py`, which lacks
    #: the graph-edge and anchor rows -- as its words, its `--json` rows, and, only where the run
    #: holds `artifacts/`, again with the output files required (the evidence for "Records
    #: agree"). With the flag a run without output files FAILs, so the flag is never the check.
    shipped_verifier()                  # the verifier is installed, or this refuses as before
    #: A run recorded in format 0.3 may declare optional stages; the check is run once more with
    #: every required stage asked for, and only its row says what was left out (`viewer.report`).
    #: An earlier format's check is the check it was.
    complete = _manifest(manifest_path).get("format") in COMPLETENESS_FORMATS
    envelope = capture_cli(run_dir, outputs=(run_dir / "artifacts").is_dir(), complete=complete,
                           timeout=CHECK_TIMEOUT_SECONDS,
                           trust=_relative_to(trust_file, run_dir) if trust_file else None,
                           tsa=(_relative_to(tsa_cert, run_dir), [_relative_to(r, run_dir) for r in tsa_roots])
                           if tsa_cert else None,
                           extra=extra)
    envelope["trust_file"] = trust_record(trust_file)
    envelope["tsa"] = tsa_record(tsa_cert, tsa_roots)
    if ran_at is not None:
        # Fixed inputs for a test that needs a stable envelope. A live `ran_at` is what it
        # is; it is never rewritten after the fact.
        envelope["ran_at"] = ran_at

    declares_edges = bool(_manifest(manifest_path).get("edges"))

    try:
        report = parse(envelope)
    except ReportUnreadable as e:
        # Unreadable is its own outcome. NEVER `contradicts`: the console has learnt
        # nothing about the record, and saying "contradicts" would be an accusation drawn
        # from its own inability to read.
        return CheckResult(
            envelope=envelope, verdict=COULD_NOT_CHECK,
            exit_status=str(envelope.get("exit_status", "")),
            output=envelope.get("stdout", "").encode("utf-8"),
            n_pass=0, n_fail=0, n_not_run=0, unreadable=str(e),
            declares_edges=declares_edges, topology_run=False,
            topology_note=topology_note(declares_edges=declares_edges,
                                        output=envelope.get("stdout", "")))

    verdict = verdict_for(report.exit_status, report.overall)
    return CheckResult(
        envelope=envelope, verdict=verdict, exit_status=report.exit_status,
        output=report.output.encode("utf-8"),
        n_pass=report.count("pass"), n_fail=report.count("fail"),
        n_not_run=report.count("not_run"),
        declares_edges=declares_edges, topology_run=False,
        topology_note=topology_note(declares_edges=declares_edges, output=report.output))


#: The chain formats whose check is run again with `--require-complete` (`check`).
COMPLETENESS_FORMATS = ("stage-receipt-chain/0.3",)


def nothing_missing_state(folder: Path, envelope: dict | None = None) -> str:
    """Rung 3, "nothing missing", as the run's own page decides it, for Home to count
    (Home once counted from the chain and said an early-stopped run missed nothing,
    while its page said "No"). The viewer's own test, `viewer.model.nothing_missing`, over the
    record read as the page reads it, beside this console's own check (`envelope`) where it has one;
    empty -- not established -- where the viewer refuses the
    record, as the page then says, or reading it fails any other way."""
    from onetrace_console.viewer.model import nothing_missing, refuse_unreadable_parts
    from onetrace_console.viewer.record import RecordError, read_record
    from onetrace_console.viewer.report import ReportUnreadable, parse
    try:
        record = read_record(folder)
        refuse_unreadable_parts(record)
        try:
            report = parse(envelope) if envelope is not None else None
        except ReportUnreadable:
            report = None
        return nothing_missing(record, report).state
    except RecordError:
        return ""
    except Exception:  # noqa: BLE001 - not established, and logged; the check still stands
        import sys
        import traceback
        traceback.print_exc(file=sys.stderr)
        return ""


#: The derivation `derived_from` makes. A run whose record carries another value is re-derived
#: once at start-up from its stored bytes, without running its check again. The rule: change this
#: value whenever `derived_from` adds or changes a field. The values so far:
#:   1. rung 3, the receipts delivered, the list row and the digests (runs stored before it had
#:      no rung 3, and read "not established" for good);
#:   2. adds the declared stages delivered and the retries;
#:   3. adds the declared stages whose last recorded attempt failed;
#:   4. adds what the run's own check says of its anchors;
#:   5. adds what it says of the run's signatures;
#:   6. the same derivation as 5, under a neutral name;
#:   7. adds the step a run stopped at by its own rule (`ingest.declined_at`);
#:   8. adds what the run's own check says of its approved plan ("Ran as approved");
#:   9. rung 3 reads "Not reached" where the run stopped at a step's own rule;
#:  10. adds rung 1, "Records agree", as the run's own page decides it, and why.
DERIVED = "derivation-10"


def _reading(folder: Path, envelope: dict | None, read) -> str:
    """`read` (a `viewer.model` reading) over the record read as the page reads it and the stored
    report: its kind, or empty -- no own check read -- where there is no report, its rows can't be
    read, or the viewer refuses the record, as the page then says."""
    if envelope is None:
        return ""
    from onetrace_console.viewer.model import refuse_unreadable_parts
    from onetrace_console.viewer.record import RecordError, read_record
    from onetrace_console.viewer.report import ReportUnreadable, parse
    try:
        record = read_record(folder)
        refuse_unreadable_parts(record)
        found = read(record, parse(envelope), True)
    except (RecordError, ReportUnreadable):
        return ""
    except Exception:  # noqa: BLE001 - no own check read, and logged; the check still stands
        import traceback
        traceback.print_exc(file=sys.stderr)
        return ""
    return found.kind if found is not None else ""


def signed_state(folder: Path, envelope: dict | None) -> str:
    """"Signed by a known recorder", as the run's own page reads it from this console's own check,
    for the Overview to count."""
    from onetrace_console.viewer.model import signature_reading
    return _reading(folder, envelope, signature_reading)


def approved_state(folder: Path, envelope: dict | None) -> str:
    """"Ran as approved", as the run's own page reads it from this console's own check
    (`viewer.model.ran_as_approved`, the verifier's own rows and exit only), for the runs list."""
    from types import SimpleNamespace

    from onetrace_console.viewer.model import ran_as_approved, rows_from_report

    def read(record, report, own_check):
        return SimpleNamespace(kind=ran_as_approved(record.manifest, rows_from_report(report),
                                                    own_check=own_check, verifier=None).state)
    return _reading(folder, envelope, read)


def anchored_state(folder: Path, envelope: dict | None) -> str:
    """"Committed by a known time", as the run's own page reads it from this console's own check:
    `viewer.model.anchor_reading` over the record read as the page reads it and the stored report,
    for the Overview to count. Empty -- no own check read -- where there is no
    report, its rows cannot be read, or the viewer refuses the record, as the page then says."""
    if envelope is None:
        return ""
    from onetrace_console.viewer.model import anchor_reading, refuse_unreadable_parts
    from onetrace_console.viewer.record import RecordError, read_record
    from onetrace_console.viewer.report import ReportUnreadable, parse
    try:
        record = read_record(folder)
        refuse_unreadable_parts(record)
        read = anchor_reading(record, parse(envelope), True)
    except (RecordError, ReportUnreadable):
        return ""
    except Exception:  # noqa: BLE001 - no own check read, and logged; the check still stands
        import traceback
        traceback.print_exc(file=sys.stderr)
        return ""
    return read.kind if read is not None else ""


def agree_state(folder: Path, envelope: dict | None) -> dict:
    """"Records agree", rung 1, as the run's own page decides it from this console's own check
    (`viewer.model.records_agree_reading`), for every list and count (`records.state`): its state
    and why. Empty -- no own check read -- where there is no report or the viewer refuses the
    record, as the page then says."""
    if envelope is None:
        return {"agree": "", "agree_why": ""}
    from onetrace_console.viewer.model import records_agree_reading, refuse_unreadable_parts
    from onetrace_console.viewer.record import RecordError, read_record
    from onetrace_console.viewer.report import ReportUnreadable, parse
    try:
        record = read_record(folder)
        refuse_unreadable_parts(record)
        try:
            report, problem = parse(envelope), None
        except ReportUnreadable as e:
            report, problem = None, str(e)
        read = records_agree_reading(record, report, problem)
    except RecordError:
        return {"agree": "", "agree_why": ""}
    except Exception:  # noqa: BLE001 - no own check read, and logged; the check still stands
        import traceback
        traceback.print_exc(file=sys.stderr)
        return {"agree": "", "agree_why": ""}
    return {"agree": read.kind, "agree_why": read.why}


def derived_from(folder: Path, envelope: dict | None = None) -> dict:
    """What the console keeps about a run beside its check, read once from its laid-out folder:
    rung 3 (`nothing_missing_state`); the list's row, or why the viewer refused it; the recorded
    digests Home's markers read; and the receipts delivered (the files the chain names that
    are receipts). JSON where the record keeps JSON. Kept so no later render reads the run's
    receipts again."""
    from onetrace_console.viewer.model import list_row
    from onetrace_console.viewer.record import RecordError, read_record

    from onetrace_console.ingest import RECEIPT_FORMATS, same_file
    from onetrace_console.overview import digests_in
    files = {same_file(p.relative_to(folder).as_posix()): p
             for p in folder.rglob("*") if p.is_file()}

    def read(name: str) -> bytes:
        return files[same_file(name)].read_bytes()

    try:
        row = list_row(read_record(folder))
        kept_row = {"case_ran": row.case_ran, "case_for": row.case_for,
                    "step_count": row.step_count, "case_for_more": row.case_for_more}
    except RecordError as e:
        kept_row = {"refused": str(e), "from_viewer": True}
    except Exception as e:  # noqa: BLE001 - kept as the list's reason, and logged
        import traceback
        traceback.print_exc(file=sys.stderr)
        kept_row = {"refused": f"{type(e).__name__}: {e}", "from_viewer": False}
    digests = digests_in(read)
    receipts = set()
    from onetrace_console.ingest import (_declared_by, declined_at, delivered_and_retries,
                                         last_attempt_failed)
    declared: list[str] = []
    seen: set[str] = set()
    attempts: list[tuple] = []  # (stage name, outcome class, outcome status), in the chain's order
    for entry in _manifest(folder / "MANIFEST.json").get("chain") or []:
        name = entry.get("file") if isinstance(entry, dict) else None
        held = files.get(same_file(name)) if isinstance(name, str) else None
        if held is None:
            continue
        try:
            receipt = load_json_bounded(held.read_bytes().decode("utf-8"), held.name)
        except (UnicodeDecodeError, ValueError, RecursionError):
            continue
        if isinstance(receipt, dict) and receipt.get("format") in RECEIPT_FORMATS:
            if held in receipts:
                continue
            receipts.add(held)
            _declared_by(receipt, declared, seen)
            stage, outcome = receipt.get("stage"), receipt.get("outcome")
            attempts.append((stage.get("name") if isinstance(stage, dict) else None,
                             outcome.get("class") if isinstance(outcome, dict) else None,
                             outcome.get("status") if isinstance(outcome, dict)
                             and isinstance(outcome.get("status"), str) else "",
                             outcome.get("reason") if isinstance(outcome, dict)
                             and isinstance(outcome.get("reason"), str) else ""))
    return {"nothing_missing": nothing_missing_state(folder, envelope),
            "anchored": anchored_state(folder, envelope),
            "signed": signed_state(folder, envelope),
            "approved": approved_state(folder, envelope),
            **agree_state(folder, envelope),
            "list_row": json.dumps(kept_row), "recorded_count": len(receipts),
            **delivered_and_retries(attempts, seen),
            "last_failed": json.dumps(last_attempt_failed(attempts, declared)),
            "declined": json.dumps(declined_at(attempts, declared)),
            "digests": json.dumps(digests), "derived": DERIVED}



def rederive(run: StoredRun, store: Store) -> StoredRun:
    """`derived_from` for a stored run, from its stored bytes, without running its check again:
    its report and verdict are left as they were. Stored, and returned."""
    envelope = None
    if run.check_report:
        try:
            envelope = load_json_bounded(store.get(run.check_report).decode("utf-8"),
                                         "the check report")
        except (ValueError, UnicodeDecodeError, StoreError, RecursionError):
            envelope = None
    with tempfile.TemporaryDirectory(prefix="onetrace-derive-") as tmp:
        try:
            fields = derived_from(materialise(run, store, Path(tmp) / "run"),
                                  envelope if isinstance(envelope, dict) else None)
        except (SameFileError, StoreError) as e:
            fields = {"nothing_missing": "", "anchored": "", "signed": "", "approved": "", "agree": "", "agree_why": "", "digests": "null", "derived": DERIVED,
                      "list_row": json.dumps({"refused": f"{type(e).__name__}: {e}",
                                              "from_viewer": False})}
    updated = replace(run, **fields)
    store.put_run(updated)
    return updated


def run_and_record(run: StoredRun, store: Store, *, ran_at: str | None = None,
                   trust_file: str | None = None, tsa_cert: str | None = None,
                   tsa_roots=()) -> StoredRun:
    """Check a stored run, store the report verbatim, and update the run's record."""
    #: A run that cannot be laid out here as it was stored is not checked at all -- the verifier
    #: is never asked about a folder that is not the run -- and is recorded as could not check,
    #: with why, and with no report. Otherwise, the check's own outcome.
    report_key, exit_status, verdict, note, topology = "", "", COULD_NOT_CHECK, "", ""
    derived = {"nothing_missing": "", "anchored": "", "signed": "", "approved": "", "agree": "", "agree_why": "", "digests": "null",
               "derived": DERIVED}
    with tempfile.TemporaryDirectory(prefix="onetrace-check-") as tmp:
        try:
            folder = materialise(run, store, Path(tmp) / "run")
        except (SameFileError, StoreError) as e:
            folder, note = None, f"the run's files cannot be laid out on this host as stored: {e}"
            derived["list_row"] = json.dumps({"refused": f"{type(e).__name__}: {e}",
                                              "from_viewer": False})
        if folder is not None:
            extra = _beside_options(run, store, folder, Path(tmp))
            #: The reader's trust and time-stamp files, copied beside the laid-out run and named
            #: from it: the stored check records no path of this machine.
            trust_file, tsa_cert, tsa_roots = _evidence_copies(Path(tmp) / "evidence", trust_file,
                                                               tsa_cert, tsa_roots)
            result = check(folder, ran_at=ran_at, trust_file=trust_file, tsa_cert=tsa_cert,
                           tsa_roots=tsa_roots, extra=extra)
            _keep_export(run, store, folder)
            derived = derived_from(folder, result.envelope)
            shutil.rmtree(folder, ignore_errors=True)
            report_key = store.put(json.dumps(result.envelope, indent=1, sort_keys=True,
                                              ensure_ascii=False).encode("utf-8"))
            exit_status, verdict, note = result.exit_status, result.verdict, result.unreadable
            if verdict == COULD_NOT_CHECK and not note and exit_status in NOT_VERIFIED_EXITS:
                #: Every could-not-check carries its reason (the store refuses one without).
                note = not_verified_reason(run.format, result.output.decode("utf-8", "replace"))
            topology = result.topology_note

    updated = replace(run,
                      check_report=report_key,
                      check_exit=exit_status,
                      check_verdict=verdict,
                      check_note=note,
                      topology_note=topology,
                      **derived)
    store.put_run(updated)
    return updated


def _evidence_copies(dest: Path, trust_file, tsa_cert, tsa_roots):
    """Each of the reader's files that exists, copied into `dest`; one that cannot be read is
    passed as given, so the verifier says why in its own row."""
    def copy(path, name):
        if not path:
            return path
        try:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest / name)
            return str(dest / name)
        except OSError:
            return path
    roots = tuple(copy(r, f"tsa-root-{n}{Path(r).suffix}") for n, r in enumerate(tsa_roots or ()))
    return (copy(trust_file, "trust" + Path(trust_file).suffix if trust_file else ""),
            copy(tsa_cert, "tsa-cert" + Path(tsa_cert).suffix if tsa_cert else ""), roots)


def _relative_to(path, run_dir: Path):
    """`path` named from the run's folder where both are in the check's own temporary folder, with
    `/` on every platform: the stored command is read on other machines."""
    import os
    if not path:
        return path
    p = Path(path)
    if p.is_absolute() and p.is_relative_to(run_dir.parent):
        return os.path.relpath(p, run_dir).replace(os.sep, "/")
    return p


def _beside_options(run: StoredRun, store: Store, folder: Path, tmp: Path) -> tuple[str, ...]:
    """onetrace-verify 0.5's options for files beside the run: the decision export and the permit
    issuers kept with it (`beside`), and `--nested-run` for each run it records calling (a `run:<id>`
    input) that the console holds, laid out next to it. A run whose inner run is not held gets the
    verifier's NOT-RUN row and its reason."""
    from onetrace_console import beside
    from onetrace_console.nesting_view import nested_inputs
    import os
    from onetrace_console.onedoor_panel import decisions, gated_stages
    receipts = []
    for p in sorted((folder / "receipts").glob("*.json")):
        try:
            receipts.append(load_json_bounded(p.read_text(encoding="utf-8"), p.name))
        except (OSError, ValueError, UnicodeDecodeError, RecursionError):
            continue
    #: The decision files only for a run that declares gated stages or cites a decision: the
    #: verifier's onedoor rows are about such runs, and given for any other they read NOT-RUN.
    gated = gated_stages(_manifest(folder / "MANIFEST.json")) or any(
        decisions(r) for r in receipts if isinstance(r, dict))
    opts = beside.verifier_files(store, run.key, tmp / "beside", folder) if gated else ()
    ids = set()
    for r in receipts:
        if isinstance(r, dict):
            ids.update(i for i, _ in nested_inputs(r))
    if ids:
        held = {r.run_id: r for r in store.runs() if r.run_id in ids}
        for n, rid in enumerate(sorted(held), start=1):
            try:
                inner = materialise(held[rid], store, tmp / "nested" / str(n))
            except (SameFileError, StoreError):
                continue
            #: Relative to the run's folder, where the verifier runs: no path of this machine kept.
            opts += ("--nested-run", Path(os.path.relpath(inner, folder)).as_posix())
    return opts


#: The SDK's own export of a run as one OpenTelemetry trace, kept for the trace panel where the
#: person gave no trace file. A view of the record, never evidence: the panel says so.
EXPORT_TIMEOUT_SECONDS = 60


def _keep_export(run: StoredRun, store: Store, folder: Path) -> None:
    from onetrace_console import beside
    from onetrace_console.child import utf8_env
    if beside.read(store, run.key).get("trace_source") == beside.GIVEN:
        return
    try:
        proc = subprocess.run([sys.executable, "-m", "onetrace", "export", "otel", "MANIFEST.json"],
                              cwd=folder, capture_output=True, timeout=EXPORT_TIMEOUT_SECONDS, env=utf8_env())
    except (OSError, subprocess.SubprocessError):
        return
    if proc.returncode == 0 and proc.stdout.strip():
        beside.keep(store, run.key, trace=proc.stdout, trace_source=beside.EXPORT)


def _manifest(path: Path) -> dict:
    try:
        obj = load_json_bounded(path.read_bytes().decode("utf-8"), path.name)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return obj if isinstance(obj, dict) else {}
