"""Sessions: per-connection state, never a stored record.

`docs/design/signin-and-roles.md` §1 item 5: *"A session is per-connection state, not a
stored record. Losing it means signing in again; it is never content-addressed, never
chained, never exported."* Built exactly that way: `SessionStore` holds sessions only in
memory, for the lifetime of the process. A restart signs everyone out -- the correct
behaviour for something that is deliberately not part of the console's own record.

Session ids and CSRF tokens come from `secrets.token_urlsafe` (stdlib, cryptographically
strong) -- never `random`, never a counter.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

SESSION_ID_BYTES = 32
CSRF_TOKEN_BYTES = 32


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    username: str
    csrf_token: str
    created_at: float          # time.monotonic(), for timeout arithmetic only
    last_seen_at: float


@dataclass
class SessionStore:
    """In-memory only -- see this module's own docstring for why. One lock guards all
    of it; sign-in traffic on a small console does not need finer-grained locking.
    """
    idle_timeout_seconds: float
    absolute_timeout_seconds: float

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def create(self, username: str, *, now: float | None = None) -> Session:
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
            created_at=now, last_seen_at=now)
        with self._lock:
            self._sessions[session.session_id] = session
        return session

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
            touched = Session(session_id=session.session_id, username=session.username,
                              csrf_token=session.csrf_token, created_at=session.created_at,
                              last_seen_at=now)
            self._sessions[session_id] = touched
            return touched

    def invalidate(self, session_id: str) -> None:
        """Sign-out: removed from the server side, not merely told to the client to
        forget its cookie -- a stolen cookie presented after this must not work.
        """
        with self._lock:
            self._sessions.pop(session_id, None)
