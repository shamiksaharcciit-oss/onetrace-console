"""Ingest one onedoor decision export: the JSONL file `python -m onedoor.export`
writes, plus its `.sha256` sidecar, wrapped in the same kind of archive `/v1/runs`
already accepts.

WHY AN ARCHIVE, NOT A NEW TWO-PART BODY FORMAT
-----------------------------------------------
The work order says: "wrap it in the same kind of archive, or define a two-part body;
choose one and say why." Chosen: the same kind of archive -- a tar, read with
`onetrace_console.ingest.read_tar`, imported and called here unchanged, never copied.
That one function already carries every upload-hardening check that applies to an
archive body (traversal, links/special files, member-count and size limits before any
content read, the `tarfile.data_filter` second layer) -- those arrive for free,
exercised by the SAME code path `/v1/runs` uses, not a parallel reimplementation
of them. A bespoke two-part body (e.g. two `Content-Length`-delimited sections in one
request) would mean re-deriving several of those checks from nothing, for a format
whose only advantage is not being a tar -- not worth it for exactly two named files.
The request body size and timeout limits are already enforced generically in
`serve.py`'s `do_POST`, before any route sees the body at all, archive or not. Refusing
malformed input (422, plain words, nothing stored) and the filter alongside the
explicit checks are what this module adds on top, for the JSONL payload itself.

WHAT "DUPLICATE request_id" MEANS HERE
---------------------------------------
See `tests/fixtures/onedoor/PROVENANCE.md`. onedoor's own `actions_audit` table
carries a `UNIQUE(request_id, kind)` constraint, not a unique `request_id`: an
auto-executed request is legitimately recorded as two rows (`exec_intent` then
`exec_result`) sharing one `request_id`. Refusing on `request_id` alone would refuse
this extension's own fixture, generated from a real, unmodified onedoor run, on its
first legitimate row. The duplicate check below is on the `(request_id, kind)` pair,
matching onedoor's own invariant -- flagged as a reading, not decided quietly.

THE FLOAT CHECK'S SCOPE
------------------------
"A float anywhere is refused, because the export contract has none" is checked
against each row's own top-level JSON values -- the columns `write_export()` itself
guarantees are float-free (it raises `TypeError` on a float column before writing a
single line). Several of those columns (`params_json`, `payload_json`,
`evaluation_trace_json`) are themselves JSON *encoded as a string* -- opaque payload
this extension does not decode, per "fields the extension doesn't know are kept in
storage and not shown." A float inside a caller's own action parameters, nested
inside one of those string columns, is not what onedoor's contract or this check is
about.
"""
from __future__ import annotations

import hashlib
from onetrace_console.bounded_json import TooDeep, load_json_bounded
import json
from dataclasses import asdict, dataclass, field

from onetrace_console.ingest import DeliveryRefused, parse_sums, read_tar
from onetrace_console.store import Store, digest

#: The two files a decision export delivery carries: the export, and its sidecar --
#: identified by suffix, not by a fixed basename, since onedoor's own export naming
#: is not part of this extension's contract.
SIDECAR_SUFFIX = ".sha256"


class DecisionsRejection(Exception):
    """Carried out of `accept_export` so a malformed delivery reads like any other
    refusal. `body` is plain words, never a traceback; nothing is stored on this path.
    """

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail

    @property
    def body(self) -> str:
        return self.detail + "\n"


@dataclass(frozen=True, slots=True)
class DecisionRow:
    """One audit row, exactly as the export delivered it.

    `raw_line` is the row's own line of the JSONL file, verbatim, with no re-encoding
    -- `decision_digest` hashes THIS, not a re-serialization of `fields`, because the
    specified definition is "the sha256 of the canonical JSON of the row, exactly as
    `python -m onedoor.export` writes it": the delivered bytes already are that
    canonical form, and reconstructing it from the parsed dict would risk a
    byte-for-byte disagreement with onedoor's own `json.dumps(..., sort_keys=True,
    separators=(",", ":"))` for no reason -- the exact bytes are already in hand.

    `fields` is DERIVED from `raw_line` when the row is built, never stored or passed in:
    one source of truth, so no page, filter or join can read fields that disagree with the
    line the digest covers. A `raw_line` that does not parse as a JSON object gives empty
    `fields` and a plain-words `unreadable` reason; it is counted and reported by the
    pages, never silently dropped, and never raises here.
    """
    raw_line: str
    fields: dict = field(init=False, repr=False, compare=False)
    unreadable: str | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        why: str | None
        try:
            obj = load_json_bounded(self.raw_line, "the row") if isinstance(self.raw_line, str) else None
            why = None if isinstance(obj, dict) else "not a JSON object"
        except TooDeep:
            obj, why = None, "nested too deeply to read"
        except json.JSONDecodeError as e:
            obj, why = None, f"not valid JSON: {e}"
        object.__setattr__(self, "fields", obj if why is None else {})
        object.__setattr__(self, "unreadable", why)

    @property
    def request_id(self) -> str | None:
        v = self.fields.get("request_id")
        return v if isinstance(v, str) else None

    @property
    def kind(self) -> str | None:
        v = self.fields.get("kind")
        return v if isinstance(v, str) else None

    @property
    def decision(self) -> str | None:
        v = self.fields.get("decision")
        return v if isinstance(v, str) else None

    @property
    def decision_digest(self) -> str:
        line = self.raw_line if isinstance(self.raw_line, str) else ""
        return "sha256:" + hashlib.sha256(line.encode("utf-8")).hexdigest()

    def to_json_obj(self) -> dict:
        return {"raw_line": self.raw_line}

    @staticmethod
    def from_json_obj(d: dict) -> "DecisionRow":
        #: A record written before `fields` was derived still carries a "fields" key, and
        #: re-ingesting the same export never rewrites it: ignored, not trusted.
        return DecisionRow(raw_line=d["raw_line"])


@dataclass(frozen=True, slots=True)
class StoredDecisionExport:
    """One ingested export. `key` is the export's own identity (the sha256 of its raw
    bytes) -- re-ingesting the identical export is acknowledged, not stored again, the
    same rule `/v1/runs` uses for `(run_id, chain_head)`.
    """
    key: str
    export_object: str      # onetrace_console.store object key: the raw bytes, verbatim
    received_at: str
    rows: tuple[DecisionRow, ...]

    def to_json(self) -> str:
        d = {
            "key": self.key,
            "export_object": self.export_object,
            "received_at": self.received_at,
            "rows": [r.to_json_obj() for r in self.rows],
        }
        return json.dumps(d, indent=1, sort_keys=True, ensure_ascii=False) + "\n"

    @staticmethod
    def from_json(text: str) -> "StoredDecisionExport":
        d = load_json_bounded(text, "a stored decision export")
        return StoredDecisionExport(
            key=d["key"],
            export_object=d["export_object"],
            received_at=d["received_at"],
            rows=tuple(DecisionRow.from_json_obj(r) for r in d["rows"]),
        )


@dataclass(frozen=True, slots=True)
class DecisionsAccepted:
    export: StoredDecisionExport
    created: bool
    status: int = 201


def _has_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, list):
        return any(_has_float(v) for v in value)
    if isinstance(value, dict):
        return any(_has_float(v) for v in value.values())
    return False


def _validate_rows(jsonl: bytes, *, limits) -> list[DecisionRow]:
    try:
        text = jsonl.decode("utf-8")
    except UnicodeDecodeError as e:
        raise DecisionsRejection(f"the export is not valid UTF-8: {e}") from None

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]          # the trailing newline every row ends with

    if len(lines) > limits.max_decision_rows:
        raise DecisionsRejection(
            f"the export holds {len(lines)} rows, over the configured "
            f"{limits.max_decision_rows}-row limit")

    rows: list[DecisionRow] = []
    seen: set[tuple[str | None, str | None]] = set()
    for i, line in enumerate(lines):
        if len(line.encode("utf-8")) > limits.max_decision_line_length:
            raise DecisionsRejection(
                f"row {i}: line is over the configured "
                f"{limits.max_decision_line_length}-byte line limit")
        try:
            obj = load_json_bounded(line, f"row {i}")
        except TooDeep:
            raise DecisionsRejection(f"row {i}: nested too deeply to read") from None
        except json.JSONDecodeError as e:
            raise DecisionsRejection(f"row {i}: not valid JSON: {e}") from None
        if not isinstance(obj, dict):
            raise DecisionsRejection(f"row {i}: not a JSON object (got {type(obj).__name__})")
        if _has_float(obj):
            raise DecisionsRejection(f"row {i}: carries a float; the export contract has none")

        row = DecisionRow(raw_line=line)
        pair = (row.request_id, row.kind)
        if pair in seen:
            raise DecisionsRejection(
                f"row {i}: duplicate (request_id, kind) = {pair!r} within one export")
        seen.add(pair)
        rows.append(row)

    if not rows:
        raise DecisionsRejection("the export carries no rows")
    return rows


def accept_export(data: bytes, store: Store, *, received_at: str | None = None,
                   limits=None) -> DecisionsAccepted:
    """Validate a decision-export delivery completely, then store it completely, or
    store nothing. Raises `DecisionsRejection` -- never returns one -- so the route
    handler's `except` maps it to a 422 the same way `ingest.Rejection` is handled,
    without a shared exception type between the two (they refuse for unrelated
    reasons and this keeps that visibly separate).
    """
    from datetime import datetime, timezone

    try:
        files = read_tar(data, limits=limits)
    except DeliveryRefused as e:
        raise DecisionsRejection("; ".join(e.rows)) from None

    sidecar_names = [n for n in files if n.endswith(SIDECAR_SUFFIX)]
    if len(sidecar_names) != 1:
        raise DecisionsRejection(
            f"the delivery must carry exactly one {SIDECAR_SUFFIX} sidecar, found "
            f"{len(sidecar_names)}")
    sidecar_name = sidecar_names[0]
    payload_names = [n for n in files if n != sidecar_name]
    if len(payload_names) != 1:
        raise DecisionsRejection(
            f"the delivery must carry exactly one export file beside its sidecar, "
            f"found {len(payload_names)}")
    payload_name = payload_names[0]

    try:
        sums = parse_sums(files[sidecar_name], name=sidecar_name)
    except DeliveryRefused as e:
        raise DecisionsRejection("; ".join(e.rows)) from None
    if payload_name not in sums:
        raise DecisionsRejection(
            f"the sidecar names {sorted(sums)}, not {payload_name!r}: checksum does not "
            f"cover the delivered file")
    #: Both ways, as a run delivery checks (the pin re-check, note 1): the side-car names the
    #: delivered file and nothing else. A second entry -- `./x`, another case, another file -- is a
    #: second digest no check would read, so it is refused, by name.
    others = sorted(set(sums) - {payload_name})
    if others:
        raise DecisionsRejection(
            f"{sidecar_name} names {others!r} beside {payload_name!r}: a side-car names the "
            f"delivered file and nothing else")
    jsonl = files[payload_name]
    got = digest(jsonl)
    want = sums[payload_name]
    if got != want:
        raise DecisionsRejection(
            f"{payload_name}: sha256 {got} does not match the sidecar's {want}")

    rows = _validate_rows(jsonl, limits=(limits or _default_limits()))

    key = digest(jsonl)
    if store.has_decision_export(key):
        #: Already held. What is reported is the delivery just received -- its own key and
        #: rows -- never the stored record, which may have been edited since. The record
        #: is not rewritten: an edited one keeps reading "couldn't check".
        return DecisionsAccepted(
            export=StoredDecisionExport(key=key, export_object=key, received_at="",
                                        rows=tuple(rows)),
            created=False, status=200)

    export_object = store.put(jsonl)
    export = StoredDecisionExport(
        key=key,
        export_object=export_object,
        received_at=received_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        rows=tuple(rows),
    )
    store.put_decision_export(export)
    return DecisionsAccepted(export=export, created=True)


def _default_limits():
    from onetrace_console.config import Config
    return Config()


# ------------------------------------------------ the delivery decides

#: The fixed words for a row whose stored copy differs from what was delivered.
CHANGED = "stored record changed since delivery"
#: Not fixed yet: the delivery itself cannot be read back, so no stored row can be checked
#: against it. Reported as "couldn't check" with its own reason, never guessed past.
DELIVERY_MISSING = "the original delivery could not be read"


@dataclass(frozen=True, slots=True)
class CheckedRow:
    """One row position of one export, checked against the original delivery.

    `delivered` is the row as the digest-checked delivery holds it, the only row whose
    values may ever be shown, and only when `problem` is None. `problem` is None when the
    stored line equals the delivered one; otherwise it says why the row cannot be checked.
    """
    export: StoredDecisionExport
    index: int
    delivered: DecisionRow | None
    problem: str | None

    @property
    def name(self) -> str:
        """Which row: its export and position, and its request id from the delivery."""
        rid = self.delivered.request_id if self.delivered is not None else None
        return (f"export {self.export.key[:12]}…, row {self.index}"
                + (f", request {rid}" if rid else ""))

    @property
    def couldnt_check(self) -> str | None:
        return None if self.problem is None else f"couldn't check: {self.problem} ({self.name})"


def delivered_lines(key: object, store: Store) -> list[str] | None:
    """The lines of the delivery stored under `key`, split exactly as ingest split them,
    or None when there is no such delivery or it cannot be read: missing, bytes moved
    (`Store.get` refuses both), not UTF-8, or a key that is not a content address."""
    from onetrace_console.store import StoreError
    try:
        text = store.get(key).decode("utf-8")
    except (StoreError, UnicodeDecodeError, TypeError, ValueError):
        return None
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines


def check_export(export: StoredDecisionExport, store: Store, *,
                 filed_as: str | None = None) -> tuple[CheckedRow, ...]:
    """Every row position of `export`, each checked against its delivery.

    `filed_as` is the record's filename stem: the delivery's content address, and the only
    part of a stored record that says which delivery it is. The record's own `key` and
    `export_object` are editable fields, so the delivery is read by `filed_as` and a record
    whose fields disagree with it has been changed as a whole -- every position `CHANGED`,
    each named by `filed_as`, never by the edited key. (`filed_as=None` checks against the
    record's own `export_object`: for a record the caller already trusts, as the store's
    own tests do.)

    A stored record holding a different number of rows than its delivery has been changed
    as a whole too, and a position either side lacks is still reported, never dropped.
    """
    anchor = export.export_object if filed_as is None else filed_as
    intact = filed_as is None or (export.key == filed_as and export.export_object == filed_as)
    if not intact:
        export = StoredDecisionExport(key=filed_as, export_object=filed_as, received_at="",
                                      rows=export.rows)
    lines = delivered_lines(anchor, store)
    if lines is None:
        return tuple(CheckedRow(export, i, None, DELIVERY_MISSING)
                     for i in range(max(len(export.rows), 1)))
    same_count = len(lines) == len(export.rows)
    out = []
    for i in range(max(len(lines), len(export.rows))):
        delivered = DecisionRow(raw_line=lines[i]) if i < len(lines) else None
        stored = export.rows[i].raw_line if i < len(export.rows) else None
        ok = intact and same_count and delivered is not None and stored == lines[i]
        out.append(CheckedRow(export, i, delivered, None if ok else CHANGED))
    return tuple(out)


def check_store(store: Store) -> tuple[CheckedRow, ...]:
    """Every row position of every stored decision record, each checked against the
    delivery its FILENAME names. A record that cannot even be read as one (not UTF-8, not
    JSON, a field missing or of the wrong type) has been changed as a whole: its
    delivery's rows are all reported `CHANGED`, and nothing raises."""
    out: list[CheckedRow] = []
    for stem, raw in store.decision_export_records():
        try:
            export = StoredDecisionExport.from_json(raw.decode("utf-8"))
            if not isinstance(export.rows, tuple):
                raise TypeError("rows")
        except Exception:
            export = None
        if export is None:
            broken = StoredDecisionExport(key=stem, export_object="", received_at="", rows=())
            out.extend(check_export(broken, store, filed_as=stem))
        else:
            out.extend(check_export(export, store, filed_as=stem))
    return tuple(out)
