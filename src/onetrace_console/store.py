"""Content-addressed, immutable storage for received runs and the reports over them.

    Objects: content-addressed, immutable. Key = sha256 of the bytes.
    Runs: the folder layout preserved as a listing (`path -> object key`), so
    `GET /v1/runs/{id}/bundle` returns a tar that is byte-identical to what was
    delivered.                          -- the store and console design note, §2

THE BYTES ARE NEVER TOUCHED
---------------------------
Everything here is received data. Files are read and written in binary, nothing is
decoded on the way in or out, and no path is normalised. A store that "helpfully" fixed a
line ending would destroy the only thing a receipt is for, silently, with a green exit
code. E10, and the reason `.gitattributes` in this repository says `* -text`.

IMMUTABLE MEANS REFUSING, NOT OVERWRITING
-----------------------------------------
Writing an object that already exists is allowed only when the bytes are identical, which
for a content address should be a tautology -- and is checked anyway, because "should be a
tautology" is what a silent corruption sounds like from the inside. A digest collision or
a damaged file makes `put` raise, never overwrite.

NOTHING PARTIAL IS EVER STORED
------------------------------
A run becomes visible when its record is written, and its record is written last. Objects
are content-addressed, so an object written for a run that was then rejected is not a
partial run -- it is unreferenced bytes with a name nobody holds. `ingest` validates
completely before it writes anything at all, so that case needs an interrupted process to
arise, not a rejected delivery.
"""
from __future__ import annotations

import hashlib
from onetrace_console.bounded_json import load_json_bounded
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

#: A store id is the sha256 of `run_id\x00chain_head`, so identity is
#: `(run_id, chain_head)` exactly as the design note requires, and the id can be computed
#: from the delivery without asking the store anything.
_KEY_SEPARATOR = b"\x00"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


#: What a stored run missing one of its objects reads as, everywhere -- the
#: shape of the "couldn't check" lines, never holds or contradicts. {objects}: the record's names
#: for them, in its listing's order.
MISSING_OBJECT = "couldn't check: the stored record is missing {objects}"


class StoreError(RuntimeError):
    """A store operation that cannot be completed honestly. Never silently repaired."""


class SameFileError(RuntimeError):
    """Two of a run's paths name one file on this host, and the second would be written over the
    first. Never an overwrite."""


def create_exclusively(target: Path, data: bytes, *, named: str) -> None:
    """Write a run's file under `target`, refusing if that file already exists.

    Staging and the check runner once wrote with `write_bytes`, which opens a file that
    already exists when a second path reaches it -- on Windows an 8.3 short name, a case variant,
    a trailing dot or space -- so a second member carrying the original bytes was written over an
    altered receipt, and the run was recorded as holding. Every folder a run is laid out in is
    new, so a file already there can only have been written by another of the run's own paths.
    """
    try:
        with open(target, "xb") as fh:
            fh.write(data)
    except FileExistsError:
        raise SameFileError(f"{named!r} names a file another of the run's paths already wrote "
                            f"on this host") from None


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def arrival_order(runs, *, newest_first: bool) -> list:
    """Runs by when they arrived, newest first or oldest first. Arrival is recorded to the second,
    so runs that share one are ordered by run name (run_id, A to Z), and only two runs sharing a
    name by their key. Never by the key first: a key is a digest of the record, which holds its
    recorded times, so the same runs built again get other keys, and a key-first order would
    differ from build to build (tests/test_arrival_ties.py)."""
    out = sorted(runs, key=lambda r: (r.run_id, r.key))
    out.sort(key=lambda r: r.received_at, reverse=newest_first)
    return out


def run_key(run_id: str, chain_head: str) -> str:
    return digest(run_id.encode("utf-8") + _KEY_SEPARATOR + chain_head.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class StoredRun:
    """One received run: what it is, what it is made of, and what was found about it.

    `listing` is `path -> object key` in the order the delivery carried, so the bundle
    can be rebuilt byte-for-byte AND file-for-file in the same order.

    `flags` is the design note's `run_id reused` and anything like it: a finding about the
    delivery rather than about the record. It is never a verdict -- verdicts come from the
    check runner reading the verifier's own report.

    The index fields (`pipeline`, `declared_stages`, `stage_count`) are recorded even
    though nothing in this slice reads them. They are cheap now and expensive to backfill:
    a run stored without them cannot be compared later without re-reading every bundle.
    See DESIGN_GAPS.md §4.
    """
    key: str
    run_id: str
    chain_head: str
    format: str
    listing: tuple[tuple[str, str], ...]
    received_at: str
    flags: tuple[str, ...] = ()
    pipeline: str = ""
    #: The stages the receipts declare (their `coverage.declared_stages`, in order, each once),
    #: the first LIST_CAP of them; `stage_count` counts them all, and `declared_digest` is the
    #: sha256 of them all, which is what runs are grouped and matched by.
    declared_stages: tuple[str, ...] = ()
    stage_count: int = 0
    #: The receipts delivered: files the manifest's chain names that the delivery holds, each
    #: counted once.
    recorded_count: int = 0
    #: The declared stages with at least one receipt
    #: delivered, and the retries recorded -- a further receipt of a stage after one of that
    #: stage's receipts failed with an error. Derived when the run is checked (`checks.DERIVED`).
    delivered_stages: int = 0
    retries: int = 0
    #: The declared stages whose last recorded attempt failed with an error, as
    #: JSON [[stage, error type], ...] in the declared order. Derived with the fields above.
    last_failed: str = ""
    #: The step the run stopped at by its own rule (`ingest.declined_at`), as JSON {"stage",
    #: "reason", "left": [...]}, or "null" where it did not stop at one. Derived with the fields above.
    declined: str = ""
    declared_digest: str = ""
    #: Rung 3, "nothing missing", as the run's own page decides it (`viewer.model.
    #: nothing_missing`), recorded when the run is checked: yes, no, couldnt-check or
    #: not-checked -- or empty, not established, where the viewer could not read the record.
    #: Home counts this, so it and the run's page cannot disagree.
    nothing_missing: str = ""
    #: "Committed by a known time" as the run's own page reads its own check (`viewer.model.
    #: anchor_reading`), recorded when the run is checked: yes, couldnt-check, failed or
    #: not-anchored -- or empty where the page has no own check whose rows it reads. The Overview
    #: counts this, so it and the run's page cannot disagree.
    anchored: str = ""
    #: "Signed by a known recorder" as the run's own page reads its own check (`viewer.model.
    #: signature_reading`), recorded when the run is checked: yes, untrusted, failed, unsigned,
    #: not-installed, couldnt-check or unreadable -- or empty where the page has no own check whose
    #: rows it reads. The Overview counts this.
    signed: str = ""
    #: "Ran as approved" as the run's own page reads it from its own check (`viewer.model.
    #: ran_as_approved`), recorded when the run is checked: approved, departed, edges-mismatch,
    #: no-plan, not-a-graph-run, cant-check, does-not-verify or couldnt-check -- or empty where
    #: the page has no own check whose rows it reads. The runs list shows this.
    approved: str = ""
    #: "Records agree" as the run's own page decides rung 1 from its own check (`viewer.model.
    #: records_agree_reading`), recorded when the run is checked: yes, no, couldnt-check or
    #: not-checked -- or empty where the page has no own check it reads. `agree_why` is
    #: `no-outputs` where the check held without the run's output files required. Every page and
    #: count reads these through `records.state` alone.
    agree: str = ""
    agree_why: str = ""
    #: What a list shows of the run (the viewer's `list_row`, or why it refused), and the recorded
    #: digests Home's change markers read, as JSON: kept when the run is checked, so no later
    #: render reads its receipts again (otherwise one upload of three 14 MB receipts made
    #: every later ingest take 40 s). Empty where not yet derived.
    list_row: str = ""
    digests: str = ""
    #: Which derivation the fields above and rung 3 come from (`checks.DERIVED`); a run stored
    #: before it is re-derived at start-up, from its stored bytes.
    derived: str = ""
    #: key of the check runner's report object, and its exit status, once it has run.
    check_report: str = ""
    check_exit: str = ""
    check_verdict: str = ""
    #: Why the check could not be read, when it could not. Home shows the
    #: reason beside the count, because "could not be checked" without a reason
    #: is a number a reader can do nothing with.
    check_note: str = ""
    topology_report: str = ""
    topology_exit: str = ""
    #: Why the topology check was not run, when it was not. The stated reason:
    #: the reference check is shipped by no distribution at the pinned commit.
    #: Stored because `I-COULD-NOT-CHECK` quotes a STATED reason, and a reason
    #: that only ever existed in memory is not something a rule can quote.
    topology_note: str = ""

    def to_json(self) -> str:
        d = asdict(self)
        d["listing"] = [list(pair) for pair in self.listing]
        d["declared_stages"] = list(self.declared_stages)
        d["flags"] = list(self.flags)
        return json.dumps(d, indent=1, sort_keys=True, ensure_ascii=False) + "\n"

    @staticmethod
    def from_json(text: str) -> StoredRun:
        """Read a run's record, refusing -- with `ValueError`, saying what is wrong -- one whose
        fields are not the types this version writes (an int `received_at` once stopped
        the start, and a verdict with no reason blanked every other run's pages)."""
        d = load_json_bounded(text, "a stored run record")
        if not isinstance(d, dict):
            raise ValueError(f"the record is a {type(d).__name__}, not an object")
        _check_fields(d)
        d["listing"] = tuple((p, k) for p, k in d["listing"])
        d["declared_stages"] = tuple(d["declared_stages"])
        d["flags"] = tuple(d["flags"])
        return StoredRun(**d)


#: The field types a run's record is written in. The verdicts are `checks.VERDICTS` and the rung
#: states `viewer.model`'s own, each with the empty string for "none recorded"; spelled here
#: because `checks` imports this module (tests/test_round4_fixes.py holds them in step).
_VERDICTS = ("", "holds", "contradicts", "could_not_check")
_RUNG_STATES = ("", "yes", "no", "couldnt-check", "not-checked", "not-reached")
_ANCHOR_READINGS = ("", "yes", "couldnt-check", "failed", "not-anchored")
_SIGNATURE_READINGS = ("", "yes", "untrusted", "failed", "unsigned", "not-installed",
                       "couldnt-check", "unreadable")
_COUNTS = ("stage_count", "recorded_count", "delivered_stages", "retries")
_LISTS = ("flags", "declared_stages")


def _check_fields(d: dict) -> None:
    for name, value in d.items():
        if name == "listing":
            ok = isinstance(value, list) and all(
                isinstance(p, list) and len(p) == 2 and all(isinstance(x, str) for x in p)
                for p in value)
            want = "a list of [path, key] pairs"
        elif name in _LISTS:
            ok = isinstance(value, list) and all(isinstance(x, str) for x in value)
            want = "a list of strings"
        elif name in _COUNTS:
            ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
            want = "a whole number"
        else:
            ok = isinstance(value, str)
            want = "a string"
        if not ok:
            raise ValueError(f"`{name}` is {_shown(value)}, not {want}")
    #: Every name a record gives that this console later joins into a path: its own key (the
    #: folder its pages are written under), each listing path (where the run is laid out) and
    #: each object key. The reviewer's probe_store_types2.py: `..\\..\\..\\escaped_key` wrote pages
    #: outside the pages folder, and `../../escaped.txt` a file outside the store.
    if "key" in d and not _SHA256.match(d["key"]):
        raise ValueError(f"`key` is {_shown(d['key'])}, not a sha256 run key")
    for path, key in d.get("listing", ()):
        why = _outside(path)
        if why:
            raise ValueError(f"the listing path {_shown(path)} {why}")
        if not _SHA256.match(key):
            raise ValueError(f"the listing's object key {_shown(key)} is not a sha256 key")
    if d.get("check_verdict", "") not in _VERDICTS:
        raise ValueError(f"`check_verdict` is {_shown(d['check_verdict'])}, not one of "
                         f"{list(_VERDICTS[1:])}")
    if d.get("nothing_missing", "") not in _RUNG_STATES:
        raise ValueError(f"`nothing_missing` is {_shown(d['nothing_missing'])}, not one of "
                         f"{list(_RUNG_STATES[1:])}")
    if d.get("signed", "") not in _SIGNATURE_READINGS:
        raise ValueError(f"`signed` is {_shown(d['signed'])}, not one of "
                         f"{list(_SIGNATURE_READINGS[1:])}")
    if d.get("anchored", "") not in _ANCHOR_READINGS:
        raise ValueError(f"`anchored` is {_shown(d['anchored'])}, not one of "
                         f"{list(_ANCHOR_READINGS[1:])}")
    if d.get("check_verdict") == "could_not_check" and not (d.get("check_note")
                                                            or d.get("topology_note")):
        #: The check runner records a reason with every could_not_check; a record without one
        #: was not written by it, and an incident would have nothing to quote.
        raise ValueError("`check_verdict` is could_not_check with no stated reason")


def _outside(path: str) -> str:
    """Why a stored path would lead out of the folder a run is laid out in, or "": as ingest
    refuses a member's name (`ingest._unsafe_path`), since this record was written from one."""
    if not path or "\\" in path:
        return "is empty or holds a backslash"
    if re.match(r"^[A-Za-z]:", path) or path.startswith("/"):
        return "is an absolute path"
    if ".." in path.split("/"):
        return "steps out with '..'"
    return ""


def _shown(value) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


@dataclass
class Store:
    """Files on disk. No database driver, because the console ships as a container the
    customer runs and every dependency is one more thing that must be present offline.

    No index at all today -- every run's own record is a file, `runs()` reads them all
    directly, and there is nothing yet large enough to need one in front of that. (An
    earlier draft of this docstring said `sqlite3` "when there is something to index";
    corrected, having measured that nothing here has ever imported it.) If an
    index arrives later, the same property should hold: a run's own record stays a file,
    so the store survives its index being deleted, and nothing lives only in the index.
    """
    root: Path
    _objects: Path = field(init=False)
    _runs: Path = field(init=False)
    #: The run records the last `runs()` could not read, by file name and what is wrong, and
    #: the same for comparisons -- with the keys their file names carry, so their
    #: old pages can be replaced by pages saying so.
    unreadable_runs: tuple[str, ...] = field(default=(), init=False)
    unreadable_run_keys: tuple[str, ...] = field(default=(), init=False)
    unreadable_comparisons: tuple[str, ...] = field(default=(), init=False)
    unreadable_comparison_keys: tuple[str, ...] = field(default=(), init=False)
    #: Each run and rule whose incidents the last `incidents.derive` could not derive, named
    #: Set there, read by the pages that count incidents.
    underived: tuple[str, ...] = field(default=(), init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self._objects = self.root / "objects"
        self._runs = self.root / "runs"
        for d in (self._objects, self._runs):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ objects

    def _object_path(self, key: str) -> Path:
        if not _SHA256.match(key):
            raise StoreError(f"not an object key: {key!r}")
        return self._objects / key[:2] / key

    def put(self, data: bytes) -> str:
        """Store bytes, return their key. Idempotent; refuses to overwrite differing bytes."""
        key = digest(data)
        path = self._object_path(key)
        if path.exists():
            existing = path.read_bytes()
            if existing != data:
                raise StoreError(
                    f"object {key} already holds different bytes ({len(existing)} on disk, "
                    f"{len(data)} offered). A content address cannot mean two things; this "
                    f"is corruption or a collision and either way it is not repaired here.")
            return key
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, data)
        return key

    def get(self, key: str) -> bytes:
        path = self._object_path(key)
        if not path.exists():
            raise StoreError(f"no object {key}")
        data = path.read_bytes()
        got = digest(data)
        if got != key:
            # Read-time verification, because a store that only checks on the way in is a
            # store that tells you about corruption at the worst possible moment.
            raise StoreError(f"object {key} reads back as {got}: the bytes on disk moved")
        return data

    def has(self, key: str) -> bool:
        return self._object_path(key).exists()

    # --------------------------------------------------------------------- runs

    def _run_path(self, key: str) -> Path:
        if not _SHA256.match(key):
            raise StoreError(f"not a run key: {key!r}")
        return self._runs / f"{key}.json"

    def missing(self, run: StoredRun) -> tuple[str, ...]:
        """The record's names for the objects it lists that this store does not hold, in its
        listing's order."""
        return tuple(path for path, key in run.listing if not self.has(key))

    def put_run(self, run: StoredRun) -> None:
        """Write the run's record. This is the act that makes a run visible -- so it is done only
        once every object the record names is held here ("complete or nothing"): otherwise
        refused, and nothing is written."""
        gone = self.missing(run)
        if gone:
            raise StoreError(f"not written: the record of run {run.key} names "
                             f"{', '.join(gone)}, which this store does not hold")
        _atomic_write(self._run_path(run.key), run.to_json().encode("utf-8"))

    def _as_held(self, run: StoredRun) -> StoredRun:
        """A run whose record names an object this store does not hold reads as could not check,
        on every page and count that reads it -- never its stored verdict. Its record is not
        rewritten: a record is never repaired."""
        gone = self.missing(run)
        if not gone:
            return run
        #: Its stored rung 1 reading goes too: it was read from objects no longer all here.
        return replace(run, check_verdict="could_not_check",
                       check_note=MISSING_OBJECT.format(objects=", ".join(gone)),
                       agree="", agree_why="")

    def get_run(self, key: str) -> StoredRun | None:
        path = self._run_path(key)
        if not path.exists():
            return None
        try:
            return self._as_held(StoredRun.from_json(path.read_bytes().decode("utf-8")))
        except _UNREADABLE as e:
            raise StoreError(f"the stored record {path.name} cannot be read: "
                             f"{_why(e)}") from None

    def runs(self) -> tuple[StoredRun, ...]:
        """Every stored run, newest delivery first; runs sharing an arrival second by run name, A
        to Z, and two sharing a name by key (`arrival_order`), so the order is the same on every
        host and every build (tests/test_arrival_ties.py).

        A run record this version cannot read -- damaged, wrong-typed, nested past what JSON
        reads, or written by a later version with a field this one does not know -- is left
        out and named in `unreadable_runs`, so Home can say so, instead of stopping every page,
        ingest and start (the third confirmation review, NEW-6; round 4, S3). It is never
        repaired."""
        out, unreadable, keys = [], [], []
        for path in sorted(self._runs.glob("*.json")):
            try:
                out.append(self._as_held(StoredRun.from_json(path.read_bytes().decode("utf-8"))))
            except _UNREADABLE as e:
                unreadable.append(f"{path.name}: {_why(e)}")
                keys.append(path.stem)
        self.unreadable_runs, self.unreadable_run_keys = tuple(unreadable), tuple(keys)
        return tuple(arrival_order(out, newest_first=True))

    def runs_with_id(self, run_id: str) -> tuple[StoredRun, ...]:
        return tuple(r for r in self.runs() if r.run_id == run_id)


    # -------------------------------------------------------------- comparisons

    def _comparison_path(self, key: str) -> Path:
        if not _SHA256.match(key):
            raise StoreError(f"not a comparison key: {key!r}")
        d = self.root / "comparisons"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{key}.json"

    def put_comparison(self, comparison) -> None:
        """Write a comparison's record. Separate from runs: a comparison is ABOUT runs.

        Kept in its own directory so that `runs()` cannot accidentally count comparisons —
        Home's numbers are counts of runs, and a count that silently included something else
        would be the exact failure the design note's prohibitions are about.
        """
        _atomic_write(self._comparison_path(comparison.key),
                      comparison.to_json().encode("utf-8"))

    def get_comparison(self, key: str):
        from onetrace_console.compare import StoredComparison
        path = self._comparison_path(key)
        if not path.exists():
            return None
        try:
            return StoredComparison.from_json(path.read_bytes().decode("utf-8"))
        except _UNREADABLE + (AttributeError,) as e:
            #: As `get_run`: a record it holds and cannot read is said as that, never raised bare.
            raise StoreError(f"the stored comparison record {path.name} cannot be read: "
                             f"{_why(e)}") from None

    def comparisons(self) -> tuple:
        from onetrace_console.compare import StoredComparison
        d = self.root / "comparisons"
        if not d.is_dir():
            return ()
        #: As `runs`: a comparison record it cannot read is left out, never repaired -- and
        #: named, never dropped without a word.
        out, unreadable, keys = [], [], []
        for p in sorted(d.glob("*.json")):
            try:
                out.append(StoredComparison.from_json(p.read_bytes().decode("utf-8")))
            except _UNREADABLE + (AttributeError,) as e:
                unreadable.append(f"{p.name}: {_why(e)}")
                keys.append(p.stem)
        self.unreadable_comparisons = tuple(unreadable)
        self.unreadable_comparison_keys = tuple(keys)
        return tuple(out)

    # --------------------------------------------------------- decision exports

    def _decision_export_path(self, key: str) -> Path:
        if not _SHA256.match(key):
            raise StoreError(f"not a decision export key: {key!r}")
        d = self.root / "decision_exports"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{key}.json"

    def put_decision_export(self, export) -> None:
        """Write a decision export's record. Separate from `runs/` and `comparisons/`
        for the same reason those are separate from each other: `runs()` must never
        silently start counting something that is not a run.

        This method, like `get_decision_export` and `decision_exports` below, imports
        `onetrace_console.onedoor_ext` -- but only from inside the method body, and
        only when actually called. Nothing at this module's own import time reaches
        into the extension; a disabled console (the extension route never wired up)
        never calls these at all, so `store.py` importing cleanly proves nothing by
        itself -- see `tests/test_onedoor_ext_isolation.py`, which checks the thing
        that actually matters: that the disabled *route* never runs this code.
        """
        _atomic_write(self._decision_export_path(export.key), export.to_json().encode("utf-8"))

    def has_decision_export(self, key: str) -> bool:
        """Whether a record is filed under `key`, without reading it: a malformed record
        must not make a re-delivery fail."""
        return self._decision_export_path(key).exists()

    def get_decision_export(self, key: str):
        from onetrace_console.onedoor_ext.decisions import StoredDecisionExport
        path = self._decision_export_path(key)
        if not path.exists():
            return None
        return StoredDecisionExport.from_json(path.read_bytes().decode("utf-8"))

    def decision_exports(self) -> tuple:
        from onetrace_console.onedoor_ext.decisions import StoredDecisionExport
        d = self.root / "decision_exports"
        if not d.is_dir():
            return ()
        return tuple(StoredDecisionExport.from_json(p.read_bytes().decode("utf-8"))
                     for p in sorted(d.glob("*.json")))

    def decision_export_records(self) -> tuple[tuple[str, bytes], ...]:
        """Every decision record as (its filename's stem, its raw bytes), unparsed. The stem
        is the delivery's content address, which the record's own editable fields are
        checked against; parsing is the caller's, so a malformed record can be reported
        instead of raising here."""
        d = self.root / "decision_exports"
        if not d.is_dir():
            return ()
        return tuple((p.stem, p.read_bytes()) for p in sorted(d.glob("*.json")))


#: What reading a stored record can raise when the record is not one this version wrote.
_UNREADABLE = (OSError, ValueError, UnicodeDecodeError, KeyError, TypeError, RecursionError)


def _why(e: BaseException) -> str:
    """What is wrong with a record, in a line: the type, and the words where there are any. For an
    OSError, its reason alone: the record is named by its file name beside this, and a page
    never shows the server's own path to it (nor, so, repr's doubled backslashes)."""
    text = (e.strerror or "") if isinstance(e, OSError) else str(e)
    said = text.splitlines()[0][:200] if text else ""
    return f"{type(e).__name__}: {said}" if said else type(e).__name__


def _atomic_write(path: Path, data: bytes) -> None:
    """Write via a temporary file in the same directory, then replace.

    A half-written object would be a file whose name is a promise about its contents that
    the contents do not keep -- and `get` would raise on it forever afterwards. Replace is
    atomic on the same filesystem, so a reader sees the old bytes or the new ones.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
