"""Trace forwarding (console 0.9): each new run's trace, sent once to the OTLP endpoints an admin names.

A trace is a view of a record, never evidence. Collectors drop, sample, rewrite and re-time spans; whether a run's
records agree is answered by the check reading the records, and nothing read back from a destination is used. The
direction is one way, record to trace.

WHAT IS SENT
------------
One trace per run, the bytes of onetrace's own export (`onetrace.otel.export`, the onetrace this console pins, the same
as `onetrace export otel`), with one attribute added to its root span, `onetrace.console.check`: the console's own
result for the run, as the runs list words it ("records agree", "not checked", "couldn't check", or how many rows
failed). Every id comes from the record, so the same run is the same trace, however often it is sent. The export
never holds an input's or an output's value, an error's text or a path; nothing is added but the one attribute, and
no record is written.

Where the console's configuration names its own address (`forwarding.console_url`), the root span also carries
`onetrace.console_url`: the run's page under that address, so a tracing tool can link back to the console. It is a
pointer, never a claim: the record is checked by onetrace-verify, not by the tool that shows the link. Without the
setting, nothing is added for it.

WHEN
----
Once, when the console's run index first holds the run (`enqueue_new`, called as the index is written): one queue
entry per destination that is on and takes that run. A run checked again later is not sent again.

HOW
---
`POST <endpoint>/v1/traces`, OTLP over HTTP: JSON by default, with the standard library alone; protobuf where the
destination says so and the `[otlp]` extra is installed (`opentelemetry-proto`). The queue is files under the store's
root (`forwarding/queue/<destination>/<run key>.json`), so it outlives a restart. A network error, a 429 or a 5xx is
retried after a wait that doubles, up to `MAX_ATTEMPTS`; any other answer that is not a success stops the entry, with
the answer's status and reason kept. A destination's own words (a `Retry-After`, a body) are not read.

Sending runs on a thread of its own: it never waits in an ingest, and a destination that is down changes no check.

THE KEYS
--------
A header's value is never written here, never drawn, never logged and never exported. Each header names where its
value is: an environment variable (`key_env`), or this user's keychain (`key_source = "keyring"`, `forward_keys`).
The value is read as the request is made and goes in the header it names, nowhere else; an error from the destination
is cut to its status and a short reason, with every header value taken out.
"""

from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlsplit

from onetrace_console.bounded_json import load_json_bounded

FOLDER = "forwarding"
DESTINATIONS = "destinations.json"
QUEUE = "queue"
STATUS = "status"
FORMAT = "onetrace-console-forwarding/1"

ENCODINGS = ("json", "protobuf")
RUNS = ("all", "agree")
#: The attribute added to each trace's root span: the console's own result for the run.
CHECK_ATTRIBUTE = "onetrace.console.check"
#: The run's page on this console, on the root span, where `forwarding.console_url` is set (`run_page`).
CONSOLE_URL_ATTRIBUTE = "onetrace.console_url"
#: The test trace's one span.
TEST_SPAN = "onetrace console test"
SERVICE = "onetrace-console"

#: An entry is tried at most this many times; the waits between double from `FIRST_WAIT`, to at most `LONGEST_WAIT`.
MAX_ATTEMPTS = 8
FIRST_WAIT = 2.0
LONGEST_WAIT = 600.0
#: How long one request may take.
TIMEOUT = 30.0
MOST_DESTINATIONS = 16
REASON_CHARS = 120

#: Headers the console sets itself, or that would change the request's framing; never taken from a destination.
RESERVED_HEADERS = ("host", "content-length", "content-type", "transfer-encoding", "connection", "te", "upgrade")
_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,64}$")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
#: The only variables a destination's key may come from: those named for forwarding. Any other variable of the
#: console's environment (the sign-in's client secret, say) is refused when a destination is set, and not read when
#: one is sent.
FORWARD_PREFIX = "ONETRACE_FORWARD_"
NOT_FOR_FORWARDING = (
    "{name}: the console reads only a variable whose name starts with "
    + FORWARD_PREFIX
    + " (as ONETRACE_FORWARD_LANGSMITH_KEY), or the keychain"
)
#: A destination kept before that rule, its header naming another variable: read with the others, never sent to.
KEPT_REFUSED = (
    "{dest}: its header {header} names the variable {env}, which forwarding does not read, so nothing is sent to it. "
    "Remove it, and add it again with a variable whose name starts with " + FORWARD_PREFIX + ", or the keychain."
)


def named_for_forwarding(env: str) -> bool:
    """Whether a variable's name is one forwarding reads."""
    return env.startswith(FORWARD_PREFIX) and len(env) > len(FORWARD_PREFIX)


_ID = re.compile(r"^[0-9a-f]{16}$")

#: The check's words, by the runs list's records-agree state (`records.state`).
CHECK_WORDS = {"yes": "records agree", "not-checked": "not checked", "couldnt-check": "couldn't check"}


class Refused(ValueError):
    """A destination, or a change to one, that the console will not keep: the message says which field and why, and
    `field` names the form's field it is about (None where it is about no one field), for the setup page to say it
    there."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class KeyMissing(LookupError):
    """A header's value is not where its destination says: the variable is not set, or nothing is stored."""


class KeyRefused(KeyMissing):
    """A header's value holds a control character (a line break pasted with it, say): it is not sent, and the reason
    names the destination and the header, never the value."""


#: A character no header value carries: the C0 controls and DEL.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class Header:
    name: str
    key_env: str = ""
    keyring: bool = False

    def where(self) -> str:
        return f"the variable {self.key_env}" if self.key_env else "the keychain"


@dataclass(frozen=True)
class Destination:
    id: str
    name: str
    endpoint: str
    encoding: str = "json"
    headers: tuple[Header, ...] = field(default_factory=tuple)
    runs: str = "all"
    enabled: bool = True

    def as_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "endpoint": self.endpoint,
            "encoding": self.encoding,
            "headers": [
                {"name": h.name, **({"key_env": h.key_env} if h.key_env else {"key_source": "keyring"})}
                for h in self.headers
            ],
            "runs": self.runs,
            "enabled": self.enabled,
        }

    def refused(self) -> str | None:
        """Why nothing is sent to this destination, where it was kept before forwarding read only its own variables
        and a header names another; None otherwise. Names the variable, never a value."""
        for h in self.headers:
            if h.key_env and not named_for_forwarding(h.key_env):
                return KEPT_REFUSED.format(dest=self.name, header=h.name, env=h.key_env)
        return None

    def takes(self, check: str) -> bool:
        """Whether this destination takes a run whose check reads `check`."""
        return self.runs == "all" or check == CHECK_WORDS["yes"]


def loopback(host: str) -> bool:
    """`localhost`, or an address of this machine's loopback."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def endpoint_problem(endpoint) -> str | None:
    """Why `endpoint` cannot be a destination's, or None: https, or http only for a loopback address; a host; no
    user or password, query or fragment."""
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > 2000 or any(ord(c) < 0x21 for c in endpoint):
        return "the endpoint is an address such as https://collector.example.com:4318"
    try:
        u = urlsplit(endpoint)
        host = u.hostname or ""
        _port = u.port
    except ValueError:
        return "the endpoint is not an address"
    if u.scheme not in ("https", "http") or not host:
        return "the endpoint starts https://, or http:// for an address on this machine, and names a host"
    if u.scheme == "http" and not loopback(host):
        return "http is only for an address on this machine (127.0.0.1, ::1 or localhost); use https"
    if u.username is not None or u.password is not None:
        return "the endpoint holds no user or password: give a key as a header"
    if u.query or u.fragment:
        return "the endpoint has no query or fragment"
    return None


def console_url_problem(url) -> str | None:
    """Why `url` cannot be `forwarding.console_url`, or None: the endpoint's rule (https, or http only for an address
    on this machine; a host; no user or password, query or fragment), where a path is allowed: the console may be
    reached under one."""
    why = endpoint_problem(url)
    #: The endpoint's words, about the console's address; a key's hint (": give a key as a header") is not for it.
    return why.split(": give")[0].replace("the endpoint", "the console's address") if why else None


def run_page(console_url: str, run_key: str) -> str:
    """The run's page under the console's address: `<console_url>/runs/<run key>/case.html`, the address's path kept
    (its unsafe characters escaped) and the key escaped as one path segment."""
    u = urlsplit(console_url)
    path = quote(u.path.rstrip("/"), safe="/%")
    return f"{u.scheme}://{u.netloc}{path}/runs/{quote(run_key, safe='')}/case.html"


def _header(raw, kept: bool = False) -> Header:
    if not isinstance(raw, dict):
        raise Refused("a header is a name and where its value is")
    name = raw.get("name")
    if not isinstance(name, str) or not _TOKEN.match(name):
        raise Refused("a header's name is letters, digits and - (as x-api-key)", "header")
    if name.lower() in RESERVED_HEADERS:
        raise Refused(f"the console sets {name} itself", "header")
    env, source = raw.get("key_env"), raw.get("key_source")
    if env is not None and source is not None:
        raise Refused(f"{name}: its value is in a variable or in the keychain, not both", "where")
    if env is not None:
        if not isinstance(env, str) or not _ENV.match(env):
            raise Refused(
                f"{name}: a variable's name is letters, digits and _ (as ONETRACE_FORWARD_LANGSMITH_KEY)", "key_env"
            )
        if not named_for_forwarding(env) and not kept:
            raise Refused(NOT_FOR_FORWARDING.format(name=name), "key_env")
        return Header(name, key_env=env)
    if source == "keyring":
        return Header(name, keyring=True)
    raise Refused(f"{name}: say where its value is: a variable, or the keychain", "where")


def destination(raw, kept: bool = False) -> Destination:
    """A destination from its stored or submitted form, every field checked; Refused naming what is wrong. A `kept`
    one (read from the file) may name a variable forwarding does not read: it is read, and `refused()` says so."""
    if not isinstance(raw, dict):
        raise Refused("a destination is a table of its fields")
    did = raw.get("id")
    if not isinstance(did, str) or not _ID.match(did):
        raise Refused("a destination's id is 16 hex characters")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 0x20 for c in name):
        raise Refused("give the destination a name, of at most 80 characters", "name")
    problem = endpoint_problem(raw.get("endpoint"))
    if problem:
        raise Refused(problem, "endpoint")
    encoding = raw.get("encoding", "json")
    if encoding not in ENCODINGS:
        raise Refused("the encoding is json or protobuf", "encoding")
    headers = raw.get("headers", [])
    if not isinstance(headers, list) or len(headers) > 8:
        raise Refused("a destination has at most 8 headers", "header")
    parsed = tuple(_header(h, kept) for h in headers)
    if len({h.name.lower() for h in parsed}) != len(parsed):
        raise Refused("each header is named once", "header")
    runs = raw.get("runs", "all")
    if runs not in RUNS:
        raise Refused("which runs: all, or only runs whose records agree", "runs")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise Refused("on or off")
    return Destination(did, name.strip(), str(raw["endpoint"]).rstrip("/"), encoding, parsed, runs, enabled)


def new_id() -> str:
    return secrets.token_hex(8)


def folder(store_root) -> Path:
    return Path(store_root) / FOLDER


def read(store_root) -> list[Destination]:
    """Every destination kept, in the order kept; [] where none is. A file that cannot be read is said by raising."""
    path = folder(store_root) / DESTINATIONS
    if not path.is_file():
        return []
    doc = load_json_bounded(path.read_text(encoding="utf-8"), "the forwarding destinations")
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or not isinstance(doc.get("destinations"), list):
        raise Refused(f"{path} is not a list of destinations this console wrote")
    return [destination(d, kept=True) for d in doc["destinations"]]


def _write(store_root, dests: list[Destination]) -> None:
    from onetrace_console.store import _atomic_write

    if len(dests) > MOST_DESTINATIONS:
        raise Refused(f"at most {MOST_DESTINATIONS} destinations")
    folder(store_root).mkdir(parents=True, exist_ok=True)
    body = {"format": FORMAT, "destinations": [d.as_json() for d in dests]}
    _atomic_write(folder(store_root) / DESTINATIONS, (json.dumps(body, indent=2) + "\n").encode("utf-8"))


#: The fields a change may name. Header values are not among them: they are never written here.
FIELDS = ("name", "endpoint", "encoding", "headers", "runs", "enabled")


def save(store_root, did: str | None, fields: dict) -> tuple[Destination, list[str]]:
    """Change only the named fields of one destination (a new one where `did` is None), every other field and every
    other destination as kept. Returns it and the names of the fields that changed. Refused, and nothing written,
    where the result would not be kept."""
    unknown = sorted(set(fields) - set(FIELDS))
    if unknown:
        raise Refused(f"not a field of a destination: {', '.join(unknown)}")
    dests = read(store_root)
    if did is None:
        before: dict = {"id": new_id(), "name": "", "endpoint": "", "encoding": "json", "headers": []}
        before.update(runs="all", enabled=True)
        at = len(dests)
    else:
        at = next((i for i, d in enumerate(dests) if d.id == did), -1)
        if at < 0:
            raise Refused("no such destination")
        before = dests[at].as_json()
    after = destination({**before, **fields})
    changed = [k for k in FIELDS if after.as_json()[k] != before.get(k)] if did is not None else list(FIELDS)
    dests = dests[:at] + [after] + dests[at + 1 :]
    _write(store_root, dests)
    return after, changed


def remove(store_root, did: str) -> Destination:
    """Remove a destination, with its queue and its status; its keychain entries are the caller's (`forward_keys`)."""
    import shutil

    dests = read(store_root)
    gone = next((d for d in dests if d.id == did), None)
    if gone is None:
        raise Refused("no such destination")
    _write(store_root, [d for d in dests if d.id != did])
    shutil.rmtree(folder(store_root) / QUEUE / did, ignore_errors=True)
    (folder(store_root) / STATUS / f"{did}.json").unlink(missing_ok=True)
    return gone


# ------------------------------------------------------------------------------------------------------ the keys


def value_of(dest: Destination, header: Header) -> str:
    """A header's value, from where its destination says; KeyMissing where it is not there, KeyRefused where it holds
    a control character."""
    if header.key_env:
        if not named_for_forwarding(header.key_env):
            raise KeyRefused(
                f"{dest.name}: {header.name} names the variable {header.key_env}, which forwarding does not read: "
                f"its name starts with {FORWARD_PREFIX}"
            )
        got = os.environ.get(header.key_env)
        if not got:
            raise KeyMissing(f"{header.name}: the variable {header.key_env} is not set")
    else:
        from onetrace_console import forward_keys

        got = forward_keys.read(dest.id, header.name)
        if not got:
            raise KeyMissing(f"{header.name}: no value is stored in the keychain")
    if _CONTROL.search(got):
        raise KeyRefused(
            f"{dest.name}: the value of {header.name} holds a control character (a line break, say), so it is not sent"
        )
    return got


def key_state(dest: Destination, header: Header) -> str:
    """ "set" / "not set" for a variable, "stored" / "not stored" for the keychain, or the keychain's error by its
    type. Never the value."""
    if header.key_env:
        if not named_for_forwarding(header.key_env):
            return "not read"
        return "set" if os.environ.get(header.key_env) else "not set"
    from onetrace_console import forward_keys

    try:
        return "stored" if forward_keys.stored(dest.id, header.name) else "not stored"
    except forward_keys.Unavailable as e:
        return f"the keychain can't be read ({e.kind or type(e).__name__})"


# ----------------------------------------------------------------------------------------------------- the trace


def check_words(entry: dict) -> str:
    """The console's own result for a run, from its run index entry, as the runs list words it."""
    state = (entry.get("list") or {}).get("records-agree") if isinstance(entry.get("list"), dict) else None
    if state is None:
        state = entry.get("records-agree", "not-checked")
    if state in CHECK_WORDS:
        return CHECK_WORDS[state]
    failed = len((entry.get("rows") or {}).get("FAIL", [])) if isinstance(entry.get("rows"), dict) else 0
    return f"{failed} rows failed" if failed != 1 else "1 row failed"


def with_check(exported: bytes, check: str, link: str = "") -> bytes:
    """onetrace's export with `onetrace.console.check` added to its root span, and `onetrace.console_url` = `link`
    where one is given, written as the export writes."""
    doc = load_json_bounded(exported.decode("utf-8"), "onetrace's export")
    roots = [
        s for rs in doc["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"] if not s.get("parentSpanId")
    ]
    if len(roots) != 1:
        raise ValueError("onetrace's export has no single root span")
    roots[0].setdefault("attributes", []).append({"key": CHECK_ATTRIBUTE, "value": {"stringValue": check}})
    if link:
        roots[0]["attributes"].append({"key": CONSOLE_URL_ATTRIBUTE, "value": {"stringValue": link}})
    return (json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def trace_of(run, store, check: str, console_url: str = "") -> bytes:
    """The run's trace, in OTLP/JSON: onetrace's export of the run, written back to a folder byte for byte, with the
    one attribute, and the run's page where the console's address is given."""
    from onetrace import otel

    from onetrace_console.checks import materialise

    with tempfile.TemporaryDirectory(prefix="onetrace-forward-") as tmp:
        where = Path(tmp) / (run.folder or "run")
        with store.reading():
            materialise(run, store, where)
        exported = otel.export(where, service_name="onetrace")
    return with_check(exported, check, run_page(console_url, run.key) if console_url else "")


def test_trace() -> bytes:
    """One span named `onetrace console test`, with no run data, in OTLP/JSON."""
    now = time.time_ns()
    span = {
        "traceId": secrets.token_hex(16),
        "spanId": secrets.token_hex(8),
        "parentSpanId": "",
        "name": TEST_SPAN,
        "kind": 1,
        "startTimeUnixNano": str(now),
        "endTimeUnixNano": str(now + 1_000_000),
        "attributes": [],
    }
    doc = {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": SERVICE}}]},
                "scopeSpans": [{"scope": {"name": SERVICE}, "spans": [span]}],
            }
        ]
    }
    return (json.dumps(doc, separators=(",", ":")) + "\n").encode("utf-8")


#: The `[otlp]` extra's line, as the setup page shows it where protobuf is chosen and the extra is missing.
OTLP_EXTRA = "opentelemetry-proto"
INSTALL = 'pip install "onetrace-console[otlp]"'


def protobuf_installed() -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec("opentelemetry.proto.collector.trace.v1.trace_service_pb2") is not None
    except (ImportError, ValueError):
        return False


_ID_KEYS = ("traceId", "spanId", "parentSpanId")


def _ids_to_base64(node):
    """OTLP/JSON writes ids in hex; protobuf's own JSON reading takes bytes in base64. The same ids, re-spelt."""
    if isinstance(node, dict):
        return {
            k: (
                base64.b64encode(bytes.fromhex(v)).decode()
                if k in _ID_KEYS and isinstance(v, str)
                else _ids_to_base64(v)
            )
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_ids_to_base64(v) for v in node]
    return node


def to_protobuf(trace_json: bytes) -> bytes:
    """The same request in OTLP's protobuf: `ExportTraceServiceRequest`, from the `[otlp]` extra."""
    from google.protobuf import json_format  # type: ignore[import-not-found,import-untyped,unused-ignore]  # the optional extra
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (  # type: ignore[import-not-found]  # as above
        ExportTraceServiceRequest,
    )

    doc = _ids_to_base64(load_json_bounded(trace_json.decode("utf-8"), "a trace"))
    msg = json_format.ParseDict(doc, ExportTraceServiceRequest())
    return msg.SerializeToString(deterministic=True)


# -------------------------------------------------------------------------------------------------- sending


@dataclass(frozen=True)
class Answer:
    status: int  # 0 where no answer came (a network error)
    reason: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def again(self) -> bool:
        """Worth trying again: no answer, a 429 or a 5xx."""
        return self.status == 0 or self.status == 429 or self.status >= 500


def cut(text: str, secrets_: list[str]) -> str:
    """`text` with every header value taken out, made one line and cut short."""
    for value in sorted({s for s in secrets_ if s}, key=len, reverse=True):
        text = text.replace(value, "[a header's value]")
    text = " ".join(text.split())
    return text if len(text) <= REASON_CHARS else text[: REASON_CHARS - 1] + "…"


def send(dest: Destination, trace_json: bytes, timeout: float = TIMEOUT) -> Answer:
    """One `POST <endpoint>/v1/traces`. Never raises for the destination's sake: a network error is Answer(0, ...).
    KeyMissing where a header's value is not where it should be (nothing is sent then)."""
    values = {h.name: value_of(dest, h) for h in dest.headers}
    if dest.encoding == "protobuf":
        if not protobuf_installed():
            return Answer(-1, f"protobuf needs the [otlp] extra: {INSTALL}")
        body, ctype = to_protobuf(trace_json), "application/x-protobuf"
    else:
        body, ctype = trace_json, "application/json"
    u = urlsplit(dest.endpoint)
    path = (u.path.rstrip("/") or "") + "/v1/traces"
    conn_type = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = conn_type(u.hostname or "", u.port, timeout=timeout)
    try:
        conn.request("POST", path, body=body, headers={"Content-Type": ctype, **values})
        r = conn.getresponse()
        r.read(4096)  # read and dropped: nothing a destination says is used
        return Answer(r.status, cut(f"{r.status} {r.reason}", list(values.values())))
    except (OSError, http.client.HTTPException) as e:
        return Answer(0, cut(f"no answer ({type(e).__name__})", list(values.values())))
    except ValueError as e:
        #: A request `http.client` will not make (a header it refuses): failed, said by its kind alone, since its
        #: words can carry a header's value.
        return Answer(-1, f"the request could not be made ({type(e).__name__})")
    finally:
        conn.close()


# ---------------------------------------------------------------------------------------------------- the queue


def _queue(store_root, did: str) -> Path:
    return folder(store_root) / QUEUE / did


def _write_json(path: Path, doc: dict) -> None:
    from onetrace_console.store import _atomic_write

    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, (json.dumps(doc, sort_keys=True) + "\n").encode("utf-8"))


def _read_json(path: Path) -> dict | None:
    try:
        doc = load_json_bounded(path.read_text(encoding="utf-8"), "a forwarding file")
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def enqueue(store_root, run_key: str, check: str, dests: list[Destination] | None = None) -> int:
    """One entry per destination that is on and takes the run, where none is queued already. Returns how many."""
    made = 0
    for d in dests if dests is not None else read(store_root):
        if not d.enabled or not d.takes(check) or d.refused():
            continue
        path = _queue(store_root, d.id) / f"{run_key}.json"
        if path.exists():
            continue
        _write_json(path, {"run": run_key, "check": check, "attempts": 0, "next_at": 0.0, "state": "queued"})
        made += 1
    return made


def wanted(store_root) -> bool:
    """Whether a destination is kept for this store root (the file is there): the index reads its last copy only then."""
    return (folder(store_root) / DESTINATIONS).is_file()


def enqueue_new(store_root, index: dict, held_before: set[str] | None) -> int:
    """Called as the run index is written: every run it holds that the index before it did not, once. Where there
    was no index before (`held_before` None), every run is new to it. Never raises: forwarding never stops an index
    being written; a failure is said on the error stream."""
    try:
        if not wanted(store_root):
            return 0
        dests = read(store_root)
        made = 0
        for entry in index.get("runs", []):
            if held_before is not None and entry.get("key") in held_before:
                continue
            made += enqueue(store_root, entry["key"], check_words(entry), dests)
        return made
    except Exception as e:  # noqa: BLE001 - forwarding never stops the index; said, by its type
        print(f"onetrace-console: forwarding: runs not queued ({type(e).__name__})", file=sys.stderr, flush=True)
        return 0


def queued(store_root, did: str) -> list[dict]:
    q = _queue(store_root, did)
    if not q.is_dir():
        return []
    return [doc for p in sorted(q.glob("*.json")) if (doc := _read_json(p)) is not None]


def status(store_root, did: str) -> dict:
    return _read_json(folder(store_root) / STATUS / f"{did}.json") or {}


def _note(store_root, did: str, **fields) -> None:
    path = folder(store_root) / STATUS / f"{did}.json"
    _write_json(path, {**status(store_root, did), **fields})


def wait_after(attempts: int) -> float:
    """The wait before the next try, after `attempts` tries: doubling from FIRST_WAIT, at most LONGEST_WAIT."""
    return min(LONGEST_WAIT, FIRST_WAIT * 2 ** max(0, attempts - 1))


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def attempt(
    store_root, store, dest: Destination, entry_path: Path, now: float | None = None, console_url: str = ""
) -> str:
    """Try one queue entry once: "sent", "again" or "stopped" (or "" where it is not due, or gone)."""
    now = time.time() if now is None else now
    entry = _read_json(entry_path)
    if entry is None or entry.get("state") != "queued" or float(entry.get("next_at", 0)) > now:
        return ""
    run = next((r for r in store.runs() if r.key == entry["run"]), None)
    attempts = int(entry.get("attempts", 0)) + 1
    if run is None:
        answer = Answer(-1, "the run is no longer in the store")
    else:
        try:
            answer = send(dest, trace_of(run, store, str(entry.get("check", "")), console_url))
        except KeyMissing as e:
            answer = Answer(-2, str(e))
        except Exception as e:  # noqa: BLE001 - a trace that cannot be made stops the entry, by its type
            answer = Answer(-1, f"the trace could not be made ({type(e).__name__})")
    if answer.ok:
        entry_path.unlink(missing_ok=True)
        _note(store_root, dest.id, last_send=_stamp(), last_status=answer.status)
        return "sent"
    if answer.status == -2 or (answer.again and attempts < MAX_ATTEMPTS):
        #: A key not where it should be waits like a network error: the operator can set it.
        entry.update(attempts=attempts, next_at=now + wait_after(attempts), last=answer.reason)
        _write_json(entry_path, entry)
        _note(store_root, dest.id, last_failure=answer.reason, last_failure_at=_stamp())
        return "again"
    why = answer.reason if not answer.again else f"gave up after {attempts} tries: {answer.reason}"
    entry.update(attempts=attempts, state="stopped", last=why)
    _write_json(entry_path, entry)
    _note(store_root, dest.id, last_failure=why, last_failure_at=_stamp())
    return "stopped"


def run_once(store_root, store, now: float | None = None, console_url: str = "") -> list[str]:
    """One pass over every destination's due entries. Each destination's entries go in order."""
    out: list[str] = []
    try:
        dests = read(store_root)
    except (OSError, ValueError):
        return out
    for d in dests:
        if not d.enabled or d.refused():
            continue
        q = _queue(store_root, d.id)
        for p in sorted(q.glob("*.json")) if q.is_dir() else []:
            got = attempt(store_root, store, d, p, now, console_url)
            if got:
                out.append(got)
    return out


class Forwarder(threading.Thread):
    """The sender, on a thread of its own: a pass over the queue every `every` seconds, until stopped; each trace links
    to its run's page under `console_url` where it is given."""

    def __init__(self, store_root, store, every: float = 1.0, console_url: str = "") -> None:
        super().__init__(name="onetrace-forwarding", daemon=True)
        self.store_root, self.store, self.every, self.console_url = store_root, store, every, console_url
        self.stopping = threading.Event()

    def run(self) -> None:
        while not self.stopping.wait(self.every):
            try:
                run_once(self.store_root, self.store, console_url=self.console_url)
            except Exception as e:  # noqa: BLE001 - the sender never stops the console; said by its type
                print(f"onetrace-console: forwarding: a pass failed ({type(e).__name__})", file=sys.stderr, flush=True)

    def stop(self) -> None:
        self.stopping.set()
