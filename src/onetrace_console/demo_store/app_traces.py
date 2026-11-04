"""The demo's bundled app traces: example data, written for the demo, labelled as such.

The demo's apps record each run inside a span of their own (`traceparent_for`), but they are small
scripts with no tracer: nothing exported their spans. So that the public pages show a step's span
tree and the spans at a first difference, the build writes, for P10's agent runs and P3's triage
runs, an app export of the kind a tracer would give: the run's span (the trace id and span id each
receipt records), and under it, for each step, its model, tool and HTTP calls, placed within that
step's recorded times. Every span is invented; the export's resource says so (`demo.note`), and
the pages say what the file says.

It is added beside onetrace's own export of the run, in `traces/<run folder>.json`, as a resource
of its own (`SERVICE`); one already there is replaced, so a build from an earlier build writes it
once. Nothing else in the file changes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from onetrace_console.bounded_json import load_json_bounded

SERVICE = "example-app"
NOTE = "example data, written for the demo; no app was traced and nothing was observed"
#: P10's agent and P3's triage runs, by their folders' prefixes; a sub-agent run records no calls.
PLANS = ("pz-5", "p3-")


def _id(*parts: str, n: int = 16) -> str:
    return hashlib.sha256(("onetrace-console demo app span: " + "/".join(parts)).encode("utf-8")).hexdigest()[:n]


def _ns(value: str) -> int:
    from onetrace_console.span_tree import _ns as ns
    got = ns(value)
    if got is None:
        raise ValueError(f"a recorded time this build does not read: {value!r}")
    return got


def _attr(key: str, value) -> dict:
    return {"key": key, "value": {"intValue": str(value)} if isinstance(value, int) else {"stringValue": value}}


def _span(trace: str, sid: str, parent: str, name: str, start: int, end: int, attrs=(), status=None,
          events=()) -> dict:
    sp = {"traceId": trace, "spanId": sid, "parentSpanId": parent, "name": name, "kind": 1,
          "startTimeUnixNano": str(start), "endTimeUnixNano": str(end), "attributes": [_attr(k, v) for k, v in attrs],
          "status": status or {}}
    if events:
        sp["events"] = [{"name": n, "timeUnixNano": str(t), "attributes": []} for n, t in events]
    return sp


def _calls(folder: str, stage: str, index: int, trace: str, root: str, start: int, end: int) -> list[dict]:
    """The invented calls under one step, within its recorded times (a step recorded in under a
    millisecond gets a millisecond)."""
    u = max(end - start, 1_000_000) // 10
    sid = lambda role: _id(folder, str(index), role)  # noqa: E731
    candidate = "amount-changed" in folder or "retried" in folder
    if stage == "agent_step":
        tool_took = 7 * u if candidate else 3 * u
        tool_status = {"code": 2, "message": "price service returned 503"} if candidate else None
        retries = [("retry", start + 5 * u), ("retry", start + 6 * u)] if candidate else []
        return [
            _span(trace, sid("plan"), root, "chat example-org/example-model", start + u // 2, start + 2 * u,
                  [("gen_ai.operation.name", "chat"), ("gen_ai.request.model", "example-org/example-model@0123abc"),
                   ("gen_ai.response.model", "example-org/example-model"),
                   ("gen_ai.usage.input_tokens", 412 if candidate else 398),
                   ("gen_ai.usage.output_tokens", 61 if candidate else 57)]),
            _span(trace, sid("tool"), root, "execute_tool price_lookup", start + 2 * u, start + 2 * u + tool_took,
                  [("gen_ai.operation.name", "execute_tool"), ("gen_ai.tool.name", "price_lookup")],
                  tool_status, retries),
            _span(trace, sid("http"), sid("tool"), "GET", start + 2 * u + u // 4, start + 2 * u + tool_took - u // 4,
                  [("http.request.method", "GET"), ("server.address", "prices.example"),
                   ("http.response.status_code", 200), ("http.request.resend_count", 2 if candidate else 0)]),
            _span(trace, sid("reply"), root, "chat example-hosted-model", start + 2 * u + tool_took,
                  start + 3 * u + tool_took, [("gen_ai.operation.name", "chat"),
                                              ("gen_ai.request.model", "example-hosted-model")]),
        ]
    if stage == "classify":
        return [_span(trace, sid("classify"), root, "chat example-classifier", start + u, start + 8 * u,
                      [("gen_ai.operation.name", "chat"), ("gen_ai.request.model", "example-classifier"),
                       ("gen_ai.usage.input_tokens", 220), ("gen_ai.usage.output_tokens", 4)])]
    if stage == "lookup_account":
        failed = candidate and index == 3
        return [_span(trace, sid("lookup"), root, "GET", start + u, start + 8 * u,
                      [("http.request.method", "GET"), ("server.address", "accounts.example"),
                       ("http.response.status_code", 503 if failed else 200)],
                      {"code": 2, "message": "accounts service returned 503"} if failed else None)]
    if stage == "draft_reply":
        return [_span(trace, sid("draft"), root, "chat example-writer", start + u, start + 9 * u,
                      [("gen_ai.operation.name", "chat"), ("gen_ai.request.model", "example-writer"),
                       ("gen_ai.usage.input_tokens", 640), ("gen_ai.usage.output_tokens", 180)])]
    return []


def spans_for(run_dir: Path) -> list[dict]:
    """The run's invented app spans; [] where it has no plan, or records no span context."""
    folder = run_dir.name
    manifest = load_json_bounded((run_dir / "MANIFEST.json").read_bytes(), "the run's manifest")
    tp = manifest.get("traceparent")
    if not folder.startswith(PLANS) or not isinstance(tp, str) or tp.count("-") != 3:
        return []
    _v, trace, root, _f = tp.split("-")
    receipts = [load_json_bounded((run_dir / e["file"]).read_bytes(), "a receipt") for e in manifest.get("chain") or []]
    steps = [(r["stage"]["name"], _ns(r["time"]["started"]), _ns(r["time"]["ended"])) for r in receipts
             if isinstance(r.get("time"), dict) and isinstance(r.get("stage"), dict)]
    calls = [c for i, (stage, s, e) in enumerate(steps, start=1) for c in _calls(folder, stage, i, trace, root, s, e)]
    if not calls:
        return []
    first = min(s for _, s, _ in steps)
    last = max([e for _, _, e in steps] + [int(c["endTimeUnixNano"]) for c in calls])
    return [_span(trace, root, "", "handle request", first, last, [("server.address", "example-app.local")]), *calls]


def write(runs: Path, folders) -> list[str]:
    """Add each planned run's app spans to `traces/<folder>.json`; the folders written."""
    written = []
    for name in folders:
        run_dir = runs / name
        trace_file = runs / "traces" / f"{name}.json"
        if not (run_dir / "MANIFEST.json").is_file():
            continue
        spans = spans_for(run_dir)
        if not spans:
            continue
        doc = (load_json_bounded(trace_file.read_bytes(), "the run's trace export") if trace_file.is_file()
               else {"resourceSpans": []})
        kept = [rs for rs in doc.get("resourceSpans") or []
                if not any(a.get("key") == "service.name" and a.get("value") == {"stringValue": SERVICE}
                           for a in (rs.get("resource") or {}).get("attributes") or [])]
        kept.append({"resource": {"attributes": [_attr("service.name", SERVICE), _attr("demo.note", NOTE)]},
                     "scopeSpans": [{"scope": {"name": "example-app"}, "spans": spans}]})
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        trace_file.write_text(json.dumps({**doc, "resourceSpans": kept}, separators=(",", ":")), encoding="utf-8")
        written.append(name)
    return written
