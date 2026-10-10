"""The access log. Append-only, hash-chained, one
entry per request, with change 8's size-bounded rotation and fail-closed behaviour.
"""
from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from onetrace_console.access_log import AccessLog, AccessLogExhausted, entry_digest


def _get(base: str, path: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(base + path, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# --------------------------------------------------------------- the log, as a unit

def test_appending_chains_each_entry_to_the_last(tmp_path, examined):
    log = AccessLog(tmp_path / "access_log", max_segment_bytes=1_000_000)
    e1 = log.append(principal="anonymous", method="GET", path="/health", status=200)
    e2 = log.append(principal="anonymous", method="GET", path="/home.html", status=200)
    examined(2, "entries appended and chain-verified")
    assert e1["prev"] is None
    assert e2["prev"] == entry_digest(e1)
    ok, detail = log.verify_chain()
    assert ok, detail


def test_sabotage_a_dropped_chain_link_is_caught_by_verify_chain(tmp_path, examined):
    """Sabotage: drop the chain link on the
    second entry; the test that recomputes the chain head must fail.
    """
    log = AccessLog(tmp_path / "access_log", max_segment_bytes=1_000_000)
    log.append(principal="anonymous", method="GET", path="/health", status=200)
    log.append(principal="anonymous", method="GET", path="/home.html", status=200)

    examined(1, "chains with a dropped link, fed to verify_chain")
    # Sabotage: rewrite the second entry's own `prev` to None, as if it were first.
    segment = sorted((tmp_path / "access_log").glob("*.jsonl"))[0]
    lines = segment.read_text(encoding="utf-8").splitlines()
    import json
    second = json.loads(lines[1])
    second["prev"] = None
    lines[1] = json.dumps(second, sort_keys=True, separators=(",", ":"))
    segment.write_text("\n".join(lines) + "\n", encoding="utf-8")

    log2 = AccessLog(tmp_path / "access_log", max_segment_bytes=1_000_000)
    ok, detail = log2.verify_chain()
    assert not ok, "a dropped chain link was not caught"
    assert "entry 1" in detail


def test_rotation_carries_the_chain_across_segments(tmp_path, examined):
    """Change 8: a new segment's first entry names the outgoing segment's own last
    entry, so the chain is one sequence across the rotation boundary.
    """
    # A tiny bound forces a rotation after very few entries.
    log = AccessLog(tmp_path / "access_log", max_segment_bytes=1)
    entries = [log.append(principal="anonymous", method="GET", path=f"/p{i}", status=200)
              for i in range(5)]
    segments = sorted((tmp_path / "access_log").glob("*.jsonl"))
    examined(len(segments), "segments produced by a 1-byte segment bound")
    assert len(segments) >= 2, "the tiny bound should have forced at least one rotation"
    ok, detail = log.verify_chain()
    assert ok, detail
    #: Each entry's own prev really does chain to the one before it, across segments.
    for i in range(1, len(entries)):
        assert entries[i]["prev"] == entry_digest(entries[i - 1])


def test_a_fresh_accesslog_instance_resumes_the_same_chain(tmp_path, examined):
    """`HEAD.json` must survive a restart -- a new `AccessLog` pointed at the same root
    continues the same chain, not a new one.
    """
    log = AccessLog(tmp_path / "access_log", max_segment_bytes=1_000_000)
    e1 = log.append(principal="anonymous", method="GET", path="/health", status=200)

    log2 = AccessLog(tmp_path / "access_log", max_segment_bytes=1_000_000)
    e2 = log2.append(principal="anonymous", method="GET", path="/home.html", status=200)

    examined(1, "a second AccessLog instance over the same root")
    assert e2["prev"] == entry_digest(e1)
    ok, detail = log2.verify_chain()
    assert ok, detail


# ------------------------------------------------------------- wired into the server

def test_every_request_appends_one_chained_access_log_entry(server, examined):
    base, store_root = server
    from onetrace_console.serve import Handler

    before = len(Handler.access_log.read_all_entries())
    _get(base, "/health")
    _get(base, "/home.html")
    _get(base, "/does-not-exist.html")
    after = Handler.access_log.read_all_entries()

    examined(3, "HTTP requests, each checked for exactly one access log entry")
    assert len(after) - before == 3
    ok, detail = Handler.access_log.verify_chain()
    assert ok, detail
    assert [e["path"] for e in after[-3:]] == ["/health", "/home.html", "/does-not-exist.html"]
    assert [e["status"] for e in after[-3:]] == [200, 200, 404]
    assert all(e["principal"] == "anonymous" for e in after[-3:])


def test_a_log_append_failure_fails_the_response_closed_not_open(server, examined, monkeypatch):
    """If the access log cannot be written, the request must NOT be served as if it
    had been -- a 500 naming the problem, never the original 200.
    """
    from onetrace_console.serve import Handler

    def boom(**kwargs):
        raise AccessLogExhausted("simulated: the access log's volume is full")

    monkeypatch.setattr(Handler.access_log, "append", boom)
    base, _ = server
    examined(1, "requests sent while the access log cannot be written")
    status, body = _get(base, "/health")
    assert status == 500
    assert b"access log" in body.lower()
