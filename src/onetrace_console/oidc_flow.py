"""Sign-in through Entra ID: the authorization code flow.

- **PKCE** (S256): a verifier made per sign-in, its challenge sent with the authorization request, the
  verifier with the token request.
- **`state` and `nonce`**, made per sign-in, are kept here, server-side, under a flow id the browser
  holds in a cookie (`HttpOnly`, `Secure` where cookies are, `SameSite=Lax`, ten minutes). A flow is
  taken once (`FlowStore.take`): a callback without the cookie, after ten minutes, or a second time is
  refused, and so is a `state` that is not the flow's.
- **`response_mode=query`**: the code comes back in the callback's query, never a fragment.
- **After sign-in**, the browser goes only to the same-origin relative path recorded when the flow
  started (`safe_next`), never to one the callback names.

`SignInRefused`'s words are plain and safe to show: no token, code or claim value.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

FLOW_COOKIE = "onetrace_oidc"
FLOW_COOKIE_PATH = "/signin/oidc"
FLOW_SECONDS = 600
SCOPE = "openid profile"
#: At most this many flows are kept; beyond it the oldest is dropped (its browser starts again).
MAX_FLOWS = 10_000
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

NOT_THIS_BROWSER = (
    "This sign-in can't be finished in this browser: it was started in another, it was finished "
    "already, or it took longer than ten minutes."
)
STATE_MISMATCH = "This sign-in's state doesn't match this browser's."


class SignInRefused(Exception):
    """A sign-in refused, in plain words safe on a page and in a log."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class Flow:
    state: str
    nonce: str
    verifier: str
    next_path: str
    started: float

    @property
    def challenge(self) -> str:
        return _b64url(hashlib.sha256(self.verifier.encode("ascii")).digest())


class FlowStore:
    """The flows begun and not yet finished, in memory only, as sessions are."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic, max_flows: int = MAX_FLOWS) -> None:
        self.clock = clock
        self.max_flows = max_flows
        self._lock = threading.Lock()
        self._flows: OrderedDict[str, Flow] = OrderedDict()

    def start(self, next_path: str) -> tuple[str, Flow]:
        flow = Flow(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            #: 43 to 128 characters (RFC 7636 §4.1): 64 here.
            verifier=secrets.token_urlsafe(48),
            next_path=safe_next(next_path),
            started=self.clock(),
        )
        flow_id = secrets.token_urlsafe(32)
        with self._lock:
            self._flows[flow_id] = flow
            while len(self._flows) > self.max_flows:
                self._flows.popitem(last=False)
        return flow_id, flow

    def take(self, flow_id: str | None) -> Flow | None:
        """The flow, removed: a flow is finished once. None for an unknown id or one past ten minutes."""
        if not flow_id:
            return None
        with self._lock:
            flow = self._flows.pop(flow_id, None)
        if flow is None or self.clock() - flow.started > FLOW_SECONDS:
            return None
        return flow


def safe_next(raw: str | None) -> str:
    """A same-origin relative path, else `/`: it starts with one `/`, names no other host (`//`, `/\\`),
    and holds no control character or backslash."""
    if not raw or not isinstance(raw, str):
        return "/"
    if not raw.startswith("/") or raw.startswith("//") or "\\" in raw:
        return "/"
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw):
        return "/"
    return raw


def authorize_url(authorization_endpoint: str, settings, flow: Flow) -> str:
    query = {
        "client_id": settings.client_id,
        "response_type": "code",
        "redirect_uri": settings.redirect_uri,
        "response_mode": "query",
        "scope": SCOPE,
        "state": flow.state,
        "nonce": flow.nonce,
        "code_challenge": flow.challenge,
        "code_challenge_method": "S256",
    }
    return f"{authorization_endpoint}?{urlencode(query)}"


def client_credential(settings, token_endpoint: str, *, now: float | None = None) -> dict[str, str]:
    """The token request's client authentication: a client assertion signed with the certificate's key
    (private_key_jwt), or the secret."""
    credential = settings.credential
    if credential.kind == "secret":
        return {"client_secret": credential.secret}
    import jwt

    now = int(time.time() if now is None else now)
    assertion = jwt.encode(
        {
            "aud": token_endpoint,
            "iss": settings.client_id,
            "sub": settings.client_id,
            "jti": str(uuid.uuid4()),
            "nbf": now,
            "iat": now,
            "exp": now + 300,
        },
        credential.private_key,
        algorithm="RS256",
        headers={"x5t": credential.x5t},
    )
    return {"client_assertion_type": ASSERTION_TYPE, "client_assertion": assertion}


def check_callback(query: dict[str, str], flow: Flow | None) -> str:
    """The code, from a callback that belongs to `flow`. Refused otherwise."""
    import re

    if flow is None:
        raise SignInRefused(NOT_THIS_BROWSER)
    state = query.get("state", "")
    if not state or not hmac.compare_digest(state.encode("utf-8"), flow.state.encode("utf-8")):
        raise SignInRefused(STATE_MISMATCH)
    error = query.get("error")
    if error is not None:
        said = f" ({error})" if re.fullmatch(r"[a-z_]{1,64}", error) else ""
        raise SignInRefused(f"Microsoft did not sign you in{said}.")
    code = query.get("code", "")
    if not code:
        raise SignInRefused("Microsoft sent no sign-in code.")
    return code


def finish(code: str, flow: Flow, settings, issuer, *, now: float | None = None):
    """Redeem the code, check the ID token and say who signed in (`oidc_identity.Identity`). Raises
    `SignInRefused`, or `oidc_identity.NoRole`."""
    from onetrace_console.oidc_identity import identity
    from onetrace_console.oidc_issuer import IssuerError
    from onetrace_console.oidc_token import TokenRefused, check_id_token

    try:
        endpoints = issuer.endpoints()
        answer = issuer.redeem(
            {
                "client_id": settings.client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.redirect_uri,
                "code_verifier": flow.verifier,
                "scope": SCOPE,
                **client_credential(settings, endpoints.token, now=now),
            }
        )
    except IssuerError as e:
        raise SignInRefused(f"The sign-in could not be finished: {e}.") from None
    token = answer.get("id_token")
    if not isinstance(token, str) or not token:
        raise SignInRefused("The sign-in could not be finished: the issuer sent no ID token.")
    try:
        claims = check_id_token(
            token,
            issuer=issuer,
            expected_issuer=settings.issuer,
            client_id=settings.client_id,
            tenant_id=settings.tenant_id,
            nonce=flow.nonce,
            now=now,
        )
        return identity(claims, session_max_hours=settings.session_max_hours, now=time.time() if now is None else now)
    except TokenRefused as e:
        raise SignInRefused(f"The sign-in was refused: {e}.") from None
