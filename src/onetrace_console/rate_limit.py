"""Rate-limit sign-in attempts: per client address, and for an account per known browser, else per
(account, address) pair under the account's ceiling (`account_refusal`).

In-memory only, like `sessions.py` -- a rate limit that survived a
restart would need to be a stored record, and nothing here claims to be one; a
restart clearing attempt counters is an acceptable, deliberate reset, not a gap.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


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
        #: key -> the last clearing mark `clear_once` acted on
        self._marks: dict[str, object] = {}

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

    def allows(self, key: str, *, now: float | None = None) -> bool:
        """Whether `check_and_record(key)` would let an attempt through now, recording nothing."""
        now = time.monotonic() if now is None else now
        with self._lock:
            kept = self._attempts.get(key)
            if not kept:
                return True
            while kept and now - kept[0] >= self.window_seconds:
                kept.popleft()
            if not kept:
                del self._attempts[key]
                return True
            return len(kept) < self.max_attempts

    def clear_once(self, key: str, mark: object) -> None:
        """Reset `key` once for each new `mark` (such as the time `admin unlock` wrote); None does
        nothing."""
        if mark is None:
            return
        with self._lock:
            if self._marks.get(key) == mark:
                return
            self._marks[key] = mark
            self._attempts.pop(key, None)

    def reset(self, key: str) -> None:
        """Called on a successful sign-in: a legitimate sign-in should not spend down
        the same budget a string of failed guesses would have used.
        """
        with self._lock:
            self._attempts.pop(key, None)


def _pair(username: str, client: str) -> str:
    return f"{username}\n{client}"


def account_refusal(
    username: str, client: str, device: str | None, limiters: dict, *, now: float | None = None
) -> str | None:
    """The account's windows for one sign-in attempt, before its password is read: "device", "pair"
    or "ceiling" for the window that refuses it, or None, with the attempt recorded.

    - `device`, the id of a valid device cookie for `username`: only that device's window counts
      (`rate_limit_per_device`). Strangers' guesses never touch it.
    - Any other attempt: the (account, client address) pair's window (`rate_limit_per_pair`) and the
      account's ceiling over all addresses (`rate_limit_per_account`). A refused attempt is kept in
      neither. A limiter that is None is not counted.
    """
    per_device = limiters.get("rate_limit_per_device")
    per_pair = limiters.get("rate_limit_per_pair")
    ceiling = limiters.get("rate_limit_per_account")
    if device is not None and per_device is not None:
        return None if per_device.check_and_record(device, now=now) else "device"
    if ceiling is not None and not ceiling.allows(username, now=now):
        return "ceiling"
    if per_pair is not None and not per_pair.check_and_record(_pair(username, client), now=now):
        return "pair"
    if ceiling is not None:
        ceiling.check_and_record(username, now=now)
    return None


def after_right_password(username: str, client: str, device: str | None, limiters: dict) -> None:
    """A right password resets the pair's window and the device's, never the account's ceiling."""
    if limiters.get("rate_limit_per_pair") is not None:
        limiters["rate_limit_per_pair"].reset(_pair(username, client))
    if device is not None and limiters.get("rate_limit_per_device") is not None:
        limiters["rate_limit_per_device"].reset(device)


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


def _trusted(address: str, networks) -> bool:
    import ipaddress

    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in n for n in networks)


def client_address(peer: str, forwarded: list[str], trusted_proxies: list[str]) -> str:
    """The client address a sign-in limit counts: the connection's peer, unless the peer is one of
    `trusted_proxies` (addresses and CIDR ranges). Then the rightmost `X-Forwarded-For` entry (over
    every such header, in order) that is not a trusted proxy; where every entry is one, the leftmost;
    where that entry is not an address, or there is none, the peer. A client can write the left of
    the header but not what the trusted proxies append to its right."""
    import ipaddress

    networks = [ipaddress.ip_network(t, strict=False) for t in trusted_proxies]
    if not networks or not _trusted(peer, networks):
        return peer
    entries = [e.strip() for h in forwarded for e in h.split(",") if e.strip()]
    if not entries:
        return peer
    for entry in reversed(entries):
        if not _trusted(entry, networks):
            try:
                return str(ipaddress.ip_address(entry))
            except ValueError:
                return peer
    return str(ipaddress.ip_address(entries[0]))
