"""A step's span tree: the app's spans, joined to the step by the trace context onetrace recorded.

1. The join: the step's span is the one with its recorded trace id and span id, never one named
   like the step; under it, the spans that start within the step's recorded times, as a waterfall.
2. A span of a recorded trace that no step's tree holds is listed as unjoined, and a step whose
   recorded span is not in the export is said to be unjoined.
3. Checked against the record: a span's model against the step's model-call records, named where
   they disagree; the step's recorded times against its span's.
4. A malformed export gets no view, with its reason.
5. A credential-shaped attribute, by name or by value, is never shown; the value shape is the
   verifier's own, held equal to its source.
6. Limits as the JSON view's: a long value by its digest, spans past the most counted.
7. On a recorded run with a trace file given, the step page and the run page carry the view.
"""
from __future__ import annotations

import html
import json
import re

import pytest

from onetrace_console import span_tree

T, OTHER_T = "a" * 32, "b" * 32
ROOT, MODEL, TOOL, HTTP, LOOSE = "1" * 16, "2" * 16, "3" * 16, "4" * 16, "5" * 16
#: The step's recorded times, and the same instants in nanoseconds.
STARTED, ENDED = "2026-11-02T05:00:00.100+00:00", "2026-11-02T05:00:00.900+00:00"
S0 = 1793595600 * 10**9


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _attr(k: str, v) -> dict:
    return {"key": k, "value": {"intValue": str(v)} if isinstance(v, int) else {"stringValue": v}}


def _span(sid, name, start_ms, end_ms, parent="", trace=T, attrs=(), status=None, events=()):
    sp = {"traceId": trace, "spanId": sid, "parentSpanId": parent, "name": name,
          "startTimeUnixNano": str(S0 + start_ms * 10**6), "endTimeUnixNano": str(S0 + end_ms * 10**6),
          "attributes": [_attr(k, v) for k, v in attrs]}
    if status:
        sp["status"] = status
    if events:
        sp["events"] = [{"name": n, "timeUnixNano": str(S0 + t * 10**6), "attributes": []} for n, t in events]
    return sp


def _export(*spans) -> bytes:
    return json.dumps({"resourceSpans": [{"resource": {"attributes": []},
                                          "scopeSpans": [{"scope": {"name": "app"}, "spans": list(spans)}]}]}).encode()


def _planted(**extra) -> list:
    return [
        _span(ROOT, "handle request", 50, 950),
        _span(MODEL, "chat example-model", 120, 400, ROOT,
              attrs=[("gen_ai.operation.name", "chat"), ("gen_ai.request.model", "example-model"),
                     ("gen_ai.usage.input_tokens", 120), ("gen_ai.usage.output_tokens", 30)]),
        _span(TOOL, "execute_tool price_lookup", 420, 800, ROOT,
              attrs=[("gen_ai.operation.name", "execute_tool"), ("gen_ai.tool.name", "price_lookup")],
              status={"code": 2, "message": "price service unavailable"}, events=[("retry", 500), ("retry", 600)]),
        _span(HTTP, "GET", 430, 790, TOOL, attrs=[("http.request.method", "GET"), ("http.request.resend_count", 2),
                                                  ("http.response.status_code", 503)]),
        #: The step's own name, in its trace, outside its span: never the join.
        _span(LOOSE, "call", 960, 990),
        _span("6" * 16, "call", 100, 900, trace=OTHER_T),
    ]


def _receipt(span_id=ROOT, started=STARTED, ended=ENDED) -> dict:
    return {"stage": {"name": "call"}, "trace": {"trace_id": T, "span_id": span_id},
            "time": {"started": started, "ended": ended}}


def _section(spans, receipt=None, reported=()):
    real = span_tree.reported_models
    span_tree.reported_models = lambda r, f, read: list(reported)
    try:
        return span_tree.step_section(spans, receipt or _receipt(), "receipts/01-call.json", lambda p: None)
    finally:
        span_tree.reported_models = real


def test_the_step_s_span_is_the_one_with_its_recorded_trace_context(examined):
    spans = span_tree.read_export(_export(*_planted()))
    page = _section(spans)
    rows = re.findall(r'<tr data-span="([0-9a-f]{16})" data-depth="(\d)" data-what="([^"]+)"', page)
    examined(len(rows), "spans in the step's tree")
    assert rows == [(ROOT, "0", "span"), (MODEL, "1", "model call"), (TOOL, "1", "tool call"), (HTTP, "2", "HTTP call")]
    assert span_tree.JOINED.format(trace_id=T, span_id=ROOT) in _text(page)
    assert span_tree.WITHIN in _text(page)
    tool = re.search(rf'<tr data-span="{TOOL}".*?</tr>', page, re.S).group(0)
    assert 'data-status="error"' in tool and 'data-retries="2"' in tool and "price service unavailable" in tool
    http = re.search(rf'<tr data-span="{HTTP}".*?</tr>', page, re.S).group(0)
    assert 'data-retries="2"' in http and "360.0 ms" in _text(http)
    assert "120 / 30" in _text(re.search(rf'<tr data-span="{MODEL}".*?</tr>', page, re.S).group(0))
    for line in span_tree.NON_CLAIMS:
        assert line in _text(page)


def test_sabotage_a_join_by_name_takes_another_span(examined):
    spans = span_tree.read_export(_export(*_planted()))
    examined(1, "planted export")
    by_name = [s for s in spans if s.name == "call"]
    assert by_name and all(s.span_id != ROOT for s in by_name)
    assert span_tree.step_tree(spans, _receipt()).root.span_id == ROOT


def test_a_span_no_step_joins_is_listed_as_unjoined(examined):
    spans = span_tree.read_export(_export(*_planted()))
    run = span_tree.run_section(spans, [_receipt()])
    examined(1, "run")
    listed = re.findall(r'data-unjoined="([0-9a-f]{16})"', run)
    #: In a recorded trace and in no step's tree; a span of an unrecorded trace is not this run's.
    assert listed == [LOOSE]
    assert span_tree.UNJOINED_HEAD in _text(run) and "from the app's traces, not checked by onetrace" in _text(run)


def test_a_step_whose_recorded_span_is_not_in_the_export_is_unjoined(examined):
    spans = span_tree.read_export(_export(*_planted()))
    page = _section(spans, _receipt(span_id="9" * 16))
    examined(1, "step")
    assert 'data-span-tree="unjoined"' in page and "9" * 16 in page and "data-span-tree=\"waterfall\"" not in page
    assert _section(spans, {**_receipt(), "trace": {"trace_id": "c" * 32, "span_id": ROOT}}) == ""


@pytest.mark.parametrize("reported, agree", [([("model_call.json", "example-model")], "agrees"),
                                             ([("model_call.json", "another-model")], "disagrees"),
                                             ([("model_call.json", None)], "nothing"), ([], "nothing")],
                         ids=["the same model", "another model", "a record with no model", "no record"])
def test_the_span_s_model_against_the_step_s_records(reported, agree, examined):
    page = _section(span_tree.read_export(_export(*_planted())), reported=reported)
    examined(1, "model-call span")
    line = re.search(r'<li data-agree="([a-z]+)">(.*?)</li>', page, re.S)
    assert line.group(1) == agree
    if agree == "disagrees":
        assert "example-model" in _text(line.group(2)) and "another-model" in _text(line.group(2))
        assert "they do not agree" in _text(line.group(2))


def test_the_step_s_recorded_times_against_its_span_s(examined):
    spans = span_tree.read_export(_export(*_planted()))
    inside = _section(spans)
    outside = _section(spans, _receipt(started="2026-11-02T05:00:00.010+00:00"))
    examined(2, "steps")
    times = lambda p: re.findall(r'<li data-agree="([a-z]+)">(The step[^<]*recorded times)', p)  # noqa: E731
    assert [k for k, _ in times(inside)] == ["agrees"] and [k for k, _ in times(outside)] == ["disagrees"]
    #: Read to the millisecond the receipts give: a span starting within the step's first millisecond agrees.
    late = [dict(s, startTimeUnixNano=str(S0 + 100 * 10**6 + 400_000)) if s["spanId"] == ROOT else s
            for s in _planted()]
    assert [k for k, _ in times(_section(span_tree.read_export(_export(*late))))] == ["agrees"]


MALFORMED = {
    "not JSON": b"{not json",
    "a repeated name": b'{"resourceSpans": [], "resourceSpans": []}',
    "NaN": b'{"resourceSpans": [{"scopeSpans": [{"spans": [{"x": NaN}]}]}]}',
    "no resourceSpans": b'{"spans": []}',
    "a span id not hex": _export(dict(_planted()[0], spanId="SPAN")),
    "times not whole numbers": _export(dict(_planted()[0], startTimeUnixNano="1.5")),
    "an end before its start": _export(dict(_planted()[0], endTimeUnixNano="1")),
    "not UTF-8": b'{"resourceSpans": "\xff"}',
}


@pytest.mark.parametrize("name", list(MALFORMED))
def test_a_malformed_export_gets_no_view(name, examined):
    examined(1, f"export with {name}")
    with pytest.raises(span_tree.Unreadable):
        span_tree.read_export(MALFORMED[name])
    page = span_tree.step_section(span_tree.Unreadable("x"), _receipt(), "r", lambda p: None)
    assert 'data-span-tree="unreadable"' in page and "waterfall" not in page


def test_an_export_past_the_most_spans_gets_no_view(monkeypatch, examined):
    monkeypatch.setattr(span_tree, "MOST_SPANS", 3)
    examined(1, "export")
    with pytest.raises(span_tree.Unreadable, match="past this view's limit"):
        span_tree.read_export(_export(*_planted()))


def test_a_credential_shaped_attribute_is_never_shown(monkeypatch, examined):
    key = "Bearer " + "x" * 20
    spans = _planted()
    spans[1]["attributes"] += [_attr("http.request.header.authorization", key), _attr("exception.message", key),
                               _attr("api_key", "plain-value-0000")]
    spans[2]["status"]["message"] = key
    #: Even listed among the names shown, a name shaped like a credential is not.
    monkeypatch.setattr(span_tree, "SHOWN", span_tree.SHOWN + ("api_key", "http.request.header.authorization"))
    page = _section(span_tree.read_export(_export(*spans)))
    examined(4, "credential-shaped attributes and messages")
    for withheld in ("x" * 20, "plain-value-0000", "api_key", "authorization"):
        assert withheld not in page


@pytest.mark.parametrize("name, shaped", [("gen_ai.usage.input_tokens", False), ("gen_ai.usage.output_tokens", False),
                                           ("http.request.header.authorization", True), ("x-api-key", True),
                                           ("api_key", True), ("db.password", True), ("session.id", True),
                                           ("gen_ai.request.model", False), ("private_key", True)])
def test_a_name_shaped_like_a_credential(name, shaped, examined):
    examined(1, "name")
    assert span_tree.CREDENTIAL_NAME.search(name) is shaped


def test_the_value_shape_is_the_verifier_s_own(examined):
    import importlib.util
    source = open(importlib.util.find_spec("onetrace_verify").submodule_search_locations[0] + "/verify.py",
                  encoding="utf-8").read()
    got = re.search(r'^_MC_CRED_SHAPE = re\.compile\(r"(.*)"\)$', source, re.M).group(1)
    examined(1, "pattern")
    assert span_tree.CREDENTIAL_VALUE.pattern == got


def test_limits_as_the_json_view_s(monkeypatch, examined):
    long = "m" * (span_tree.LIMIT + 1)
    spans = _planted()
    spans[1]["attributes"].append(_attr("gen_ai.response.model", long))
    monkeypatch.setattr(span_tree, "MAX_MEMBERS", 2)
    page = _section(span_tree.read_export(_export(*spans)))
    examined(2, "limits")
    assert long not in page and "data-digest" in page
    assert len(re.findall(r"<tr data-span=", page)) == 2 and span_tree.MORE.format(n=2) in _text(page)


@pytest.mark.parametrize("word", ["caused", "because", "why"])
def test_no_line_says_what_produced_a_difference(word, examined):
    lines = [v for k, v in vars(span_tree).items() if k.isupper() and isinstance(v, str)] + list(span_tree.NON_CLAIMS)
    examined(len(lines), "lines")
    assert not any(re.search(rf"\b{word}\b", line, re.I) for line in lines)


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    """A run recorded inside the app's span, with the app's export given beside it."""
    import os
    from onetrace_console import beside
    from onetrace_console.checks import run_and_record
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store
    from tests.model_call_runs import record_run
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    folder = tmp_path_factory.mktemp("span-tree")
    before = os.environ.get("TRACEPARENT")
    os.environ["TRACEPARENT"] = f"00-{T}-{ROOT}-01"
    try:
        made = record_run(folder / "a", "span-a")
    finally:
        os.environ.pop("TRACEPARENT") if before is None else os.environ.__setitem__("TRACEPARENT", before)
    receipt = json.loads(next((made / "receipts").glob("*.json")).read_bytes())
    s0, s1 = (span_tree._ns(receipt["time"][k]) for k in ("started", "ended"))
    planted = [dict(_span(ROOT, "handle request", 0, 0), startTimeUnixNano=str(s0 - 10**6),
                    endTimeUnixNano=str(s1 + 10**6)),
               dict(_span(MODEL, "chat example-model.reported", 0, 0, ROOT,
                          attrs=[("gen_ai.response.model", "example-model.reported")]),
                    startTimeUnixNano=str(s0), endTimeUnixNano=str(s0)),
               dict(_span(LOOSE, "other work", 0, 0), startTimeUnixNano=str(s1 + 5 * 10**6),
                    endTimeUnixNano=str(s1 + 6 * 10**6))]
    store = Store(folder / "store")
    run = run_and_record(_deliver(made, store, outputs=True), store, ran_at=FIXED_RAN_AT)
    beside.keep(store, run.key, trace=_export(*planted), trace_source=beside.GIVEN)
    with rendering(onedoor=False, sign_in=False, public=True):
        return render_execution(run, store, generated_at="2026-11-02T06:00:00+00:00").pages


def test_a_recorded_run_s_step_and_run_pages_carry_the_view(recorded, examined):
    step = next(p for n, p in recorded.items() if re.fullmatch(r"stage-\d+\.html", n.split("/")[-1]))
    case = next(p for n, p in recorded.items() if n.endswith("case.html"))
    examined(2, "pages")
    assert 'data-section="span-tree"' in step and f'data-span="{MODEL}"' in step
    assert re.search(r'<li data-agree="agrees">The span <code>chat example-model.reported</code>', step)
    assert re.search(r'<li data-agree="agrees">The step[^<]*recorded times', step)
    assert f'data-unjoined="{LOOSE}"' in case
