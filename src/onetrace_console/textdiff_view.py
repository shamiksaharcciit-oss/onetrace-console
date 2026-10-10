"""The text diff, read strictly and drawn as the SDK wrote it.

The input is what `onetrace diff A B --text --json` prints, `onetrace-textdiff/0.3`
(`docs/textdiff-format.md` and its schema, in the SDK's sdist). This module never diffs text
itself and never shows an output the SDK did not mark verified:

- **Read strictly** (`read_textdiff`): exactly the format and `text_form: "escaped"`; every key
  the schema allows and no other; every enum, decimal string and span checked; an output that is
  not verified must carry no hunks. Anything else is `TextDiffUnreadable` -- the page says it
  can't read this text diff, never a guess.
- **Escaped once** (`render_textdiff`): every display string is the SDK's own escaping, so it is
  HTML-escaped and nothing more (the format: "a renderer displays `text` as given, HTML-escaped
  if it is HTML, and never escapes it again"; `spans` index into `text` exactly as delivered).
  The reader refuses a display string that still holds a raw character of the SDK's escaped class,
  as the Diff page's SDK layer does.
- **Verified only**: an output's lines, notes and "verified" badge are drawn only where
  `verified` is `true`; otherwise only the SDK's own `reason`, word for word.

Where it comes from: each comparison's own stored run of `onetrace diff A B
--text --json --no-follow` (`compare.text_diff_raw`), and "Show more" its run at the console's one
larger limit; the corpus trace is board 7's.
"""
from __future__ import annotations

import re
from html import escape as _html

from onetrace_console.bounded_json import load_json_bounded

FORMAT = "onetrace-textdiff/0.3"
TEXT_FORM = "escaped"

_TOP = {"format", "text_form", "envelope", "exit", "shown", "reason", "first_line",
        "unknown_stages", "nodes", "corpus_traces"}
_TOP_REQUIRED = {"format", "text_form", "envelope", "exit", "shown"}
_ENVELOPES = {"identical": "0", "diverged": "1", "not comparable": None, "refused": None,
              "could not check": None}
_NODE = {"node", "verdict", "settings", "inputs", "presence", "causes", "outputs"}
_NODE_REQUIRED = {"node", "verdict", "settings", "inputs", "outputs"}
_VERDICTS = {"FIRST DIFFERENCE", "downstream", "reconverged", "same", "COULD NOT CHECK"}
_OUTPUT = {"name", "media_type", "verified", "kind", "notes", "reason", "presence", "truncated",
           "hunks", "entries"}
_OUTPUT_REQUIRED = {"name", "media_type", "verified", "kind", "notes", "hunks"}
_KINDS = {"text", "chunk index", "hits", "binary", "not diffed", "not shown"}
_PRESENCE = {"only in the baseline", "only in the candidate"}
_HUNK = {"baseline", "candidate", "lines", "note"}
_RANGE = {"start", "lines"}
_LINE = {"op", "baseline", "candidate", "text", "spans"}
_OPS = {" ", "-", "+"}
_ENTRY = {"id", "doc", "position", "change", "note"}
_CHANGES = {"changed", "added", "removed", "entered", "left", "moved"}
_CAUSE = {"kind", "name", "baseline", "candidate", "status"}
_CAUSE_KINDS = {"input", "tool", "setting", "corpus link"}
_DECIMAL = re.compile(r"^(0|[1-9][0-9]*)$")


class TextDiffUnreadable(ValueError):
    """The text diff exists but is not one this console reads. Never drawn as a guess."""


def _fail(why: str):
    raise TextDiffUnreadable(why)


def _keys(obj, allowed: set, required: set, what: str) -> None:
    if not isinstance(obj, dict):
        _fail(f"{what} is not an object")
    if set(obj) - allowed:
        _fail(f"{what} carries fields this console has not been taught: {sorted(set(obj) - allowed)}")
    if required - set(obj):
        _fail(f"{what} is missing {sorted(required - set(obj))}")


def _decimal(value, what: str, *, null: bool = False) -> None:
    if value is None and null:
        return
    if not (isinstance(value, str) and _DECIMAL.match(value)):
        _fail(f"{what} is not a decimal string: {value!r:.40}")


def _shown(value, what: str) -> None:
    """A display string: a string holding no character of the SDK's escaped class raw."""
    if not isinstance(value, str):
        _fail(f"{what} is not a string")
    from onetrace.escaping import escaped
    if escaped(value) != value.replace("\\", "\\\\"):
        _fail(f"{what} holds a character the SDK left unescaped")


def _strings(value, what: str) -> None:
    if not isinstance(value, list):
        _fail(f"{what} is not a list")
    for i, s in enumerate(value):
        _shown(s, f"{what}[{i}]")


def _line(line, what: str) -> None:
    _keys(line, _LINE, _LINE, what)
    if line["op"] not in _OPS:
        _fail(f"{what}'s op is {line['op']!r}")
    _decimal(line["baseline"], f"{what}'s baseline", null=line["op"] == "+")
    _decimal(line["candidate"], f"{what}'s candidate", null=line["op"] == "-")
    if line["op"] == "-" and line["candidate"] is not None or line["op"] == "+" and line["baseline"] is not None:
        _fail(f"{what} numbers a side it is not on")
    _shown(line["text"], f"{what}'s text")
    if not isinstance(line["spans"], list) or (line["op"] == " " and line["spans"]):
        _fail(f"{what}'s spans are not ones this console reads")
    end = -1
    for span in line["spans"]:
        if not (isinstance(span, list) and len(span) == 2):
            _fail(f"{what} has a span that is not [start, end]")
        _decimal(span[0], f"{what}'s span start")
        _decimal(span[1], f"{what}'s span end")
        a, b = int(span[0]), int(span[1])
        if not (end <= a < b <= len(line["text"])):
            _fail(f"{what} has a span outside its text or out of order: {span}")
        end = b


def _output(out, what: str) -> None:
    _keys(out, _OUTPUT, _OUTPUT_REQUIRED, what)
    if not (out["name"] is None or isinstance(out["name"], str)):
        _fail(f"{what}'s name is neither a string nor null")
    if out["name"] is not None:
        _shown(out["name"], f"{what}'s name")
    _shown(out["media_type"], f"{what}'s media type")
    if not isinstance(out["verified"], bool):
        _fail(f"{what}'s verified is not true or false")
    if out["kind"] not in _KINDS:
        _fail(f"{what}'s kind is {out['kind']!r}")
    _strings(out["notes"], f"{what}'s notes")
    if "presence" in out and out["presence"] not in _PRESENCE:
        _fail(f"{what}'s presence is {out['presence']!r}")
    if not isinstance(out["hunks"], list):
        _fail(f"{what}'s hunks are not a list")
    if not out["verified"]:
        #: The format: not verified, "with `reason` ..., and no hunks". Anything else is refused.
        if out["hunks"]:
            _fail(f"{what} is not verified and carries lines")
        if "reason" not in out:
            _fail(f"{what} is not verified and gives no reason")
    if "reason" in out:
        _shown(out["reason"], f"{what}'s reason")
    if "truncated" in out:
        _keys(out["truncated"], {"more_lines"}, {"more_lines"}, f"{what}'s truncated")
        _decimal(out["truncated"]["more_lines"], f"{what}'s more lines")
    for i, hunk in enumerate(out["hunks"]):
        _keys(hunk, _HUNK, _HUNK - {"note"}, f"{what}'s hunk {i}")
        for side in ("baseline", "candidate"):
            _keys(hunk[side], _RANGE, _RANGE, f"{what}'s hunk {i} {side}")
            _decimal(hunk[side]["start"], f"{what}'s hunk {i} {side} start")
            _decimal(hunk[side]["lines"], f"{what}'s hunk {i} {side} lines")
        if "note" in hunk:
            _shown(hunk["note"], f"{what}'s hunk {i} note")
        if not (isinstance(hunk["lines"], list) and hunk["lines"]):
            _fail(f"{what}'s hunk {i} has no lines")
        for j, line in enumerate(hunk["lines"]):
            _line(line, f"{what}'s hunk {i} line {j}")
    for i, entry in enumerate(out.get("entries", [])):
        #: Not drawn here (board 7 and item 3 read them); held to their shape all the same.
        _keys(entry, _ENTRY, {"change", "note"}, f"{what}'s entry {i}")
        if entry["change"] not in _CHANGES:
            _fail(f"{what}'s entry {i} change is {entry['change']!r}")
        _decimal(entry["note"], f"{what}'s entry {i} note")
        if int(entry["note"]) >= len(out["notes"]):
            _fail(f"{what}'s entry {i} names a note line that is not there")


def _node(node, what: str) -> None:
    _keys(node, _NODE, _NODE_REQUIRED, what)
    _shown(node["node"], f"{what}'s id")
    if node["verdict"] not in _VERDICTS:
        _fail(f"{what}'s verdict is {node['verdict']!r}")
    _strings(node["settings"], f"{what}'s settings")
    _strings(node["inputs"], f"{what}'s inputs")
    if "presence" in node:
        _shown(node["presence"], f"{what}'s presence")
    for i, cause in enumerate(node.get("causes", [])):
        #: Not drawn here (the cause table is board 6's); held to its keys and enums.
        _keys(cause, _CAUSE, _CAUSE, f"{what}'s cause {i}")
        if cause["kind"] not in _CAUSE_KINDS or cause["status"] not in ("same", "changed"):
            _fail(f"{what}'s cause {i} is not one this console reads")
    if not isinstance(node["outputs"], list):
        _fail(f"{what}'s outputs are not a list")
    for i, out in enumerate(node["outputs"]):
        _output(out, f"{what}'s output {i}")


def read_textdiff(raw: str | bytes) -> dict:
    """`onetrace diff A B --text --json`'s document, read strictly, or `TextDiffUnreadable`."""
    try:
        doc = load_json_bounded(raw, "the text diff")
    except ValueError as e:
        raise TextDiffUnreadable(f"the text diff is not JSON this console reads: {e}") from None
    _keys(doc, _TOP, _TOP_REQUIRED, "the text diff")
    if doc["format"] != FORMAT:
        _fail(f"the text diff's format is {doc['format']!r}, not {FORMAT!r}")
    if doc["text_form"] != TEXT_FORM:
        _fail(f"the text diff's text form is {doc['text_form']!r}, not {TEXT_FORM!r}")
    if doc["envelope"] not in _ENVELOPES:
        _fail(f"the text diff's envelope is {doc['envelope']!r}")
    _decimal(doc["exit"], "the text diff's exit")
    expected_exit = _ENVELOPES[doc["envelope"]]
    if expected_exit is not None and doc["exit"] != expected_exit:
        _fail(f"the text diff's exit {doc['exit']} disagrees with its envelope {doc['envelope']!r}")
    if not isinstance(doc["shown"], bool):
        _fail("the text diff's shown is not true or false")
    if doc["shown"] and doc["envelope"] not in ("identical", "diverged"):
        _fail("the text diff shows text for runs it did not compare")
    if not doc["shown"]:
        if "reason" not in doc or doc.get("nodes"):
            _fail("the text diff shows nothing and gives no reason, or shows nothing with nodes")
    for key in ("reason", "first_line"):
        if key in doc:
            _shown(doc[key], f"the text diff's {key}")
    if "unknown_stages" in doc:
        _strings(doc["unknown_stages"], "the text diff's unknown stages")
    if not isinstance(doc.get("nodes", []), list):
        _fail("the text diff's nodes are not a list")
    for i, node in enumerate(doc.get("nodes", [])):
        _node(node, f"node {i}")
    if "corpus_traces" in doc and not (isinstance(doc["corpus_traces"], list)
                                       and all(isinstance(t, dict) for t in doc["corpus_traces"])):
        _fail("the text diff's corpus traces are not a list of objects")
    return doc


# --------------------------------------------------------------------------------------- drawing

#: The word on the "verified" badge each output shown carries.
VERIFIED = "verified"


def _marked(text: str, spans: list, mark: str) -> str:
    """`text` HTML-escaped once, with each span's characters in a `<mark>` (spans index `text`
    exactly as delivered)."""
    out, at = [], 0
    for start, end in ((int(a), int(b)) for a, b in spans):
        out.append(_html(text[at:start]))
        out.append(f'<mark class="{mark}">{_html(text[start:end])}</mark>')
        at = end
    out.append(_html(text[at:]))
    return "".join(out)


def _render_output(out: dict) -> str:
    name = _html(out["name"]) if out["name"] is not None else ""
    head = (f'<p class="output-head"><code>{name}</code> '
            f'<span class="value">{_html(out["media_type"])}</span>')
    if out.get("presence"):
        head += f' · {_html(out["presence"])}'
    if out["verified"] is not True:
        #: Never an unverified output's lines, notes or badge: the SDK's reason, word for word.
        return (f'<div data-output data-verified="false">{head}</p>'
                f'<p data-not-shown>{_html(out.get("reason", ""))}</p></div>')
    parts = [f'<div data-output data-verified="true">{head} '
             f'<span class="pill ok" data-badge="verified">{VERIFIED}</span></p>']
    if out["notes"]:
        parts.append('<pre data-notes>' + "\n".join(_html(n) for n in out["notes"]) + "</pre>")
    for hunk in out["hunks"]:
        lines = []
        for line in hunk["lines"]:
            mark = {"-": "del", "+": "ins"}.get(line["op"], "")
            lines.append(f'<span data-op="{_html(line["op"])}">{_html(line["op"])} '
                         f'{_marked(line["text"], line["spans"], mark)}</span>')
        note = f'<p data-hunk-note>{_html(hunk["note"])}</p>' if "note" in hunk else ""
        parts.append(f'{note}<pre data-hunk>' + "\n".join(lines) + "</pre>")
    if "truncated" in out:
        #: The SDK's own words for a cut output (`… n more lines`, the plain form's).
        parts.append(f'<p data-truncated>… {_html(out["truncated"]["more_lines"])} more lines</p>')
    parts.append("</div>")
    return "".join(parts)


def render_textdiff(doc: dict) -> str:
    """The text diff as the SDK wrote it: a strict reading's result, escaped once, verified only."""
    if not doc["shown"]:
        return f'<div data-textdiff="not-shown"><p>{_html(doc["reason"])}</p></div>'
    parts = ['<div data-textdiff="shown">']
    if "first_line" in doc:
        parts.append(f'<p data-first-line>{_html(doc["first_line"])}</p>')
    for node in doc.get("nodes", []):
        parts.append(f'<article data-node="{_html(node["node"])}">'
                     f'<h3>{_html(node["node"])} · {_html(node["verdict"])}</h3>')
        if node.get("presence"):
            parts.append(f'<p>{_html(node["presence"])}</p>')
        parts.extend(f'<p data-settings>{_html(s)}</p>' for s in node["settings"])
        parts.extend(f'<p data-input>{_html(s)}</p>' for s in node["inputs"])
        parts.extend(_render_output(out) for out in node["outputs"])
        parts.append("</article>")
    parts.append("</div>")
    return "".join(parts)
