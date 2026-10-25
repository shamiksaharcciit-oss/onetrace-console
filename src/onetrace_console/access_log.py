"""The console's own access log: append-only, hash-chained, one entry per request.

The design note: *"every ingest and every page view is attributable to a named
principal, recorded in the console's own access log, which is append-only and
hash-chained like our other records."* This is step 1, with a configured maximum size
per segment, `StoreExhausted`-style fail-closed behaviour, and rotation to a new
chained segment.

NO ENFORCEMENT YET
------------------
This module only records. Every principal is the literal string `"anonymous"` until step
2 (local accounts) exists to name a real one. Nothing here refuses a request for lacking
one; that is step 3's job (role enforcement). Recording now, before there is anyone to
attribute, is deliberate: it is how a bug in the LOGGING gets found before there is a real
sign-in system whose absence would otherwise hide it.

WHY BaseException, LIKE StoreExhausted
----------------------------------------
`onetrace`'s own `StoreExhausted` derives from `BaseException`, specifically so that an
ordinary `except Exception` elsewhere does not silently swallow a size limit being hit and
carry on as if nothing happened (the SDK manual, section 5.11). The same reasoning applies
here for the same reason: if the access log cannot be appended to, the request it would
have recorded must not be served as if it had been -- silently answering a request nobody
could later prove happened is exactly the failure this log exists to prevent. See
`serve.py`'s `_respond`, which calls `append` BEFORE writing any bytes to the client, so a
raised `AccessLogExhausted` can still change what response goes out.

THE ONE HONEST GAP
-------------------
If appending itself fails, `serve.py` sends a 500 explaining why -- and does **not** try to
log that failure into the same broken log. A log that is failing cannot also record its own
failure; this is the one request that goes unrecorded, and it is the request that failed to
be served at all, never a request that succeeded silently.

ROTATION
--------
Entries live in numbered segments (`access_log/000001.jsonl`, `000002.jsonl`, ...), each
bounded by `access_log_max_segment_bytes`. When the next entry would push the current
segment over that bound, a new segment starts, and **its first entry's `prev` names the
outgoing segment's own last entry** -- the chain is one unbroken sequence across every
segment, the same way a run's chain does not restart at a stage boundary. `HEAD.json`
(atomically rewritten, `store.py`'s own `_atomic_write`) records the current segment number,
its size so far, and the chain head, so a restart resumes the same chain rather than a new
one.
"""
from __future__ import annotations

import hashlib
from onetrace_console.bounded_json import load_json_bounded
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from onetrace_console.oserror import said
from onetrace_console.store import _atomic_write

SEGMENT_DIGITS = 6


class AccessLogExhausted(BaseException):
    """The access log could not be appended to. Derives from `BaseException`, not
    `Exception` -- see this module's own docstring for why, and `onetrace`'s
    `StoreExhausted` (the SDK manual, section 5.11) for the precedent this follows.
    """


def _canonical_json(entry: dict) -> bytes:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def entry_digest(entry: dict) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(entry)).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _segment_path(root: Path, segment: int) -> Path:
    return root / f"{segment:0{SEGMENT_DIGITS}d}.jsonl"


_CHAIN_HEAD = re.compile(r"sha256:[0-9a-f]{64}")


def _read_head(path: Path) -> dict:
    """The log's own HEAD.json, or `ValueError` saying why it is not one.

    One nested past what JSON reads stopped the start with a traceback, and one
    with the wrong types started, then answered no request at all (`append` raised in every
    response). Refused at the start instead, in words, like the other shapes it is not."""
    try:
        head = load_json_bounded(path.read_text(encoding="utf-8"), path.name)
    except RecursionError:
        raise ValueError(f"{path.name} is nested past what JSON can read, so it is not the "
                         f"access log's own") from None
    if not isinstance(head, dict):
        raise ValueError(f"{path.name} is a {type(head).__name__}, not the access log's own")
    #: Bounded above too: a segment number of 10**400 started, and then every
    #: request answered 500. A segment's number is what its file name spells in SEGMENT_DIGITS.
    bounds = {"segment": (1, 10 ** SEGMENT_DIGITS - 1), "segment_size": (0, 2 ** 62)}
    for key in ("segment", "segment_size"):
        value = head.get(key)
        low, high = bounds[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{path.name}'s {key} is {value!r}, not the whole number the "
                             f"access log writes")
    chain_head = head.get("chain_head")
    if not (chain_head is None or isinstance(chain_head, str)
            and _CHAIN_HEAD.fullmatch(chain_head)):
        raise ValueError(f"{path.name}'s chain_head is {chain_head!r}, not a sha256 digest")
    return head


#: One append at a time, in this process: the server answers requests on threads, and an append
#: composes its entry from the chain head, writes it, then replaces HEAD.json. Two at once broke the
#: chain (two entries naming one `prev`), and on Windows a replace onto a file another replace is
#: writing is refused, so a request answered 500 (`AccessLogExhausted`) among 200s.
_APPEND_LOCK = threading.Lock()


@dataclass
class AccessLog:
    """One access log, rooted at `root` (typically `<store-root>/access_log/`)."""
    root: Path
    max_segment_bytes: int

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._head_path = self.root / "HEAD.json"
        if self._head_path.is_file():
            head = _read_head(self._head_path)
            self._segment = head["segment"]
            self._segment_size = head["segment_size"]
            self._chain_head = head["chain_head"]
        else:
            self._segment = 1
            self._segment_size = 0
            self._chain_head = None
            self._write_head()

    def _write_head(self) -> None:
        head = {"segment": self._segment, "segment_size": self._segment_size,
               "chain_head": self._chain_head}
        _atomic_write(self._head_path, (json.dumps(head, sort_keys=True) + "\n").encode("utf-8"))

    def append(self, *, principal: str, method: str, path: str, status: int,
              now: str | None = None) -> dict:
        """Append one entry. Raises `AccessLogExhausted` -- never returns partially --
        if the entry cannot be written at all (rotation itself failing, or the
        underlying filesystem refusing the write). One at a time (`_APPEND_LOCK`).
        """
        with _APPEND_LOCK:
            return self._append(principal=principal, method=method, path=path, status=status, now=now)

    def _append(self, *, principal: str, method: str, path: str, status: int, now: str | None) -> dict:
        entry = {
            "principal": principal,
            "method": method,
            "path": path,
            "status": status,
            "time": now or _now_iso(),
            "prev": self._chain_head,
        }
        line = _canonical_json(entry) + b"\n"

        if self._segment_size + len(line) > self.max_segment_bytes:
            self._rotate()

        try:
            segment_path = _segment_path(self.root, self._segment)
            with open(segment_path, "ab") as fh:
                fh.write(line)
        except OSError as e:
            raise AccessLogExhausted(f"cannot append to the access log: {said(e)}") from e

        self._segment_size += len(line)
        self._chain_head = entry_digest(entry)
        try:
            self._write_head()
        except OSError as e:
            raise AccessLogExhausted(f"cannot record the access log's own head: {said(e)}") from e
        return entry

    def _rotate(self) -> None:
        self._segment += 1
        self._segment_size = 0
        #: The new segment's own file does not exist yet -- append() creates it as an
        #: empty file on the first write, via "ab". Nothing to do here except advance
        #: the pointer; the next entry's own `prev` (already set from `self._chain_head`
        #: in `append`, computed before this method runs) is what carries the chain
        #: across the boundary.

    def read_all_entries(self) -> list[dict]:
        """Every entry, across every segment, in order. For tests and verification --
        not on any request-serving path.
        """
        out: list[dict] = []
        for segment_path in sorted(self.root.glob("*.jsonl")):
            for line in segment_path.read_text(encoding="utf-8").splitlines():
                if line:
                    out.append(load_json_bounded(line, f"{segment_path.name}: an entry"))
        return out

    def verify_chain(self) -> tuple[bool, str]:
        """Recompute the chain from every stored entry and compare against the recorded
        head. `(True, "")` if it matches; `(False, <reason>)` if it does not.
        """
        entries = self.read_all_entries()
        prev = None
        for i, entry in enumerate(entries):
            if entry["prev"] != prev:
                return False, (f"entry {i}: prev={entry['prev']!r} but the chain up to "
                              f"here computes {prev!r}")
            prev = entry_digest(entry)
        if prev != self._chain_head:
            return False, f"recomputed head {prev!r} disagrees with recorded head {self._chain_head!r}"
        return True, ""
