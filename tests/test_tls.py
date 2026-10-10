"""The TLS refusal's other half: a real TLS-wrapped server actually serves HTTPS,
not merely that `build_ssl_context` returns a context object. A self-signed cert is
generated once, with `openssl` (a test-fixture tool here, not a runtime dependency --
the shipped console never invokes it; see `tools/fetch_wheel_cache.py`'s own docstring
for the same reasoning about `pip`).
"""
from __future__ import annotations

import shutil
import ssl
import subprocess
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from onetrace_console.config import Config
from onetrace_console.serve import Handler, _render_all_pages
from onetrace_console.signin import build_ssl_context
from onetrace_console.store import Store
from tests.test_checks import _require_installed

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None,
                                reason="this test's own fixture cert needs openssl; the "
                                      "console itself never invokes it at runtime")


@pytest.fixture(scope="module")
def self_signed_cert(tmp_path_factory):
    d = tmp_path_factory.mktemp("tls")
    cert, key = d / "cert.pem", d / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(key),
         "-out", str(cert), "-days", "1", "-nodes", "-subj", "/CN=localhost"],
        check=True, capture_output=True, timeout=30)
    return str(cert), str(key)


def test_a_tls_configured_server_actually_serves_https(self_signed_cert, tmp_path, examined):
    _require_installed()
    cert, key = self_signed_cert
    config = Config(sign_in={"enabled": True, "tls_cert_path": cert, "tls_key_path": key})

    store_root = tmp_path / "data"
    store_root.mkdir()
    Handler.store_root = store_root
    Handler.store = Store(store_root / "store")
    Handler.config = config
    from onetrace_console.access_log import AccessLog
    Handler.access_log = AccessLog(store_root / "access_log", max_segment_bytes=5_000_000)
    _render_all_pages(Handler.store, store_root, config)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    ctx = build_ssl_context(config)
    assert ctx is not None
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        client_ctx = ssl.create_default_context()
        client_ctx.check_hostname = False
        client_ctx.verify_mode = ssl.CERT_NONE   # self-signed test cert; not the point here
        examined(1, "a plain HTTPS request against the TLS-wrapped server")
        with urllib.request.urlopen(f"https://127.0.0.1:{port}/health", timeout=10,
                                    context=client_ctx) as resp:
            assert resp.status == 200
            assert resp.read() == b"ok\n"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_a_tls11_only_client_is_refused(self_signed_cert, tmp_path, examined):
    """`build_ssl_context` sets an explicit
    `minimum_version = TLSv1_2`, so a client that will only speak TLS 1.1 must
    fail its handshake against this server.
    """
    _require_installed()
    cert, key = self_signed_cert
    config = Config(sign_in={"enabled": True, "tls_cert_path": cert, "tls_key_path": key})

    store_root = tmp_path / "data"
    store_root.mkdir()
    Handler.store_root = store_root
    Handler.store = Store(store_root / "store")
    Handler.config = config
    from onetrace_console.access_log import AccessLog
    Handler.access_log = AccessLog(store_root / "access_log", max_segment_bytes=5_000_000)
    _render_all_pages(Handler.store, store_root, config)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    ctx = build_ssl_context(config)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client_ctx.check_hostname = False
        client_ctx.verify_mode = ssl.CERT_NONE
        try:
            client_ctx.maximum_version = ssl.TLSVersion.TLSv1_1
            client_ctx.minimum_version = ssl.TLSVersion.TLSv1_1
        except ValueError as e:
            pytest.skip(f"this OpenSSL build cannot construct a TLS 1.1-only client: {e}")
        examined(1, "a handshake attempt restricted to TLS 1.1 only")
        with pytest.raises((ssl.SSLError, OSError)):
            with urllib.request.urlopen(f"https://127.0.0.1:{port}/health", timeout=10,
                                        context=client_ctx):
                pass
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
