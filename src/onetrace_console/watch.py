"""Live folder pickup: while `onetrace-console <runs folder>` runs, a run written into the folder is
taken in on its own, within a few seconds, with no restart.

How it decides, every `interval` seconds (2 by default; `--watch-interval N`, `--no-watch`):
- **Only finished runs.** A folder is taken in only once its MANIFEST.json exists and its list of
  files and their sizes are the same on two reads in a row. A run still being written is never
  taken, never shown as failed, and not mentioned until it is.
- **One intake, through the one path.** A finished folder goes through exactly what the start-up
  load does (`folder_load.deliver_one`): the same delivery into the store, the same check, the
  same pages. Taken in once: if the folder changes afterwards, the stored copy stays as recorded
  and the page says the folder now differs; a folder deleted afterwards stays in the store with a
  note that it is no longer there.
- **A cap on each round.** Each round takes in at most `MAX_PER_PASS` runs; any others wait for the
  next round. The checking happens in a separate thread. It locks the console's adding of runs only
  while it adds one, and it never stops the console: a problem is written to the log and kept for
  the page, and the next round carries on.

Standard library only: polling, never an operating system's file events, so it behaves the same
on Windows, macOS and Linux.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

INTERVAL = 2.0
MAX_PER_PASS = 50
MANIFEST = "MANIFEST.json"
RECORDING_LOCK = ".lock"


def signature(run_dir: Path) -> tuple | None:
    """What two reads must agree on: every file's path and size. None while there is no manifest,
    or while the recorder's own lock file says the run is still being written."""
    try:
        files = sorted((p.relative_to(run_dir).as_posix(), p.stat().st_size)
                       for p in run_dir.rglob("*") if p.is_file())
    except OSError:
        return None
    names = {rel for rel, _ in files}
    if MANIFEST not in names or RECORDING_LOCK in {Path(rel).name for rel in names}:
        return None
    return tuple(files)


#: A run folder taken in that has since changed or gone: its tone by the one colour rule, and the
#: page's words for it. `examine` decides "differs": red where the folder now contradicts its own
#: record, amber otherwise; a folder that's gone is neutral.
GONE = ("neu", "No longer in the folder. The copy taken in stays in the store.")


@dataclass
class Watched:
    """What the watcher knows of the folder, for the pages and the notice."""
    folder: str = ""
    interval: float = INTERVAL
    last_read: str = ""
    taken: list[str] = field(default_factory=list)       # run folder names, in intake order
    changed: dict[str, tuple[str, str]] = field(default_factory=dict)  # name -> (tone, words)
    errors: list[str] = field(default_factory=list)
    version: int = 0                                    # bumped whenever the pages change

    def as_json(self) -> dict:
        return {"folder": self.folder, "interval": self.interval, "last_read": self.last_read,
                "taken": len(self.taken), "version": self.version,
                "changed": {n: list(v) for n, v in sorted(self.changed.items())},
                "errors": self.errors[-20:]}


#: The watcher of this console's folder, while there is one: the pages read it when drawn.
CURRENT: "Watcher | None" = None


class Watcher:
    def __init__(self, folder: Path, intake, *, interval: float = INTERVAL, taken=None,
                 on_change=None, examine=None):
        """`intake(run_dir) -> bool`: take one finished run folder in (True when stored).
        `taken`: {name: signature} of the folders already taken in. `on_change(names)`: after a
        pass that took runs in or noted a change. `examine(run_dir) -> (tone, words)`: what a
        folder changed since its intake now reads."""
        self.folder = Path(folder)
        self.intake = intake
        self.interval = interval
        self.on_change = on_change
        self.examine = examine
        self.lock = threading.Lock()
        self.state = Watched(folder=str(self.folder.resolve()), interval=interval,
                             taken=sorted(taken or {}))
        self._taken: dict[str, tuple] = dict(taken or {})
        self._last: dict[str, tuple | None] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def scan(self) -> list[str]:
        """One pass: the names taken in by it. One pass at a time (a "read now" waits for the
        loop's, and the reverse)."""
        with self.lock:
            return self._scan()

    def _scan(self) -> list[str]:
        noted = self.state.version
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        names = sorted(p.name for p in self.folder.iterdir() if p.is_dir()) if self.folder.is_dir() else []
        took: list[str] = []
        for name in names:
            sig = signature(self.folder / name)
            if name in self._taken:
                if sig is not None and sig != self._taken[name] and name not in self.state.changed:
                    self.state.changed[name] = (self.examine(self.folder / name) if self.examine
                                                else ("cc", "Changed since it was taken in."))
                    self.state.version += 1
                continue
            ready = sig is not None and self._last.get(name) == sig
            self._last[name] = sig
            if not ready or len(took) >= MAX_PER_PASS:
                continue
            try:
                stored = self.intake(self.folder / name)
            except Exception as e:  # noqa: BLE001 - kept for the page and the log; the next folder is read
                self.state.errors.append(f"{name}: {type(e).__name__}: {e}")
                continue
            self._taken[name] = sig
            self._last.pop(name, None)
            if stored:
                took.append(name)
        for name in sorted(set(self._taken) - set(names)):
            if self.state.changed.get(name) != GONE:
                self.state.changed[name] = GONE
                self.state.version += 1
        if took:
            self.state.taken.extend(took)
            self.state.version += 1
        self.state.last_read = now
        if self.state.version != noted and self.on_change is not None:
            self.on_change(took)
        return took

    def start(self) -> None:
        def loop():
            while not self._stop.wait(self.interval):
                try:
                    self.scan()
                except Exception as e:  # noqa: BLE001 - never fatal
                    self.state.errors.append(f"{type(e).__name__}: {e}")
        self._thread = threading.Thread(target=loop, name="onetrace-console-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 2 + 1)
