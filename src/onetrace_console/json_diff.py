"""A structured view of a JSON output that changed: its added, removed and changed members by path.

Beside the text diff, for an output the SDK's text diff shows as verified on both sides (a changed
output both runs kept). The console reads each side's stored bytes itself and uses them only where
their digest is the one the step's receipt records. Where both parse as JSON, the members that differ
are listed by path, in a stable order: an object's members in the order of their names, an array's
by position. Where either side is not JSON, nothing is added and the text diff stands alone.

- **JSON, read strictly:** UTF-8; a repeated name in one object, `NaN` or `Infinity`, or nesting past
  the console's limit (`bounded_json`) is not read as JSON here.
- **Numbers as written:** a number is kept as its text, never a float, so `1.0` and `1.00` are two
  values, as their bytes are; the line under the view's heading says so (`NUMBERS`).
- **Paths:** JSON Pointer (RFC 6901), `/` for each step down, `~0` and `~1` for `~` and `/` in a
  name; the whole value is `(the whole value)`.
- **Values:** as compact JSON; one longer than `LIMIT` characters is shown by its sha256 digest, as
  the text diff shows a chunk; at most `MAX_MEMBERS` members are listed, then how many more.

It shows members, not meaning: a member that differs is named, never what it stands for.
"""
from __future__ import annotations

import hashlib
import json

from onetrace_console.bounded_json import load_json_bounded
from onetrace_console.words import escape

#: A value's characters shown; past it, its digest.
LIMIT = 200
#: The members listed, as the SDK's default caps an output's lines.
MAX_MEMBERS = 200
ROOT = "(the whole value)"
HEADING = "By member, as JSON"
#: Under the heading, always: two numbers that read as one value are two members here.
NUMBERS = "Numbers are compared as written, so 1.0 and 1.00 differ."
COUNTS = "{added} added · {removed} removed · {changed} changed"
NONE_DIFFER = "Both sides read as JSON, and no member differs: only the bytes do."
MORE = "… {n} more members"


class Number(str):
    """A JSON number, kept as written."""


class _NotJson(ValueError):
    pass


def _pairs(pairs):
    names = [k for k, _ in pairs]
    if len(set(names)) != len(names):
        raise _NotJson("a repeated name")
    return dict(pairs)


def _constant(name):
    raise _NotJson(name)


def parse(data: bytes | None):
    """(True, the value) where `data` reads as JSON here; (False, None) otherwise."""
    if data is None:
        return False, None
    try:
        return True, load_json_bounded(data.decode("utf-8"), "an output", "show", object_pairs_hook=_pairs,
                                       parse_constant=_constant, parse_float=Number, parse_int=Number)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return False, None


def text(v) -> str:
    """A value as compact JSON, a number as written."""
    if isinstance(v, Number):
        return str(v)
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + text(x) for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(text(x) for x in v) + "]"
    return json.dumps(v, ensure_ascii=False)


def _same(a, b) -> bool:
    return type(a) is type(b) and text(a) == text(b)


def _step(path: str, key) -> str:
    return f"{path}/{str(key).replace('~', '~0').replace('/', '~1')}"


def members(a, b, path: str = "") -> list[tuple[str, str, object, object]]:
    """[(added | removed | changed, path, baseline value, candidate value)], in a stable order."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(a.keys() | b.keys()):
            if key not in b:
                out.append(("removed", _step(path, key), a[key], None))
            elif key not in a:
                out.append(("added", _step(path, key), None, b[key]))
            else:
                out += members(a[key], b[key], _step(path, key))
        return out
    if isinstance(a, list) and isinstance(b, list):
        out = []
        for i in range(max(len(a), len(b))):
            if i >= len(b):
                out.append(("removed", _step(path, i), a[i], None))
            elif i >= len(a):
                out.append(("added", _step(path, i), None, b[i]))
            else:
                out += members(a[i], b[i], _step(path, i))
        return out
    return [] if _same(a, b) else [("changed", path, a, b)]


def _shown(v) -> str:
    from onetrace.escaping import escaped
    said = text(v)
    if len(said) <= LIMIT:
        return f'<code>{escape(escaped(said))}</code>'
    d = hashlib.sha256(said.encode("utf-8")).hexdigest()
    return (f'<span class="mono" data-json-digest title="sha256:{d}">sha256:{d[:12]}…</span> '
            f'({len(said)} characters)')


def _path(p: str) -> str:
    from onetrace.escaping import escaped
    return f'<code data-json-path>{escape(escaped(p))}</code>' if p else escape(ROOT)


def render(found: list) -> str:
    """The view, under an output's text diff."""
    head = (f'<div data-json-diff><p class="label">{escape(HEADING)}</p>'
            f'<p data-json-numbers>{escape(NUMBERS)}</p>')
    if not found:
        return f'{head}<p data-json-none>{escape(NONE_DIFFER)}</p></div>'
    n = {op: sum(f[0] == op for f in found) for op in ("added", "removed", "changed")}
    rows = []
    for op, path, old, new in found[:MAX_MEMBERS]:
        said = {"added": lambda: f"added: {_shown(new)}", "removed": lambda: f"removed: {_shown(old)}",
                "changed": lambda: f"changed: {_shown(old)} → {_shown(new)}"}[op]()
        rows.append(f'<li data-json-op="{op}">{_path(path)} {said}</li>')
    more = (f'<p data-json-more>{escape(MORE.format(n=len(found) - MAX_MEMBERS))}</p>'
            if len(found) > MAX_MEMBERS else "")
    return (f'{head}<p data-json-counts>{escape(COUNTS.format(**n))}</p>'
            f'<ul class="plain" data-json-members>{"".join(rows)}</ul>{more}</div>')


def _bytes(side, node: str, name: str) -> bytes | None:
    """One side's stored output, where its digest is the one its receipt records."""
    from pathlib import PurePosixPath

    from onetrace import canonical
    from onetrace_console.kept_inputs import _receipt_for
    if side is None:
        return None
    step = _receipt_for(side[0], node)
    if step is None:
        return None
    outs = [o for o in step["receipt"].get("outputs") or [] if isinstance(o, dict) and o.get("name") == name]
    if len(outs) != 1:
        return None
    data = side[1](f"artifacts/{PurePosixPath(step['file']).stem}/{name}")
    return data if data is not None and canonical.digest(data) == outs[0].get("digest") else None


def for_node(node: dict, sides) -> dict:
    """{output name: its members} for each output of `node` the text diff shows on both sides
    where both read as JSON."""
    out = {}
    if sides is None or None in sides:
        return out
    for o in node.get("outputs") or []:
        if o.get("verified") is not True or o.get("presence") or not isinstance(o.get("name"), str):
            continue
        got = [parse(_bytes(side, str(node.get("node", "")), o["name"])) for side in sides]
        if all(ok for ok, _ in got):
            out[o["name"]] = members(got[0][1], got[1][1])
    return out
