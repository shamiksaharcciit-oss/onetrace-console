"""A step's model-call records, shown as written: each output named `model_call.json` or
`model_call.<N>.json`, in the draft format `model-call-record/0.1-draft`.

The reader is strict. A record is shown only where its stored bytes match the digest the step's
receipt records for it (as every output on a step page is), it is UTF-8 JSON with no repeated key,
it names the draft's format, and it holds to the format's JSON Schema, shipped beside this module.
Anything else is refused with its reason, and no part of the file is shown. The schema is read by a
reader of the keywords it uses; a keyword this reader does not know refuses the schema, never skips.

What is shown: each field grouped (the call, the model, the tokenizer, the engine and runtime, the
batch context, the output fingerprints), its state as the record states it, its value or values,
and the reason the record gives (`source`). No comparator and no verdict: two runs' records are not
compared here, and a comparison's short answer does not read them.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from onetrace_console.bounded_json import TooDeep, load_json_bounded
from onetrace_console.words import escape

FORMAT = "model-call-record/0.1-draft"
LABEL = ("Model-call record, draft format `model-call-record/0.1-draft`: shown as written; "
         "the format may change.")
HEADING = "Model-call records"
SCHEMA = Path(__file__).with_name("model_call_record_0.1-draft.schema.json")
NAME = re.compile(r"model_call(?:\.(?:0|[1-9][0-9]*))?\.json")
#: The largest record read; a record is one call's fields, a few kilobytes.
MOST_BYTES = 1 << 20
#: The groups, in order: each field by its name, or a name ending in "." for every field under it.
GROUPS = (
    ("The call", ("format", "call.kind", "call.api", "credential", "input.")),
    ("The model", ("model.", "provider.fingerprint")),
    ("The tokenizer", ("tokenizer.",)),
    ("The engine and runtime", ("engine.", "runtime.", "dtype", "attention_backend", "sampling.")),
    ("The batch context", ("batch.",)),
    ("The output fingerprints", ("output.", "fingerprints")),
)
#: The schema's keywords this reader applies, and those that only describe.
_APPLIED = {"$ref", "type", "required", "properties", "patternProperties", "additionalProperties",
            "const", "enum", "pattern", "minLength", "items", "oneOf", "allOf", "if", "then"}
_DESCRIBE = {"$schema", "$id", "$defs", "title", "description"}


class Refused(ValueError):
    """A record not shown, with its reason."""


def _group(field: str) -> int:
    for n, (_title, names) in enumerate(GROUPS):
        if any(field == x or (x.endswith(".") and field.startswith(x)) for x in names):
            return n
    return 0


# ------------------------------------------------------------------ the schema

def load_schema(path: Path = SCHEMA) -> dict:
    schema = load_json_bounded(path.read_text(encoding="utf-8"), "the model-call record's schema")
    if not isinstance(schema, dict) or schema.get("$id") != FORMAT:
        raise Refused(f"the schema beside the console is not {FORMAT}'s")
    return schema


def _resolve(root: dict, ref: str) -> dict:
    if not ref.startswith("#/$defs/") or ref[len("#/$defs/"):] not in root.get("$defs", {}):
        raise Refused(f"the schema refers to {ref}, which this reader cannot follow")
    return root["$defs"][ref[len("#/$defs/"):]]


def problems(value, schema: dict, root: dict, at: str = "the record") -> list[str]:
    """What in `value` does not hold to `schema`; [] where all of it does."""
    unknown = sorted(k for k in schema if k not in _APPLIED | _DESCRIBE and not k.startswith("x-"))
    if unknown:
        raise Refused(f"the schema uses {', '.join(unknown)}, which this reader does not apply")
    out: list[str] = []
    if "$ref" in schema:
        out += problems(value, _resolve(root, schema["$ref"]), root, at)
    kind = schema.get("type")
    if kind is not None:
        ok = {"object": isinstance(value, dict), "string": isinstance(value, str),
              "array": isinstance(value, list)}.get(kind)
        if ok is None:
            raise Refused(f"the schema asks for type {kind}, which this reader does not apply")
        if not ok:
            return out + [f"{at} is not a JSON {kind}"]
    if "const" in schema and value != schema["const"]:
        out.append(f"{at} is {json.dumps(value)}, not {json.dumps(schema['const'])}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{at} is {json.dumps(value)}, not one of {', '.join(json.dumps(e) for e in schema['enum'])}")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{at} is {json.dumps(value)}, not of the form {schema['pattern']}")
        if len(value) < schema.get("minLength", 0):
            out.append(f"{at} is empty")
    if isinstance(value, list) and "items" in schema:
        for n, item in enumerate(value):
            out += problems(item, schema["items"], root, f"{at}[{n}]")
    if isinstance(value, dict):
        out += [f"{at} has no {k}" for k in schema.get("required", []) if k not in value]
        props, patterns = schema.get("properties", {}), schema.get("patternProperties", {})
        for k, v in value.items():
            matched = [s for p, s in patterns.items() if re.search(p, k)]
            if k in props:
                out += problems(v, props[k], root, f"{at}'s {k}" if at != "the record" else k)
            for s in matched:
                out += problems(v, s, root, k)
            if k not in props and not matched and schema.get("additionalProperties") is False:
                out.append(f"{at} has a field the format does not name: {k}")
    if "oneOf" in schema:
        held = [s for s in schema["oneOf"] if not problems(value, s, root, at)]
        if len(held) != 1:
            state = value.get("status") if isinstance(value, dict) else None
            out.append(f"{at} is not a value in one of the format's states"
                       + (f" (its status is {json.dumps(state)})" if state is not None else ""))
    for s in schema.get("allOf", []):
        out += problems(value, s, root, at)
    if "if" in schema and not problems(value, schema["if"], root, at):
        out += problems(value, schema.get("then", {}), root, at)
    return out


# ------------------------------------------------------------------ one record

def _no_repeats(pairs):
    keys = [k for k, _ in pairs]
    repeated = sorted({k for k in keys if keys.count(k) > 1})
    if repeated:
        raise Refused(f"the record names {', '.join(repeated)} more than once")
    return dict(pairs)


def _no_constant(name):
    raise Refused(f"the record holds {name}, which is not JSON")


def read(raw: bytes, schema: dict | None = None) -> dict:
    """The record, where every check holds; `Refused` with the first reason otherwise."""
    if len(raw) > MOST_BYTES:
        raise Refused(f"the record is {len(raw)} bytes, over the {MOST_BYTES} this reader reads")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused("the record is not UTF-8") from None
    try:
        record = load_json_bounded(text, "the model-call record", "show", object_pairs_hook=_no_repeats,
                                   parse_constant=_no_constant)
    except Refused:
        raise
    except TooDeep:
        raise Refused("the record nests more deeply than this reader reads") from None
    except (ValueError, RecursionError):
        raise Refused("the record is not JSON") from None
    if not isinstance(record, dict):
        raise Refused("the record is not a JSON object")
    if record.get("format") != FORMAT:
        said = record.get("format")
        raise Refused(f"the record's format is {json.dumps(said)}, not {FORMAT}" if said is not None
                      else f"the record names no format; this reader reads {FORMAT}")
    schema = load_schema() if schema is None else schema
    found = problems(record, schema, schema)
    if found:
        raise Refused(found[0] + (f" (and {len(found) - 1} more)" if len(found) > 1 else ""))
    return record


def _values(v) -> str:
    """A value as written: a fingerprint short with its fold, a list one per line."""
    from onetrace_console.trace_panel import code_or_fold
    if isinstance(v, list):
        return "".join(f"<div>{code_or_fold(str(x))}</div>" for x in v)
    return code_or_fold(str(v))


def _shown(field: str, v) -> str:
    """One field: its name, state, value(s) and the record's reason, each as written."""
    if not isinstance(v, dict) or "status" not in v:
        return (f'<tr data-field="{escape(field)}"><td><code>{escape(field)}</code></td><td></td>'
                f'<td>{_values(v)}</td><td></td></tr>')
    shown = _values(v["value"]) if "value" in v else ""
    if "declared" in v:
        shown += f'<div>declared {_values(v["declared"])}</div>'
    if "observed_value" in v:
        shown += f'<div>observed {_values(v["observed_value"])}</div>'
    return (f'<tr data-field="{escape(field)}" data-state="{escape(str(v["status"]))}"><td><code>{escape(field)}</code></td>'
            f'<td>{escape(str(v["status"]))}</td><td>{shown}</td>'
            f'<td class="reason">{escape(str(v.get("source", "")))}</td></tr>')


def _fingerprints(items: list) -> str:
    rows = "".join(
        f'<tr data-field="fingerprints[{n}]" data-state="{escape(str(f["value"]["status"]))}"><td><code>'
        f'fingerprints[{n}]</code> {escape(f["form"])} over {escape(f["quantity"])}, k {escape(f["k"])},'
        f' decimals {escape(f["decimals"])}</td><td>{escape(str(f["value"]["status"]))}</td>'
        f'<td>{_values(f["value"]["value"]) if "value" in f["value"] else ""}</td>'
        f'<td class="reason">{escape(str(f["value"].get("source", "")))}</td></tr>' for n, f in enumerate(items))
    return rows


def record_block(name: str, record: dict) -> str:
    groups: list[list[str]] = [[] for _ in GROUPS]
    for field, v in record.items():
        if field == "fingerprints":
            groups[_group(field)].append(_fingerprints(v))
        else:
            groups[_group(field)].append(_shown(field, v))
    body = "".join(
        f'<tr class="group"><th colspan="4">{escape(title)}</th></tr>' + "".join(rows)
        for (title, _names), rows in zip(GROUPS, groups) if rows)
    from onetrace_console.words import scroll_region
    table = scroll_region(f'<table class="board" data-model-call-table><thead><tr><th>field</th><th>state</th>'
                          f'<th>value</th><th>reason, as the record gives it</th></tr></thead>'
                          f'<tbody>{body}</tbody></table>', f"The model-call record {name}", "model-call")
    return (f'<div class="model-call" data-model-call="{escape(name)}"><h3><code>{escape(name)}</code></h3>'
            f'{table}</div>')


def refused_block(name: str, why: str) -> str:
    return (f'<div class="model-call" data-model-call="{escape(name)}" data-refused><h3><code>{escape(name)}</code></h3>'
            f'<p>Not shown: {escape(why)}.</p></div>')


def step_section(receipt: dict, receipt_file: str, read_file) -> str:
    """A step page's model-call records, or "" where its outputs hold none. `read_file(path)`: the
    stored bytes at a run path, or None."""
    from onetrace_console.stage_pages import _artifact_path
    outs = [o for o in receipt.get("outputs") or [] if isinstance(o, dict) and NAME.fullmatch(str(o.get("name", "")))]
    if not outs:
        return ""
    blocks = []
    for o in outs:
        name = str(o["name"])
        blob = read_file(_artifact_path(receipt_file, name))
        if blob is None:
            blocks.append(refused_block(name, "the run does not hold its bytes"))
            continue
        if str(o.get("digest", "")) != "sha256:" + hashlib.sha256(blob).hexdigest():
            blocks.append(refused_block(name, "its stored bytes do not match its receipt"))
            continue
        try:
            blocks.append(record_block(name, read(blob)))
        except Refused as e:
            blocks.append(refused_block(name, str(e)))
    return (f'<section data-section="model-call" class="model-call"><h2>{escape(HEADING)}</h2>'
            f'<p class="label" data-model-call-label>{_label()}</p>{"".join(blocks)}</section>')


def _label() -> str:
    head, code, tail = LABEL.split("`")
    return f"{escape(head)}<code>{escape(code)}</code>{escape(tail)}"
