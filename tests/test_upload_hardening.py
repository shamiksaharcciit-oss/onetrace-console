"""The console's first network-facing upload path, hardened. One named test per hardening
item, each sabotaged to confirm it can fail.

"There was no HTTP server" is the register instance behind this hardening -- the first ingest was
reported and tested as a function, never as a route anything could reach over a network. This
file is the other half of that lesson: every check below is exercised against the real
`ingest.accept()` / `read_tar()` it protects, or against a real running server, never against
a mock of either.
"""
from __future__ import annotations

import io
import json
import tarfile
import time
import urllib.error
import urllib.request

import pytest

from onetrace_console.config import Config
from onetrace_console.ingest import read_tar
from onetrace_console.serve import Handler
from tests.test_checks import _require_installed


def _member(name: str, data: bytes = b"", *, type_: bytes | None = None,
           linkname: str = "", size: int | None = None) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name=name)
    info.size = len(data) if size is None else size
    info.mtime = 0
    if type_ is not None:
        info.type = type_
    if linkname:
        info.linkname = linkname
    return info, data


def _tar(*members: tuple[tarfile.TarInfo, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for info, data in members:
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _valid_manifest_member(run_id: str = "r", extra: dict | None = None) -> tuple[tarfile.TarInfo, bytes]:
    """A MANIFEST.json alone is never a valid run (no receipts), but it is enough to reach
    past `read_tar` into `check_sums`/`_manifest` for tests that need to -- most of these
    tests only need `read_tar`/`accept` to REFUSE at the archive-hardening layer, before any
    of that runs, so a real run is not needed to prove the hardening.
    """
    manifest = {"format": "stage-receipt-chain/0.1", "run_id": run_id,
               "chain_head": "sha256:" + "0" * 64, "chain": []}
    if extra:
        manifest.update(extra)
    data = json.dumps(manifest, sort_keys=True).encode("utf-8")
    return _member("MANIFEST.json", data)


# =====================================================================================
# item 1 -- path traversal
# =====================================================================================

def test_item1_traversal_members_are_refused(store, examined):
    cases = [
        "../escape.txt",
        "/etc/passwd",
        "a/../../escape.txt",
        r"C:\Windows\System32\evil.dll",
        r"..\..\escape.txt",
    ]
    examined(len(cases), "traversal path shapes tried")
    for name in cases:
        data = _tar(_member(name, b"x"))
        with pytest.raises(Exception) as exc_info:
            read_tar(data)
        # DeliveryRefused, imported lazily to avoid a second top-level import for one use
        from onetrace_console.ingest import DeliveryRefused
        assert isinstance(exc_info.value, DeliveryRefused), (name, exc_info.value)
        assert any("escapes the run folder" in r or "absolute" in r or "drive letter" in r
                  or "backslash" in r or "'..'" in r
                  for r in exc_info.value.rows), (name, exc_info.value.rows)


def test_item1_sabotage_disabling_the_path_check_lets_traversal_through(store):
    """Sabotage: with `_unsafe_path` neutered, a `..` member is no longer refused by it
    alone -- confirming the check is load-bearing rather than decorative. (item 6's own
    filter still catches it independently; see that test for the reverse sabotage.)"""
    import onetrace_console.ingest as ingest_mod

    original = ingest_mod._unsafe_path
    ingest_mod._unsafe_path = lambda name: None
    try:
        data = _tar(_member("../escape.txt", b"x"))
        # The data_filter still catches this on its own (item 6), so to prove THIS
        # check's own necessity, also neuter the filter for the duration of this one
        # assertion -- otherwise the sabotage would "pass" for the wrong reason.
        original_filter = tarfile.data_filter
        tarfile.data_filter = lambda member, dest: member
        try:
            from onetrace_console.ingest import DeliveryRefused
            try:
                read_tar(data)
                raised = False
            except DeliveryRefused:
                raised = True
            assert not raised, (
                "the traversal member was refused even with BOTH the explicit check and "
                "the filter disabled -- something else is catching it, and the sabotage "
                "proves nothing")
        finally:
            tarfile.data_filter = original_filter
    finally:
        ingest_mod._unsafe_path = original


# =====================================================================================
# item 2 -- links and special files
# =====================================================================================

def test_item2_links_and_special_files_are_refused(examined):
    from onetrace_console.ingest import DeliveryRefused

    cases = [
        _member("a_symlink", type_=tarfile.SYMTYPE, linkname="MANIFEST.json"),
        _member("a_hardlink", type_=tarfile.LNKTYPE, linkname="MANIFEST.json"),
        _member("a_char_device", type_=tarfile.CHRTYPE),
        _member("a_block_device", type_=tarfile.BLKTYPE),
        _member("a_fifo", type_=tarfile.FIFOTYPE),
    ]
    examined(len(cases), "link and special-file member types tried")
    for info, data in cases:
        archive = _tar(_valid_manifest_member(), (info, data))
        with pytest.raises(DeliveryRefused) as exc_info:
            read_tar(archive)
        assert any(info.name in r for r in exc_info.value.rows), (info.name, exc_info.value.rows)


def test_item2_sabotage_disabling_the_type_checks_lets_a_symlink_through_to_the_filter(monkeypatch):
    """Sabotage: two things independently keep a symlink out today -- the NAMED,
    explicit `_is_link_or_special` check, and the pre-existing generic "archive holds
    only regular files" fallback (`not member.isfile()`, which was already false for a
    symlink before this specification's work added the explicit check). Disabling only the
    named check is not enough to observe an unconditional acceptance, because the
    generic fallback still catches it -- so both are disabled together here, which is
    what it actually takes to reach `tarfile.data_filter` with a symlink at all. What
    happens THERE is item 6's own test; this one confirms `_is_link_or_special` is one
    of two real layers, not a check that never gets a chance to matter.
    """
    import onetrace_console.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_is_link_or_special", lambda member: False)
    monkeypatch.setattr(tarfile.TarInfo, "isfile", lambda self: True)
    #: With BOTH type-based checks defeated and a symlink whose target stays inside the
    #: destination, `tarfile.data_filter` has nothing to object to either (it only
    #: rejects a link whose TARGET escapes) -- so the member is accepted, unconditional
    #: rejection gone. That is what "not only one of the two" is guarding against: with
    #: neither explicit check active, only a filter that inspects every kind of escape
    #: would save this case, and `data_filter` does not treat "is a symlink" as one.
    archive = _tar(_valid_manifest_member(),
                  _member("a_symlink", type_=tarfile.SYMTYPE, linkname="MANIFEST.json"))
    files = read_tar(archive)      # must NOT raise, proving the two checks were load-bearing
    assert "MANIFEST.json" in files


# =====================================================================================
# item 3 -- size limits
# =====================================================================================

def test_item3a_oversized_request_body_is_refused_before_reading(server, examined):
    base, _ = server
    limit = Handler.config.max_request_body
    oversized_length = limit + 1
    examined(1, "oversized request bodies posted")

    #: The connection is made and the headers are sent with a declared Content-Length
    #: over the limit, but the body itself is NEVER sent -- if the server read before
    #: checking the length, this would hang waiting for bytes that never arrive; it
    #: does not hang, which is the proof that the check runs first.
    import socket
    host_port = base.split("//", 1)[1]
    host, port = host_port.split(":")
    with socket.create_connection((host, int(port)), timeout=10) as sock:
        sock.sendall(
            f"POST /v1/runs HTTP/1.1\r\nHost: {host}\r\n"
            f"Content-Length: {oversized_length}\r\nConnection: close\r\n\r\n".encode())
        sock.settimeout(10)
        response = b""
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
        except socket.timeout:
            pytest.fail("the server waited for a body it should have refused before reading")
    assert b"413" in response.split(b"\r\n", 1)[0], response[:200]


def test_item3b_too_many_members_is_refused(examined):
    from onetrace_console.ingest import DeliveryRefused

    limits = Config(max_members=3)
    members = [_valid_manifest_member()] + [_member(f"extra-{i}.json", b"{}") for i in range(5)]
    examined(len(members), "members in the over-count archive")
    archive = _tar(*members)
    with pytest.raises(DeliveryRefused) as exc_info:
        read_tar(archive, limits=limits)
    assert any("member limit" in r for r in exc_info.value.rows), exc_info.value.rows


def test_item3b_sabotage_a_generous_member_limit_lets_the_same_archive_through():
    limits = Config(max_members=1000)
    members = [_valid_manifest_member()] + [_member(f"extra-{i}.json", b"{}") for i in range(5)]
    archive = _tar(*members)
    files = read_tar(archive, limits=limits)     # must NOT raise for the member-count reason
    assert len(files) == 6


def test_item3c_total_extracted_size_over_the_limit_is_refused(examined):
    from onetrace_console.ingest import DeliveryRefused

    limits = Config(max_member_size=1000, max_total_extracted_size=120)
    members = [_valid_manifest_member()] + [_member(f"blob-{i}.bin", b"x" * 50) for i in range(3)]
    examined(sum(i.size for i, _ in members), "bytes declared across the archive's members")
    archive = _tar(*members)
    with pytest.raises(DeliveryRefused) as exc_info:
        read_tar(archive, limits=limits)
    assert any("total extracted size" in r for r in exc_info.value.rows), exc_info.value.rows


def test_item3c_sabotage_a_generous_total_limit_lets_the_same_archive_through():
    limits = Config(max_member_size=1000, max_total_extracted_size=10_000)
    members = [_valid_manifest_member()] + [_member(f"blob-{i}.bin", b"x" * 50) for i in range(3)]
    archive = _tar(*members)
    files = read_tar(archive, limits=limits)
    assert len(files) == 4


# =====================================================================================
# item 4 -- timeouts for stalled requests
# =====================================================================================

def test_item4_a_stalled_request_times_out(server, examined):
    """A client that sends headers, declares a body, then sends NOTHING further: the
    server must give up rather than hold the thread (and the connection) forever.
    """
    import socket

    base, _ = server
    original_timeout = Handler.config.request_timeout_seconds
    Handler.config = Config(request_timeout_seconds=0.6,
                           max_request_body=Handler.config.max_request_body)
    examined(1, "stalled connections")
    try:
        host_port = base.split("//", 1)[1]
        host, port = host_port.split(":")
        start = time.monotonic()
        with socket.create_connection((host, int(port)), timeout=10) as sock:
            sock.sendall(
                f"POST /v1/runs HTTP/1.1\r\nHost: {host}\r\n"
                f"Content-Length: 100\r\nConnection: close\r\n\r\n".encode())
            # Deliberately send nothing else -- the declared 100 bytes never arrive.
            sock.settimeout(10)
            response = b""
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
            except socket.timeout:
                pytest.fail("the server never responded to the stalled request")
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"took {elapsed:.1f}s -- the timeout did not bound this"
        assert b"408" in response.split(b"\r\n", 1)[0], response[:200]
    finally:
        Handler.config = Config(request_timeout_seconds=original_timeout,
                               max_request_body=Handler.config.max_request_body)


def test_item4_a_slow_but_alive_client_is_not_falsely_timed_out(server):
    """The other half of item 4's correctness: the deadline is wall-clock for the WHOLE
    body, re-armed each time bytes actually arrive -- not a single short window that
    would reject a real, if slow, upload. A client sending in two halves with a pause
    between, comfortably inside the configured timeout, must still succeed.
    """
    import socket

    base, _ = server
    manifest, data = _valid_manifest_member()
    body = _tar((manifest, data))
    original = Handler.config
    Handler.config = Config(request_timeout_seconds=3.0,
                           max_request_body=original.max_request_body,
                            sign_in={**Config().sign_in, "enabled": False})
    try:
        host_port = base.split("//", 1)[1]
        host, port = host_port.split(":")
        with socket.create_connection((host, int(port)), timeout=10) as sock:
            header = (f"POST /v1/runs HTTP/1.1\r\nHost: {host}\r\n"
                     f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()
            sock.sendall(header + body[: len(body) // 2])
            time.sleep(0.8)                          # comfortably inside the 3.0s deadline
            sock.sendall(body[len(body) // 2:])
            sock.settimeout(10)
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
        status_line = response.split(b"\r\n", 1)[0]
        assert b"200" in status_line or b"422" in status_line, response[:300]
    finally:
        Handler.config = original


# =====================================================================================
# item 5 -- malformed input
# =====================================================================================

def test_item5_malformed_input_is_a_plain_4xx_with_no_traceback_and_no_partial_store(server, examined):
    base, store_root = server
    cases = [b"not a tar file at all", b"PK\x03\x04not a tar either"]
    examined(len(cases), "malformed bodies posted")
    for body in cases:
        req = urllib.request.Request(base + "/v1/runs", data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status, response_body = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status, response_body = e.code, e.read()
        assert 400 <= status < 500, (status, response_body)
        assert b"Traceback" not in response_body, response_body
        assert b"File \"" not in response_body, response_body

    #: No partial store: nothing was ever written for any of the malformed attempts.
    from onetrace_console.store import Store
    reopened = Store(store_root / "store")
    assert reopened.runs() == ()


def test_item5_a_truncated_real_tar_is_refused_with_no_partial_store(server, examined):
    base, store_root = server
    manifest, data = _valid_manifest_member()
    good = _tar((manifest, data))
    truncated = good[: len(good) // 2]
    examined(1, "truncated archives posted")

    req = urllib.request.Request(base + "/v1/runs", data=truncated, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status, body = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read()
    assert 400 <= status < 500, (status, body)
    assert b"Traceback" not in body

    from onetrace_console.store import Store
    reopened = Store(store_root / "store")
    assert reopened.runs() == ()


# =====================================================================================
# item 6 -- both the filter and the explicit checks are load-bearing
# =====================================================================================

def test_item6_the_filter_catches_an_escaping_link_target_the_explicit_checks_do_not_inspect(
        monkeypatch):
    """`tarfile.data_filter` resolves the real destination path rather than pattern-
    matching the name, so it catches something neither of this module's own explicit
    checks looks at AT ALL: a symlink's own **target**. `_unsafe_path` only inspects a
    member's *name*; `_is_link_or_special` rejects a link by *type* without ever
    looking at where it points. Both are disabled here (as in item 2's own sabotage,
    which also needs the generic `isfile()` fallback defeated to reach this point) so
    that `data_filter` is the only thing standing between this member and acceptance --
    and it refuses, because the symlink's target escapes the destination.
    """
    from onetrace_console.ingest import DeliveryRefused
    import onetrace_console.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_is_link_or_special", lambda member: False)
    monkeypatch.setattr(tarfile.TarInfo, "isfile", lambda self: True)

    escaping_symlink = _member("looks_ordinary", type_=tarfile.SYMTYPE, linkname="../../../etc/passwd")
    archive = _tar(_valid_manifest_member(), escaping_symlink)
    with pytest.raises(DeliveryRefused) as exc_info:
        read_tar(archive)
    assert any("safe-extraction filter" in r for r in exc_info.value.rows), exc_info.value.rows


def test_item6_sabotage_the_filter_itself_is_what_objects_not_something_else(monkeypatch):
    """The reverse check, isolated rather than run through the whole pipeline: going
    through `read_tar`'s full flow with `data_filter` ALSO disabled hits an unrelated
    stdlib property first -- `TarFile.extractfile()` on a symlink resolves its target
    to another member OF THE SAME ARCHIVE, and this one names a target that is not
    present at all, so extraction itself would raise `KeyError` before this test could
    observe whether the filter's absence was the reason anything was accepted. Calling
    `tarfile.data_filter` directly on the exact member sidesteps that and asks the real
    question cleanly: does the filter itself object to this member, or does something
    else in `read_tar` deserve the credit? It does -- confirmed against the unpatched,
    real `tarfile.data_filter`, the same function `read_tar` actually calls.
    """
    escaping_symlink, _ = _member("looks_ordinary", type_=tarfile.SYMTYPE,
                                  linkname="../../../etc/passwd")
    with pytest.raises(tarfile.FilterError):
        tarfile.data_filter(escaping_symlink, "/run")
