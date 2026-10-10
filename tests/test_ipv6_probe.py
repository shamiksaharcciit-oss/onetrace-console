"""The two IPv6 tests skip only where the host has no IPv6 loopback, measured
by binding ('::1', 0) -- never assumed from the platform. On Windows a failed probe is a failure,
not a skip: the PC has IPv6, and §5's Windows run is what covers these tests.

These tests drive `ipv6_loopback_port()` with a stand-in socket, so each outcome is exercised on
every host: a bind that works, a bind that fails off Windows, and a bind that fails on Windows.
"""
from __future__ import annotations

import errno
import socket

import pytest

from tests.conftest import ipv6_loopback_port


class _Socket:
    """Stands in for socket.socket: binds, or raises the OSError given."""

    def __init__(self, fails: OSError | None):
        self.fails = fails

    def __call__(self, family, kind):
        assert (family, kind) == (socket.AF_INET6, socket.SOCK_STREAM)
        return self

    def bind(self, address):
        assert address == ("::1", 0)
        if self.fails:
            raise self.fails

    def getsockname(self):
        return ("::1", 54321, 0, 0)

    def close(self):
        pass


NO_ADDRESS = OSError(errno.EADDRNOTAVAIL, "Cannot assign requested address")


def _outcome(**kw) -> tuple[str, object]:
    """The probe's outcome as a value. A skip raised inside a test skips THAT test, even inside
    `pytest.raises(pytest.fail.Exception)` -- so a probe that skipped where it should fail would
    leave these tests skipped, not failed. Caught here, a skip is something to assert on."""
    try:
        return "returned", ipv6_loopback_port(**kw)
    except pytest.skip.Exception as e:
        return "skipped", str(e)
    except pytest.fail.Exception as e:
        return "failed", str(e)


def test_a_working_ipv6_loopback_gives_its_free_port(monkeypatch):
    monkeypatch.setattr(socket, "socket", _Socket(None))
    assert _outcome(windows=False) == ("returned", 54321)
    assert _outcome(windows=True) == ("returned", 54321)


def test_no_ipv6_loopback_off_windows_is_a_skip_naming_the_failure(monkeypatch):
    monkeypatch.setattr(socket, "socket", _Socket(NO_ADDRESS))
    kind, said = _outcome(windows=False)
    assert kind == "skipped", (kind, said)
    assert said.startswith("this host has no IPv6 loopback (Errno ")
    assert f"Errno {errno.EADDRNOTAVAIL}" in said


def test_no_ipv6_loopback_on_windows_is_a_failure_not_a_skip(monkeypatch):
    monkeypatch.setattr(socket, "socket", _Socket(NO_ADDRESS))
    kind, said = _outcome(windows=True)
    assert kind == "failed", (kind, said)
    assert "Windows" in said and f"Errno {errno.EADDRNOTAVAIL}" in said


def test_a_host_with_no_ipv6_at_all_is_measured_the_same_way(monkeypatch):
    """Creating the AF_INET6 socket can itself fail (EAFNOSUPPORT) where IPv6 is compiled out."""
    def no_family(family, kind):
        raise OSError(errno.EAFNOSUPPORT, "Address family not supported by protocol")
    monkeypatch.setattr(socket, "socket", no_family)
    kind, said = _outcome(windows=False)
    assert kind == "skipped" and f"Errno {errno.EAFNOSUPPORT}" in said, (kind, said)
    assert _outcome(windows=True)[0] == "failed"


@pytest.mark.parametrize("module, test", [
    ("tests/test_rereview_fixes.py", "test_ipv6_loopback_is_listened_on"),
    ("tests/test_third_review_fixes.py", "test_an_ipv6_host_is_said_as_a_url"),
])
def test_both_ipv6_tests_take_their_port_from_the_probe(module, test):
    """The skip lives in one place: each IPv6 test gets its port from the probe and binds ::1
    nowhere else."""
    from tests.conftest import REPO
    source = (REPO / module).read_text(encoding="utf-8")
    body = source.split(f"def {test}(", 1)[1].split("\ndef ", 1)[0]
    assert "ipv6_loopback_port()" in body
    assert 'bind(("::1"' not in body
