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
    #: The time (time.time_ns()) before which an account's sessions are ended, or None
    #: (`AccountStore.sessions_ended_at`); a session made before it is gone.
    ended: Callable[[str], int | None] | None = None
    #: The wall clock a session's `expires_at` is read against.
    wall: Callable[[], float] = time.time

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def create(
        self,
        username: str,
        *,
        now: float | None = None,
        role: str | None = None,
        display_name: str = "",
        expires_at: float | None = None,
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
        )
        with self._lock:
            self._sessions[session.session_id] = session
            if self.max_per_account is not None:
                mine = sorted(
                    (s for s in self._sessions.values() if s.username == username and not self._expired(s, now)),
                    key=lambda s: (s.created_at, s.created_wall_ns),
                )
                for old in mine[: max(0, len(mine) - self.max_per_account)]:
                    del self._sessions[old.session_id]
        return session

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
            if now - session.created_at > self.absolute_timeout_seconds:
                del self._sessions[session_id]
                return None
            if now - session.last_seen_at > self.idle_timeout_seconds:
                del self._sessions[session_id]
                return None
            if session.expires_at is not None and self.wall() >= session.expires_at:
                del self._sessions[session_id]
                return None
        ended = self.ended(session.username) if self.ended is not None else None
        with self._lock:
            if ended is not None and session.created_wall_ns <= ended:
                self._sessions.pop(session_id, None)
                return None
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
            self._sessions.pop(session_id, None)
