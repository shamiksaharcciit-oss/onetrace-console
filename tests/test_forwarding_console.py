"""Trace forwarding in a running console: a run delivered over HTTP reaches a recording receiver on loopback, once,
as onetrace's export with the one attribute; a run already held is not sent again when the index is written again;
and a destination that is slow or down does not slow a delivery (measured). No backend, no key, no network."""

from __future__ import annotations

import json
import statistics
import time
import urllib.request
from pathlib import Path

import pytest

from onetrace_console import forwarding as F
from tests.conftest import make_tar, serving
from tests.http_limits import limit
from tests.otlp_receiver import Receiver


def _post(base: str, body: bytes) -> tuple[int, bytes]:
    req = urllib.request.Request(base + "/v1/runs", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=limit(60)) as resp:
        return resp.status, resp.read()


def test_a_delivered_run_reaches_the_receiver_once_as_its_trace(tmp_path, files, examined):
    from onetrace_console.serve import Handler

    with Receiver() as r, serving(tmp_path) as (base, store_root):
        F.save(store_root, None, {"name": "receiver", "endpoint": r.endpoint})
        status, body = _post(base, make_tar(files))
        assert status == 200, body
        key = json.loads(body)["key"] if "key" in json.loads(body) else None
        sender = F.Forwarder(store_root, Handler.store, every=0.05)
        sender.start()
        try:
            got = r.wait_for(1)
            time.sleep(0.5)
        finally:
            sender.stop()
        assert len(r.traces()) == 1, "sent once"
        run = Handler.store.runs()[0]
        if key is not None:
            assert run.key == key
        doc = json.loads(got[0].body)
        root = [s for s in doc["resourceSpans"][0]["scopeSpans"][0]["spans"] if not s.get("parentSpanId")][0]
        check = [a["value"]["stringValue"] for a in root["attributes"] if a["key"] == F.CHECK_ATTRIBUTE]
        assert len(check) == 1
        assert got[0].body == F.trace_of(run, Handler.store, check[0])
        assert got[0].headers["Content-Type"] == "application/json"
        #: The index written again (as after any page drawing) holds no new run: nothing is queued.
        from onetrace_console import run_index

        run_index.write(Handler.store, store_root)
        assert F.queued(store_root, F.read(store_root)[0].id) == []
    examined(1, "run sent")


def _timed_delivery(where: Path, files, endpoint: str | None) -> float:
    """Seconds one delivery takes over HTTP, with a destination at `endpoint` (and its sender running), or none.
    `where` is a folder of its own, made for this delivery and empty."""
    from onetrace_console.serve import Handler

    assert where.is_dir() and not any(where.iterdir()), where
    with serving(where) as (base, store_root):
        sender = None
        if endpoint is not None:
            F.save(store_root, None, {"name": "slow", "endpoint": endpoint})
            sender = F.Forwarder(store_root, Handler.store, every=0.01)
            sender.start()
        try:
            t0 = time.perf_counter()
            status, body = _post(base, make_tar(files))
            took = time.perf_counter() - t0
            assert status == 200, body
        finally:
            if sender is not None:
                sender.stop()
    return took


@pytest.mark.parametrize("down", ["slow", "refusing"])
def test_a_destination_slow_or_down_does_not_slow_a_delivery(tmp_path_factory, files, down, examined, capsys):
    """Measured: three deliveries each with no destination, and with one whose receiver holds every answer 8 seconds
    (or one at a port nothing listens on); the medians are compared."""
    hold = 8.0
    with Receiver(delay=hold if down == "slow" else 0.0) as r:
        if down == "refusing":
            r.httpd.server_close()
        endpoint = r.endpoint
        #: Each delivery in a folder of its own, named for its case: two cases, or two runs of one, share none.
        fresh = tmp_path_factory.mktemp
        none = [_timed_delivery(fresh(f"forward-{down}-none"), files, None) for _ in range(3)]
        with_dest = [_timed_delivery(fresh(f"forward-{down}-dest"), files, endpoint) for _ in range(3)]
    a, b = statistics.median(none), statistics.median(with_dest)
    with capsys.disabled():
        print(f"\nforwarding ({down}): a delivery's median {a:.3f} s with no destination, {b:.3f} s with one")
    assert b < hold / 2, "a delivery never waits for the destination"
    assert b <= a * 1.5 + 0.5, (a, b)
    examined(6, "deliveries timed")
