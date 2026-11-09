"""Rate-limit sign-in attempts, per account and per client, over the same rolling window.

In-memory only, like `sessions.py` -- a rate limit that survived a
restart would need to be a stored record, and nothing here claims to be one; a
restart clearing attempt counters is an acceptable, deliberate reset, not a gap.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """A rolling window per key: the time of each attempt let through is kept, and
    `check_and_record(key)` returns `False` while `max_attempts` of them fall inside the
    last `window_seconds`; so in any span of `window_seconds`, at most `max_attempts`
    calls return `True`. An attempt leaves the count `window_seconds` after it was made.
    A refused attempt is not kept. Two independent limiters -- one keyed by
    account, one by client -- are how "per account and per client" is built: this
    class does not know which is which, it just counts by whatever key it's given.
    """
    max_attempts: int
    window_seconds: float

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        #: key -> the times of the attempts let through inside the last window, oldest first
        self._attempts: dict[str, deque[float]] = {}

    def check_and_record(self, key: str, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            kept = self._attempts.setdefault(key, deque())
            while kept and now - kept[0] >= self.window_seconds:
                kept.popleft()
            if len(kept) >= self.max_attempts:
                return False
            kept.append(now)
            return True

    def reset(self, key: str) -> None:
        """Called on a successful sign-in: a legitimate sign-in should not spend down
        the same budget a string of failed guesses would have used.
        """
        with self._lock:
            self._attempts.pop(key, None)


@dataclass
class ConcurrencyLimiter:
    """A global cap on concurrent scrypt computations. scrypt at
    `N=2**17` uses 128 MiB per call; per-account and per-client rate limits bound
    the RATE of attempts, but not how many can be hashing at once from different
    accounts/clients simultaneously -- a burst across many identities could still
    exhaust memory. `try_acquire()`/`release()` around the hash call itself is the
    only place that bounds concurrency directly, independent of who is asking.

    Non-blocking by design: a caller that cannot acquire a slot must refuse
    outright (503), never queue -- queuing in front of a memory-bounded resource
    just moves the exhaustion to request threads piling up instead of memory.
    """
    max_concurrent: int

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight = 0

    def try_acquire(self) -> bool:
        with self._lock:
            if self._in_flight >= self.max_concurrent:
                return False
            self._in_flight += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._in_flight -= 1
