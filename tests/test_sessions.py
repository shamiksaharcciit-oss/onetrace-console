"""Sessions. In-memory, fresh id per sign-in, idle/absolute timeouts,
server-side sign-out.
"""
from __future__ import annotations

from onetrace_console.sessions import SessionStore


def test_a_created_session_is_retrievable_and_carries_the_username(examined):
    store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    session = store.create("alice")
    examined(1, "a freshly created session, looked up by its own id")
    got = store.get(session.session_id)
    assert got is not None
    assert got.username == "alice"


def test_each_sign_in_gets_a_fresh_session_id_never_reused(examined):
    """Session fixation: an id from before sign-in must never be the one after."""
    store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    s1 = store.create("alice")
    s2 = store.create("alice")
    examined(2, "two sign-ins for the same user")
    assert s1.session_id != s2.session_id
    #: The first id is a distinct, independent session -- not silently invalidated by
    #: the second (that is sign-out's job, not create's); each carries its own csrf token.
    assert s1.csrf_token != s2.csrf_token


def test_idle_timeout_expires_the_session(examined):
    store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    #: Two independent sessions, each checked exactly once, so the first lookup's own
    #: touch (get() updates last_seen_at) cannot mask the second case's real gap.
    just_inside = store.create("alice", now=0.0)
    just_past = store.create("alice", now=0.0)
    examined(2, "a lookup just inside, then just past, the idle timeout")
    assert store.get(just_inside.session_id, now=1799.0) is not None
    assert store.get(just_past.session_id, now=1801.0) is None


def test_absolute_timeout_expires_the_session_even_if_active(examined):
    store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    session = store.create("alice", now=0.0)
    #: Touch it repeatedly, well inside the idle window each time, right up to the
    #: absolute boundary -- it must still expire, because "active" does not reset it.
    examined(2, "repeated activity that never lets the idle timeout fire on its own")
    for t in range(0, 43200, 1000):
        assert store.get(session.session_id, now=float(t)) is not None
    assert store.get(session.session_id, now=43201.0) is None


def test_sign_out_invalidates_the_session_on_the_server(examined):
    store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    session = store.create("alice")
    store.invalidate(session.session_id)
    examined(1, "a lookup of a session id after its own sign-out")
    assert store.get(session.session_id) is None


def test_session_ids_and_csrf_tokens_are_not_predictable(examined):
    store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    sessions = [store.create("alice") for _ in range(20)]
    examined(20, "session ids and csrf tokens checked for uniqueness")
    ids = {s.session_id for s in sessions}
    tokens = {s.csrf_token for s in sessions}
    assert len(ids) == 20
    assert len(tokens) == 20
