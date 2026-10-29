"""A step's model-call records, shown as written: each output named as `model-call-record/1.0` names
them (`model_call.json`, then `model_call.2.json`, `model_call.3.json`, ...), read by the installed
onetrace's own `onetrace.model_call`.

The reader is strict. A record is shown only where its stored bytes match the digest the step's
receipt records for it (as every output on a step page is), it is UTF-8 JSON with no repeated key,
it names `model-call-record/1.0`, and the installed onetrace's `validate` holds it to that format.
Anything else is refused with its reason, and no part of the file is shown: a record in the earlier
draft format, or an output named like a record that 1.0 does not name one (`model_call.1.json`), is
named and its reason said. The format's rules are the installed package's: the console checks a
record with nothing else.

The one copy: `_received/model_call_record.schema.json`, the format's schema copied byte for byte from
the onetrace 0.6.0 source package (the installed wheel does not carry it). It is read for the record's
field groups (`x-groups`) and each field's description, and for nothing else: nothing is checked
against it and nothing imported from it. A test holds its digest and where it came from.

What is shown: each field under its group as the schema copy groups them (`x-groups`), in the
group's order, with the format's description of it one fold away; its state as the record states it,
its value or values, and the reason the record gives (`source`). A field the record names that no
group lists (an `engine.settings.` or `sampling.` field) follows, under its own heading. Then whether
the call's per-step capture was taken (the record's `steps`); where it was, the steps file is read --
its bytes must match both its receipt and the digest the record names -- and drawn as the token
timeline: one decode-step row per step, each chosen token as an id, never decoded to text. What else
the steps file holds is named and not shown. No comparator and no verdict here: two runs' records are
compared on a comparison's page (`model_call_compare`).

Where the record names its model files (`model.files_digest`, observed or declared), the other runs
whose records name the same value are listed, each linked to its step.
"""
from __future__ import annotations

import hashlib
import json
import re

from onetrace_console.bounded_json import TooDeep, load_json_bounded
from onetrace_console.words import escape

FORMAT = "model-call-record/1.0"
LABEL = "Model-call record, format `model-call-record/1.0`: shown as written."
HEADING = "Model-call records"
#: An output named like a model-call record, in any format this console has met: what the reader looks
#: at. Which of these 1.0 names a record is the installed onetrace's (`naming.is_record_name`).
NAME = re.compile(r"model_call(?:\.(?:0|[1-9][0-9]*))?\.json")
#: The largest record read; a record is one call's fields, a few kilobytes.
MOST_BYTES = 1 << 20
NOT_A_RECORD_NAME = ("its name is not a record's name in model-call-record/1.0, which names a step's "
                     "records model_call.json, then model_call.2.json, model_call.3.json and on")
STEPS_TAKEN = "per-step capture: {name}"
STEPS_NOT_TAKEN = "per-step capture: not taken"
#: The token timeline's words.
TIMELINE_HEADING = "Token timeline"
TIMELINE_LABEL = ("Each decode step's chosen token, as the steps file holds it: token ids, not text. The "
                  "file is the model's output (classed model-generated); this console never decodes it.")
TIMELINE_NOT_SHOWN = "Token timeline not shown: {why}."
STEPS_HELD_NOT_SHOWN = "Also in the steps file, not shown by this console: {keys}."
STEPS_LEVEL = "capture level, as the steps file names it: {level}"
#: The largest steps file read: one id per decode step.
STEPS_MOST_BYTES = 16 << 20
#: A field no x-group lists, under its own heading.
UNGROUPED = "Named by the record, in no group of the schema"
ABOUT = "what the format says"
#: The runs whose records name the same model files.
#: The field and its value come last: the value's whole form is a fold, which ends its line.
SAME_FILES = "Other runs whose model-call records name the same model files, {field} {value}"
SAME_FILES_NONE = "No other run's model-call record names the same model files, {field} {value}"
FILES_FIELD = "model.files_digest"
#: On a run whose model-call records are in a draft format: one line, near the top of its page.
DRAFT_LINE = ("Recorded by an earlier release, before model-call-record/1.0: this run's model-call records "
              "are in the draft format {formats}, and the run is kept as it was recorded, unchanged.")
#: A step's output that is a model-call record links to its panel on the same page.
RECORD_LINK = "the model-call record, as read above"
#: The schema copy (see above): its file in this package, its sha256, and where it came from.
SCHEMA_FILE = "_received/model_call_record.schema.json"
SCHEMA_SHA256 = "877f40cb6fde322adf321b8b0e4860ccc5ec63db24983bb531f31d5bd2d76ab6"
SCHEMA_SOURCE = ("docs/model_call_record.schema.json in onetrace-0.6.0.tar.gz (sha256 "
                 "abad114580f0d82dc35f44011d9644ca6bc2eb42ef309d0ce5994af6dcb17964), copied byte for byte")
#: The panel's one line on where its groups and descriptions come from.
SCHEMA_NOTE = ("Field groups and descriptions: model_call_record.schema.json from the onetrace 0.6.0 "
               "source package, copied unchanged; the record itself is checked by the installed onetrace.")


class Refused(ValueError):
    """A record not shown, with its reason."""


def _sdk():
    """The installed onetrace's model-call package: the format's rules, never a copy of them."""
    from onetrace import model_call
    return model_call


def is_record_name(name: str) -> bool:
    from onetrace.model_call import naming
    return naming.is_record_name(name)


def _no_repeats(pairs):
    keys = [k for k, _ in pairs]
    repeated = sorted({k for k in keys if keys.count(k) > 1})
    if repeated:
        raise Refused(f"the record names {', '.join(repeated)} more than once")
    return dict(pairs)


def _no_constant(name):
    raise Refused(f"the record holds {name}, which is not JSON")


def read(raw: bytes) -> dict:
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
        raise Refused(f"the record's format is {json.dumps(said)}, not {FORMAT}; this console reads {FORMAT} only"
                      if said is not None else f"the record names no format; this console reads {FORMAT}")
    sdk = _sdk()
    try:
        sdk.validate(record)
    except sdk.RecordError as e:
        raise Refused(f"onetrace's model-call reader refuses it: {e}") from None
    return record


_LABELS: dict | None = None


def schema_labels() -> dict:
    """From the schema copy, labels only: `groups` (title -> its fields, in the schema's order) and
    `descriptions` (field -> its description). Read once, bounded; the copy checks nothing."""
    global _LABELS
    if _LABELS is None:
        from importlib.resources import files
        raw = files("onetrace_console").joinpath(SCHEMA_FILE).read_bytes()
        schema = load_json_bounded(raw.decode("utf-8"), "the model-call schema copy", "read")
        _LABELS = {"groups": {str(t): [str(f) for f in fs] for t, fs in schema["x-groups"].items()},
                   "descriptions": {str(k): str(v["description"]) for k, v in schema["properties"].items()
                                    if isinstance(v, dict) and "description" in v}}
    return _LABELS


def _values(v) -> str:
    """A value as written: a fingerprint short with its fold, a list one per line."""
    from onetrace_console.trace_panel import code_or_fold
    if isinstance(v, list):
        return "".join(f"<div>{code_or_fold(str(x))}</div>" for x in v)
    return code_or_fold(str(v))


def _name_cell(field: str) -> str:
    """A field's name, and the format's description of it one fold away (from the schema copy)."""
    about = schema_labels()["descriptions"].get(field)
    fold = (f'<details class="about" data-about="{escape(field)}"><summary>{escape(ABOUT)}</summary>'
            f"<p>{escape(about)}</p></details>") if about else ""
    return f"<td><code>{escape(field)}</code>{fold}</td>"


def _shown(field: str, v) -> str:
    """One field: its name, state, value(s) and the record's reason, each as written."""
    if not isinstance(v, dict) or "status" not in v:
        return (f'<tr data-field="{escape(field)}">{_name_cell(field)}<td></td>'
                f'<td>{_values(v)}</td><td></td></tr>')
    shown = _values(v["value"]) if "value" in v else ""
    if "declared" in v:
        shown += f'<div>declared {_values(v["declared"])}</div>'
    if "observed_value" in v:
        shown += f'<div>observed {_values(v["observed_value"])}</div>'
    return (f'<tr data-field="{escape(field)}" data-state="{escape(str(v["status"]))}">{_name_cell(field)}'
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


def _group_row(title: str) -> str:
    return (f'<tr class="group" data-group="{escape(title)}"><th colspan="4" scope="colgroup">'
            f"{escape(title)}</th></tr>")


def grouped(record: dict) -> list[tuple[str, list[str]]]:
    """[(group title, the record's fields in it, in the group's order)], as the schema copy groups
    them; then the record's fields no group lists, in the record's order, under `UNGROUPED`. A group
    the record holds none of is left out."""
    groups = schema_labels()["groups"]
    listed = {f for fs in groups.values() for f in fs}
    out = [(title, [f for f in fs if f in record]) for title, fs in groups.items()]
    out.append((UNGROUPED, [f for f in record if f not in listed]))
    return [(t, fs) for t, fs in out if fs]


def anchor(name: str) -> str:
    """A record's id on its step's page: `model-call-` and its name, dots as dashes."""
    return "model-call-" + name.replace(".", "-")


def decode_anchor(name: str, step: int) -> str:
    """A decode-step row's id on its step's page."""
    return f"decode-{anchor(name)[len('model-call-'):]}-{step}"


_ID = re.compile(r"0|[1-9][0-9]*")


def read_steps(receipt: dict, receipt_file: str, name: str, record: dict, read_file) -> dict:
    """The steps file a record names: {"file", "token_ids", "level", "other"}; `Refused` with the
    reason where it is not read. Its bytes must match its receipt's digest and the record's `steps`."""
    from onetrace.model_call import naming
    from onetrace_console.stage_pages import _artifact_path
    said = record.get("steps")
    if not isinstance(said, dict) or said.get("status") != "observed":
        raise Refused(f"the record's steps field is {said.get('status') if isinstance(said, dict) else 'absent'}")
    file = naming.steps_name(name)
    out = next((o for o in receipt.get("outputs") or [] if isinstance(o, dict) and o.get("name") == file), None)
    if out is None:
        raise Refused(f"the step's receipt lists no output {file}")
    blob = read_file(_artifact_path(receipt_file, file))
    if blob is None:
        raise Refused("the run does not hold its bytes")
    digest = "sha256:" + hashlib.sha256(blob).hexdigest()
    if str(out.get("digest", "")) != digest:
        raise Refused("its stored bytes do not match its receipt")
    if str(said.get("value", "")) != digest:
        raise Refused("its bytes do not match the digest the record names")
    if len(blob) > STEPS_MOST_BYTES:
        raise Refused(f"the steps file is {len(blob)} bytes, over the {STEPS_MOST_BYTES} this reader reads")
    try:
        doc = load_json_bounded(blob.decode("utf-8"), "the steps file", "show", object_pairs_hook=_no_repeats,
                                parse_constant=_no_constant)
    except Refused:
        raise
    except (UnicodeDecodeError, TooDeep, ValueError, RecursionError):
        raise Refused("the steps file is not JSON this reader reads") from None
    ids = doc.get("token_ids") if isinstance(doc, dict) else None
    if not isinstance(ids, list) or not all(isinstance(i, str) and _ID.fullmatch(i) for i in ids):
        raise Refused("the steps file holds no token_ids list of decimal strings")
    level = doc.get("level")
    return {"file": file, "token_ids": ids, "level": level if isinstance(level, str) else "",
            "other": sorted(k for k in doc if k not in ("token_ids", "level"))}


def timeline(name: str, steps: dict) -> str:
    """The token timeline: one decode-step row per step, its chosen token as an id."""
    from onetrace_console.words import scroll_region
    rows = "".join(f'<tr id="{decode_anchor(name, i)}" data-decode-step="{i}"><td>{i}</td><td><code>{escape(t)}</code>'
                   f"</td></tr>" for i, t in enumerate(steps["token_ids"]))
    table = scroll_region(f'<table class="board" data-token-timeline><thead><tr><th>decode step</th>'
                          f"<th>chosen token id</th></tr></thead><tbody>{rows}</tbody></table>",
                          f"The token timeline of {name}", "token-timeline")
    level = f'<p data-steps-level>{escape(STEPS_LEVEL.format(level=steps["level"]))}</p>' if steps["level"] else ""
    held = (f'<p data-steps-held>{escape(STEPS_HELD_NOT_SHOWN.format(keys=", ".join(steps["other"])))}</p>'
            if steps["other"] else "")
    return (f'<div class="token-timeline" data-token-timeline-of="{escape(name)}"><h4>{escape(TIMELINE_HEADING)}</h4>'
            f'<p class="label">{escape(TIMELINE_LABEL)}</p>{level}{table}{held}</div>')


def files_value(record: dict) -> tuple[str, str] | None:
    """(the value, its state) of the record's `model.files_digest`, where observed or declared."""
    v = record.get(FILES_FIELD)
    if isinstance(v, dict) and v.get("status") in ("observed", "declared") and isinstance(v.get("value"), str):
        return v["value"], v["status"]
    return None


def same_files_line(record: dict, others: list[tuple[str, str, str, str, str]]) -> str:
    """The runs whose records name the same model files: `others` is [(run label, href, step, record
    name, the value's state)] as `same_files` finds them. "" where the record names none."""
    got = files_value(record)
    if got is None:
        return ""
    from onetrace_console.viewer.page import fingerprint_html
    value = fingerprint_html(got[0]) if got[0].startswith("sha256:") else f"<code>{escape(got[0])}</code>"
    field = f"<code>{FILES_FIELD}</code>"
    if not others:
        head, tail = SAME_FILES_NONE.split("{field} {value}")
        #: A div, not a p: the value's whole form is a fold, which a paragraph cannot hold.
        return f'<div data-same-files="none">{escape(head)}{field} {value}{escape(tail)}</div>'
    head, tail = SAME_FILES.split("{field} {value}")
    items = "".join(f'<li data-same-files-run="{escape(label)}"><a href="{escape(href)}">{escape(label)}</a>'
                    f" · step <code>{escape(step)}</code> · <code>{escape(rec)}</code> ({escape(state)})</li>"
                    for label, href, step, rec, state in others)
    return f'<div data-same-files><div>{escape(head)}{field} {value}{escape(tail)}</div><ul class="plain">{items}</ul></div>'


def draft_formats(run, store) -> list[str]:
    """The draft formats the run's stored model-call records name (their bytes matching their receipts),
    in the order met; [] where none is a draft."""
    from onetrace_console.stage_pages import _artifact_path, _files, _read, _steps
    found = []
    try:
        files, steps = _files(run, store), _steps(run, store)
    except Exception:  # noqa: BLE001 - a run that can't be read says nothing here
        return []
    for s in steps:
        for o in outputs(s["receipt"]):
            blob = _read(files, store, _artifact_path(s["file"], str(o["name"])))
            if blob is None or str(o.get("digest", "")) != "sha256:" + hashlib.sha256(blob).hexdigest():
                continue
            try:
                said = load_json_bounded(blob.decode("utf-8"), "a model-call record", "show").get("format")
            except (UnicodeDecodeError, TooDeep, ValueError, RecursionError, AttributeError):
                continue
            if isinstance(said, str) and said != FORMAT and said.endswith("-draft") and said not in found:
                found.append(said)
    return found


def draft_line(run, store) -> str:
    """The run page's one line where its model-call records are in a draft format; "" otherwise."""
    formats = draft_formats(run, store)
    if not formats:
        return ""
    head, tail = DRAFT_LINE.split("{formats}")
    shown = ", ".join(f"<code>{escape(f)}</code>" for f in formats)
    return (f'<section data-section="draft-records" class="notice"><p>{escape(head)}{shown}{escape(tail)}</p>'
            "</section>")


def same_files(store, run_key: str, value: str) -> list[tuple[str, str, str, str, str]]:
    """Every other run whose readable records name `value` as their model files, with the step and
    record that name it: [(run label, its step page's href from a step page, step, record, state)]."""
    from onetrace_console.stage_pages import _files, _read, _stage_name, _steps, stage_page
    from onetrace_console.store import arrival_order
    from onetrace_console.words import run_named
    import html as _html
    out = []
    for run in arrival_order(store.runs(), newest_first=False):
        if run.key == run_key:
            continue
        try:
            files, steps = _files(run, store), _steps(run, store)
        except Exception:  # noqa: BLE001 - a run that can't be read names nothing here
            continue
        for s in steps:
            for o in outputs(s["receipt"]):
                try:
                    rec = read_output(s["file"], o, lambda path, files=files, run=run: _read(files, store, path))
                except Refused:
                    continue
                got = files_value(rec)
                if got is not None and got[0] == value:
                    label = " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", run_named(store, run.key))).split())
                    href = f"../{run.key}/{stage_page(s['index'])}#{anchor(str(o['name']))}"
                    out.append((label, href, _stage_name(s["receipt"]), str(o["name"]), got[1]))
    return out


def steps_line(name: str, record: dict) -> str:
    """Whether the call's per-step capture was taken: its file's name where the record names one."""
    if "steps" not in record:
        return f'<p data-model-call-steps="not-taken">{escape(STEPS_NOT_TAKEN)}</p>'
    from onetrace.model_call import naming
    return (f'<p data-model-call-steps="taken">{escape(STEPS_TAKEN.format(name=""))}'
            f"<code>{escape(naming.steps_name(name))}</code></p>")


def record_block(name: str, record: dict, steps: str = "", same: str = "") -> str:
    """One record: its per-step capture line, its fields under their groups, then its token timeline
    (`steps`, drawn by `timeline` or the reason it is not) and the runs that share its model files."""
    rows = "".join(_group_row(title) + "".join(_fingerprints(record[f]) if f == "fingerprints" else _shown(f, record[f])
                                               for f in fields) for title, fields in grouped(record))
    from onetrace_console.words import scroll_region
    table = scroll_region(f'<table class="board" data-model-call-table><thead><tr><th>field</th><th>state</th>'
                          f'<th>value</th><th>reason, as the record gives it</th></tr></thead>'
                          f'<tbody>{rows}</tbody></table>', f"The model-call record {name}", "model-call")
    return (f'<div class="model-call" id="{anchor(name)}" data-model-call="{escape(name)}"><h3><code>{escape(name)}</code></h3>'
            f'{steps_line(name, record)}{table}{steps}{same}</div>')


def refused_block(name: str, why: str) -> str:
    return (f'<div class="model-call" id="{anchor(name)}" data-model-call="{escape(name)}" data-refused><h3><code>{escape(name)}</code></h3>'
            f'<p>Not shown: {escape(why)}.</p></div>')


def outputs(receipt: dict) -> list[dict]:
    """A step's outputs named like a model-call record (`NAME`); a per-step capture file is never one."""
    return [o for o in receipt.get("outputs") or [] if isinstance(o, dict) and NAME.fullmatch(str(o.get("name", "")))]


def read_output(receipt_file: str, output: dict, read_file) -> dict:
    """One output named like a record: the record, or `Refused` with the reason it is not shown."""
    from onetrace_console.stage_pages import _artifact_path
    name = str(output["name"])
    if not is_record_name(name):
        raise Refused(NOT_A_RECORD_NAME)
    blob = read_file(_artifact_path(receipt_file, name))
    if blob is None:
        raise Refused("the run does not hold its bytes")
    if str(output.get("digest", "")) != "sha256:" + hashlib.sha256(blob).hexdigest():
        raise Refused("its stored bytes do not match its receipt")
    return read(blob)


def step_section(receipt: dict, receipt_file: str, read_file, same=None) -> str:
    """A step page's model-call records, or "" where its outputs hold none. `read_file(path)`: the
    stored bytes at a run path, or None. `same(value)`: the other runs naming the same model files
    (`same_files`), or None where none are looked for."""
    outs = outputs(receipt)
    if not outs:
        return ""
    blocks = []
    for o in outs:
        name = str(o["name"])
        try:
            record = read_output(receipt_file, o, read_file)
        except Refused as e:
            blocks.append(refused_block(name, str(e)))
            continue
        drawn = ""
        if "steps" in record:
            try:
                drawn = timeline(name, read_steps(receipt, receipt_file, name, record, read_file))
            except Refused as e:
                drawn = f'<p data-token-timeline-refused>{escape(TIMELINE_NOT_SHOWN.format(why=e))}</p>'
        got = files_value(record)
        line = same_files_line(record, same(got[0])) if same is not None and got is not None else ""
        blocks.append(record_block(name, record, drawn, line))
    return (f'<section data-section="model-call" class="model-call"><h2>{escape(HEADING)}</h2>'
            f'<p class="label" data-model-call-label>{_label()}</p>{"".join(blocks)}'
            f'<p class="footnote" data-model-call-schema>{escape(SCHEMA_NOTE)}</p></section>')


def _label() -> str:
    head, code, tail = LABEL.split("`")
    return f"{escape(head)}<code>{escape(code)}</code>{escape(tail)}"
