"""Ingest: a delivered run is accepted whole or rejected whole.

    Server checks before storing anything: every file in the tar matches
    `SHA256SUMS`; the manifest's `chain_head` equals the header's; the `format` is one
    the store implements (R16). Any failure -> `422` with the row that failed, in the
    verifier's own words. Nothing partial is ever stored.
                                        -- the store and console design note, §1

WHOSE WORDS THESE ARE
---------------------
The note says "in the verifier's own words", and for these three checks that is not
available and is not claimed. The sums check, the `chain_head` agreement and the
format-known check all happen **before** anything is stored and therefore before the
verifier has been near the run; the verifier's words arrive from the check runner, after.

So the rows below are the **store's** words, in the verifier's row *grammar* so that one
parser reads both, and each one names `delivery` as its subject so a reader is never
misled about who found it. Recorded in DESIGN_GAPS.md rather than papered over: dressing
our sentence as the verifier's would be the exact move this programme exists to refuse.

THE ROW GRAMMAR
---------------
`[FAIL   ] <subject>: <check> -- <detail>`, seven characters inside the brackets, as
`verify.py` writes it. The viewer's strict reader parses it; a row that does not fit the
grammar would make the report unreadable rather than be quietly displayed.
"""
from __future__ import annotations

import errno
from onetrace_console.viewer.depth import MAX_JSON_DEPTH

from onetrace_console.bounded_json import TooDeep, ingest_refusal, load_json_bounded
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

from onetrace_console.preview import PREVIEW_NOT_INGESTED, is_format_refusal, preview_not_run_row
from onetrace_console.staging import (StagingError, ask_the_verifier, staging,
                                      write_delivery)
from onetrace_console.store import SameFileError, StoredRun, Store, StoreError, digest, run_key

#: R16: a format the store implements. Not a guess -- these are the two strings the
#: emitter writes, measured from a run the SDK produced, and anything else is refused
#: rather than read hopefully. A new format is a decision, not a surprise.
#: Both minors of major 0, because both are real. Measured across the SDK's own bench at
#: pin `4c11f0e`: 13 runs declare `0.0-preview` and 9 declare `0.1`. The reference verifier
#: says of itself *"this verifier implements major 0"*, and reads both -- on a preview run it
#: passes and notes `draft-00 checks not performed: record format is stage-receipt/0.0-preview
#: (Appendix C)`, which is a NOT-RUN with a reason and not a refusal.
#:
#: Widened deliberately and recorded in DESIGN_GAPS.md, not drifted into: a store
#: that refused the format most of the SDK's own bench is written in would have refused the
#: only pair that differs by converter version, which is what step 1's second check is about.
#: R16 is unharmed -- an unknown major is still refused, now in the verifier's own words.
#:
#: 0.2 is accepted because it is what the pinned SDK writes, and the pinned
#: verifier reads it (major 0). Until then this store refused every run the SDK it pins makes.
#: Files a 0.2 run carries beside its chain (`anchors/<n>.json`, `signatures/<n>.json` from
#: 0.2.0) are accepted and kept like any listed file and are not part of the chain.
MANIFEST_FORMATS = ("stage-receipt-chain/0.2", "stage-receipt-chain/0.1",
                    "stage-receipt-chain/0.0-preview")
RECEIPT_FORMATS = ("stage-receipt/0.2", "stage-receipt/0.1", "stage-receipt/0.0-preview")

SUMS_NAME = "SHA256SUMS"
MANIFEST_NAME = "MANIFEST.json"

#: The design note's flag. A finding about the delivery, never a verdict about the record.
RUN_ID_REUSED = "run_id reused"

#: The verifier's own row for the `chain_head` check -- one of the three pre-store checks
#: run in staging, and the ONLY one of the three the verifier has words for. Measured with
#: the verifier the pinned distribution ships: a wrong `chain_head` gives exit 1 and this
#: row; an unknown manifest format gives exit 0 and no row at all.
#:
#: Matched as a substring of the row rather than reconstructed, so this holds the
#: verifier's wording and does not restate it.
CHAIN_HEAD_ROW = "manifest: chain head matches the last receipt"


class DeliveryRefused(Exception):
    """Carried out of the tar reader so a malformed archive reads like any other refusal."""

    def __init__(self, rows: list[str]):
        super().__init__("; ".join(rows))
        self.rows = rows


#: A held run the store is missing an object for, delivered again.
HELD_MISSING = ("Not stored: this run is already held, but the console is missing {objects} for "
                "it. A held record is never repaired. Remove the held run, then deliver it again.")


def row(subject: str, check: str, detail: str = "", result: str = "FAIL") -> str:
    return f"[{result:<7}] {subject}: {check}" + (f" -- {detail}" if detail else "")


@dataclass(frozen=True, slots=True)
class Rejection:
    """422 for a DAMAGED UPLOAD. Nothing was stored, and staging is gone.

    A run whose checks contradict is still stored and recorded as contradicting: a 422 is
    for damaged uploads only, never for a verdict.

    `body` is what a client gets back: **the verifier's own message, word for word**, when
    the verifier has one for what went wrong. `rows` is the same failure as lines, for a
    caller that wants them structured; `from_verifier` says whose words `body` is, because
    a reader must never have to guess that.
    """
    rows: tuple[str, ...]
    body: str = ""
    from_verifier: bool = False
    status: int = 422


@dataclass(frozen=True, slots=True)
class Accepted:
    """201, or 200 for a delivery that was already held.

    `created` is False when the identity `(run_id, chain_head)` was already stored: the
    note says a repeat delivery is "acknowledged and not stored again".
    """
    run: StoredRun
    created: bool
    status: int = 201


#: Refused unconditionally -- not "if the target escapes",
#: which is `tarfile.data_filter`'s own, narrower rule (see below), but simply "this type
#: of member is not a run".
def _is_link_or_special(member: tarfile.TarInfo) -> bool:
    return member.issym() or member.islnk() or member.isdev() or member.isfifo()


#: A drive letter is not absolute to `PurePosixPath` or to `os.path.isabs` on a POSIX host
#: (this container's own), so it is its own explicit check, item 1's third named case.
#: A literal backslash is refused outright for the same reason: `PurePosixPath` does not
#: treat it as a separator, so `"..\\..\\evil"` has no `..` **part** to catch even though
#: it is a traversal attempt spelled the Windows way.
_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")


def _unsafe_path(name: str) -> str | None:
    """Why a member's path is refused, or `None` if it is not."""
    if "\\" in name:
        return "contains a backslash"
    if _DRIVE_LETTER.match(name):
        return "starts with a drive letter"
    p = PurePosixPath(name)
    if p.is_absolute():
        return "is an absolute path"
    if ".." in p.parts:
        return "contains '..'"
    return None


def same_file(name: str) -> str:
    """What `name` resolves to on this host, for comparing names: `.` and `..` resolved, and
    case-folded on Windows. Names were once compared as written, so one file spelled two ways
    passed every comparison as two files."""
    return os.path.normcase(os.path.normpath(name))


#: The parts of a name Windows cannot hold: its device names (with or without an extension --
#: `notes/NUL` was written to the null device, and the verifier never saw it), its reserved
#: characters and the control characters, and a trailing dot or space, which it drops.
_WINDOWS_DEVICES = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
                             | {f"{d}{n}" for d in ("COM", "LPT")
                                for n in "123456789¹²³"})
_WINDOWS_RESERVED = re.compile(r'[<>:"|?*\x00-\x1f]')
#: The 8.3 short-name shape: `~` and digits ending the name before its extension, as in
#: `01-ZET~1.JSO` or `RECEIP~1`. Windows answers to it for a longer name in the same folder, and
#: a member so named was written over the file it aliases.
_WINDOWS_SHORT_NAME = re.compile(r"~[0-9]+(\.[^.]*)?$")

#: The longest name one part of a path may be, on every host this runs on.
NAME_MAX = 255


def _name_length(part: str) -> int:
    """A name's length as this host counts it: UTF-16 units on Windows, UTF-8 bytes elsewhere.
    `surrogatepass`, because a member name that is not UTF-8 arrives with its bytes escaped."""
    if os.name == "nt":
        return len(part.encode("utf-16-le", "surrogatepass")) // 2
    return len(part.encode("utf-8", "surrogatepass"))


def _windows_path_room() -> int:
    """How long a member's path may be on Windows: MAX_PATH (259 characters and its NUL), less
    the temp folder and the deepest folder this console writes a run under there (staging's
    `onetrace-staging-XXXXXXXX\\run\\`, and a list's `onetrace-list-XXXXXXXX\\run-NNNNN\\`),
    with room to spare."""
    return 259 - len(os.path.abspath(tempfile.gettempdir())) - 48


def _unholdable(name: str) -> str | None:
    """Why this host cannot hold a member's name as a file, or None if it can.

    Without this, on Windows `notes/a:b.txt` answered 500, and names it cannot hold answered 422
    as "the delivery can be examined", outside the 422 set. A delivery whose names cannot be
    written here cannot be read as a run here: that is the set's (b) (see `accept`), said in
    words.
    """
    #: `..` is a traversal, not a name: `_unsafe_path` refuses it, in its own words.
    parts = tuple(p for p in PurePosixPath(name).parts if p != "..")
    if any(_name_length(part) > NAME_MAX for part in parts):
        return f"has a part longer than the {NAME_MAX} characters a name may be"
    if os.name != "nt":
        return None
    for part in parts:
        bad = _WINDOWS_RESERVED.search(part)
        if bad:
            return f"holds {bad.group(0)!r}, which is not allowed in a name on this host"
        if _WINDOWS_SHORT_NAME.search(part):
            return (f"has the part {part!r} in the 8.3 short-name shape, which this host may "
                    f"read as another file's name")
        if part.endswith((".", " ")):
            return "has a part ending in a dot or a space, which this host drops"
        if part.split(".")[0].rstrip(" ").upper() in _WINDOWS_DEVICES:
            return f"names the device {part.split('.')[0]!r} on this host, not a file"
    if len(name) > _windows_path_room():
        return f"is longer than the {_windows_path_room()} characters a path may be here"
    return None


#: A staging write this host refused for the name itself, rather than for want of room or
#: permission: invalid argument, name too long, and Windows's own invalid-name codes.
_NAME_ERRNOS = frozenset({errno.EINVAL, errno.ENAMETOOLONG})
_NAME_WINERRORS = frozenset({123, 161, 206})


def _refused_for_its_name(e: OSError) -> bool:
    return e.errno in _NAME_ERRNOS or getattr(e, "winerror", None) in _NAME_WINERRORS


def read_tar(data: bytes, *, limits=None) -> dict[str, bytes]:
    """The archive's regular files, by POSIX path, in archive order.

    Nothing is extracted to disk at all here: the files are read into memory (bounded --
    see below) so that every check can run before anything is written.

    HARDENING
    ---------
    Every check here runs on the member's **header** -- name, type, declared size --
    before its content is read. A member that fails any check is refused and its bytes
    are never read, which is what "refused before reading it all" means at this layer
    (the request body as a whole is bounded earlier, in `serve.py`, before this function
    is ever called).

    **Two independent path/type checks, not one.** `_unsafe_path` and `_is_link_or_
    special` are this module's own, explicit rules (the traversal cases and the
    link/special-file cases). `tarfile.data_filter` is additionally applied to every
    member that passes both -- the standard library's own safe-extraction filter, which
    independently re-derives the same destination-containment property by resolving the
    real path rather than pattern-matching a string, and which also rejects a symlink or
    hardlink whose *target* escapes even when the member's own name is safe. So the filter
    **and** the explicit checks both run, not either alone.
    """
    from onetrace_console.config import Config

    limits = limits or Config()
    rows: list[str] = []
    out: dict[str, bytes] = {}
    first_named: dict[str, str] = {}
    total_size = 0
    member_count = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
            for member in tar.getmembers():
                member_count += 1
                if member_count > limits.max_members:
                    raise DeliveryRefused([row(
                        "delivery", "the archive holds no more than the configured member limit",
                        f"more than {limits.max_members} members")])

                reason = _unsafe_path(member.name)
                if reason is not None:
                    rows.append(row("delivery", "archive paths stay inside the run",
                                    f"{member.name!r} {reason}"))
                    continue
                if member.isdir():
                    continue
                reason = _unholdable(member.name)
                if reason is not None:
                    rows.append(row("delivery", "each archive path is a name this host can hold",
                                    f"{member.name!r} {reason}"))
                    continue
                if _is_link_or_special(member):
                    rows.append(row("delivery", "archive holds only regular files",
                                    f"{member.name!r} is a "
                                    f"{'symlink' if member.issym() else 'hardlink' if member.islnk() else 'device file' if member.isdev() else 'FIFO'}, "
                                    f"not a regular file"))
                    continue
                if not member.isfile():
                    rows.append(row("delivery", "archive holds only regular files",
                                    f"{member.name!r} is not a regular file"))
                    continue

                #: Size, checked from the header -- before `extractfile().read()` -- both
                #: per member and as a running total, so an archive whose members are
                #: individually small but numerous (or one huge member) is refused before
                #: its bytes are read either way. This is the archive-bomb guard.
                if member.size > limits.max_member_size:
                    raise DeliveryRefused([row(
                        "delivery", "each member stays inside the configured size limit",
                        f"{member.name!r} declares {member.size} bytes, "
                        f"over the {limits.max_member_size}-byte limit")])
                if total_size + member.size > limits.max_total_extracted_size:
                    raise DeliveryRefused([row(
                        "delivery",
                        "the archive's total extracted size stays inside the configured limit",
                        f"over {limits.max_total_extracted_size} bytes once "
                        f"{member.name!r} is included")])

                #: The standard library's own filter, in addition to the two explicit
                #: checks above -- re-derives path safety by resolving the real
                #: destination rather than matching the name as a string, and is the only
                #: one of the three that also checks a link's OWN target.
                try:
                    tarfile.data_filter(member, "/run")
                except (tarfile.FilterError, ValueError) as e:
                    #: ValueError too: on Windows the filter's `ntpath.commonpath` raises it for
                    #: `notes/a:b.txt`, and the upload answered 500.
                    rows.append(row("delivery", "the archive passes the safe-extraction filter",
                                    f"{member.name!r}: {type(e).__name__}: {e}"))
                    continue

                handle = tar.extractfile(member)
                if handle is None:                       # pragma: no cover - defensive
                    rows.append(row("delivery", "every file in the archive is readable",
                                    f"{member.name!r} could not be read"))
                    continue
                name = PurePosixPath(member.name).as_posix()
                #: Compared as this host resolves them: on Windows `notes/A.txt`
                #: and `notes/a.txt` are one file, and staging wrote the second over the first.
                if same_file(name) in first_named:
                    first = first_named[same_file(name)]
                    rows.append(row("delivery", "each path appears once",
                                    f"{name!r} appears more than once" if first == name else
                                    f"{name!r} names the same file as {first!r} on this host"))
                    continue
                first_named[same_file(name)] = name
                blob = handle.read()
                total_size += len(blob)
                out[name] = blob
    except tarfile.TarError as e:
        raise DeliveryRefused([row("delivery", "the archive can be read",
                                   f"{type(e).__name__}: {e}")]) from None
    if rows:
        raise DeliveryRefused(rows)
    if not out:
        raise DeliveryRefused([row("delivery", "the archive holds a run",
                                   "the archive is empty")])
    return out


#: One line as `sha256sum` writes it: 64 lower-case hex, a space, the mode -- a space for text,
#: `*` for binary -- and the path. Git for Windows writes the binary form by default. The mode is
#: never part of the path, and a path cannot itself begin with a second `*`.
_SUMS_LINE = re.compile(r"(?P<want>[0-9a-f]{64}) [ *](?P<path>[^*].*)")


def parse_sums(text: bytes, *, name: str = SUMS_NAME) -> dict[str, str]:
    """`<sha256>  <path>` or `<sha256> *<path>` per line: the two forms `sha256sum` writes.

    `name` is the sums file's own name, for the rows a refusal gives: a run's `SHA256SUMS`,
    or the onedoor side-car's `<export>.sha256` (the pin re-check, note 4).
    """
    sums: dict[str, str] = {}
    #: Which line first named each path: a path listed twice, with the same
    #: digest or another, is refused naming both lines. Last-line-wins ignored a digest the sender
    #: wrote, and two digests for one path is a contradiction in the delivery.
    first_line: dict[str, str] = {}
    for line in text.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        m = _SUMS_LINE.fullmatch(line)
        if m is None:
            raise DeliveryRefused([row(name, "each line is a digest and a path",
                                       f"cannot read {line!r}")])
        path = m["path"].replace("\\", "/")
        if path in first_line:
            raise DeliveryRefused([row(name, "each path is listed once",
                                       f"{path!r} is listed twice: {first_line[path]!r} and "
                                       f"{line!r}")])
        first_line[path] = line
        sums[path] = m["want"]
    if not sums:
        raise DeliveryRefused([row(name, "the sums file lists the run's files",
                                   "it lists nothing")])
    return sums


def check_sums(files: dict[str, bytes]) -> list[str]:
    """Every file matches its sum, and the sums file covers every file. Both directions.

    A one-directional check is how a hole gets in: covering only the listed files lets an
    extra file ride along unlisted, and covering only the present files lets a listed file
    go missing. F6 on the canary channel was exactly this, in a coverage scan.
    """
    if SUMS_NAME not in files:
        return [row("delivery", f"the delivery carries {SUMS_NAME}", "it is not in the archive")]
    sums = parse_sums(files[SUMS_NAME])
    rows: list[str] = []
    payload = {p: b for p, b in files.items() if p != SUMS_NAME}

    for path, want in sorted(sums.items()):
        if path not in payload:
            rows.append(row(path, "the file the sums list is present", "it is not in the archive"))
            continue
        got = digest(payload[path])
        if got != want:
            rows.append(row(path, "bytes match the sums file",
                            f"sha256 {got} does not match {want}"))
    for path in sorted(set(payload) - set(sums)):
        rows.append(row(path, f"the file is listed in {SUMS_NAME}",
                        "it is present but unlisted"))
    return rows


def _manifest(files: dict[str, bytes]) -> dict:
    if MANIFEST_NAME not in files:
        raise DeliveryRefused([row("delivery", f"the delivery carries {MANIFEST_NAME}",
                                   "it is not in the archive")])
    try:
        obj = load_json_bounded(files[MANIFEST_NAME].decode("utf-8"), MANIFEST_NAME)
    except TooDeep:
        #: The run is refused, in the fixed words, the number from the constant.
        raise DeliveryRefused([row(MANIFEST_NAME, f"nested at most {MAX_JSON_DEPTH} levels deep",
                                   ingest_refusal(MANIFEST_NAME))]) from None
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as e:
        #: RecursionError too: a manifest nested past what JSON can read cannot be parsed
        #: (the 422 set's (b)), and answered 500 (the second confirmation review, N6).
        raise DeliveryRefused([row(MANIFEST_NAME, "the manifest is readable JSON",
                                   f"{type(e).__name__}: {e}")]) from None
    if not isinstance(obj, dict):
        raise DeliveryRefused([row(MANIFEST_NAME, "the manifest is an object",
                                   f"it is a {type(obj).__name__}")])
    #: A lone surrogate escape in the manifest's identity -- valid JSON syntax, not text -- is
    #: refused: an identity must be well formed, and it answered 500 (the third confirmation
    #: review, NEW-2). Only there: anywhere else in the record, a surrogate
    #: is stored as delivered and shown escaped.
    for field in ("run_id", "chain_head"):
        value = obj.get(field)
        if isinstance(value, str) and not _is_text(value):
            raise DeliveryRefused([row(MANIFEST_NAME, "the manifest's text is valid UTF-8",
                                       f"its {field} holds a lone surrogate escape")])
    return obj


def delivered_and_retries(attempts: list[tuple], declared: set) -> dict:
    """The declared stages with at least one receipt -- each stage counted
    once, however many receipts it has, so a retry can never stand in for a stage that is
    missing -- and the retries: a receipt of a stage after one of that stage's receipts failed
    with an error. Two instances of one stage that both succeed are not a retry."""
    failed: set = set()
    retries = 0
    for name, outcome, *_ in attempts:
        if name in failed:
            retries += 1
        if outcome == "error":
            failed.add(name)
    delivered = len({name for name, *_ in attempts if name in declared})
    return {"delivered_stages": delivered, "retries": retries}


def last_attempt_failed(attempts: list[tuple], declared: list) -> list[list[str]]:
    """Each declared stage whose LAST recorded attempt failed with an error, as
    [stage, error type], in the declared order. `attempts` is (stage name, outcome class, outcome
    status) in the chain's order; the SDK writes an error's status as the exception's type.

    The same definition of failure as the retry rule above: an outcome of class `error`. A stage
    retried until it succeeded is not counted, and neither is one whose last outcome is not an
    error -- "declined" (the SDK's `refused`) is a stage's own contract, not a failure. A stage
    with no attempt is missing, which rung 3 and the delivered count already state."""
    last: dict = {}
    for name, outcome, *rest in attempts:
        last[name] = (outcome, rest[0] if rest else "")
    return [[name, last[name][1] or ""] for name in dict.fromkeys(declared)
            if name in last and last[name][0] == "error"]


def _declared_by(receipt: dict, declared: list[str], seen: set[str]) -> None:
    """Add the stages a receipt declares to `declared`, in its order, each once.

    Only strings: one that is not makes the viewer refuse the record. A name holding a lone
    surrogate is shown escaped and never makes a run unshowable, so it is indexed in
    the escaped form a page shows it in: the store's records are UTF-8."""
    from onetrace_console.viewer.page import display
    coverage = receipt.get("coverage")
    names = coverage.get("declared_stages") if isinstance(coverage, dict) else None
    for name in (names if isinstance(names, list) else ()):
        if isinstance(name, str) and name not in seen:
            seen.add(name)
            declared.append(name if _is_text(name) else display(name))


def _is_text(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _member_named(e: OSError, run_folder) -> str:
    """The delivery's own path for the file a staging write failed on, never the server's."""
    from pathlib import Path
    try:
        return repr(Path(e.filename).relative_to(run_folder).as_posix())
    except (TypeError, ValueError):
        return "one of its names"


def accept(data: bytes, store: Store, *, headers: dict[str, str] | None = None,
           received_at: str | None = None, limits=None) -> Accepted | Rejection:
    """Validate a delivery completely, then store it completely, or store nothing.

    `headers` may carry `run_id`, `chain_head` and `format`. The design note has the
    server compare the manifest's `chain_head` against the header's. Headers are optional
    here and **checked when present**: a delivery that supplies one and disagrees with its
    own manifest is refused, and a delivery that supplies none is read from the manifest.
    Requiring them would reject a valid run for want of a duplicate of what it contains;
    ignoring them would make a header a decoration.

    `limits` is an `onetrace_console.config.Config` (or `None` for its defaults) --
    `read_tar`'s own upload-hardening limits.
    """
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    try:
        files = read_tar(data, limits=limits)
        rows = check_sums(files)
        manifest = _manifest(files)
    except DeliveryRefused as e:
        return Rejection(tuple(e.rows), body="\n".join(e.rows) + "\n")

    fmt = manifest.get("format")
    if fmt not in MANIFEST_FORMATS:
        rows.append(row(MANIFEST_NAME, "format is one this store implements",
                        f"{fmt!r} is not among {list(MANIFEST_FORMATS)}"))
    #: `run_id` and `chain_head` ABSENT is case (b), "the format cannot be parsed": the
    #: declared format requires both, and a manifest without them cannot be read as that
    #: format at all -- there is no identity to store the run under. That is a different
    #: thing from `chain_head` being present and WRONG, which is a verdict and is stored.
    run_id = manifest.get("run_id")
    chain_head = manifest.get("chain_head")
    if not isinstance(run_id, str) or not run_id:
        rows.append(row(MANIFEST_NAME, "the format's required run_id can be read",
                        f"it carries {run_id!r}"))
    if not isinstance(chain_head, str) or not chain_head:
        rows.append(row(MANIFEST_NAME, "the format's required chain_head can be read",
                        f"it carries {chain_head!r}"))

    chain = manifest.get("chain")

    #: **`chain_head` is deliberately NOT checked here any more.** It used to be, against the
    #: chain's own last link, and that check was right about the fact and wrong about the
    #: consequence: a manifest whose `chain_head` does not match its last receipt has
    #: arrived exactly as its sender made it and contradicts *itself*. That is why it is
    #: outside the 422 set: the verifier reports it after storing and the run is recorded
    #: as contradicting. Nothing is lost -- the verifier has
    #: its own row for it, `CHAIN_HEAD_ROW`, and `tests/test_staging.py` pins that the
    #: stored verdict says so.

    #: A header that disagrees with the manifest is **not** damage either, and is not in the
    #: two-item set. It is recorded as a flag on the stored run instead of being dropped: a
    #: delivery whose envelope contradicts its contents is worth knowing about, and silently
    #: ignoring a header would make it a decoration.
    header_disagreements = tuple(
        f"header {name}={headers[name]!r} disagrees with the manifest's {value!r}"
        for name, value in (("run_id", run_id), ("chain_head", chain_head), ("format", fmt))
        if headers.get(name) is not None and headers[name] != value)

    #: Only the files the manifest's `chain` names are receipts. Checking every `*.json`
    #: in the delivery instead would reject a run folder that carries a verb report
    #: beside its receipts -- `localize/localize.json` is `onetrace-report/0.1` and is
    #: not a receipt and was never claimed to be. Found by pointing this at a real run
    #: folder, which is the only reason it is not still here.
    #:
    #: Looked up as this host resolves the name, and each file read once: the
    #: chain's `receipts/./02-alpha.json` was not found as written, so its format went unread
    #: while the verifier and the viewer read the file it names; and a chain naming one large
    #: receipt many times was parsed once per naming.
    #:
    #: The stages the run declares are read here too, from the receipts' own
    #: `coverage.declared_stages` -- as the viewer's `missing_stages` reads them, in order, each
    #: once. They were once taken from the chain when the manifest declared none, and the
    #: pinned SDK's manifest never does, so every run it made "declared" what it recorded.
    by_file = {same_file(p): p for p in files}
    read: set[str] = set()
    receipts: set[str] = set()
    declared: list[str] = []
    seen_declared: set[str] = set()
    attempts: list[tuple] = []  # (stage name, outcome class) of each receipt, in chain order
    for entry in (chain if isinstance(chain, list) else []):
        if not isinstance(entry, dict):
            continue
        path = entry.get("file")
        held = by_file.get(same_file(path)) if isinstance(path, str) else None
        if held is None or held in read:
            continue          # a missing chain file is the verifier's finding, after storing
        read.add(held)
        try:
            receipt = load_json_bounded(files[held].decode("utf-8"), held)
        except TooDeep:
            #: Not skipped like an unreadable receipt -- the run is refused.
            rows.append(row(held, f"nested at most {MAX_JSON_DEPTH} levels deep", ingest_refusal(held)))
            continue
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            continue          # the verifier's business, and it will say so after storing
        if not isinstance(receipt, dict):
            continue
        receipt_format = receipt.get("format")
        if receipt_format is not None and receipt_format not in RECEIPT_FORMATS:
            rows.append(row(held, "format is one this store implements",
                            f"{receipt_format!r} is not among {list(RECEIPT_FORMATS)}"))
        if receipt_format in RECEIPT_FORMATS:
            #: Delivered: a file the chain names that is a receipt (otherwise `notes.txt` and
            #: `SHA256SUMS` named in the chain read "3 of 3 delivered").
            receipts.add(held)
            stage, outcome = receipt.get("stage"), receipt.get("outcome")
            attempts.append((stage.get("name") if isinstance(stage, dict) else None,
                             outcome.get("class") if isinstance(outcome, dict) else None))
        _declared_by(receipt, declared, seen_declared)

    #: The three pre-store checks run in a scratch
    #: staging area, and a refusal returns THE VERIFIER'S OWN MESSAGE word for word.
    #:
    #: Staging is entered whether or not our own checks already found something, because
    #: the verifier's words are what the client is owed and only the verifier can produce
    #: them. Measured, on this fixture, with the verifier the pinned distribution ships:
    #:
    #:   chain_head wrong        -> exit 1, "[FAIL   ] manifest: chain head matches the
    #:                              last receipt"
    #:   one receipt byte moved  -> exit 1, "…: digest matches the manifest" and
    #:                              "…: chain link -- expected … found …"
    #:   unknown manifest format -> exit 0, AND NO ROW AT ALL
    #:
    #: The last one is why `from_verifier` exists. The reference verifier does not check a
    #: manifest's format, so for an R16 refusal there is no verifier message to return and
    #: the body is this store's words, saying so. Reported rather than papered over: a 422
    #: that claimed to be the verifier's sentence when it was ours would be undetectable
    #: from outside, which is the whole reason a refusal carries the verifier's.
    said = None
    try:
        with staging() as scratch:
            try:
                folder = write_delivery(files, scratch / "run")
                said = ask_the_verifier(folder)
            except subprocess.TimeoutExpired:
                #: A verifier that did not finish is neither damage nor an unknown format, so
                #: it is not in the 422 set (the third confirmation review, NEW-5): the
                #: delivery is stored, and its own check says what it can.
                said = None
            except SameFileError as e:
                #: A second member reaching a file another already wrote, by a name the checks
                #: above did not foresee: written over, it recorded an altered receipt as holding
                #: The set's (b), as a name appearing twice is.
                rows.append(row("delivery", "each path appears once", str(e)))
            except (StagingError, OSError, subprocess.SubprocessError) as e:
                if isinstance(e, OSError) and _refused_for_its_name(e):
                    #: A name this host would not write, that `_unholdable` did not foresee:
                    #: the set's (b), as there, named by the delivery's own path.
                    rows.append(row("delivery", "each archive path is a name this host can hold",
                                    f"{_member_named(e, scratch / 'run')}: {e.strerror or e}"))
                else:
                    #: Named without the server's own paths (the third review, NEW-12).
                    why = e.strerror if isinstance(e, OSError) and e.strerror else e
                    rows.append(row("delivery", "the delivery can be examined",
                                    f"{type(e).__name__}: {why}"))
    except StagingError:
        #: The staging area could not be deleted afterwards. Raised past ingest, it answered 500
        #: naming the server's temp path. Logged for the operator, without
        #: the path; what the delivery was found to be stands.
        print("ingest: a staging area could not be deleted after an upload; look for a "
              "leftover onetrace staging folder in this host's temp folder", file=sys.stderr)
    # Staging is gone by here, on every path, accepted or rejected, or the log says it is not.

    #: **The 422 set is exactly two things**, and `chain_head` is not one of them:
    #:
    #:     (a) any file fails its sum or is missing from `SHA256SUMS`;
    #:     (b) the format cannot be parsed or is unknown.
    #:
    #: **Damage means the delivery does not match its own sums.** A `chain_head` mismatch
    #: under honest sums is not damage: the delivery arrived exactly as its sender made it,
    #: and what it says contradicts itself. That is a verdict, so it is stored and recorded
    #: as contradicting -- the same as a change to any earlier receipt. A console that
    #: refused to hold a record because the record is bad news would have the job backwards.
    #:
    #: `rows` holds only (a) and (b) by construction; see `_pre_store_rows`.
    #: **The verifier vetoes a format, whatever this store's list says.**
    #: `MANIFEST_FORMATS` is this store's declaration and it is kept,
    #: but a list in this repository cannot be the last word about a pinned dependency that
    #: will move without it. When the verifier drops a format, the store stops ingesting it
    #: the same day, and the 422 carries the verifier's own words.
    if is_format_refusal(said):
        rows.append(row(MANIFEST_NAME, "the pinned verifier checks this format",
                        f"the verifier refused {fmt!r}"))
    #: A delivery the 0.2.0 verifier does not check (the preview format) is
    #: not ingested. The body is one console sentence, then the verifier's own row, verbatim --
    #: not the verifier's whole text, so it is not attributed to the verifier.
    preview_row = None if rows else preview_not_run_row(said)
    if preview_row is not None:
        rows.append(row(MANIFEST_NAME, "the pinned verifier checks this format",
                        f"the verifier does not check {fmt!r}"))
        return Rejection(rows=tuple(rows) + (preview_row,),
                         body=f"{PREVIEW_NOT_INGESTED}\n{preview_row}\n", from_verifier=False)

    if rows:
        if said is not None and said.refused:
            #: The verifier spoke, so the body is what it said, UNEDITED -- word for word.
            #: Our own rows ride alongside for a caller that wants
            #: them structured; they are never merged into the body, because merging would
            #: put this channel's sentences inside a message attributed to the verifier.
            return Rejection(rows=tuple(rows) + said.failed_rows(),
                             body=said.text, from_verifier=True)
        return Rejection(tuple(rows), body="\n".join(rows) + "\n", from_verifier=False)

    key = run_key(run_id, chain_head)
    try:
        held = store.get_run(key)
    except StoreError as e:
        #: The store holds this run's record and cannot read it (this once answered 500).
        #: Not the delivery's fault, so not a 422; a conflict with what is stored, said, and
        #: nothing stored or overwritten: a record is never repaired.
        rows = [row("store", "the stored record of this run can be read", str(e))]
        return Rejection(tuple(rows), body="\n".join(rows) + "\n", status=409)
    if held is not None:
        gone = store.missing(held)
        if gone:
            #: A held run missing an object is refused, in its words, and
            #: nothing is stored: a held record is never repaired.
            rows = [row("store", "the stored record of this run holds every object it names",
                        ", ".join(gone))]
            return Rejection(tuple(rows), body=HELD_MISSING.format(objects=", ".join(gone)) + "\n",
                             status=409)
        # "A second delivery with the same identity is acknowledged and not stored again."
        return Accepted(run=held, created=False, status=200)

    flags: list[str] = []
    if store.runs_with_id(run_id):
        # "two chains under one name is itself a finding"
        flags.append(RUN_ID_REUSED)
    flags.extend(header_disagreements)

    #: The first LIST_CAP names are kept to show, and a digest of them all to group by: a list
    #: of stage names is as long as an upload makes it, and every page reads
    #: every run's record.
    from onetrace_console.viewer.model import LIST_CAP

    listing: list[tuple[str, str]] = []
    for path, blob in files.items():
        listing.append((path, store.put(blob)))

    run = StoredRun(
        key=key,
        run_id=run_id,
        chain_head=chain_head,
        format=fmt,
        listing=tuple(listing),
        received_at=received_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        flags=tuple(flags),
        pipeline=digest(files[MANIFEST_NAME]),
        declared_stages=tuple(declared[:LIST_CAP]),
        declared_digest=digest(json.dumps(declared).encode("ascii")) if declared else "",
        stage_count=len(declared),
        #: The receipts delivered: files the chain names that the delivery holds and that are
        #: receipts, each once. Not the chain's entries -- a run missing two receipt files read
        #: "3 of 3" on Home -- nor any file it names.
        recorded_count=len(receipts),
        **delivered_and_retries(attempts, seen_declared),
    )
    store.put_run(run)
    return Accepted(run=run, created=True)


def bundle(run: StoredRun, store: Store) -> bytes:
    """The delivery rebuilt: every file byte-for-byte, in the order it arrived.

    Deterministic on purpose -- fixed mtime, uid, gid and names -- so that the same run
    exports to the same bytes. `GET /v1/runs/{id}/bundle` is the "Export evidence" button
    and the "repeat the check without us" answer, and an export that differed run to run
    would make a reader wonder which copy was the evidence.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, key in run.listing:
            blob = store.get(key)
            info = tarfile.TarInfo(name=path)
            info.size = len(blob)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(blob))
    return buf.getvalue()
