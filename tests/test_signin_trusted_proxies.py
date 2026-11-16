"""The sign-in limit behind a proxy: `sign_in.trusted_proxies` (addresses and CIDR ranges, empty by default).
Only where the connection's peer is in it, the client address the per-client limit counts is the rightmost
`X-Forwarded-For` entry that is not a trusted proxy; otherwise it is the peer's, as before. Held on the
function, and over real HTTP on the sign-in limit itself.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from onetrace_console.config import Config, ConfigError, load
from onetrace_console.rate_limit import RateLimiter, client_address
from onetrace_console.serve import Handler
from tests.test_signin_flow import _get_signin_form, _post, signin_enabled  # noqa: F401

PROXY = ["127.0.0.1", "10.0.0.0/8"]


@pytest.mark.parametrize(
    "peer, forwarded, want",
    [
        #: An untrusted peer's header is ignored.
        ("203.0.113.9", ["198.51.100.1"], "203.0.113.9"),
        #: A trusted peer's is used.
        ("127.0.0.1", ["198.51.100.1"], "198.51.100.1"),
        #: A spoofed leftmost entry is passed over for the rightmost that is not a trusted proxy.
        ("127.0.0.1", ["6.6.6.6, 198.51.100.1"], "198.51.100.1"),
        ("127.0.0.1", ["6.6.6.6, 198.51.100.1, 10.1.2.3"], "198.51.100.1"),
        ("127.0.0.1", ["6.6.6.6", "198.51.100.1"], "198.51.100.1"),
        #: A trusted peer with no header, or a header naming only trusted proxies.
        ("127.0.0.1", [], "127.0.0.1"),
        ("127.0.0.1", ["10.1.2.3"], "10.1.2.3"),
        #: An entry that is not an address, where the client would be, leaves the peer's.
        ("127.0.0.1", ["6.6.6.6, not-an-address"], "127.0.0.1"),
        ("::1", ["2001:db8::5"], "::1"),
    ],
)
def test_the_client_address(peer, forwarded, want, examined):
    examined(1, f"peer {peer}, X-Forwarded-For {forwarded}")
    assert client_address(peer, forwarded, PROXY) == want


def test_with_no_trusted_proxy_the_header_is_never_read(examined):
    examined(1, "the default")
    assert Config().sign_in["trusted_proxies"] == []
    assert client_address("127.0.0.1", ["198.51.100.1"], []) == "127.0.0.1"


def _try(base, forwarded: str | None) -> int:
    csrf, token = _get_signin_form(base)
    headers = {"Cookie": f"onetrace_csrf={csrf}", "Content-Type": "application/x-www-form-urlencoded"}
    if forwarded is not None:
        headers["X-Forwarded-For"] = forwarded
    try:
        return _post(
            base, "/signin", f"username=alice&password=wrong+wrong+wrong&csrf_token={token}".encode(), headers=headers
        )[0]
    except urllib.error.HTTPError as e:
        return e.code


@pytest.mark.parametrize(
    "trusted, forwarded, want",
    [
        ([], ["198.51.100.1", "198.51.100.2"], [401, 429]),
        (["127.0.0.1"], ["198.51.100.1", "198.51.100.2"], [401, 401]),
        (["127.0.0.1"], ["6.6.6.6, 198.51.100.1", "7.7.7.7, 198.51.100.1"], [401, 429]),
        #: The same spoofed leftmost entry, two clients: counted apart, by the entry the proxy appended.
        (["127.0.0.1"], ["6.6.6.6, 198.51.100.1", "6.6.6.6, 198.51.100.2"], [401, 401]),
    ],
)
def test_the_sign_in_limit_counts_the_address_the_proxy_gave(
    signin_enabled, monkeypatch, trusted, forwarded, want, examined
):
    base = signin_enabled
    monkeypatch.setattr(Handler, "config", Config(sign_in={"enabled": True, "trusted_proxies": trusted}))
    monkeypatch.setattr(Handler, "rate_limit_per_client", RateLimiter(max_attempts=1, window_seconds=60))
    got = [_try(base, f) for f in forwarded]
    examined(len(got), "sign-in attempts")
    assert got == want


@pytest.mark.parametrize("value", ["127.0.0.1", ["not-an-address"], ["10.0.0.0/33"], [7]])
def test_a_trusted_proxies_value_that_is_not_a_list_of_addresses_is_refused(tmp_path, value, examined):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"sign_in": {"trusted_proxies": value}}), encoding="utf-8")
    examined(1, f"trusted_proxies {value!r}")
    with pytest.raises(ConfigError, match=r"sign_in\.trusted_proxies must be"):
        load(p)


def test_a_list_of_addresses_and_ranges_loads(tmp_path, examined):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"sign_in": {"trusted_proxies": ["127.0.0.1", "10.0.0.0/8", "::1"]}}), encoding="utf-8")
    examined(1, "a configuration")
    assert load(p).sign_in["trusted_proxies"] == ["127.0.0.1", "10.0.0.0/8", "::1"]
