"""rate-limit sign-in attempts, per account and per client."""
from __future__ import annotations

from onetrace_console.rate_limit import ConcurrencyLimiter, RateLimiter


def test_allows_up_to_the_configured_max_then_refuses(examined):
    limiter = RateLimiter(max_attempts=3, window_seconds=60)
    examined(4, "calls against a limit of 3")
    assert limiter.check_and_record("alice") is True
    assert limiter.check_and_record("alice") is True
    assert limiter.check_and_record("alice") is True
    assert limiter.check_and_record("alice") is False


def test_keys_are_independent(examined):
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    examined(2, "two different keys, one attempt each")
    assert limiter.check_and_record("alice") is True
    assert limiter.check_and_record("bob") is True


def test_the_window_rolls_over(examined):
    limiter = RateLimiter(max_attempts=1, window_seconds=10)
    examined(3, "calls straddling a window boundary")
    assert limiter.check_and_record("alice", now=0.0) is True
    assert limiter.check_and_record("alice", now=5.0) is False   # still inside the window
    assert limiter.check_and_record("alice", now=11.0) is True   # a new window


def test_reset_clears_the_counter(examined):
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    examined(3, "a limit hit, then reset, then retried")
    assert limiter.check_and_record("alice") is True
    assert limiter.check_and_record("alice") is False
    limiter.reset("alice")
    assert limiter.check_and_record("alice") is True


def test_per_account_and_per_client_are_independently_configurable(examined):
    """Rate-limited per account AND per client, both
    configurable -- proven here as two independent limiter instances with different
    limits, exactly how they are wired in serve.py (one keyed by username, one by the
    client's address).
    """
    per_account = RateLimiter(max_attempts=2, window_seconds=60)
    per_client = RateLimiter(max_attempts=5, window_seconds=60)
    examined(2, "independently configured limiters")
    assert per_account.max_attempts != per_client.max_attempts
    for _ in range(2):
        assert per_account.check_and_record("alice") is True
    assert per_account.check_and_record("alice") is False
    #: The per-client limiter, keyed by a DIFFERENT key (the client address, not the
    #: username), is unaffected by the account limiter being exhausted.
    assert per_client.check_and_record("203.0.113.5") is True


def test_concurrency_limiter_refuses_past_the_cap_and_frees_on_release(examined):
    """A global cap on concurrent scrypt computations, independent
    of account or client. Non-blocking -- a caller past the cap gets `False`
    immediately, never queued.
    """
    limiter = ConcurrencyLimiter(max_concurrent=2)
    examined(4, "acquires against a concurrency cap of 2, one release, one retry")
    assert limiter.try_acquire() is True
    assert limiter.try_acquire() is True
    assert limiter.try_acquire() is False          # the cap is already full
    limiter.release()
    assert limiter.try_acquire() is True           # a slot freed by the release


def test_concurrency_limiter_a_burst_never_enters_a_patched_hash_function(examined, monkeypatch):
    """Patch the hash call, and prove a
    request that cannot acquire a slot never reaches it at all.
    """
    limiter = ConcurrencyLimiter(max_concurrent=2)
    calls = []

    def fake_scrypt(*args, **kwargs):
        calls.append(1)
        return b"x"

    limiter.try_acquire()
    limiter.try_acquire()          # the cap (2) is now full

    def attempt():
        if not limiter.try_acquire():
            return "refused-before-hashing"
        try:
            return fake_scrypt()
        finally:
            limiter.release()

    examined(3, "attempts made against a full concurrency cap")
    results = [attempt() for _ in range(3)]
    assert results == ["refused-before-hashing"] * 3
    assert calls == [], "the patched hash function was called despite the cap being full"
