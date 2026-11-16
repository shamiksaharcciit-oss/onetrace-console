"""What the console asks Microsoft Entra ID for, in sign-in through OpenID Connect: the issuer's
discovery document, its signing keys (JWKS) and its token endpoint. Nothing else.

- **One origin.** Every call is to the configured issuer's own scheme, host and port: an endpoint the
  discovery document places anywhere else is refused before it is called, and no redirect is followed.
- **Time limits and size bounds.** Each call has a time limit (`timeout`) and reads at most
  `max_bytes` of answer.
- **The standard proxy variables** (`https_proxy`, `http_proxy`, `no_proxy`, upper case too) are
  honoured, as urllib reads them.
- **The keys** are cached. An unknown key id refreshes them once, and they are fetched at most once a
  minute (`refresh_interval`), so a stream of unknown key ids can't make the console hammer the issuer.

An `IssuerError`'s words are safe to show and to log: they never hold a token, a code or a claim's
value, and of a refusal from the token endpoint only its error code (`invalid_grant`, ...) is kept,
never the issuer's description.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit

#: The issuer's own error codes (RFC 6749 §5.2, OpenID Connect): the only part of a refusal kept.
_ERROR_CODE = re.compile(r"^[a-z_]{1,64}$")


class IssuerError(RuntimeError):
    """The issuer could not be asked, or refused. `str()` is plain words, safe on a page and in a log."""


@dataclass(frozen=True)
class Endpoints:
    authorization: str
    token: str
    jwks: str
    end_session: str | None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def _origin(url: str) -> tuple[str, str]:
    s = urlsplit(url)
    return s.scheme.lower(), s.netloc.lower()


class Issuer:
    def __init__(
        self,
        issuer: str,
        *,
        timeout: float = 10.0,
        refresh_interval: float = 60.0,
        max_bytes: int = 1 << 20,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.issuer = issuer
        self.timeout = timeout
        self.refresh_interval = refresh_interval
        self.max_bytes = max_bytes
        self.clock = clock
        self._origin = _origin(issuer)
        self._lock = threading.Lock()
        self._endpoints: Endpoints | None = None
        self._keys: dict[str, object] = {}
        self._keys_fetched_at: float | None = None

    # ------------------------------------------------------------------ the calls

    def _open(self, request: urllib.request.Request, what: str) -> bytes:
        if _origin(request.full_url) != self._origin:
            raise IssuerError(f"the {what} is not on the issuer's own address, so it is not called")
        #: Built per call, so the proxy variables are read as they are now.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(), _NoRedirect())
        try:
            with opener.open(request, timeout=self.timeout) as answer:
                body = answer.read(self.max_bytes + 1)
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:
                raise IssuerError(f"the issuer answered the {what} with a redirect, which is not followed") from None
            body = e.read(self.max_bytes + 1)
            raise _HttpRefusal(e.code, body) from None
        except TimeoutError:
            raise IssuerError(f"the issuer did not answer the {what} within {self.timeout:g} seconds") from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                raise IssuerError(f"the issuer did not answer the {what} within {self.timeout:g} seconds") from None
            raise IssuerError(f"the issuer could not be reached for the {what}") from None
        except OSError:
            raise IssuerError(f"the issuer could not be reached for the {what}") from None
        if len(body) > self.max_bytes:
            raise IssuerError(f"the issuer's answer to the {what} is larger than {self.max_bytes} bytes")
        return body

    def _json(self, body: bytes, what: str) -> dict:
        from onetrace_console.bounded_json import TooDeep, load_json_bounded

        try:
            doc = load_json_bounded(body, f"the issuer's answer to the {what}")
        except TooDeep:
            raise IssuerError(f"the issuer's answer to the {what} nests too deeply to read") from None
        except (ValueError, UnicodeDecodeError):
            raise IssuerError(f"the issuer's answer to the {what} is not JSON") from None
        if not isinstance(doc, dict):
            raise IssuerError(f"the issuer's answer to the {what} is not a JSON object")
        return doc

    def _get(self, url: str, what: str) -> dict:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            return self._json(self._open(request, what), what)
        except _HttpRefusal as r:
            raise IssuerError(f"the issuer answered the {what} with HTTP {r.status}") from None

    # ------------------------------------------------------------------ discovery

    def endpoints(self) -> Endpoints:
        """The discovery document's endpoints, read once and kept. Each must be on the issuer's own
        address, and the document must name this issuer exactly."""
        with self._lock:
            if self._endpoints is not None:
                return self._endpoints
        what = "discovery document"
        doc = self._get(self.issuer.rstrip("/") + "/.well-known/openid-configuration", what)
        if doc.get("issuer") != self.issuer:
            raise IssuerError("the issuer's discovery document names another issuer than the one configured")

        def on_origin(member: str) -> str:
            url = doc.get(member)
            if not isinstance(url, str) or not url:
                raise IssuerError(f"the issuer's discovery document has no {member}")
            if _origin(url) != self._origin:
                raise IssuerError(f"the {member} is not on the issuer's own address, so it is not called")
            return url

        endpoints = Endpoints(
            authorization=on_origin("authorization_endpoint"),
            token=on_origin("token_endpoint"),
            jwks=on_origin("jwks_uri"),
            #: Entra's own sign-out, offered after the console's; optional, and held to the same origin.
            end_session=on_origin("end_session_endpoint") if doc.get("end_session_endpoint") is not None else None,
        )
        with self._lock:
            self._endpoints = endpoints
        return endpoints

    # ------------------------------------------------------------------ the keys

    def _fetch_keys(self) -> None:
        import jwt

        doc = self._get(self.endpoints().jwks, "key set")
        keys: dict[str, object] = {}
        for jwk in doc.get("keys") or []:
            if not isinstance(jwk, dict) or not isinstance(jwk.get("kid"), str):
                continue
            if jwk.get("kty") != "RSA" or jwk.get("use", "sig") != "sig" or jwk.get("alg", "RS256") != "RS256":
                continue
            try:
                keys[jwk["kid"]] = jwt.PyJWK(jwk, algorithm="RS256").key
            except jwt.PyJWTError:
                continue
        self._keys = keys

    def signing_key(self, kid: str) -> object:
        """The issuer's public key for `kid`. An id not in the cache refreshes it, at most once per
        `refresh_interval`; an id still unknown is refused."""
        with self._lock:
            key = self._keys.get(kid)
            if key is not None:
                return key
            now = self.clock()
            if self._keys_fetched_at is not None and now - self._keys_fetched_at < self.refresh_interval:
                raise IssuerError("the ID token is signed with a key the issuer does not publish")
            self._keys_fetched_at = now
        self._fetch_keys()
        with self._lock:
            key = self._keys.get(kid)
        if key is None:
            raise IssuerError("the ID token is signed with a key the issuer does not publish")
        return key

    # ------------------------------------------------------------------ the token endpoint

    def redeem(self, form: dict[str, str]) -> dict:
        """POST `form` to the token endpoint; its JSON answer. A refusal keeps only the error code."""
        what = "token request"
        request = urllib.request.Request(
            self.endpoints().token,
            data=urlencode(form).encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        try:
            return self._json(self._open(request, what), what)
        except _HttpRefusal as r:
            from onetrace_console.bounded_json import TooDeep, load_json_bounded

            try:
                code = load_json_bounded(r.body, "the issuer's refusal of the token request").get("error")
            except (TooDeep, ValueError, AttributeError, UnicodeDecodeError):
                code = None
            said = f" ({code})" if isinstance(code, str) and _ERROR_CODE.match(code) else ""
            raise IssuerError(f"the issuer refused the token request{said}") from None


class _HttpRefusal(Exception):
    def __init__(self, status: int, body: bytes) -> None:
        super().__init__(status)
        self.status, self.body = status, body
