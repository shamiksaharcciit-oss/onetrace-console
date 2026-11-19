"""Sessions: per-connection state, never a stored record.

A session is per-connection state, not a stored record. Losing it means signing in again;
it is never content-addressed, never chained, never exported. Built exactly that way: `SessionStore` holds sessions only in
memory, for the lifetime of the process. A restart signs everyone out -- the correct
behaviour for something that is deliberately not part of the console's own record.

Session ids and CSRF tokens come from `secrets.token_urlsafe` (stdlib, cryptographically
strong) -- never `random`, never a counter.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

SESSION_ID_BYTES = 32
CSRF_TOKEN_BYTES = 32


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    username: str
    csrf_token: str
    created_at: float  # time.monotonic(), for timeout arithmetic only
    last_seen_at: float
    #: time.time_ns() at creation: compared with the time an account's sessions were ended, which
    #: another process (`admin sessions end`) writes.
    created_wall_ns: int = 0
    #: Sign-in through Entra ID: the role the `roles` claim gave at sign-in (`oidc_identity`), the name
    #: shown for display only, and the time (time.time()) the session ends: the ID token's expiry or
    #: `session_max_hours`, whichever came first. None, "" and None for a local account's session.
    role: str | None = None
    display_name: str = ""
    expires_at: float | None = None
    #: The teams the person was in at sign-in (a role claim is read at sign-in only); () for a
    #: local account's session, and without teams.
    teams: tuple[str, ...] = ()


@dataclass
class SessionStore:
    """In-memory only -- see this module's own docstring for why. One lock guards all
    of it; sign-in traffic on a small console does not need finer-grained locking.
    """

    idle_timeout_seconds: float
    absolute_timeout_seconds: float
    #: An account's live sessions at most (`sign_in.max_sessions_per_account`): a sign-in beyond it
    #: ends that account's oldest. None: no bound.
    max_per_account: int | None = None
    #: The time (time.time_ns()) before which a principal's sessions are ended, or None (`admin sessions end`,
    #: `serve.session_store_for`); a session made at or before it is gone.
    ended: Callable[[str], int | None] | None = None
    #: The wall clock a session's `expires_at` is read against.
    wall: Callable[[], float] = time.time
    #: Told the principal and how many of its sessions an end time ended, once, at the request that found it
    #: (`sessions.ended`, actor `console`, with the count).
    on_ended: Callable[[str, int], None] | None = None
    #: Told a session that ended by itself, and how: "idle", "absolute", "token expiry" or "bound" (the audit
    #: log's `signout`). Sign-out's own press is the server's to record.
    on_end: Callable[[Session, str], None] | None = None

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}
        #: The index from a principal (a local account's name or an Entra ID key) to its live session ids:
        #: every session enters it when made and leaves it by `_drop`, whatever ends it.
        self._by_principal: dict[str, set[str]] = {}

    def _drop(self, session_id: str) -> None:
        """End one session: from the map and from its principal's entry in the index. Under `_lock`."""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        ids = self._by_principal.get(session.username)
        if ids is not None:
            ids.discard(session_id)
            if not ids:
                del self._by_principal[session.username]

    def sessions_of(self, principal: str) -> set[str]:
        """The ids the index holds for `principal`: its sessions not yet found ended."""
        with self._lock:
            return set(self._by_principal.get(principal, ()))

    def indexed(self) -> dict[str, set[str]]:
        """The whole index, a copy: for the tests and the admin pages, never a session's own answer."""
        with self._lock:
            return {p: set(ids) for p, ids in self._by_principal.items()}

    def end_principal(self, principal: str, *, made_by_ns: int | None = None) -> int:
        """End every session the index holds for `principal` (made at or before `made_by_ns`, where given), at once.
        How many it ended."""
        with self._lock:
            ids = [
                i
                for i in self._by_principal.get(principal, ())
                if made_by_ns is None or self._sessions[i].created_wall_ns <= made_by_ns
            ]
            for i in ids:
                self._drop(i)
            return len(ids)

    def create(
        self,
        username: str,
        *,
        now: float | None = None,
        role: str | None = None,
        display_name: str = "",
        expires_at: float | None = None,
        teams: tuple[str, ...] = (),
    ) -> Session:
        """A FRESH session id every time -- called only after a password check
        succeeds, never to "renew" an existing id, which is what defends against
        session fixation: a session id issued before sign-in (to an
        attacker who planted it, for instance) is never the one a signed-in user ends
        up holding.
        """
        now = time.monotonic() if now is None else now
        session = Session(
            session_id=secrets.token_urlsafe(SESSION_ID_BYTES),
            username=username,
            csrf_token=secrets.token_urlsafe(CSRF_TOKEN_BYTES),
            created_at=now,
            last_seen_at=now,
            created_wall_ns=time.time_ns(),
            role=role,
            display_name=display_name,
            expires_at=expires_at,
            teams=tuple(teams),
        )
        bounded: list[Session] = []
        with self._lock:
            self._sessions[session.session_id] = session
            self._by_principal.setdefault(username, set()).add(session.session_id)
            if self.max_per_account is not None:
                mine = sorted(
                    (s for s in self._sessions.values() if s.username == username and not self._expired(s, now)),
                    key=lambda s: (s.created_at, s.created_wall_ns),
                )
                for old in mine[: max(0, len(mine) - self.max_per_account)]:
                    self._drop(old.session_id)
                    bounded.append(old)
        for old in bounded:
            self._told(old, "bound")
        return session

    def _told(self, session: Session, how: str) -> None:
        if self.on_end is not None:
            self.on_end(session, how)

    def _expired(self, session: Session, now: float) -> bool:
        return (
            now - session.created_at > self.absolute_timeout_seconds
            or now - session.last_seen_at > self.idle_timeout_seconds
        )

    def get(self, session_id: str, *, now: float | None = None) -> Session | None:
        """`None` if the id is unknown OR has timed out -- a timed-out session is
        removed here, not merely reported absent, so it cannot be revived by a clock
        question asked twice.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            how = None
            if now - session.created_at > self.absolute_timeout_seconds:
                how = "absolute"
            elif now - session.last_seen_at > self.idle_timeout_seconds:
                how = "idle"
            elif session.expires_at is not None and self.wall() >= session.expires_at:
                how = "token expiry"
            if how is not None:
                self._drop(session_id)
        if how is not None:
            self._told(session, how)
            return None
        ended = self.ended(session.username) if self.ended is not None else None
        if ended is not None and session.created_wall_ns <= ended:
            #: An end time names a person, not a session: every session of theirs made by then ends now, through
            #: the index, and the console is told how many.
            count = self.end_principal(session.username, made_by_ns=ended)
            if count and self.on_ended is not None:
                self.on_ended(session.username, count)
            return None
        with self._lock:
            if session_id not in self._sessions:
                return None
            touched = replace(session, last_seen_at=now)
            self._sessions[session_id] = touched
            return touched

    def invalidate(self, session_id: str) -> None:
        """Sign-out: removed from the server side, not merely told to the client to
        forget its cookie -- a stolen cookie presented after this must not work.
        """
        with self._lock:
            self._drop(session_id)
