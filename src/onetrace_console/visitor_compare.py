"""Compare on the public demo: the one thing a public console does on request.

`POST /compare` on a public console takes exactly two run ids of the demo's build, `a` (the
baseline) and `b`, as a form's body, and nothing else. It refuses, with the reason, an id the build
does not hold, a path, two runs of different pipelines, the same run twice, a third field, a field
twice, anything in the address after `/compare`, and a body over `MOST_BODY` bytes (unread). A pair
the build compared is served as built; a pair a visitor compared before is served from the cache;
any other pair is compared with the SDK's verbs on the two folders the demo holds (as the build
compares its own pairs: no model, no network, no explanation) and its pages written into the cache,
`<store root>/compared/` unless the configuration names another folder, beside the built store and
never in it. The answer is a redirect to the comparison's page.

Bounds, each held by a test (`tests/test_visitor_compare.py`):

- one comparison in flight per client address, with at most `QUEUE` more from it waiting, each
  waiting at most `WAIT_SECONDS`;
- at most `RUNNING` comparisons running at once on the whole console;
- at most `PER_MINUTE` comparisons started in any minute on the whole console; over it the answer is
  "busy, try again" at once, and nothing is queued;
- each verb stopped after `TIMEOUT_SECONDS`; a comparison stopped so is not kept;
- no cookie, header or form field is read but `Content-Length`, the configured client-address header
  where one is named, and the two ids (`OnlyHeaders` refuses any other header the handler asks for);
- the log line holds the pair, the outcome and the time taken; the client address is held by the
  limiter only while that address has a comparison in flight or waiting, and never logged.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl

from onetrace_console.words import escape

#: The cache, under the store root, beside the built store.
FOLDER = "compared"
#: The shipped bounds; a public console's configuration can lower each (`config.Config.compare_*`).
QUEUE = 2
RUNNING = 2
PER_MINUTE = 20
WAIT_SECONDS = 20.0
TIMEOUT_SECONDS = 30
#: The largest body read: two run ids and their names.
MOST_BODY = 512
WINDOW_SECONDS = 60.0

BUSY = "Busy, try again"
BUSY_WORDS = ("This demo is comparing as many pairs as it allows at once, or has started as many as "
              "it allows this minute. Nothing was queued. Try again in a minute.")
TIMED_OUT = ("The comparison took longer than this demo allows ({seconds} seconds a step) and was "
             "stopped; nothing was kept. Try again, or pick another pair.")
NO_CACHE = ("This demo cannot keep a comparison: its folder {folder} cannot be written ({why}). The "
            "comparisons it holds are on each run's page.")
VISITOR_MADE = ("Compared on this demo's server at a visitor's request, with the SDK's verbs on the "
                "two runs as recorded: no model and no network. No explanation is kept for it.")
#: The picker's words on a pipeline's page.
PICKER_HEAD = "Compare two of its runs"
PICKER_WORDS = ("Pick two runs of this pipeline; this demo compares them on its server with the SDK's "
                "verbs, as it compared its own pairs when it was built: no model, no network and no "
                "explanation. A pair compared before opens at once. At most {per_minute} new "
                "comparisons a minute for everyone; it sends and keeps nothing else.")
PICKER_BUTTON = "Compare"


class Refused(ValueError):
    """A request refused, with the reason a visitor reads; `status` its HTTP status."""

    def __init__(self, reason: str, status: int = 400):
        super().__init__(reason)
        self.status = status


# --------------------------------------------------------------------------- the request

def read_pair(query: str, body: bytes) -> tuple[str, str]:
    """(a, b) from a form body holding exactly the two fields, each once; `Refused` otherwise."""
    if query:
        raise Refused("the request carries its two run ids in its body, and nothing after /compare")
    try:
        text = body.decode("ascii")
        fields = parse_qsl(text, keep_blank_values=True, strict_parsing=bool(text))
    except (UnicodeDecodeError, ValueError):
        raise Refused("the body is not a form of two run ids, a and b") from None
    names = [n for n, _v in fields]
    extra = sorted(set(names) - {"a", "b"})
    if extra:
        raise Refused(f"the request holds a field other than a and b: {', '.join(extra)}")
    for n in ("a", "b"):
        if names.count(n) != 1:
            raise Refused(f"the request must hold {n} exactly once")
    got = dict(fields)
    for n in ("a", "b"):
        v = got[n]
        if "/" in v or "\\" in v or ".." in v or ":" in v:
            raise Refused(f"{n} is a path; this demo compares two of its own runs, named by run id")
    return got["a"], got["b"]


def resolve(store, a_id: str, b_id: str):
    """The two runs of the build the ids name, of one pipeline; `Refused` with the reason otherwise."""
    from onetrace_console.overview import declared_list
    runs = []
    for n, rid in (("a", a_id), ("b", b_id)):
        found = store.runs_with_id(rid) if rid else ()
        if len(found) != 1:
            raise Refused(f"{n}: this demo holds no run named {rid!r}" if not found else
                          f"{n}: {len(found)} runs of this demo are named {rid!r}")
        runs.append(found[0])
    a, b = runs
    if a.key == b.key:
        raise Refused("a and b name the same run; there is nothing to compare")
    if declared_list(a) != declared_list(b):
        raise Refused(f"{a.run_id} and {b.run_id} are runs of different pipelines; this demo "
                      "compares two runs of one pipeline")
    return a, b


def client_address(config, headers, socket_address: str) -> str:
    """The address the limiter holds a request by: the configured header's value where the
    configuration names one (a proxy in front of the console sets it) and the request carries it, the
    connection's own address otherwise. No header is read where none is named."""
    if config.compare_client_header:
        said = (headers.get(config.compare_client_header) or "").strip()
        if said:
            return said
    return socket_address


# ---------------------------------------------------------------------------- the limiter

class Limiter:
    """One in flight per address with a small queue, a bound on those running at once, and a
    per-minute bound for the whole console. Addresses are held only while in flight or waiting."""

    def __init__(self, *, per_minute: int = PER_MINUTE, running: int = RUNNING, queue: int = QUEUE,
                 wait_seconds: float = WAIT_SECONDS, clock=time.monotonic):
        self.per_minute, self.running_most, self.queue = per_minute, running, queue
        self.wait_seconds, self.clock = wait_seconds, clock
        self._cond = threading.Condition()
        self._started: deque[float] = deque()
        self._held: dict[str, int] = {}          # address -> in flight and waiting
        self._busy: set[str] = set()             # addresses with one in flight
        self._running = 0

    def addresses(self) -> set[str]:
        with self._cond:
            return set(self._held)

    def _full_minute(self, now: float) -> bool:
        while self._started and now - self._started[0] >= WINDOW_SECONDS:
            self._started.popleft()
        return len(self._started) >= self.per_minute

    def _take(self, address: str) -> bool:
        """A slot for `address`, waiting in its queue where it can; False where the console is busy."""
        with self._cond:
            if self._full_minute(self.clock()) or self._held.get(address, 0) >= 1 + self.queue:
                return False
            self._held[address] = self._held.get(address, 0) + 1
            deadline = time.monotonic() + self.wait_seconds
            while address in self._busy or self._running >= self.running_most:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self._cond.wait(left)
            if address in self._busy or self._running >= self.running_most or self._full_minute(self.clock()):
                self._release_hold(address)
                return False
            self._started.append(self.clock())
            self._busy.add(address)
            self._running += 1
            return True

    @contextmanager
    def slot(self, address: str):
        """Yields True with a slot held, or False where the console is busy (nothing queued)."""
        if not self._take(address):
            yield False
            return
        try:
            yield True
        finally:
            with self._cond:
                self._running -= 1
                self._busy.discard(address)
                self._release_hold(address)
                self._cond.notify_all()

    def _release_hold(self, address: str) -> None:
        n = self._held.get(address, 0) - 1
        if n > 0:
            self._held[address] = n
        else:
            self._held.pop(address, None)


# ---------------------------------------------------------------------------- the stores

class VisitorStore:
    """The built store, read-only, with the cache's store beside it: objects and comparisons are read
    from either and written to the cache only. Everything else is the built store's."""

    def __init__(self, base, cache):
        self._base, self._cache = base, cache

    def __getattr__(self, name):
        return getattr(self._base, name)

    def get(self, key: str) -> bytes:
        return self._cache.get(key) if self._cache.has(key) else self._base.get(key)

    def has(self, key: str) -> bool:
        return self._cache.has(key) or self._base.has(key)

    def put(self, data: bytes) -> str:
        from onetrace_console.store import digest
        key = digest(data)
        if self._base.has(key):
            return key
        got = self._cache.put(data)
        self._base._forget()
        return got

    def missing(self, run) -> tuple[str, ...]:
        return tuple(path for path, key in run.listing if not self.has(key))

    def get_comparison(self, key: str):
        return self._cache.get_comparison(key) or self._base.get_comparison(key)

    def put_comparison(self, comparison) -> None:
        self._cache.put_comparison(comparison)
        self._base._forget()

    def comparisons(self) -> tuple:
        return tuple(self._base.comparisons()) + tuple(self._cache.comparisons())


def cache_root(config, store_root: Path) -> Path:
    return Path(config.compare_cache) if config.compare_cache else Path(store_root) / FOLDER


def cache_store(root: Path):
    """The cache's own store, made on first use; `Refused` (503) where its folder cannot be written."""
    import os
    import tempfile

    from onetrace_console.store import Store
    try:
        (root / "store").mkdir(parents=True, exist_ok=True)
        #: A probe of this request's own: two requests at once each write and remove their own.
        fd, probe = tempfile.mkstemp(prefix=".write-check-", dir=root / "store")
        os.close(fd)
        os.unlink(probe)
        return Store(root / "store")
    except OSError as e:
        raise Refused(NO_CACHE.format(folder=root, why=e.strerror or type(e).__name__), 503) from None


def held_page(base, root: Path, a, b) -> str | None:
    """The page of a pair the build compared, or a visitor compared before: its path, or None."""
    from onetrace_console.what_changed import held
    c = held(base, a.key, b.key)
    if c is not None:
        return f"diff/{c.key}.html"
    store_dir = root / "store" / "comparisons"
    if not store_dir.is_dir():
        return None
    from onetrace_console.store import Store
    c = held(Store(root / "store"), a.key, b.key)
    if c is not None and (root / "pages" / "diff" / f"{c.key}.html").is_file():
        return f"diff/{c.key}.html"
    return None


def make(base, root: Path, a, b, *, timeout: int = TIMEOUT_SECONDS) -> str:
    """Compare the pair into the cache and draw its pages there; the page's path. A comparison a verb
    did not finish is not kept: `Refused` (504) with the words."""
    from onetrace_console.compare import compare
    from onetrace_console.serve import _render_diff_page
    cache = cache_store(root)
    store = VisitorStore(base, cache)
    comparison = compare(a, b, store, timeout=timeout)
    if any(v.note == "timed out" for v in comparison.verbs):
        (cache.root / "comparisons" / f"{comparison.key}.json").unlink(missing_ok=True)
        raise Refused(TIMED_OUT.format(seconds=timeout), 504)
    with base.reading():
        rel = _render_diff_page(comparison, store, root, public=True)
    #: The page says how it was made, and that no explanation is kept for it: under its heading.
    page = root / "pages" / rel
    html = page.read_text(encoding="utf-8")
    said = f'<p class="note" data-visitor-made>{escape(VISITOR_MADE)}</p>'
    page.write_text(html.replace("</h1>", "</h1>" + said, 1), encoding="utf-8", newline="\n")
    return rel


def cached_page(root: Path, rel: str) -> bytes | None:
    """A page a visitor's comparison drew, by its path under the cache's pages; None where none is."""
    pages = (root / "pages").resolve()
    target = root / "pages" / rel
    try:
        if target.resolve().relative_to(pages).as_posix() != rel:
            return None
    except (ValueError, OSError):
        return None
    try:
        return target.read_bytes() if rel.startswith("diff/") and target.is_file() else None
    except OSError:
        return None


# ------------------------------------------------------------------------------ the pages

def picker(pipeline) -> str:
    """The form on a pipeline's page of a public console: two of its runs, by run id."""
    from onetrace_console.store import arrival_order
    runs = arrival_order(pipeline.runs, newest_first=False)
    if len(runs) < 2:
        return ""

    def select(name: str, label: str, chosen: int) -> str:
        options = "".join(f'<option value="{escape(r.run_id)}"{" selected" if i == chosen else ""}>'
                          f"{escape(r.run_id)}</option>" for i, r in enumerate(runs))
        return f'<label>{escape(label)} <select name="{name}">{options}</select></label>'
    return (f'<section id="visitor-compare" data-section="visitor-compare" class="visitor-compare">'
            f"<h2>{escape(PICKER_HEAD)}</h2>"
            f"<p>{escape(PICKER_WORDS.format(per_minute=PER_MINUTE))}</p>"
            f'<form method="post" action="/compare" data-visitor-compare>'
            f'{select("a", "Baseline (run A)", 0)} {select("b", "Candidate (run B)", 1)} '
            f'<button type="submit">{escape(PICKER_BUTTON)}</button></form></section>')


def answer_page(title: str, words: str, *, back: str = "") -> str:
    """A short page for a refusal or "busy": its title, its words, and the way back to the Overview
    (the request carries no pipeline, and no header is read for one)."""
    from onetrace_console.render import _document
    link = f'<p><a href="{escape(back)}">Back to the Overview</a></p>' if back else ""
    return _document(title, f'<div class="cp"><h1>{escape(title)}</h1>'
                            f'<p data-visitor-compare="said" role="alert">{escape(words)}</p>{link}</div>')
