"""Trace context: the span context a run recorded, a link to the person's own tracing tool, and the
side-by-side trace panel at a comparison's first difference.

onetrace 0.5 records, where a step ran inside an OpenTelemetry span, the span's ids in the receipt
(`trace`: `trace_id`, `span_id`) and the run's `traceparent` in its manifest. The run page shows
them; a step with none says "ran outside any span"; a run with no span context shows nothing new.

On a local console only, a link pattern the person sets (`"tracing": {"link": "<url with {trace_id}
and optional {span_id}>"}` in the console's configuration) makes each id a link, "Open in your
tracing tool". The console builds the link and never calls it.

The trace panel reads OTLP/JSON: the SDK's own export of each run (`onetrace export otel`, made when
the run is checked), or a file the person gives under `traces/` in the runs folder, which is used in
its place. It shows, for the first-difference step, both runs' spans side by side: name, duration,
start offset within the run, the `gen_ai.*` and `onetrace.*` attributes, and child spans; values
that differ are marked. Every trace view says it is what the app reported, never something onetrace
checked. A span's `onetrace.receipt.digest` is set beside the step's receipt digest: "matches the
receipt" or "differs from the receipt"; with none, nothing.
"""
from __future__ import annotations

import json
import re

from onetrace_console.words import escape

SPAN_HEADING = "Span context"
SPAN_LEAD = "The span context the app reported, as the run recorded it. onetrace does not check it."
OUTSIDE = "ran outside any span"
OPEN = "Open in your tracing tool"
PANEL_HEADING = "The app's spans at the first difference"
PANEL_LEAD = "From the app's own traces, as reported. Not checked by onetrace."
MATCHES, DIFFERS = "matches the receipt", "differs from the receipt"
NO_FILE = "No trace file for the {role} run."
NO_SPAN = "No span for `{stage}` in the {role} run's trace file."
SOURCES = {"export": "onetrace export otel of the run, made when it was checked",
           "given": "the file given under traces/ with the runs"}
#: The attributes the panel shows, by their prefix.
SHOWN = ("gen_ai.", "onetrace.")
_HEX = {"trace_id": re.compile(r"[0-9a-f]{32}"), "span_id": re.compile(r"[0-9a-f]{16}")}


def trace_of(receipt: dict) -> dict | None:
    t = receipt.get("trace") if isinstance(receipt, dict) else None
    if not isinstance(t, dict):
        return None
    out = {k: t.get(k) for k in ("trace_id", "span_id")}
    return out if all(isinstance(v, str) and _HEX[k].fullmatch(v) for k, v in out.items()) else None


def traceparent(manifest: dict) -> str:
    tp = manifest.get("traceparent") if isinstance(manifest, dict) else None
    return tp if isinstance(tp, str) and re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", tp) else ""


def link(pattern: str | None, trace_id: str, span_id: str = "") -> str:
    """The person's link for an id, built and never called; "" with no pattern, or one that is
    not an http(s) address holding `{trace_id}`."""
    if not pattern or "{trace_id}" not in pattern or not re.match(r"https?://", pattern):
        return ""
    return pattern.replace("{trace_id}", trace_id).replace("{span_id}", span_id)


def _id(label: str, value: str, href: str) -> str:
    a = (f' <a href="{escape(href)}" rel="noreferrer" data-trace-link>{escape(OPEN)}</a>' if href else "")
    return f'<li><span class="k">{escape(label)}</span> <code>{escape(value)}</code>{a}</li>'


def run_section(manifest: dict, steps: list[dict], pattern: str | None = None) -> str:
    """The run page's span-context section; empty for a run with no span context."""
    tp = traceparent(manifest)
    traces = [(s, trace_of(s.get("receipt") or {})) for s in steps]
    if not tp and not any(t for _, t in traces):
        return ""
    rows = []
    if tp:
        tid = tp.split("-")[1]
        rows.append(_id("the run's traceparent", tp, link(pattern, tid, tp.split("-")[2])))
    for s, t in traces:
        r = s.get("receipt") or {}
        name = (r.get("stage") or {}).get("name", "") if isinstance(r.get("stage"), dict) else ""
        if t is None:
            rows.append(f'<li data-trace-step="{escape(name)}"><code>{escape(name)}</code>: {escape(OUTSIDE)}</li>')
        else:
            rows.append(f'<li data-trace-step="{escape(name)}"><code>{escape(name)}</code><ul class="plain">'
                        + _id("trace id", t["trace_id"], link(pattern, t["trace_id"], t["span_id"]))
                        + _id("span id", t["span_id"], "") + "</ul></li>")
    return (f'<section data-section="span-context" class="span-context"><h2>{escape(SPAN_HEADING)}</h2>'
            f'<p class="reported">{escape(SPAN_LEAD)}</p><ul class="plain">{"".join(rows)}</ul></section>')


# ------------------------------------------------------------------ OTLP/JSON

class TraceUnreadable(ValueError):
    pass


def _value(v: dict):
    if not isinstance(v, dict) or len(v) != 1:
        return json.dumps(v, sort_keys=True)
    (k, x), = v.items()
    if k == "arrayValue":
        return [_value(i) for i in (x or {}).get("values", [])]
    return x


def spans(doc) -> list[dict]:
    """Every span of an OTLP/JSON document: id, parent, name, start and end (ns), attributes."""
    if not isinstance(doc, dict) or not isinstance(doc.get("resourceSpans"), list):
        raise TraceUnreadable("not an OTLP/JSON trace: no resourceSpans")
    out = []
    for rs in doc["resourceSpans"]:
        for ss in (rs or {}).get("scopeSpans") or []:
            for sp in (ss or {}).get("spans") or []:
                if not isinstance(sp, dict):
                    continue
                try:
                    start, end = int(sp.get("startTimeUnixNano", 0)), int(sp.get("endTimeUnixNano", 0))
                except (TypeError, ValueError):
                    raise TraceUnreadable("a span's times are not whole numbers") from None
                attrs = {a.get("key"): _value(a.get("value")) for a in sp.get("attributes") or []
                         if isinstance(a, dict) and isinstance(a.get("key"), str)}
                out.append({"id": str(sp.get("spanId", "")), "parent": str(sp.get("parentSpanId", "") or ""),
                            "name": str(sp.get("name", "")), "start": start, "end": end, "attrs": attrs})
    return out


def step_spans(all_spans: list[dict], stage: str) -> list[dict]:
    """The step's span (by `onetrace.node`, or `onetrace.stage`, or its name) and its descendants, in
    start order, each with its depth below the step's."""
    top = [s for s in all_spans if s["attrs"].get("onetrace.node") == stage
           or s["attrs"].get("onetrace.stage") == stage or s["name"] in (stage, f"onetrace.stage {stage}")]
    out = []

    def walk(s, depth):
        out.append({**s, "depth": depth})
        for c in sorted((c for c in all_spans if c["parent"] == s["id"]), key=lambda c: c["start"]):
            walk(c, depth + 1)
    for s in sorted(top, key=lambda s: s["start"]):
        walk(s, 0)
    return out


def code_or_fold(text: str) -> str:
    """A value in a list or table: a fingerprint short, the whole of it in its fold (as every page
    shows one); a value holding fingerprints (a list of them, say) as code with each one short and
    the whole ones in a fold after it; anything else as code, as written."""
    from onetrace_console.viewer.page import _FINGERPRINT, fingerprint_html, shortened_in_text
    if _FINGERPRINT.fullmatch(text):
        return fingerprint_html(text)
    inline, folded = shortened_in_text(text)
    return f"<code>{inline}</code>{folded}"


def _ms(ns: int) -> str:
    return f"{ns / 1e6:.1f} ms"


def _cell(s: dict | None, origin: int, other: dict | None, receipt_digest: str) -> str:
    if s is None:
        return "<td>—</td>"
    attrs = {k: v for k, v in sorted(s["attrs"].items()) if k.startswith(SHOWN)}
    oattrs = other["attrs"] if other else {}
    lines = []
    for k, v in attrs.items():
        mark = ' data-differs="yes"' if other is not None and oattrs.get(k) != v else ""
        lines.append(f'<li{mark}><span class="k">{escape(k)}</span> {code_or_fold(json.dumps(v) if not isinstance(v, str) else v)}'
                     + (' <span class="mark">differs</span>' if mark else "") + "</li>")
    digest = s["attrs"].get("onetrace.receipt.digest")
    said = ""
    if isinstance(digest, str) and receipt_digest and s["depth"] == 0:
        said = f'<p data-trace-receipt="{"matches" if digest == receipt_digest else "differs"}">' \
               f'{escape(MATCHES if digest == receipt_digest else DIFFERS)}</p>'
    dur, off = s["end"] - s["start"], s["start"] - origin
    dmark = ' data-differs="yes"' if other is not None and (other["end"] - other["start"]) != dur else ""
    return (f'<td><p><code>{escape(s["name"])}</code></p><p{dmark}>{escape(_ms(dur))}, from {escape(_ms(off))}</p>'
            f'{said}<ul class="plain">{"".join(lines)}</ul></td>')


def panel(stage: str, docs: tuple, sources: tuple, receipt_digests: tuple, roles=("baseline", "candidate")) -> str:
    """The side-by-side panel for `stage`; `docs` the two OTLP/JSON documents (None where none)."""
    found, notes = [], []
    for doc, role in zip(docs, roles):
        if doc is None:
            found.append(None)
            notes.append(NO_FILE.format(role=role))
            continue
        try:
            every = spans(doc)
        except TraceUnreadable as e:
            found.append(None)
            notes.append(f"The {role} run's trace file cannot be read: {e}.")
            continue
        origin = min((s["start"] for s in every), default=0)
        mine = step_spans(every, stage)
        if not mine:
            notes.append(NO_SPAN.format(stage=stage, role=role).replace("`", ""))
        found.append((mine, origin))
    if all(f is None or not f[0] for f in found):
        body = "".join(f"<p>{escape(n)}</p>" for n in notes)
        return (f'<section data-section="trace-panel" class="trace-panel"><h2>{escape(PANEL_HEADING)}</h2>'
                f'<p class="reported">{escape(PANEL_LEAD)}</p>{body}</section>')
    #: Paired by name and order within the step.
    keyed = []
    for f in found:
        seen, out = {}, []
        for s in (f[0] if f else []):
            seen[s["name"]] = seen.get(s["name"], 0) + 1
            out.append(((s["name"], seen[s["name"]]), s))
        keyed.append(out)
    order = list(dict.fromkeys([k for k, _ in keyed[0]] + [k for k, _ in keyed[1]]))
    a, b = dict(keyed[0]), dict(keyed[1])
    oa, ob = (f[1] if f else 0 for f in found)
    rows = "".join(f"<tr>{_cell(a.get(k), oa, b.get(k), receipt_digests[0])}{_cell(b.get(k), ob, a.get(k), receipt_digests[1])}</tr>"
                   for k in order)
    src = " · ".join(f"{role}: {SOURCES.get(s, s)}" for role, s in zip(roles, sources) if s)
    from onetrace_console.words import scroll_region
    table = scroll_region(f'<table class="board" data-trace="spans"><thead><tr><th>{escape(roles[0])}</th>'
                          f'<th>{escape(roles[1])}</th></tr></thead><tbody>{rows}</tbody></table>',
                          "The app's spans, side by side", "trace")
    return (f'<section data-section="trace-panel" class="trace-panel"><h2>{escape(PANEL_HEADING)}</h2>'
            f'<p class="reported">{escape(PANEL_LEAD)}</p><p class="source">At <code>{escape(stage)}</code>. '
            f'From {escape(src)}.</p>{"".join(f"<p>{escape(n)}</p>" for n in notes)}{table}</section>')
