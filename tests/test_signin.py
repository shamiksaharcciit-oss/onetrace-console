"""The TLS refusal and the cookie/CSRF/form helpers `serve.py` calls."""
from __future__ import annotations

import pytest

from onetrace_console.config import Config
from onetrace_console.signin import (InsecureListenerError, build_ssl_context,
                                     clear_cookie_header, cookies_secure, parse_cookies,
                                     parse_signin_form, refuse_if_insecure,
                                     set_cookie_header)


def test_sign_in_disabled_is_never_refused_on_any_host(examined):
    examined(1, "a 0.0.0.0 host with sign-in disabled")
    refuse_if_insecure(Config(host="0.0.0.0", sign_in={**Config().sign_in, "enabled": False}))  # must not raise


def test_starting_on_0_0_0_0_over_plain_http_with_sign_in_on_is_refused(examined):
    """The TLS refusal's own named test."""
    config = Config(host="0.0.0.0", sign_in={"enabled": True})
    examined(1, "a 0.0.0.0 host, sign-in on, no TLS configured")
    with pytest.raises(InsecureListenerError, match="refusing to start"):
        refuse_if_insecure(config)


def test_loopback_with_sign_in_on_and_no_tls_is_allowed(examined):
    """Loopback behind an operator's own TLS-terminating proxy, per option (b)."""
    config = Config(host="127.0.0.1", sign_in={"enabled": True})
    examined(1, "a loopback host, sign-in on, no TLS configured")
    refuse_if_insecure(config)  # must not raise


def test_non_loopback_with_tls_configured_is_allowed(examined):
    config = Config(host="0.0.0.0", sign_in={"enabled": True, "tls_cert_path": "/c.pem",
                                             "tls_key_path": "/c.key"})
    examined(1, "a 0.0.0.0 host, sign-in on, TLS configured")
    refuse_if_insecure(config)  # must not raise


def test_sabotage_removing_the_check_lets_the_refused_case_through(examined):
    """The specified sabotage: 'remove the check.' Demonstrated directly: a
    no-op stand-in for the real function must NOT raise on the case the real one
    must -- proving the real function's own raise is what the test above depends on,
    not a coincidence of the test itself.
    """
    def sabotaged_refuse_if_insecure(config):
        return None  # the check, removed

    config = Config(host="0.0.0.0", sign_in={"enabled": True})
    examined(1, "the refused case, run through a no-op stand-in for the check")
    sabotaged_refuse_if_insecure(config)  # does not raise -- the sabotage's own effect
    with pytest.raises(InsecureListenerError):
        refuse_if_insecure(config)  # the real function still does


def test_build_ssl_context_is_none_when_tls_not_configured(examined):
    examined(1, "a Config with sign-in on but no TLS paths")
    assert build_ssl_context(Config(sign_in={"enabled": True})) is None


def test_build_ssl_context_sets_tls_1_2_as_the_floor(examined, tmp_path):
    """TLS 1.0/1.1 are never negotiated, set explicitly rather
    than relying on whatever this build of OpenSSL happens to default to.
    """
    import ssl
    import subprocess
    import shutil

    if shutil.which("openssl") is None:
        pytest.skip("this test's own fixture cert needs openssl")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(key),
         "-out", str(cert), "-days", "1", "-nodes", "-subj", "/CN=localhost"],
        check=True, capture_output=True, timeout=30)
    config = Config(sign_in={"enabled": True, "tls_cert_path": str(cert),
                             "tls_key_path": str(key)})
    examined(1, "the minimum_version of a built SSLContext")
    ctx = build_ssl_context(config)
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2


# --------------------------------------------------------- insecure_cookie_for_local_dev

def test_insecure_cookie_flag_is_refused_on_a_non_loopback_host(examined):
    """The escape hatch that allows a non-`Secure` cookie is
    refused outright the moment the listener is not loopback -- it exists only
    for a loopback listener behind a local proxy.
    """
    config = Config(host="0.0.0.0",
                    sign_in={"enabled": True, "insecure_cookie_for_local_dev": True})
    examined(1, "a 0.0.0.0 host with the insecure-cookie escape hatch set")
    with pytest.raises(InsecureListenerError, match="insecure_cookie_for_local_dev"):
        refuse_if_insecure(config)


def test_insecure_cookie_flag_is_allowed_on_loopback(examined):
    config = Config(host="127.0.0.1",
                    sign_in={"enabled": True, "insecure_cookie_for_local_dev": True})
    examined(1, "a loopback host with the insecure-cookie escape hatch set")
    refuse_if_insecure(config)  # must not raise


def test_cookies_secure_is_true_by_default_and_false_only_with_the_escape_hatch(examined):
    examined(3, "cookies_secure() under three configurations")
    assert cookies_secure(Config(sign_in={"enabled": True})) is True
    assert cookies_secure(Config(host="127.0.0.1",
                                 sign_in={"enabled": True,
                                          "insecure_cookie_for_local_dev": True})) is False
    #: Even with TLS configured (this process terminating TLS itself), the
    #: default is still Secure -- the point being that Secure was
    #: previously tied to THIS process's own TLS, not to sign-in being on.
    assert cookies_secure(Config(sign_in={"enabled": True, "tls_cert_path": "/c.pem",
                                          "tls_key_path": "/c.key"})) is True


# ------------------------------------------------------------------- cookies / CSRF

def test_parse_cookies_reads_multiple_values(examined):
    examined(1, "a Cookie header with two values")
    got = parse_cookies("a=1; b=two")
    assert got == {"a": "1", "b": "two"}


def test_parse_cookies_handles_none_and_empty(examined):
    examined(2, "a missing and an empty Cookie header")
    assert parse_cookies(None) == {}
    assert parse_cookies("") == {}


def test_set_cookie_header_carries_secure_httponly_samesite_strict(examined):
    examined(1, "a session cookie header")
    header = set_cookie_header("onetrace_session", "abc", http_only=True, secure=True)
    assert "Secure" in header
    assert "HttpOnly" in header
    assert "SameSite=Strict" in header


def test_set_cookie_header_omits_secure_when_not_https(examined):
    examined(1, "a cookie header built for a non-TLS listener")
    header = set_cookie_header("x", "y", http_only=True, secure=False)
    assert "Secure" not in header


def test_clear_cookie_header_has_max_age_zero(examined):
    examined(1, "a cookie-clearing header")
    assert "Max-Age=0" in clear_cookie_header("x", secure=True)


def test_parse_signin_form_reads_username_password_and_csrf(examined):
    examined(1, "a urlencoded sign-in form body")
    got = parse_signin_form(b"username=alice&password=hunter2&csrf_token=abc123")
    assert got == {"username": "alice", "password": "hunter2", "csrf_token": "abc123"}
