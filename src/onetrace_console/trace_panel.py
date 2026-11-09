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
its place. It shows, for the first-difference step, both runs' spans: for each span (by name and order
within the step, children under their step's), one table, one row per attribute -- duration, start
offset within the run, and the `gen_ai.*` and `onetrace.*` attributes -- attribute | baseline |
candidate, so the values line up. The rows that differ come first, marked "differs" in a column of
their own; the rows that are the same are folded under "N attributes the same". Every trace view says it is what the app reported, never something onetrace
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
#: What the ids are for, said once under the run page's heading: and where they lead from this console.
SPAN_FOR = ("The traceparent, trace id and span id are pointers into the app's own tracing tool: they are "
            "how to find this run's spans there.")
SPAN_OPENS = "This console has a tracing tool configured: each trace id's link opens it there."
SPAN_NO_TOOL = "This console has no tracing tool configured, so no id links to one."
SPAN_PUBLIC = "This is a public console: it links to no tracing tool."
OPEN = "Open in your tracing tool"
PANEL_HEADING = "At step {step}: spans from your app's traces ({where})"
#: Where the spans come from, in the heading's words.
WHERE = {"given": "the files under traces/", "export": "onetrace export otel of each run"}
COLUMNS = ("attribute", "baseline", "candidate")
DIFFERS_WORD = "differs"
DIFFERS_COLUMN = "whether it differs"
SAME = "{n} attributes the same"
SAME_ONE = "1 attribute the same"
DURATION, OFFSET = "duration", "start, from the run's first span"
ABSENT = "—"
PANEL_LEAD = "From the app's own traces, as reported. Not checked by onetrace."
MATCHES, DIFFERS = "matches the receipt", "differs from the receipt"
NO_FILE = "No trace file for the {role} run."
NO_SPAN = "No span for `{stage}` in the {role} run's trace file."
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


def run_section(manifest: dict, steps: list[dict], pattern: str | None = None, *, public: bool = False) -> str:
    """The run page's span-context section; empty for a run with no span context. Under its lead, what
    the ids are for, and where they lead from this console: a configured tracing tool's link (`pattern`),
    none configured, or a public console, which links to none."""
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
    where = SPAN_PUBLIC if public else (SPAN_OPENS if link(pattern, "0" * 32) else SPAN_NO_TOOL)
    return (f'<section data-section="span-context" class="span-context"><h2>{escape(SPAN_HEADING)}</h2>'
            f'<p class="reported">{escape(SPAN_LEAD)}</p>'
            f'<p data-span-for>{escape(SPAN_FOR)} {escape(where)}</p><ul class="plain">{"".join(rows)}</ul></section>')


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


def _rows(sa: dict | None, sb: dict | None, origins: tuple) -> list[tuple[str, str, str, bool]]:
    """(attribute, baseline's value, candidate's value, whether they differ), for one span pair: its
    duration, its start offset in its run, then each shown attribute, by name."""
    def shown(s):
        return {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in sorted(s["attrs"].items())
                if k.startswith(SHOWN)} if s else {}
    out = []
    for name, f in ((DURATION, lambda s, o: _ms(s["end"] - s["start"])), (OFFSET, lambda s, o: _ms(s["start"] - o))):
        va = f(sa, origins[0]) if sa else None
        vb = f(sb, origins[1]) if sb else None
        out.append((name, va, vb, va != vb))
    xa, xb = shown(sa), shown(sb)
    for k in sorted(xa.keys() | xb.keys()):
        out.append((k, xa.get(k), xb.get(k), xa.get(k) != xb.get(k)))
    return out


def _row(name: str, va, vb, differs: bool) -> str:
    def cell(v):
        return f"<td>{escape(ABSENT)}</td>" if v is None else f"<td>{code_or_fold(v)}</td>"
    mark = ' data-differs="yes"' if differs else ""
    #: Every cell a `td`, so a row stacked at a narrow width labels each by its column (`words.labelled`).
    return (f'<tr{mark}><td data-attribute><span class="k">{escape(name)}</span></td>{cell(va)}{cell(vb)}'
            f'<td data-differs-cell>{escape(DIFFERS_WORD) if differs else ""}</td></tr>')


def _span_table(sa: dict | None, sb: dict | None, origins: tuple, receipt_digests: tuple) -> str:
    """One span pair's table: the differing rows, then the same rows folded under their count."""
    rows = _rows(sa, sb, origins)
    first = [r for r in rows if r[3]]
    same = [r for r in rows if not r[3]]
    named = (sa or sb)["name"]
    depth = (sa or sb).get("depth", 0)
    head = "".join(f'<th scope="col">{escape(c)}</th>' for c in COLUMNS) + f'<th scope="col" aria-label="{escape(DIFFERS_COLUMN)}"></th>'
    said = ""
    for s, digest, role in ((sa, receipt_digests[0], "baseline"), (sb, receipt_digests[1], "candidate")):
        got = s["attrs"].get("onetrace.receipt.digest") if s else None
        if isinstance(got, str) and digest and s["depth"] == 0:
            said += (f'<p data-trace-receipt="{"matches" if got == digest else "differs"}">{escape(role)}: '
                     f'{escape(MATCHES if got == digest else DIFFERS)}</p>')
    from onetrace_console.words import scroll_region
    fold = ""
    if same:
        n = SAME_ONE if len(same) == 1 else SAME.format(n=len(same))
        fold = (f"<details data-trace-same><summary>{escape(n)}</summary>"
                + scroll_region(f'<table class="board" data-trace="same"><thead><tr>{head}</tr></thead>'
                                f'<tbody>{"".join(_row(*r) for r in same)}</tbody></table>', n, "trace-same")
                + "</details>")
    return (f'<div data-trace-span data-depth="{depth}"><p><code>{escape(named)}</code></p>'
            + scroll_region(f'<table class="board" data-trace="spans"><thead><tr>{head}</tr></thead>'
                            f'<tbody>{"".join(_row(*r) for r in first)}</tbody></table>', named, "trace")
            + f"{fold}{said}</div>")


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
        where = " and ".join(dict.fromkeys(WHERE.get(s, s) for s in sources if s)) or WHERE["export"]
        h1, h2 = PANEL_HEADING.split("{step}")
        return (f'<section data-section="trace-panel" class="trace-panel"><h2>{escape(h1)}<code>{escape(stage)}</code>'
                f'{escape(h2.format(where=where))}</h2><p class="reported">{escape(PANEL_LEAD)}</p>{body}</section>')
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
    tables = "".join(_span_table(a.get(k), b.get(k), (oa, ob), receipt_digests) for k in order)
    where = " and ".join(dict.fromkeys(WHERE.get(s, s) for s in sources if s)) or WHERE["export"]
    h1, h2 = PANEL_HEADING.split("{step}")
    heading = f"<h2>{escape(h1)}<code>{escape(stage)}</code>{escape(h2.format(where=where))}</h2>"
    return (f'<section data-section="trace-panel" class="trace-panel">{heading}'
            f'<p class="reported">{escape(PANEL_LEAD)}</p>{"".join(f"<p>{escape(n)}</p>" for n in notes)}'
            f"{tables}</section>")
