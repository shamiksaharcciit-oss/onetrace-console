"""The audit log: who did what to which run, team or person, hash-chained, append-only, with its head
kept off the store's volume, and checkable by a stranger with `audit_verify.py`.

**Where it lives**: `<store_root>/audit_log/`, beside `access_log/`:

- numbered segments `NNNNNN.jsonl`, rotated at `audit.max_segment_bytes`;
- `HEAD.json`: the segment, its size, the last `seq` and the head digest;
- `.lock`, which every append holds;
- `unrecorded/`, a note per action an append failed to record, folded into one `audit.append_failed` entry by the
  first append that succeeds after them.

**An entry** is one line of JSON, its keys sorted and no spaces: `seq`, `at`, `actor`, `event`, `object`, `detail`,
`prev`. `prev` is `"sha256:"` and the sha256 of the previous entry's line as stored, without its newline; the first
entry's is null. So a reader in another language checks the chain over the bytes, never by writing JSON again.

**The head, off the store's volume**: every append also adds its `seq` and head digest as a line to the file
`audit.head_location` names, which must not lie on the store's volume. The verifier's `--heads` reads it.

**One writer at a time**: an append takes an exclusive lock on `.lock`, reads `HEAD.json` again, writes the
entry, `HEAD.json` and the head line, in that order, and lets the lock go. The server and the command line append to
one chain; one waits for the other at most `LOCK_WAIT_SECONDS`, then the append fails. After a crash between the
writes, the verifier reads the segments as the truth: a `HEAD.json` or head line behind the chain by the last entry is
said as that.

**A failed append**: the action is refused, `AuditRefused`, except an action that removes access, which is
applied and the failure said on the error stream and the start-up line, and kept as a note in `unrecorded/`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from onetrace_console.bounded_json import load_json_bounded
from onetrace_console.oserror import said
from onetrace_console.store import _atomic_write

DIRNAME = "audit_log"
HEAD_NAME = "HEAD.json"
LOCK_NAME = ".lock"
UNRECORDED_DIRNAME = "unrecorded"
SEGMENT_DIGITS = 6
#: How long an append waits for another writer's lock.
LOCK_WAIT_SECONDS = 10.0
DEFAULT_MAX_SEGMENT_BYTES = 1024 * 1024
#: The actors that are not a principal's key.
CLI, CONSOLE = "cli", "console"


class AuditUnavailable(Exception):
    """An append did not happen: the lock was not had in time, or a write failed. Its words say which."""


class AuditRefused(Exception):
    """An action refused because its entry could not be appended: nothing was done."""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def line_of(entry: dict) -> bytes:
    """An entry's line as stored, without its newline."""
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(line: bytes) -> str:
    return "sha256:" + hashlib.sha256(line).hexdigest()


def segment_name(n: int) -> str:
    return f"{n:0{SEGMENT_DIGITS}d}.jsonl"


def device_of(path: Path) -> int:
    """The device `path` lies on: the nearest existing folder's. A test replaces it to stand for a second volume."""
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    return os.stat(p).st_dev


# ------------------------------------------------------------------ the lock between processes


@contextmanager
def _file_lock(path: Path, wait: float):
    """An exclusive lock on `path` between processes, waited for at most `wait` seconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+b")  # noqa: SIM115 - held for the lock's life
    try:
        deadline = time.monotonic() + wait
        while True:
            try:
                _lock(fh)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise AuditUnavailable(
                        f"another writer held the audit log's lock for over {wait:g} seconds"
                    ) from None
                time.sleep(0.02)
        try:
            yield
        finally:
            _unlock(fh)
    finally:
        fh.close()


if sys.platform == "win32":  # pragma: no cover - the Windows runner's
    import msvcrt

    def _lock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


#: One append at a time within a process too: the server's threads share one log.
_THREADS = threading.Lock()


# ------------------------------------------------------------------ the log


@dataclass
class AuditLog:
    """The audit log under `root` (`<store_root>/audit_log/`), its heads also written to `head_location`."""

    root: Path
    head_location: Path
    max_segment_bytes: int = DEFAULT_MAX_SEGMENT_BYTES
    lock_wait: float | None = None

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.head_location = Path(self.head_location)

    # -------------------------------------------------------------- reading

    def head(self) -> dict:
        """`HEAD.json`, or the head of an empty log."""
        path = self.root / HEAD_NAME
        if not path.is_file():
            return {"segment": 1, "segment_size": 0, "seq": 0, "head": None}
        head = load_json_bounded(path.read_text(encoding="utf-8"), "the audit log's HEAD.json")
        if not isinstance(head, dict) or not all(k in head for k in ("segment", "segment_size", "seq", "head")):
            raise AuditUnavailable(f"{path.name} is not the audit log's own")
        return head

    def entries(self) -> list[dict]:
        """Every entry, in order, across the segments."""
        out: list[dict] = []
        for seg in sorted(self.root.glob("*.jsonl")):
            out.extend(
                load_json_bounded(line.decode("utf-8"), f"{seg.name}: an entry")
                for line in seg.read_bytes().splitlines()
                if line
            )
        return out

    # -------------------------------------------------------------- appending

    @contextmanager
    def locked(self):
        """The log's lock, between threads and processes."""
        wait = LOCK_WAIT_SECONDS if self.lock_wait is None else self.lock_wait
        if not _THREADS.acquire(timeout=wait):
            raise AuditUnavailable(f"another writer held the audit log's lock for over {wait:g} seconds")
        try:
            with _file_lock(self.root / LOCK_NAME, wait):
                yield
        finally:
            _THREADS.release()

    def append(self, actor: str, event: str, obj: str, detail: dict | None = None) -> dict:
        """Append one entry, after an `audit.append_failed` entry for any notes `unrecorded/` holds. The entry, or
        `AuditUnavailable`, never half of it."""
        try:
            with self.locked():
                self._fold_unrecorded()
                return self._append_locked(actor, event, obj, detail or {})
        except OSError as e:
            raise AuditUnavailable(f"the audit log could not be written: {said(e)}") from e

    def _append_locked(self, actor: str, event: str, obj: str, detail: dict) -> dict:
        head = self.head()
        entry = {
            "seq": head["seq"] + 1,
            "at": now_iso(),
            "actor": actor,
            "event": event,
            "object": obj,
            "detail": detail,
            "prev": head["head"],
        }
        line = line_of(entry)
        segment, size = head["segment"], head["segment_size"]
        if size and size + len(line) + 1 > self.max_segment_bytes:
            segment, size = segment + 1, 0
        self.root.mkdir(parents=True, exist_ok=True)
        new_head = {"segment": segment, "segment_size": size + len(line) + 1, "seq": entry["seq"], "head": digest(line)}
        #: Both files are opened before either is written, so a second location that cannot be written refuses the
        #: append with nothing written. The order: the entry, then HEAD.json, then the head line.
        with open(self.head_location, "ab") as heads, open(self.root / segment_name(segment), "ab") as fh:
            fh.write(line + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
            _atomic_write(self.root / HEAD_NAME, (json.dumps(new_head, sort_keys=True) + "\n").encode("utf-8"))
            heads.write(line_of({"at": entry["at"], "head": new_head["head"], "seq": entry["seq"]}) + b"\n")
            heads.flush()
            os.fsync(heads.fileno())
        return entry

    # -------------------------------------------------------------- what was not recorded

    def note_unrecorded(self, event: str, reason: str) -> None:
        """Keep a note that `event` was not recorded, without the lock (it may be what failed). Best effort: where
        even this cannot be written, the error stream has said it."""
        try:
            folder = self.root / UNRECORDED_DIRNAME
            folder.mkdir(parents=True, exist_ok=True)
            note = {"at": now_iso(), "event": event, "reason": reason}
            _atomic_write(folder / f"{time.time_ns():020d}-{uuid.uuid4().hex}.json", line_of(note) + b"\n")
        except OSError:
            pass

    def unrecorded(self) -> list[dict]:
        folder = self.root / UNRECORDED_DIRNAME
        notes = []
        for p in sorted(folder.glob("*.json")) if folder.is_dir() else ():
            try:
                notes.append({**load_json_bounded(p.read_text(encoding="utf-8"), "a note"), "_path": p})
            except (OSError, ValueError, TypeError):
                continue
        return notes

    def _fold_unrecorded(self) -> None:
        notes = self.unrecorded()
        if not notes:
            return
        kinds = Counter(n.get("event", "?") for n in notes)
        detail = {
            "began": min(n.get("at", "") for n in notes),
            "ended": max(n.get("at", "") for n in notes),
            "not_recorded": dict(sorted(kinds.items())),
        }
        self._append_locked(CONSOLE, "audit.append_failed", "log", detail)
        for n in notes:
            n["_path"].unlink(missing_ok=True)


# ------------------------------------------------------------------ the console's use of it


@dataclass
class Audit:
    """What the console and its commands record through: the log, or nothing where `audit.enabled` is off."""

    log: AuditLog | None = None
    err: TextIO | None = None
    #: Since when appends have failed in this process, and the last reason: the start-up line and the error stream
    #: say it, and the admin pages will.
    failing: tuple[str, str] | None = None
    _signins: dict[str, tuple] | None = field(default=None, repr=False)

    @property
    def on(self) -> bool:
        return self.log is not None

    def record(self, actor: str, event: str, obj: str, detail: dict | None = None, *, removes_access=False) -> bool:
        """Append the entry. On a failure, an action that removes access is applied (False, the failure said and
        noted); any other is refused (`AuditRefused`). True where it was recorded, or the log is off."""
        if self.log is None:
            return True
        try:
            self.log.append(actor, event, obj, detail)
        except AuditUnavailable as e:
            reason = str(e)
            self.failing = self.failing or (now_iso(), reason)
            self.log.note_unrecorded(event, reason)
            applied = "applied anyway, as it removes access" if removes_access else "refused"
            print(
                f"audit log: {event} was not recorded ({reason}); the action was {applied}", file=self.err or sys.stderr
            )
            if removes_access:
                return False
            raise AuditRefused(f"the audit log could not record it, so it was not done: {reason}") from e
        self.failing = None
        return True

    def signin_differs(self, principal: str, granted: tuple) -> bool:
        """Whether `granted` (roles and teams) differs from the principal's last `signin.ok`, read from the log once
        and kept up to date after."""
        if self._signins is None:
            self._signins = {}
            try:
                for e in self.log.entries() if self.log is not None else ():
                    if e.get("event") == "signin.ok":
                        d = e.get("detail", {})
                        self._signins[e.get("object", "")] = (tuple(d.get("roles", ())), tuple(d.get("teams", ())))
            except (OSError, ValueError):
                pass
        last = self._signins.get(principal)
        self._signins[principal] = granted
        return last is not None and last != granted


def audit_for(config, store_root: Path) -> Audit:
    """The configuration's audit: the log under `store_root` where `audit.enabled`, else off."""
    settings = getattr(config, "audit", None) or {}
    if not settings.get("enabled"):
        return Audit()
    return Audit(
        AuditLog(
            Path(store_root) / DIRNAME,
            head_location=Path(settings["head_location"]),
            max_segment_bytes=settings.get("max_segment_bytes", DEFAULT_MAX_SEGMENT_BYTES),
        )
    )


def required_refusal(config) -> tuple[str, str] | None:
    """A console's start with teams or SCIM and the audit log off: access control is offered only with its record.
    (message, fix), or None. The console's start only; its commands are as they were."""
    settings = getattr(config, "audit", None) or {}
    if settings.get("enabled"):
        return None
    #: Access control without its record is not offered: teams and SCIM each need the audit log on.
    needs = [k for k, on in (("teams", bool(config.teams)), ("scim.enabled", bool(config.scim.get("enabled")))) if on]
    if needs:
        return (
            f"{' and '.join(needs)} {'is' if len(needs) == 1 else 'are'} set and audit.enabled is false. Access "
            "control is offered only with its record: who was let in, who was refused, and every change to it.",
            "set audit.enabled to true and audit.head_location to a file on a second mounted volume, or remove "
            + " and ".join(needs)
            + ".",
        )
    return None


def start_refusal(config, store_root: Path) -> tuple[str, str] | None:
    """The console's start refusals for the audit log: on, with no `audit.head_location`, or with one on the
    store's volume. (message, fix), or None."""
    settings = getattr(config, "audit", None) or {}
    if not settings.get("enabled"):
        return None
    location = settings.get("head_location")
    if not location:
        return (
            "audit.enabled is true and audit.head_location is not set. The head of the audit log is written off the "
            "store's volume on every append, so a cut tail shows.",
            "set audit.head_location to a file on a second mounted volume, not the store's.",
        )
    where = Path(location)
    if not where.parent.is_dir():
        return (
            f"audit.head_location is {location!r}, and its folder does not exist.",
            "mount the second volume, or set audit.head_location to a file on one that is mounted.",
        )
    if device_of(where) == device_of(Path(store_root)):
        return (
            f"audit.head_location is {location!r}, on the store's volume (the device store_root lies on). The head "
            "written there shows a cut tail only where whoever can edit the store's volume cannot also write it.",
            "set audit.head_location to a file on a second mounted volume, not the store's.",
        )
    return None


def start_line(audit: Audit) -> str | None:
    """The start-up line's words for the audit log: its head, and any actions not recorded."""
    if audit.log is None:
        return None
    head = audit.log.head()
    line = f"audit log: on, seq {head['seq']}, head {head['head'] or 'none yet'}"
    notes = audit.log.unrecorded()
    if notes:
        line += (
            f"; WARNING: {len(notes)} action(s) not recorded since {min(n.get('at', '') for n in notes)}, "
            "until an append succeeds"
        )
    return line


# ------------------------------------------------------------------ export


def export(log: AuditLog, to: Path) -> dict:
    """`audit export <new folder>`: the segments, `HEAD.json`, a `CHECKPOINT` line, the verifier, the heads
    written off the store's volume, and a `SHA256SUMS` over them all, taken under the log's lock so they agree; then
    an `audit.exported` entry, actor `cli`. Never `tokens/`, `accounts/`, SCIM's records or a page: only the log's own
    files are read. The head exported."""
    import shutil
    from importlib.resources import files

    to = Path(to)
    if to.exists() and any(to.iterdir()):
        raise AuditUnavailable(f"{to} is not empty: an export is written to a new folder")
    try:
        with log.locked():
            head = log.head()
            if not head["seq"]:
                raise AuditUnavailable("the audit log holds no entry yet")
            to.mkdir(parents=True, exist_ok=True)
            for seg in sorted(log.root.glob("*.jsonl")):
                shutil.copyfile(seg, to / seg.name)
            shutil.copyfile(log.root / HEAD_NAME, to / HEAD_NAME)
            (to / "CHECKPOINT").write_bytes(f"{head['seq']}:{head['head']}\n".encode("ascii"))
            (to / "audit_verify.py").write_bytes((files("onetrace_console") / "audit_verify.py").read_bytes())
            if log.head_location.is_file():
                shutil.copyfile(log.head_location, to / "heads.jsonl")
            names = sorted(p.name for p in to.iterdir() if p.is_file())
            sums = "".join(f"{hashlib.sha256((to / n).read_bytes()).hexdigest()}  {n}\n" for n in names)
            (to / "SHA256SUMS").write_bytes(sums.encode("ascii"))
            log._fold_unrecorded()
            log._append_locked(CLI, "audit.exported", "log", {"seq": head["seq"], "head": head["head"]})
    except OSError as e:
        raise AuditUnavailable(f"the export could not be written: {said(e)}") from e
    return head


# ------------------------------------------------------------------ what a start sees


#: What the last start saw of the configuration, beside the log: the team mapping, `folder_team` and the file's sha256.
SEEN_NAME = "seen.json"


def at_start(audit: Audit, config, config_file: str | None, store_root: Path) -> None:
    """At start: `teams.changed` where the team mapping or `folder_team` differs from what the last start saw,
    with the teams it touched, and `setting.changed` where the configuration file's sha256 does; both actor
    `console`. The first start with the log on records them as changed from nothing. `AuditRefused` where an entry
    cannot be appended: the start is refused, as any action is."""
    if audit.log is None:
        return
    sha = None
    if config_file:
        try:
            sha = hashlib.sha256(Path(config_file).read_bytes()).hexdigest()
        except OSError:
            sha = None
    now = {"teams": dict(config.teams), "folder_team": config.folder_team, "config_sha256": sha}
    path = audit.log.root / SEEN_NAME
    try:
        before = load_json_bounded(path.read_text(encoding="utf-8"), "seen.json") if path.is_file() else {}
        before = before if isinstance(before, dict) else {}
    except (OSError, ValueError):
        before = {}
    was_teams = before.get("teams") or {}
    touched = sorted(t for t in set(was_teams) | set(now["teams"]) if was_teams.get(t) != now["teams"].get(t))
    folder_moved = before.get("folder_team") != now["folder_team"]
    if touched or folder_moved:
        detail: dict = {"touched": touched, "config_sha256": sha}
        if folder_moved:
            detail["folder_team"] = {"before": before.get("folder_team"), "after": now["folder_team"]}
        audit.record(CONSOLE, "teams.changed", "configuration", detail)
    if sha is not None and before.get("config_sha256") != sha:
        audit.record(CONSOLE, "setting.changed", "configuration", {"setting": "configuration file", "sha256": sha})
    try:
        _atomic_write(path, (json.dumps(now, sort_keys=True) + "\n").encode("utf-8"))
    except OSError:
        pass
