"""A run folder's `.lock`: onetrace holds it while it records, and removes it when the run closes.

What a `.lock` says, as the console reads it (`state`):
- **none**: no `.lock`; the folder is read as any other.
- **live**: it names a process on this host that is still running: the run is still being recorded,
  and the folder is skipped, as before.
- **dead**: it names a process on this host that is gone: the recorder was stopped without closing
  the run. The folder is loaded without its `.lock`, and the run reads "not closed".
- **elsewhere**: it names another host. Whether that process lives can't be read from here, so the
  folder is listed as locked.
- **empty**: it names no process. onetrace writes it empty before 0.9, so a run still recording
  can't be told from one stopped without closing. The folder is listed on the Runs page as locked;
  a local console offers "Load as not closed".

A `.lock` that names one is JSON with `pid` (an integer) and `host` (the recording host's name); its
other members, such as the start time, are not read. Anything else reads as empty.
"""

from __future__ import annotations

import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

NAME = ".lock"
#: The Runs page's words for a listed folder, by the state that lists it.
LISTED_WORDS = {
    "empty": "locked: still recording, or stopped without closing",
    "elsewhere": "locked: recording on another host, or stopped there without closing",
}
#: What a folder load says of a listed folder, after "not loaded: ".
REFUSED = {
    "empty": (
        "it is still being recorded, or it stopped without closing (onetrace's .lock is in it, and "
        "names no process); it is listed on the Runs page"
    ),
    "elsewhere": (
        "it is still being recorded on another host, or it stopped there without closing (its "
        ".lock names another host); it is listed on the Runs page"
    ),
}
#: The Runs page's heading over the listed folders.
HEADING = "Locked run folders"
#: The press a local console offers beside a folder whose `.lock` is empty.
PRESS = "Load as not closed"
#: The route the press sends the folder's name to.
ROUTE = "/runs/load-not-closed"

#: The folders listed as locked, by name: (their path, the state that lists them). Kept by the
#: loading (`folder_load.deliver_one`) and the watcher, read by the Runs page when it is drawn.
LISTED: dict[str, tuple[str, str]] = {}


@dataclass(frozen=True)
class LockState:
    kind: str  # "none", "live", "dead", "elsewhere" or "empty"
    pid: int | None = None
    host: str | None = None


def this_host() -> str:
    return socket.gethostname()


def _same_host(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def process_alive(pid: int, *, windows: bool | None = None, kernel32=None) -> bool:
    """Whether a process with this id runs on this host. Where it can't be told (no permission to ask),
    it is read as running, so a live run is never taken for a stopped one."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    windows = sys.platform == "win32" if windows is None else windows
    if windows:
        return _alive_on_windows(pid, kernel32)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


#: Windows' own values.
_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ACCESS_DENIED = 5
_INVALID_PARAMETER = 87


def _alive_on_windows(pid: int, kernel32=None) -> bool:
    import ctypes

    k = kernel32 if kernel32 is not None else ctypes.windll.kernel32  # type: ignore[attr-defined]  # Windows's name, read only on Windows
    handle = k.OpenProcess(_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        #: No such process is ERROR_INVALID_PARAMETER; a process this user may not open still runs.
        return k.GetLastError() != _INVALID_PARAMETER
    try:
        code = ctypes.c_ulong(0)
        if not k.GetExitCodeProcess(handle, ctypes.pointer(code)):
            return True
        return code.value == _STILL_ACTIVE
    finally:
        k.CloseHandle(handle)


def state(run_dir: Path, *, alive=process_alive, host: str | None = None) -> LockState:
    """What the run folder's own `.lock` says (module docstring)."""
    path = Path(run_dir) / NAME
    try:
        if not path.is_file():
            return LockState("none")
        raw = path.read_bytes()[:4096]
    except OSError:
        return LockState("empty")
    try:
        from onetrace_console.bounded_json import load_json_bounded

        said = load_json_bounded(raw.decode("utf-8"), "a run folder's .lock") if raw.strip() else None
    except (UnicodeDecodeError, ValueError, RecursionError):  # TooDeep is a ValueError
        said = None
    pid = said.get("pid") if isinstance(said, dict) else None
    named = said.get("host") if isinstance(said, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or not isinstance(named, str) or not named.strip():
        return LockState("empty")
    if not _same_host(named, this_host() if host is None else host):
        return LockState("elsewhere", pid, named)
    return LockState("live" if alive(pid) else "dead", pid, named)


def note(name: str, run_dir: Path, kind: str) -> bool:
    """List the folder as locked; True where that changed the list."""
    entry = (str(run_dir), kind)
    if LISTED.get(name) == entry:
        return False
    LISTED[name] = entry
    return True


def unlist(name: str) -> bool:
    return LISTED.pop(name, None) is not None
