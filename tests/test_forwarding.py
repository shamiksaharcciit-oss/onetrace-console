"""Trace forwarding (`forwarding`): the trace a run is sent as, which runs a destination takes, the queue's
retries and stops, and the endpoints refused. Every request goes to a recording receiver on loopback
(`tests/otlp_receiver.py`): no backend, no key and no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from onetrace_console import forwarding as F
from tests.otlp_receiver import RESET, Receiver

ID = "0123456789abcdef"


def _dest(endpoint: str, **over) -> F.Destination:
    return F.destination({"id": ID, "name": "the receiver", "endpoint": endpoint, **over})


@pytest.fixture
def stored(store, delivery):
    from onetrace_console.ingest import accept

    return accept(delivery, store).run


def _export(run, store) -> bytes:
    import tempfile

    from onetrace import otel

    from onetrace_console.checks import materialise

    with tempfile.TemporaryDirectory() as tmp:
        where = Path(tmp) / (run.folder or "run")
        materialise(run, store, where)
        return otel.export(where, service_name="onetrace")


def _without_check(doc: dict) -> dict:
    for rs in doc["resourceSpans"]:
        for ss in rs["scopeSpans"]:
            for s in ss["spans"]:
                s["attributes"] = [a for a in s.get("attributes", []) if a["key"] != F.CHECK_ATTRIBUTE]
    return doc


def test_the_trace_is_onetrace_s_export_and_the_one_attribute_in_json(stored, store, examined):
    exported = _export(stored, store)
    sent = F.trace_of(stored, store, "records agree")
    assert sent == F.with_check(exported, "records agree")
    doc = json.loads(sent)
    roots = [s for s in doc["resourceSpans"][0]["scopeSpans"][0]["spans"] if not s.get("parentSpanId")]
    assert [a for a in roots[0]["attributes"] if a["key"] == F.CHECK_ATTRIBUTE] == [
        {"key": F.CHECK_ATTRIBUTE, "value": {"stringValue": "records agree"}}
    ]
    assert _without_check(doc) == json.loads(exported), "nothing else is added or changed"
    assert F.trace_of(stored, store, "records agree") == sent, "the same run is the same trace"
    examined(len(doc["resourceSpans"][0]["scopeSpans"][0]["spans"]), "spans compared")


def test_the_trace_in_protobuf_is_the_same_request(stored, store, examined):
    pytest.importorskip("opentelemetry.proto.collector.trace.v1.trace_service_pb2")
    from google.protobuf import json_format
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    sent = F.trace_of(stored, store, "1 row failed")
    msg = ExportTraceServiceRequest()
    msg.ParseFromString(F.to_protobuf(sent))
    back = json_format.MessageToDict(msg, preserving_proto_field_name=False)
    want = json.loads(sent)
    spans_back = back["resourceSpans"][0]["scopeSpans"][0]["spans"]
    spans_want = want["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans_back) == len(spans_want)
    for b, w in zip(spans_back, spans_want, strict=True):
        import base64

        assert base64.b64decode(b["traceId"]).hex() == w["traceId"]
        assert base64.b64decode(b["spanId"]).hex() == w["spanId"]
        assert b["name"] == w["name"]
        assert {a["key"] for a in b.get("attributes", [])} == {a["key"] for a in w.get("attributes", [])}
    examined(len(spans_back), "spans read back from protobuf")


@pytest.mark.parametrize(
    "check, all_, agree",
    [("records agree", 1, 1), ("not checked", 1, 0), ("couldn't check", 1, 0), ("2 rows failed", 1, 0)],
)
def test_only_agreeing_runs_go_where_the_destination_says_so(tmp_path, check, all_, agree, examined):
    every = _dest("https://a.example", runs="all")
    only = F.destination({**every.as_json(), "id": "fedcba9876543210", "runs": "agree"})
    assert F.enqueue(tmp_path, "k" * 64, check, [every]) == all_
    assert F.enqueue(tmp_path, "k" * 64, check, [only]) == agree
    examined(2, "destinations")


def test_a_destination_that_is_off_takes_nothing(tmp_path, examined):
    off = _dest("https://a.example", enabled=False)
    assert F.enqueue(tmp_path, "k" * 64, "records agree", [off]) == 0
    examined(1, "destination")


def _setup(tmp_path, endpoint: str, **over) -> F.Destination:
    d = _dest(endpoint, **over)
    F._write(tmp_path, [d])
    return d


def test_the_queue_retries_on_429_5xx_and_a_reset_and_then_sends(tmp_path, stored, store, examined):
    with Receiver([429, 503, RESET, 200]) as r:
        d = _setup(tmp_path, r.endpoint)
        F.enqueue(tmp_path, stored.key, "records agree")
        entry = F._queue(tmp_path, d.id) / f"{stored.key}.json"
        now = 1000.0
        got = []
        for _ in range(4):
            got.append(F.attempt(tmp_path, store, d, entry, now=now))
            doc = F._read_json(entry)
            if doc:
                assert doc["next_at"] == now + F.wait_after(doc["attempts"])
                now = doc["next_at"]
        assert got == ["again", "again", "again", "sent"]
        assert not entry.exists()
        assert len(r.traces()) == 4 and all(q.path == "/v1/traces" for q in r.traces())
    examined(4, "attempts")


def test_the_waits_double_and_stop_at_the_longest(examined):
    waits = [F.wait_after(n) for n in range(1, 12)]
    assert waits[:3] == [F.FIRST_WAIT, 2 * F.FIRST_WAIT, 4 * F.FIRST_WAIT]
    assert max(waits) == F.LONGEST_WAIT
    examined(len(waits), "waits")


def test_after_the_most_tries_an_entry_stops_and_says_so(tmp_path, stored, store, examined):
    with Receiver([500] * F.MAX_ATTEMPTS) as r:
        d = _setup(tmp_path, r.endpoint)
        F.enqueue(tmp_path, stored.key, "records agree")
        entry = F._queue(tmp_path, d.id) / f"{stored.key}.json"
        results = [F.attempt(tmp_path, store, d, entry, now=1e12 + i * 1e6) for i in range(F.MAX_ATTEMPTS)]
    assert results[-1] == "stopped" and set(results[:-1]) == {"again"}
    doc = F._read_json(entry)
    assert doc["state"] == "stopped" and doc["last"].startswith(f"gave up after {F.MAX_ATTEMPTS} tries: 500")
    examined(F.MAX_ATTEMPTS, "tries")


@pytest.mark.parametrize(
    "status, reason", [(400, "Bad Request"), (401, "Unauthorized"), (403, "Forbidden"), (404, "Not Found")]
)
def test_a_4xx_other_than_429_stops_the_entry_with_the_reason(tmp_path, stored, store, status, reason, examined):
    with Receiver([status]) as r:
        d = _setup(tmp_path, r.endpoint)
        F.enqueue(tmp_path, stored.key, "records agree")
        entry = F._queue(tmp_path, d.id) / f"{stored.key}.json"
        assert F.attempt(tmp_path, store, d, entry, now=1e12) == "stopped"
    doc = F._read_json(entry)
    assert doc["state"] == "stopped" and doc["last"] == f"{status} {reason}"
    assert F.status(tmp_path, d.id)["last_failure"] == f"{status} {reason}"
    examined(1, "entry")


def test_the_queue_outlives_a_restart(tmp_path, stored, store, examined):
    with Receiver([RESET, 200]) as r:
        d = _setup(tmp_path, r.endpoint)
        F.enqueue(tmp_path, stored.key, "records agree")
        assert F.run_once(tmp_path, store) == ["again"]
        #: A new console on the same store: nothing kept in memory, only the files.
        from onetrace_console.store import Store

        again = Store(store.root)
        assert F.run_once(tmp_path, again, now=1e12) == ["sent"]
        assert len(r.traces()) == 2
        assert F.status(tmp_path, d.id)["last_send"]
    examined(2, "passes, one before the restart and one after")


@pytest.mark.parametrize(
    "endpoint, refused",
    [
        ("https://collector.example.com:4318", False),
        ("http://127.0.0.1:4318", False),
        ("http://[::1]:4318", False),
        ("http://localhost:4318", False),
        ("http://collector.example.com:4318", True),
        ("http://10.0.0.5:4318", True),
        ("ftp://collector.example.com", True),
        ("https://user:pass@collector.example.com", True),
        ("https://collector.example.com/?k=v", True),
        ("https://", True),
    ],
)
def test_http_is_refused_for_an_address_off_this_machine(endpoint, refused, examined):
    assert (F.endpoint_problem(endpoint) is not None) is refused, endpoint
    examined(1, "endpoint")


def test_with_protobuf_chosen_and_the_extra_missing_nothing_is_sent_and_the_line_is_said(
    tmp_path, monkeypatch, examined
):
    monkeypatch.setattr(F, "protobuf_installed", lambda: False)
    with Receiver() as r:
        d = _dest(r.endpoint, encoding="protobuf")
        answer = F.send(d, F.test_trace())
        assert not r.traces()
    assert answer.status == -1 and F.INSTALL in answer.reason
    examined(1, "send")


def test_the_test_trace_is_one_span_with_no_run_data(examined):
    doc = json.loads(F.test_trace())
    spans = doc["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert [s["name"] for s in spans] == [F.TEST_SPAN]
    assert spans[0]["attributes"] == []
    examined(1, "span")


def test_a_header_s_value_goes_only_in_its_header_and_never_in_an_error(monkeypatch, examined):
    planted = "planted-value-7f3a9c"
    monkeypatch.setenv("ONETRACE_FORWARD_TEST_KEY", planted)
    with Receiver([401]) as r:
        d = _dest(r.endpoint, headers=[{"name": "x-api-key", "key_env": "ONETRACE_FORWARD_TEST_KEY"}])
        answer = F.send(d, F.test_trace())
        req = r.traces()[0]
    assert req.headers.get("x-api-key") == planted
    assert planted not in req.body.decode()
    assert planted not in answer.reason
    assert F.cut(f"401 {planted} bad", [planted]) == "401 [a header's value] bad"
    examined(1, "request")


def test_a_variable_that_is_not_set_sends_nothing_and_says_so(monkeypatch, examined):
    monkeypatch.delenv("ONETRACE_FORWARD_TEST_KEY", raising=False)
    with Receiver() as r:
        d = _dest(r.endpoint, headers=[{"name": "x-api-key", "key_env": "ONETRACE_FORWARD_TEST_KEY"}])
        with pytest.raises(F.KeyMissing, match="ONETRACE_FORWARD_TEST_KEY is not set"):
            F.send(d, F.test_trace())
        assert not r.traces()
    assert F.key_state(d, d.headers[0]) == "not set"
    examined(1, "header")


@pytest.mark.parametrize(
    "raw, why",
    [
        ({"headers": [{"name": "Content-Type", "key_env": "X"}]}, "sets Content-Type itself"),
        ({"headers": [{"name": "x-api-key"}]}, "say where its value is"),
        ({"headers": [{"name": "x-api-key", "key_env": "X", "key_source": "keyring"}]}, "not both"),
        ({"headers": [{"name": "x-api-key", "value": "v"}]}, "say where its value is"),
        ({"encoding": "xml"}, "json or protobuf"),
        ({"runs": "some"}, "only runs whose records agree"),
        ({"name": ""}, "give the destination a name"),
    ],
)
def test_a_destination_is_refused_naming_what_is_wrong(raw, why, examined):
    with pytest.raises(F.Refused, match=why):
        F.destination({"id": ID, "name": "n", "endpoint": "https://a.example", **raw})
    examined(1, "destination")


def test_save_changes_only_the_named_fields_and_never_holds_a_value(tmp_path, examined):
    d, changed = F.save(tmp_path, None, {"name": "one", "endpoint": "https://a.example/otel"})
    other, _ = F.save(tmp_path, None, {"name": "two", "endpoint": "https://b.example"})
    _, changed = F.save(tmp_path, d.id, {"runs": "agree"})
    assert changed == ["runs"]
    kept = F.read(tmp_path)
    assert [x.name for x in kept] == ["one", "two"] and kept[0].runs == "agree" and kept[1] == other
    with pytest.raises(F.Refused, match="not a field"):
        F.save(tmp_path, d.id, {"value": "secret"})
    examined(2, "destinations")
