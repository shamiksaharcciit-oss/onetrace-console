"""A fake Microsoft Entra ID, in the test process, for sign-in through OpenID Connect.

It serves one tenant's discovery document, its keys (JWKS), an authorization endpoint that signs in
whichever user a test names (as if that person had entered their password), a token endpoint that
enforces PKCE and single-use codes and checks the client's credential, and a sign-out endpoint. Its
signing keys are made per instance, so per test. It never touches a real tenant: its issuer is
`http://127.0.0.1:<port>/<tenant>/v2.0`.

Every request is counted (`hits`), so a test can say what the console asked for and how often.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SECRET = "fake-entra-client-secret-0123456789"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def rsa_key():
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_jwk(key, kid: str) -> dict:
    nums = key.public_key().public_numbers()

    def n2b(n: int) -> str:
        return b64url(n.to_bytes((n.bit_length() + 7) // 8, "big"))

    return {"kty": "RSA", "use": "sig", "kid": kid, "n": n2b(nums.n), "e": n2b(nums.e)}


class FakeEntra:
    def __init__(self, *, tenant: str = TENANT, client_id: str = CLIENT, client_secret: str | None = SECRET):
        self.tenant, self.client_id, self.client_secret = tenant, client_id, client_secret
        #: The client certificate's public key, where the console signs a client assertion with it.
        self.client_public_key = None
        self.keys: dict[str, object] = {}
        self.current_kid = self.rotate()
        #: Who signs in at the authorization endpoint next.
        self.user = {
            "oid": "99999999-8888-7777-6666-555555555555",
            "name": "Ada Lovelace",
            "roles": ["onetrace.viewer"],
        }
        #: Changes to the next ID token's claims and header, and a replacement for the token itself.
        self.claims_override: dict = {}
        self.header_override: dict = {}
        self.token_override = None
        self.discovery_override: dict = {}
        #: Paths whose answer waits this many seconds first.
        self.stall: dict[str, float] = {}
        self.codes: dict[str, dict] = {}
        self.hits: list[tuple[str, str]] = []
        self.token_forms: list[dict] = []
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None

    # ------------------------------------------------------------------ addresses

    @property
    def base(self) -> str:
        assert self._server is not None, "start() first"
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    @property
    def issuer(self) -> str:
        return f"{self.base}/{self.tenant}/v2.0"

    def endpoint(self, name: str) -> str:
        return {
            "authorize": f"{self.base}/{self.tenant}/oauth2/v2.0/authorize",
            "token": f"{self.base}/{self.tenant}/oauth2/v2.0/token",
            "keys": f"{self.base}/{self.tenant}/discovery/v2.0/keys",
            "logout": f"{self.base}/{self.tenant}/oauth2/v2.0/logout",
        }[name]

    def count(self, name: str) -> int:
        path = (
            urlsplit(self.endpoint(name)).path
            if name != "discovery"
            else f"/{self.tenant}/v2.0/.well-known/openid-configuration"
        )
        return sum(1 for _m, p in self.hits if p == path)

    # ------------------------------------------------------------------ keys and tokens

    def rotate(self) -> str:
        """A new signing key, published beside the others, and used from now on."""
        kid = secrets.token_hex(8)
        self.keys[kid] = rsa_key()
        self.current_kid = kid
        return kid

    def id_token(self, *, nonce: str, user: dict | None = None) -> str:
        import jwt

        user = self.user if user is None else user
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "aud": self.client_id,
            "tid": self.tenant,
            "oid": user["oid"],
            "name": user["name"],
            "preferred_username": user.get("preferred_username", "ada@example.org"),
            "nonce": nonce,
            "iat": now,
            "nbf": now,
            "exp": now + 3600,
        }
        if user.get("roles") is not None:
            claims["roles"] = list(user["roles"])
        claims.update(self.claims_override)
        claims = {k: v for k, v in claims.items() if v is not DROP}
        if self.token_override is not None:
            return self.token_override(claims, self)
        headers = {"kid": self.current_kid, **self.header_override}
        return jwt.encode(claims, self.keys[self.current_kid], algorithm="RS256", headers=headers)

    # ------------------------------------------------------------------ the server

    def __enter__(self) -> FakeEntra:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def start(self) -> None:
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802
                fake._answer(self, "GET")

            def do_POST(self) -> None:  # noqa: N802
                fake._answer(self, "POST")

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _send(self, h, status: int, body: bytes = b"", ctype: str = "application/json", headers=()) -> None:
        h.send_response(status)
        h.send_header("Content-Type", ctype)
        h.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            h.send_header(k, v)
        h.end_headers()
        h.wfile.write(body)

    def _json(self, h, status: int, obj) -> None:
        self._send(h, status, json.dumps(obj).encode())

    def _answer(self, h, method: str) -> None:
        split = urlsplit(h.path)
        with self._lock:
            self.hits.append((method, split.path))
        if split.path in self.stall:
            time.sleep(self.stall[split.path])
        t = f"/{self.tenant}"
        if method == "GET" and split.path == f"{t}/v2.0/.well-known/openid-configuration":
            doc = {
                "issuer": self.issuer,
                "authorization_endpoint": self.endpoint("authorize"),
                "token_endpoint": self.endpoint("token"),
                "jwks_uri": self.endpoint("keys"),
                "end_session_endpoint": self.endpoint("logout"),
                "response_modes_supported": ["query", "fragment", "form_post"],
                "id_token_signing_alg_values_supported": ["RS256"],
            }
            doc.update(self.discovery_override)
            return self._json(h, 200, {k: v for k, v in doc.items() if v is not DROP})
        if method == "GET" and split.path == f"{t}/discovery/v2.0/keys":
            return self._json(h, 200, {"keys": [public_jwk(k, kid) for kid, k in self.keys.items()]})
        if method == "GET" and split.path == f"{t}/oauth2/v2.0/authorize":
            return self._authorize(h, {k: v[0] for k, v in parse_qs(split.query).items()})
        if method == "POST" and split.path == f"{t}/oauth2/v2.0/token":
            length = int(h.headers.get("Content-Length") or 0)
            form = {k: v[0] for k, v in parse_qs(h.rfile.read(length).decode()).items()}
            return self._token(h, form)
        if method == "GET" and split.path == f"{t}/oauth2/v2.0/logout":
            return self._send(h, 200, b"signed out of the fake", "text/plain")
        return self._send(h, 404, b"not here", "text/plain")

    def _authorize(self, h, q: dict) -> None:
        """The person signs in: a code for the console's redirect URI, holding what the token
        request must match."""
        if q.get("client_id") != self.client_id or q.get("response_type") != "code":
            return self._send(h, 400, b"bad authorize request", "text/plain")
        if q.get("code_challenge_method") != "S256" or not q.get("code_challenge"):
            return self._send(h, 400, b"PKCE S256 required", "text/plain")
        code = secrets.token_urlsafe(24)
        self.codes[code] = {
            "nonce": q.get("nonce", ""),
            "challenge": q["code_challenge"],
            "redirect_uri": q.get("redirect_uri", ""),
            "used": False,
            "user": dict(self.user),
        }
        target = q.get("redirect_uri", "") + "?" + urlencode({"code": code, "state": q.get("state", "")})
        return self._send(h, 302, b"", "text/plain", [("Location", target)])

    def _client_ok(self, form: dict) -> bool:
        if form.get("client_assertion_type") == "urn:ietf:params:oauth:client-assertion-type:jwt-bearer":
            import jwt

            if self.client_public_key is None:
                return False
            try:
                c = jwt.decode(
                    form.get("client_assertion", ""),
                    self.client_public_key,
                    algorithms=["RS256"],
                    audience=self.endpoint("token"),
                )
            except jwt.PyJWTError:
                return False
            return c.get("iss") == self.client_id and c.get("sub") == self.client_id and bool(c.get("jti"))
        return self.client_secret is not None and form.get("client_secret") == self.client_secret

    def _token(self, h, form: dict) -> None:
        self.token_forms.append(form)
        if form.get("grant_type") != "authorization_code" or form.get("client_id") != self.client_id:
            return self._json(h, 400, {"error": "invalid_request", "error_description": "AADSTS900144 fake"})
        if not self._client_ok(form):
            return self._json(h, 401, {"error": "invalid_client", "error_description": "AADSTS7000215 fake"})
        grant = self.codes.get(form.get("code", ""))
        if grant is None or grant["used"]:
            return self._json(h, 400, {"error": "invalid_grant", "error_description": "AADSTS54005 code redeemed"})
        grant["used"] = True
        if form.get("redirect_uri") != grant["redirect_uri"]:
            return self._json(h, 400, {"error": "invalid_grant", "error_description": "AADSTS50011 redirect"})
        verifier = form.get("code_verifier", "")
        if b64url(hashlib.sha256(verifier.encode()).digest()) != grant["challenge"]:
            return self._json(h, 400, {"error": "invalid_grant", "error_description": "AADSTS501481 PKCE"})
        token = self.id_token(nonce=grant["nonce"], user=grant["user"])
        return self._json(h, 200, {"token_type": "Bearer", "id_token": token, "access_token": "fake-access"})


#: Put in `claims_override` or `discovery_override` to leave a member out.
DROP = object()
