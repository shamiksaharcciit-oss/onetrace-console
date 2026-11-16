"""`admin sessions end` and `admin unlock` on a wall clock whose tick is coarse (Windows'): each returns only once the
clock reads past the time it wrote, so a session made after `end_sessions` returns is never taken for one made before
it, and a second unlock is never taken for the first. The clock here is faked: the same reading twice, then a later
one."""

from __future__ import annotations

import time

import pytest

from onetrace_console.accounts import AccountStore
from onetrace_console.serve import ACCOUNTS_DIRNAME
from onetrace_console.sessions import SessionStore

T = 1_794_750_330_000_000_000


class CoarseClock:
    """`time.time_ns` that gives its readings in order, then the last one for ever."""

    def __init__(self, *readings: int) -> None:
        self.readings = list(readings)

    def __call__(self) -> int:
        return self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]


@pytest.fixture
def accounts(tmp_path):
    store = AccountStore(tmp_path / ACCOUNTS_DIRNAME)
    store.create("alice", b"correct horse battery staple")
    return store


def test_a_session_made_after_end_sessions_returns_lives_on_a_coarse_clock(accounts, monkeypatch, examined):
    sessions = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200, ended=accounts.sessions_ended_at)
    #: before's reading; the end time; the same tick again; then the tick after, which every later reading gives.
    monkeypatch.setattr(time, "time_ns", CoarseClock(T - 1, T, T, T + 1))
    before = sessions.create("alice")
    written = accounts.end_sessions("alice")
    after = sessions.create("alice")
    assert written == T and accounts.sessions_ended_at("alice") == T
    assert sessions.get(before.session_id) is None, "a session made before the end time is gone"
    assert sessions.get(after.session_id) is not None, "a session made after end_sessions returned lives"
    examined(2, "sessions either side of the end time")


def test_a_session_made_in_the_end_time_s_own_tick_is_ended(accounts, monkeypatch, examined):
    """`<=` kept: a session whose reading equals the end time was made before or in that tick, and is ended."""
    sessions = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200, ended=accounts.sessions_ended_at)
    monkeypatch.setattr(time, "time_ns", CoarseClock(T, T, T + 1))
    same_tick = sessions.create("alice")
    accounts.end_sessions("alice")
    assert sessions.get(same_tick.session_id) is None
    examined(1, "session")


def test_two_unlocks_in_one_tick_write_two_times(accounts, monkeypatch, examined):
    """The sign-in limit clears once for each new time `unlock` writes (`rate_limit.clear_once`): a second unlock in
    the first's tick would write the same time, and clear nothing."""
    monkeypatch.setattr(time, "time_ns", CoarseClock(T, T, T + 1))
    first = accounts.unlock("alice")
    second = accounts.unlock("alice")
    assert (first, second) == (T, T + 1)
    examined(2, "unlocks")


def test_the_wait_is_bounded_where_the_clock_does_not_move(accounts, monkeypatch, examined):
    """A clock that never moves past the time written: the call returns after its bound, having written the time."""
    from onetrace_console import accounts as A

    monkeypatch.setattr(time, "time_ns", CoarseClock(T))
    started = time.monotonic()
    assert accounts.end_sessions("alice") == T
    assert time.monotonic() - started < A.CLOCK_WAIT_SECONDS + 1.0
    examined(1, "call")
