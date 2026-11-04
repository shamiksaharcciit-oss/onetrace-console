"""A step's span tree: the app's own spans (its OTLP/JSON export), joined to the step by the trace
context onetrace recorded, as a timing waterfall.

The export. The trace file the person gives under `traces/<run folder>.json` (`beside`), read
strictly: UTF-8 JSON with no repeated name, no `NaN` or `Infinity`, numbers as written, nesting
within the console's limit (`json_diff.parse`), at most `MOST_SPANS` spans, each with a 32-hex
`traceId`, a 16-hex `spanId`, a name, and whole-number start and end times, the end not before the
start. Anything else gets no view: the page says the file cannot be read, and its reason.

The join. A step's receipt records the span it ran inside (`trace`: `trace_id`, `span_id`). The
step's span is the span in the export with that trace id and span id, and nothing else: never a
name, a time or a guess. Under it, its descendants; where the receipt records when the step started
and ended, the ones that start within those times, as several steps can run inside one span. A step
whose recorded span is not in the export is said to be unjoined; a span of a recorded trace that no
step's tree holds is listed on the run's page as unjoined.

What is shown. For each span: its name, what it is (a model call, a tool call, an HTTP call, from its
attributes: `gen_ai.request.model` or `gen_ai.operation.name` other than `execute_tool`; `execute_tool`
or `gen_ai.tool.name`; `http.request.method`), when it started within the step's span and how long
it took, with a bar, its model and tokens, its retries (`http.request.resend_count`, or else its
events named `retry`), its status and status message, and its events. Only the attributes in
`SHOWN` are shown, and never one whose name is shaped like a credential (`CREDENTIAL_NAME`) or whose
value has the verifier's authorization-header shape (`CREDENTIAL_VALUE`, the verifier's pattern as
written there, held equal to its source by a test).
A value longer than `json_diff.LIMIT` characters is shown by its sha256, and at most
`json_diff.MAX_MEMBERS` spans are listed, then how many more, as the JSON view does.

Checked against the record, where both name the same thing: the model each model-call span names
against what the step's model-call record in the same place reports (`model.reported`; spans and
records paired in call order, the first span with `model_call.json`), and the step's recorded start and end against
its span's, to the millisecond the receipts give. Each such line says whether they agree.
Everything else is from the app's traces, not checked by onetrace, and the page says so.

At a comparison's first difference, both runs' trees at that step side by side, and their
differences as facts, ranked (`RANK`): a status error, then retries, a model, a span on one side
only, tokens, then time (one side taking at least `TIMES` times the other). Spans are paired by name
and the order of that name in the tree. Each line says which run, what, on which span, and both
times: "candidate: 2 retries on price_lookup, status error, 3.1 s against 0.4 s". A line names what
the traces say, never what produced the difference, and changes no verdict.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from onetrace_console.json_diff import LIMIT, MAX_MEMBERS, Number, parse
from onetrace_console.words import escape

#: The most spans an export holds and still gets a view.
MOST_SPANS = 10_000
HEADING = "The app's spans for this step"
#: A resource attribute in an export, saying what its spans are (the demo's: example data).
NOTE_KEY = "demo.note"
LABELLED = "The trace file says of these spans: {note}"
LEAD = "From the app's traces, not checked by onetrace."
NON_CLAIMS = (
    "The spans are the app's own report of what it did.",
    "onetrace checks the join, the trace context it recorded for this step, not what the spans say.",
    "A span difference is not a verdict and changes no verdict.",
)
NON_CLAIMS_HEAD = "What these spans do not say"
JOINED = "Joined by the trace context onetrace recorded for this step: trace {trace_id}, span {span_id}."
WITHIN = "Under it, the spans that start within this step's recorded times."
UNJOINED_STEP = ("Unjoined: the trace file holds spans in this step's recorded trace, but none with the "
                 "span id this step recorded, {span_id}.")
UNREADABLE = "The trace file cannot be read, so there is no span view: {reason}."
COLUMNS = ("Span", "What", "Start", "Took", "", "Model", "Tokens in / out", "Retries", "Status")
MORE = "… {n} more spans"
NAMED = "Each attribute shown is one of the names this view shows; a name shaped like a credential never is."
CHECKED_HEAD = "Checked against the record"
MODEL_AGREES = ("The span {span} names the model {model}, and the step's model-call record {record} reports it: "
                "they agree.")
MODEL_DIFFERS = ("The span {span} names the model {model}; the step's model-call record {record} reports {reported}: "
                 "they do not agree.")
MODEL_NOTHING = ("The span {span} names the model {model}; {record} reports no model, so there is nothing to check "
                 "it against.")
#: The model-call spans and the step's records are paired in order: the first span with `model_call.json`.
NO_RECORD = "no model-call record of the step is left to pair with it"
TIMES_AGREE = ("The step's recorded times, {started} to {ended}, lie within its span's, {span_started} to "
               "{span_ended}: they agree.")
TIMES_DIFFER = ("The step's recorded times, {started} to {ended}, do not lie within its span's, {span_started} "
                "to {span_ended}: they do not agree.")
UNJOINED_HEAD = "The app's spans no step joins"
UNJOINED_LEAD = ("Spans in a trace this run recorded that no step's tree holds: from the app's traces, not "
                 "checked by onetrace.")
#: OTLP's status codes.
STATUS = {"0": "unset", "1": "ok", "2": "error", "STATUS_CODE_UNSET": "unset", "STATUS_CODE_OK": "ok",
          "STATUS_CODE_ERROR": "error"}
MODEL, TOOL, HTTP, OTHER = "model call", "tool call", "HTTP call", "span"
#: The attributes shown, by name.
SHOWN = ("gen_ai.system", "gen_ai.provider.name", "gen_ai.operation.name", "gen_ai.request.model",
         "gen_ai.response.model", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
         "gen_ai.tool.name", "http.request.method", "http.response.status_code", "http.request.resend_count",
         "server.address", "error.type", "exception.type", "exception.message")
#: A name shaped like a credential: one of its parts (split at `.`, `_` and `-`) is one of these words, or
#: two parts read "api key" or "private key". Never shown, whatever list it is on.
CREDENTIAL_WORDS = frozenset({"password", "passwd", "pass", "secret", "token", "apikey", "credential", "credentials",
                              "authorization", "auth", "cookie", "session", "bearer"})


class _CredentialName:
    """`search(name)`: whether the name is shaped like a credential."""

    @staticmethod
    def search(name: str) -> bool:
        parts = [p for p in re.split(r"[._\-\s]+", name.lower()) if p]
        pairs = {(a, b) for a, b in zip(parts, parts[1:])}
        return bool(CREDENTIAL_WORDS.intersection(parts) or {("api", "key"), ("private", "key")} & pairs)


CREDENTIAL_NAME = _CredentialName()
#: Recorded times are to the millisecond: a span is read against them at that precision.
_MS = 1_000_000
_HEX32, _HEX16, _DIGITS = re.compile(r"[0-9a-f]{32}"), re.compile(r"[0-9a-f]{16}"), re.compile(r"[0-9]{1,20}")


#: The verifier's authorization-header shape (`onetrace_verify.verify._MC_CRED_SHAPE`), as written there:
#: the verifier runs as its own program and is not imported, so a test holds this equal to its source.
CREDENTIAL_VALUE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")


def credential_value(value: str) -> bool:
    """A value with the verifier's authorization-header shape."""
    return bool(CREDENTIAL_VALUE.search(value))


class Unreadable(ValueError):
    pass


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent: str
    name: str
    start: int
    end: int
    status: str = "unset"
    message: str = ""
    attrs: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    #: What the export says of its own spans (its resource's `demo.note`), as written.
    note: str = ""

    @property
    def took(self) -> int:
        return self.end - self.start

    @property
    def what(self) -> str:
        op = str(self.attrs.get("gen_ai.operation.name", ""))
        if op == "execute_tool" or "gen_ai.tool.name" in self.attrs:
            return TOOL
        if "gen_ai.request.model" in self.attrs or "gen_ai.response.model" in self.attrs or op:
            return MODEL
        if "http.request.method" in self.attrs:
            return HTTP
        return OTHER

    @property
    def model(self) -> str:
        return str(self.attrs.get("gen_ai.response.model") or self.attrs.get("gen_ai.request.model") or "")

    @property
    def retries(self) -> int:
        n = self.attrs.get("http.request.resend_count")
        if isinstance(n, str) and _DIGITS.fullmatch(n):
            return int(n)
        return sum(1 for e in self.events if e["name"] == "retry")


def _scalar(v: dict):
    """An OTLP AnyValue as a string, or None where it is not a scalar this view reads."""
    if not isinstance(v, dict) or len(v) != 1:
        return None
    (k, x), = v.items()
    if k == "stringValue" and isinstance(x, str):
        return x
    if k in ("intValue", "doubleValue") and isinstance(x, (str, Number)):
        return str(x)
    if k == "boolValue" and isinstance(x, bool):
        return "true" if x else "false"
    return None


def _attrs(items) -> dict:
    """The attributes this view shows: on `SHOWN`, never shaped like a credential, by name or value."""
    out = {}
    for a in items if isinstance(items, list) else []:
        if not isinstance(a, dict) or not isinstance(a.get("key"), str):
            continue
        key, value = a["key"], _scalar(a.get("value"))
        if key not in SHOWN or CREDENTIAL_NAME.search(key) or value is None or credential_value(value):
            continue
        out[key] = value
    return out


def _time(v, what: str) -> int:
    if isinstance(v, (str, Number)) and _DIGITS.fullmatch(str(v)):
        return int(str(v))
    raise Unreadable(f"a span's {what} is not a whole number of nanoseconds")


def read_export(raw: bytes | None) -> list[Span]:
    """Every span of an OTLP/JSON export, read strictly; `Unreadable` with the reason otherwise."""
    ok, doc = parse(raw)
    if not ok:
        raise Unreadable("it is not JSON as this view reads it (UTF-8, no repeated name, no NaN or Infinity, "
                         "within the nesting limit)")
    if not isinstance(doc, dict) or not isinstance(doc.get("resourceSpans"), list):
        raise Unreadable("it is not an OTLP/JSON trace: no resourceSpans")
    out = []
    for rs in doc["resourceSpans"]:
        res = rs.get("resource") if isinstance(rs, dict) and isinstance(rs.get("resource"), dict) else {}
        note = next((_scalar(a.get("value")) or "" for a in res.get("attributes") or []
                     if isinstance(a, dict) and a.get("key") == NOTE_KEY), "")
        note = "" if credential_value(note) else note
        scopes = rs.get("scopeSpans") if isinstance(rs, dict) else None
        if not isinstance(scopes, list):
            raise Unreadable("a resourceSpans entry has no scopeSpans list")
        for ss in scopes:
            spans = ss.get("spans") if isinstance(ss, dict) else None
            if not isinstance(spans, list):
                raise Unreadable("a scopeSpans entry has no spans list")
            for sp in spans:
                if len(out) >= MOST_SPANS:
                    raise Unreadable(f"it holds more than {MOST_SPANS} spans, past this view's limit")
                if not isinstance(sp, dict):
                    raise Unreadable("a span is not an object")
                tid, sid, parent = sp.get("traceId"), sp.get("spanId"), sp.get("parentSpanId") or ""
                if not (isinstance(tid, str) and _HEX32.fullmatch(tid) and isinstance(sid, str)
                        and _HEX16.fullmatch(sid) and isinstance(parent, str)
                        and (parent == "" or _HEX16.fullmatch(parent))):
                    raise Unreadable("a span's trace id, span id or parent id is not lowercase hex of its length")
                if not isinstance(sp.get("name"), str):
                    raise Unreadable("a span has no name")
                start, end = _time(sp.get("startTimeUnixNano"), "start"), _time(sp.get("endTimeUnixNano"), "end")
                if end < start:
                    raise Unreadable("a span ends before it starts")
                st = sp.get("status") if isinstance(sp.get("status"), dict) else {}
                code = STATUS.get(str(st.get("code", "0")), "unset")
                message = st.get("message") if isinstance(st.get("message"), str) else ""
                events = []
                for e in sp.get("events") or []:
                    if not isinstance(e, dict) or not isinstance(e.get("name"), str):
                        raise Unreadable("a span event has no name")
                    events.append({"name": e["name"], "time": _time(e.get("timeUnixNano"), "event time"),
                                   "attrs": _attrs(e.get("attributes"))})
                out.append(Span(tid, sid, parent, sp["name"], start, end, code,
                                "" if credential_value(message) else message,
                                _attrs(sp.get("attributes")), events, note))
    return out


def _ns(value) -> int | None:
    """A recorded time (ISO 8601 with its offset) in nanoseconds since the epoch, or None."""
    from datetime import datetime, timezone
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return None
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    d = t - epoch
    return (d.days * 86400 + d.seconds) * 1_000_000_000 + d.microseconds * 1000


@dataclass
class Tree:
    """A step's join: its span (or None, unjoined), and the spans under it, each with its depth."""
    root: Span | None
    rows: list
    started: int | None
    ended: int | None


def step_tree(spans: list[Span], receipt: dict) -> Tree | None:
    """The step's tree; None where the export holds no span of the step's recorded trace."""
    from onetrace_console.trace_panel import trace_of
    t = trace_of(receipt)
    if t is None or not any(s.trace_id == t["trace_id"] for s in spans):
        return None
    times = receipt.get("time") if isinstance(receipt.get("time"), dict) else {}
    started, ended = _ns(times.get("started")), _ns(times.get("ended"))
    root = next((s for s in spans if s.trace_id == t["trace_id"] and s.span_id == t["span_id"]), None)
    if root is None:
        return Tree(None, [], started, ended)
    kids: dict[str, list[Span]] = {}
    for s in spans:
        if s.trace_id == root.trace_id and s.parent:
            kids.setdefault(s.parent, []).append(s)
    rows = []

    def walk(s: Span, depth: int, top: bool):
        inside = top or started is None or ended is None or started <= s.start <= ended + _MS - 1
        if not inside:
            return
        rows.append((s, depth))
        for c in sorted(kids.get(s.span_id, []), key=lambda c: (c.start, c.span_id)):
            walk(c, depth + 1, False)
    walk(root, 0, True)
    return Tree(root, rows, started, ended)


def unjoined(spans: list[Span], receipts: list[dict]) -> list[Span]:
    """The spans of a trace the run recorded that no step's tree holds, in start order."""
    from onetrace_console.trace_panel import trace_of
    traces = {t["trace_id"] for t in (trace_of(r) for r in receipts) if t}
    held = set()
    for r in receipts:
        tree = step_tree(spans, r)
        if tree is not None:
            held |= {(s.trace_id, s.span_id) for s, _ in tree.rows}
    return sorted((s for s in spans if s.trace_id in traces and (s.trace_id, s.span_id) not in held),
                  key=lambda s: (s.start, s.span_id))


def ms(ns: int) -> str:
    return f"{ns / 1e6:.1f} ms" if ns < 1_000_000_000 else f"{ns / 1e9:.2f} s"


def value_html(v: str) -> str:
    """A value as code; one longer than the JSON view's limit by its sha256, as that view shows one."""
    if len(v) > LIMIT:
        return f'<code data-digest>sha256:{hashlib.sha256(v.encode("utf-8")).hexdigest()}</code>'
    return f"<code>{escape(v)}</code>"


def _bar(s: Span, origin: int, total: int) -> str:
    x = 100 * (s.start - origin) / total if total else 0
    w = max(100 * s.took / total if total else 100, 0.5)
    return ('<svg class="bar" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
            f'<rect x="{min(x, 99.5):.3f}" y="0" width="{min(w, 100 - min(x, 99.5)):.3f}" height="8"/></svg>')


def _row(s: Span, depth: int, origin: int, total: int) -> str:
    a = s.attrs
    tokens = (f'{escape(a.get("gen_ai.usage.input_tokens", "—"))} / {escape(a.get("gen_ai.usage.output_tokens", "—"))}'
              if s.what == MODEL else "")
    status = escape(s.status) + (f": {value_html(s.message)}" if s.message else "")
    events = "".join(f'<li data-span-event><code>{escape(e["name"])}</code> at {escape(ms(e["time"] - origin))}'
                     + "".join(f" · <span class=\"k\">{escape(k)}</span> {value_html(v)}" for k, v in e["attrs"].items())
                     + "</li>" for e in s.events)
    shown = "".join(f'<li><span class="k">{escape(k)}</span> {value_html(v)}</li>' for k, v in sorted(a.items()))
    extra = (f'<details class="span-attrs"><summary>Attributes and events</summary><ul class="plain">{shown}'
             f"{events}</ul></details>") if shown or events else ""
    return (f'<tr data-span="{escape(s.span_id)}" data-depth="{depth}" data-what="{escape(s.what)}"'
            f'{" data-status=\"error\"" if s.status == "error" else ""}>'
            f'<td><span class="indent" data-indent="{depth}">{"· " * depth}</span><code>{escape(s.name)}</code>{extra}</td>'
            f"<td>{escape(s.what)}</td><td>{escape(ms(s.start - origin))}</td><td>{escape(ms(s.took))}</td>"
            f"<td>{_bar(s, origin, total)}</td><td>{value_html(s.model) if s.model else ''}</td><td>{tokens}</td>"
            f'<td data-retries="{s.retries}">{s.retries or ""}</td><td>{status}</td></tr>')


def reported_models(receipt: dict, receipt_file: str, read_file) -> list[tuple[str, str | None]]:
    """The step's model-call records in order, each (its name, the model it reports or None): `model.reported`
    with a value; None where it gives none, or where the step page refuses the record."""
    from onetrace_console import model_call
    out = []
    for o in sorted(model_call.outputs(receipt), key=lambda o: _record_order(str(o.get("name", "")))):
        try:
            record = model_call.read_output(receipt_file, o, read_file)
        except Exception:  # noqa: BLE001 - a record the step page refuses reports nothing here
            out.append((str(o.get("name", "")), None))
            continue
        rep = record.get("model.reported")
        value = rep.get("value") if isinstance(rep, dict) else None
        out.append((str(o["name"]), value if isinstance(value, str) and value else None))
    return out


def _record_order(name: str) -> int:
    m = re.fullmatch(r"model_call(?:\.(\d+))?\.json", name)
    return int(m.group(1) or 1) if m else 10**9


def checked(tree: Tree, reported: list[str]) -> list[tuple[str, str]]:
    """(agrees, disagrees or nothing, the line) for each thing both the spans and the record name."""
    out = []
    calls = [s for s, _ in tree.rows if s.what == MODEL and s.model]
    for i, s in enumerate(calls):
        span, model = f"<code>{escape(s.name)}</code>", value_html(s.model)
        name, value = reported[i] if i < len(reported) else ("", None)
        record = f"<code>{escape(name)}</code>" if name else escape(NO_RECORD)
        if value is None:
            out.append(("nothing", _fill(MODEL_NOTHING, span=span, model=model,
                                         record=(f"the step's model-call record {record}" if name else record))))
        elif value == s.model:
            out.append(("agrees", _fill(MODEL_AGREES, span=span, model=model, record=record)))
        else:
            out.append(("disagrees", _fill(MODEL_DIFFERS, span=span, model=model, record=record,
                                           reported=value_html(value))))
    root = tree.root
    if root is not None and tree.started is not None and tree.ended is not None:
        inside = root.start // _MS * _MS <= tree.started <= tree.ended <= -(-root.end // _MS) * _MS
        when = {k: _time_html(_iso(v)) for k, v in (("started", tree.started), ("ended", tree.ended),
                                                   ("span_started", root.start), ("span_ended", root.end))}
        out.append(("agrees" if inside else "disagrees", _fill(TIMES_AGREE if inside else TIMES_DIFFER, **when)))
    return out


def _time_html(iso: str) -> str:
    """A time in the one form, to the millisecond."""
    from onetrace_console.words import clock, short_time, time_html
    return time_html(iso, text=f"{short_time(iso)[:10]} {clock(iso)}")


def _iso(ns: int) -> str:
    from datetime import datetime, timezone
    t = datetime.fromtimestamp(ns // 1_000_000_000, tz=timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S") + f".{(ns % 1_000_000_000) // 1_000_000:03d}+00:00"


def _fill(template: str, **parts) -> str:
    """`template` with each part as already drawn markup; the words around them escaped."""
    out, at = [], 0
    for m in re.finditer(r"\{(\w+)\}", template):
        out.append(escape(template[at:m.start()]) + parts[m.group(1)])
        at = m.end()
    return "".join(out) + escape(template[at:])


def _labelled(spans) -> str:
    notes = sorted({s.note for s in spans if s.note})
    return "".join(f'<p data-span-note>{escape(LABELLED.format(note=n[:LIMIT]))}</p>' for n in notes)


def _non_claims() -> str:
    return (f'<div data-span-non-claims><p class="k">{escape(NON_CLAIMS_HEAD)}</p><ul class="plain">'
            + "".join(f"<li>{escape(n)}</li>" for n in NON_CLAIMS) + "</ul></div>")


def step_section(spans, receipt: dict, receipt_file: str, read_file) -> str:
    """The step page's span view; "" where the run has no trace file holding a span of the step's
    recorded trace. `spans`: the run's read export, an `Unreadable`, or None."""
    from onetrace_console.trace_panel import trace_of
    from onetrace_console.words import scroll_region
    if spans is None or trace_of(receipt) is None:
        return ""
    head = (f'<section data-section="span-tree" class="span-tree"><h2>{escape(HEADING)}</h2>'
            f'<p class="reported">{escape(LEAD)}</p>')
    if isinstance(spans, Unreadable):
        return head + f'<p data-span-tree="unreadable">{escape(UNREADABLE.format(reason=spans))}</p></section>'
    tree = step_tree(spans, receipt)
    if tree is None:
        return ""
    t = trace_of(receipt)
    if tree.root is None:
        return (head + f'<p data-span-tree="unjoined">{escape(UNJOINED_STEP.format(span_id=t["span_id"]))}</p>'
                + _non_claims() + "</section>")
    origin, total = tree.root.start, max(tree.root.took, 1)
    shown, more = tree.rows[:MAX_MEMBERS], len(tree.rows) - MAX_MEMBERS
    heads = "".join(f"<th>{escape(c)}</th>" for c in COLUMNS)
    table = scroll_region(f'<table class="board" data-span-tree="waterfall"><thead><tr>{heads}</tr></thead><tbody>'
                          + "".join(_row(s, d, origin, total) for s, d in shown) + "</tbody></table>",
                          HEADING, "span-tree")
    lines = checked(tree, reported_models(receipt, receipt_file, read_file))
    check = (f'<div data-span-checked><p class="k">{escape(CHECKED_HEAD)}</p><ul class="plain">'
             + "".join(f'<li data-agree="{k}">{line}</li>' for k, line in lines) + "</ul></div>") if lines else ""
    return (head + _labelled(r for r, _ in tree.rows) + f'<p data-span-tree="joined">{escape(JOINED.format(**t))}'
            + (f" {escape(WITHIN)}" if tree.started is not None and tree.ended is not None else "") + "</p>"
            + table + (f'<p data-span-more>{escape(MORE.format(n=more))}</p>' if more > 0 else "")
            + f'<p class="footnote">{escape(NAMED)}</p>' + check + _non_claims() + "</section>")


def run_section(spans, receipts: list[dict]) -> str:
    """The run page's list of the app's spans no step joins; "" where there are none."""
    if spans is None or isinstance(spans, Unreadable):
        return ""
    left = unjoined(spans, receipts)
    if not left:
        return ""
    origin = min(s.start for s in left)
    items = "".join(f'<li data-unjoined="{escape(s.span_id)}"><code>{escape(s.name)}</code>: {escape(s.what)}, '
                    f"from {escape(ms(s.start - origin))}, took {escape(ms(s.took))}</li>" for s in left[:MAX_MEMBERS])
    more = len(left) - MAX_MEMBERS
    return (f'<section data-section="spans-unjoined" class="span-tree"><h2>{escape(UNJOINED_HEAD)}</h2>'
            f'<p class="reported">{escape(UNJOINED_LEAD)}</p><ul class="plain">{items}</ul>'
            + (f'<p data-span-more>{escape(MORE.format(n=more))}</p>' if more > 0 else "") + "</section>")


def for_run(run, store):
    """The run's trace file read: its spans, an `Unreadable`, or None where it has none."""
    from onetrace_console import beside
    raw, _source = beside.trace(store, run.key)
    if raw is None:
        return None
    try:
        return read_export(raw)
    except Unreadable as e:
        return e


# ------------------------------------------------------------------ at the first difference

DIFF_HEADING = "The app's spans at the first difference, side by side"
DIFF_LEAD = ("Facts from the app's traces, not checked by onetrace, ranked: a status error first, then retries, "
             "a model, a span on one side only, tokens, then time.")
DIFF_NONE = "The two runs' spans under this step differ in none of these."
DIFF_NO_TREE = "No span view for the {role} run here: {said}."
NO_TREE_WORDS = {"none": "its trace file holds no span of the trace this step recorded",
                 "unjoined": "its trace file holds no span with the span id this step recorded",
                 "unreadable": "its trace file cannot be read", "absent": "no trace file is kept for it",
                 "no-step": "the step is not in its record"}
#: A time differs where one side took at least this many times the other.
TIMES = 2
#: Each kind of difference, by rank; and the order a line says them in.
RANK = ("status", "retries", "model", "only", "tokens", "time")
LINE_ORDER = ("retries", "status", "model", "tokens")


def _label(s: Span) -> str:
    return str(s.attrs.get("gen_ai.tool.name") or s.name)


def _keyed(tree: Tree) -> dict:
    """The tree's spans by name and the order of that name among them."""
    seen, out = {}, {}
    for s, _ in tree.rows:
        seen[s.name] = seen.get(s.name, 0) + 1
        out[(s.name, seen[s.name])] = s
    return out


def differences(trees: tuple, roles=("baseline", "candidate")) -> list[tuple[int, float, str]]:
    """(rank, size, the line) for each pair of spans that differ, most first; `trees` the two Trees."""
    a, b = (_keyed(t) for t in trees)
    order = list(dict.fromkeys([*a, *b]))
    out = []
    for i, key in enumerate(order):
        x, y = a.get(key), b.get(key)
        if x is None or y is None:
            s, role, other = (y, roles[1], roles[0]) if x is None else (x, roles[0], roles[1])
            out.append((RANK.index("only"), 0.0, i,
                        f"{role}: {_label(s)}, {ms(s.took)}, not in the {other}'s spans"))
            continue
        facts, side = [], None
        if x.status != y.status and "error" in (x.status, y.status):
            side = 1 if y.status == "error" else 0
            facts.append(("status", "status error"))
        if x.retries != y.retries:
            side = side if side is not None else (1 if y.retries > x.retries else 0)
            n = (y if side else x).retries
            facts.append(("retries", f"{n} retr{'y' if n == 1 else 'ies'}"))
        if x.model != y.model and (x.model or y.model):
            facts.append(("model", f"model {y.model or '(none)'} against {x.model or '(none)'}"))
            side = 1 if side is None else side
        tok = lambda s: (s.attrs.get("gen_ai.usage.input_tokens"), s.attrs.get("gen_ai.usage.output_tokens"))  # noqa: E731
        if tok(x) != tok(y) and (x.what == MODEL or y.what == MODEL):
            facts.append(("tokens", f"tokens {'/'.join(v or '—' for v in tok(y))} against "
                                    f"{'/'.join(v or '—' for v in tok(x))}"))
            side = 1 if side is None else side
        slow, fast = max(x.took, y.took), min(x.took, y.took)
        times = slow >= TIMES * max(fast, 1) and slow != fast
        if not facts and not times:
            continue
        if side is None:
            side = 1 if y.took >= x.took else 0
        me, them = (y, x) if side else (x, y)
        rank = min(RANK.index(k) for k, _ in facts) if facts else RANK.index("time")
        #: Said as the app's facts read: its retries, then its status, then the rest.
        words = [w for _, w in sorted(facts, key=lambda f: LINE_ORDER.index(f[0]))]
        head = f"{words[0]} on {_label(me)}" if words else _label(me)
        line = ", ".join([head, *words[1:], f"{ms(me.took)} against {ms(them.took)}"])
        out.append((rank, slow / max(fast, 1), i, f"{roles[side]}: {line}"))
    out.sort(key=lambda r: (r[0], -r[1], r[2]))
    return [(r, size, line) for r, size, _i, line in out]


def _side_rows(trees: tuple) -> str:
    a, b = (_keyed(t) for t in trees)
    cell = lambda s: (f'<td><code>{escape(s.name)}</code> · {escape(s.what)} · {escape(ms(s.took))}'  # noqa: E731
                      + (f" · {s.retries} retries" if s.retries else "")
                      + (" · status error" if s.status == "error" else "") + "</td>") if s else "<td>—</td>"
    return "".join(f"<tr>{cell(a.get(k))}{cell(b.get(k))}</tr>" for k in dict.fromkeys([*a, *b]))


def difference_section(found: tuple, roles=("baseline", "candidate")) -> str:
    """The comparison page's section: `found` holds, for each run, a Tree or the word for its absence
    (`NO_TREE_WORDS`); "" where neither run's trace file holds a span of the step's trace."""
    from onetrace_console.words import scroll_region
    if all(f in ("none", "absent", "no-step") for f in found):
        return ""
    head = (f'<section data-section="span-differences" class="span-tree"><h2>{escape(DIFF_HEADING)}</h2>'
            f'<p class="reported">{escape(DIFF_LEAD)}</p>')
    notes = "".join(f'<p data-span-no-tree="{escape(f)}">{escape(DIFF_NO_TREE.format(role=r, said=NO_TREE_WORDS[f]))}</p>'
                    for f, r in zip(found, roles) if isinstance(f, str))
    if notes:
        return head + notes + _non_claims() + "</section>"
    ranked = differences(found, roles)
    head += _labelled(s for tree in found for s, _ in tree.rows)
    items = ("<ol data-span-ranked>" + "".join(f'<li data-rank="{escape(RANK[r])}">{escape(line)}</li>'
                                              for r, _s, line in ranked[:MAX_MEMBERS]) + "</ol>"
             if ranked else f"<p data-span-ranked>{escape(DIFF_NONE)}</p>")
    more = len(ranked) - MAX_MEMBERS
    table = scroll_region(f'<table class="board" data-span-side><thead><tr><th>{escape(roles[0])}</th>'
                          f"<th>{escape(roles[1])}</th></tr></thead><tbody>{_side_rows(found)}</tbody></table>",
                          DIFF_HEADING, "span-side")
    return (head + items + (f'<p data-span-more>{escape(MORE.format(n=more))}</p>' if more > 0 else "")
            + table + _non_claims() + "</section>")


def found_at(run, store, stage: str, nth: int = 1):
    """The run's Tree at its `nth` step named `stage`, or the word for its absence."""
    from onetrace_console.stage_pages import _stage_name, _steps
    receipts = [s["receipt"] for s in _steps(run, store) if _stage_name(s["receipt"]) == stage]
    if len(receipts) < nth:
        return "no-step"
    spans = for_run(run, store)
    if spans is None:
        return "absent"
    if isinstance(spans, Unreadable):
        return "unreadable"
    tree = step_tree(spans, receipts[nth - 1])
    if tree is None:
        return "none"
    return tree if tree.root is not None else "unjoined"
