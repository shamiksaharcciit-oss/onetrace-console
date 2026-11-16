"""Sign-in through Entra ID: what the console asks the issuer for (`oidc_issuer.Issuer`). Only the
configured issuer's discovery document, its keys and its token endpoint, each with a time limit, through
the standard proxy variables, with no redirect followed; the keys cached, refreshed once on an unknown
key id and at most once a minute."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.fake_entra import DROP, FakeEntra
from tests.http_limits import limit


@pytest.fixture
def fake():
    with FakeEntra() as f:
        yield f


def _issuer(fake, **kw):
    from onetrace_console.oidc_issuer import Issuer

    return Issuer(fake.issuer, **kw)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_discovery_document_is_read_once_and_names_the_endpoints(fake, examined):
    examined(4, "the three endpoints, and one fetch for two reads")
    issuer = _issuer(fake)
    assert issuer.endpoints().token == fake.endpoint("token")
    assert issuer.endpoints().authorization == fake.endpoint("authorize")
    assert issuer.endpoints().end_session == fake.endpoint("logout")
    assert fake.count("discovery") == 1


def test_a_discovery_document_naming_another_issuer_is_refused(fake, examined):
    from onetrace_console.oidc_issuer import IssuerError

    examined(1, "issuer in the document not the configured one")
    fake.discovery_override = {"issuer": "http://127.0.0.1:1/other/v2.0"}
    with pytest.raises(IssuerError, match="names another issuer"):
        _issuer(fake).endpoints()


@pytest.mark.parametrize("member", ["token_endpoint", "jwks_uri", "authorization_endpoint", "end_session_endpoint"])
def test_an_endpoint_off_the_issuer_s_origin_is_refused_and_never_called(fake, member, examined):
    from onetrace_console.oidc_issuer import IssuerError

    examined(2, f"{member} on another origin: refused, and that origin never reached")
    with FakeEntra() as other:
        fake.discovery_override = {member: other.endpoint("keys")}
        issuer = _issuer(fake)
        with pytest.raises(IssuerError, match="not on the issuer's own address"):
            issuer.endpoints()
        assert other.hits == []


def test_a_missing_endpoint_is_refused(fake, examined):
    from onetrace_console.oidc_issuer import IssuerError

    examined(1, "no token_endpoint")
    fake.discovery_override = {"token_endpoint": DROP}
    with pytest.raises(IssuerError, match="token_endpoint"):
        _issuer(fake).endpoints()


def test_the_keys_are_cached(fake, examined):
    examined(2, "two reads of a known key, one fetch")
    issuer = _issuer(fake)
    kid = fake.current_kid
    assert issuer.signing_key(kid) is not None and issuer.signing_key(kid) is not None
    assert fake.count("keys") == 1


def test_a_new_key_id_is_fetched_once_and_accepted(fake, examined):
    examined(2, "a rotated key: one more fetch, then known")
    clock = _Clock()
    issuer = _issuer(fake, clock=clock)
    issuer.signing_key(fake.current_kid)
    clock.now += 61
    new = fake.rotate()
    assert issuer.signing_key(new) is not None
    assert fake.count("keys") == 2


def test_a_stream_of_unknown_key_ids_fetches_the_keys_at_most_once_a_minute(fake, examined):
    from onetrace_console.oidc_issuer import IssuerError

    examined(3, "a hundred unknown kids in one minute, then one more after it")
    clock = _Clock()
    issuer = _issuer(fake, clock=clock)
    issuer.signing_key(fake.current_kid)
    clock.now += 61
    for n in range(100):
        with pytest.raises(IssuerError, match="a key the issuer does not publish"):
            issuer.signing_key(f"unknown-{n}")
        clock.now += 0.5
    assert fake.count("keys") == 2, "one fetch at start, one refresh for the first unknown id"
    clock.now += 61
    with pytest.raises(IssuerError):
        issuer.signing_key("unknown-again")
    assert fake.count("keys") == 3


def test_a_key_the_issuer_says_is_not_for_rs256_signatures_is_not_used(fake, examined):
    """A published key marked for encryption, or for another algorithm, is passed over."""
    from onetrace_console.oidc_issuer import IssuerError
    from tests import fake_entra

    examined(1, "a key published with use enc")
    original = fake_entra.public_jwk
    try:
        fake_entra.public_jwk = lambda key, kid: {**original(key, kid), "use": "enc"}
        with pytest.raises(IssuerError, match="a key the issuer does not publish"):
            _issuer(fake).signing_key(fake.current_kid)
    finally:
        fake_entra.public_jwk = original


def test_a_call_that_does_not_answer_within_its_limit_is_refused(fake, examined):
    import time

    from onetrace_console.oidc_issuer import IssuerError

    examined(2, "a stalled discovery: refused, within its limit")
    fake.stall[f"/{fake.tenant}/v2.0/.well-known/openid-configuration"] = 3.0
    started = time.monotonic()
    with pytest.raises(IssuerError, match="did not answer the discovery document within 0.5 seconds"):
        _issuer(fake, timeout=0.5).endpoints()
    assert time.monotonic() - started < 2.5


def test_a_redirect_is_not_followed(fake, examined):
    from onetrace_console.oidc_issuer import IssuerError

    examined(2, "discovery answering 302 to another origin: refused, that origin never reached")
    with FakeEntra() as other:

        def redirected(h, method, _orig=fake._answer):
            if "openid-configuration" in h.path:
                return fake._send(
                    h, 302, b"", "text/plain", [("Location", other.issuer + "/.well-known/openid-configuration")]
                )
            return _orig(h, method)

        fake._answer = redirected
        with pytest.raises(IssuerError):
            _issuer(fake).endpoints()
        assert other.hits == []


def test_the_token_endpoint_answers_its_json_and_a_refusal_names_only_its_code(fake, examined):
    from onetrace_console.oidc_issuer import IssuerError

    examined(2, "a refused code: the error code said, its description not")
    issuer = _issuer(fake)
    with pytest.raises(IssuerError) as e:
        issuer.redeem({"grant_type": "authorization_code", "client_id": fake.client_id, "client_secret": "wrong"})
    assert "invalid_client" in str(e.value)
    assert "AADSTS" not in str(e.value), "the issuer's description is not repeated"


class _Proxy(BaseHTTPRequestHandler):
    seen: list[str] = []
    upstream = ""

    def log_message(self, *a) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        import urllib.request

        type(self).seen.append(self.path)
        #: An absolute-form target, as a client sends a proxy: forward it to the fake, by its real address.
        target = self.path.replace("http://issuer.test", type(self).upstream)
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(target, timeout=limit(5)) as r:
            body = r.read()
        body = body.replace(type(self).upstream.encode(), b"http://issuer.test")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_the_standard_proxy_variables_are_honoured(fake, monkeypatch, examined):
    """An issuer named `issuer.test` (no such host) is reached only through the proxy that
    `http_proxy` names."""
    from onetrace_console.oidc_issuer import Issuer

    examined(2, "discovery reached through the proxy, by its absolute address")
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), _Proxy)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    _Proxy.seen, _Proxy.upstream = [], fake.base
    try:
        for name in ("http_proxy", "HTTP_PROXY"):
            monkeypatch.setenv(name, f"http://127.0.0.1:{proxy.server_address[1]}")
        for name in ("no_proxy", "NO_PROXY"):
            monkeypatch.setenv(name, "127.0.0.1,localhost,::1")
        issuer = Issuer(f"http://issuer.test/{fake.tenant}/v2.0")
        assert issuer.endpoints().token == f"http://issuer.test/{fake.tenant}/oauth2/v2.0/token"
        assert _Proxy.seen == [f"http://issuer.test/{fake.tenant}/v2.0/.well-known/openid-configuration"]
    finally:
        proxy.shutdown()
        proxy.server_close()


def test_an_answer_larger_than_its_bound_is_refused(fake, examined):
    from onetrace_console.oidc_issuer import IssuerError

    examined(1, "a discovery document over the bound")
    fake.discovery_override = {"padding": "x" * 300_000}
    with pytest.raises(IssuerError, match="larger than"):
        _issuer(fake, max_bytes=100_000).endpoints()
