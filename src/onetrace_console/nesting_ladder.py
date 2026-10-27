"""Steps inside steps, in the ladder: a run page's table of steps, and a comparison's table of nodes.

onetrace 0.5 records a step called inside another as a step of the run with `parent` naming the
calling step, and the calling step's `children` naming them in call order; the chain holds them in
the order they finished, so a child's receipt comes before its parent's. A step that started a run
of its own records it as an input `run:<id>`, its digest that run's chain head.

Here each child's row is moved under its calling step, in call order, marked (`data-child-of`) and
indented, its own result in its own cells, with "inside `<step>`" in its step cell. A nested run is
a row of its own under its calling step: "nested run <id>", the head the step recorded, and a link to
its page where the console holds it, "not loaded" where it does not. A table with neither is
returned as it is, byte for byte.
"""
from __future__ import annotations

import html
import re

from onetrace_console.nesting_view import NESTED, NOT_LOADED, _name, nested_inputs
from onetrace_console.words import escape

INSIDE = "inside"
_STEP_ROW = re.compile(r'<tr data-step="([^"]+)">.*?</tr>', re.S)
#: Where the step's cell ends, before its closing tag: the first cell of a run's table, the node cell of
#: a comparison's.
_STEP_CELL = re.compile(r"<td\b[^>]*>.*?(?=</td>)", re.S)
_NODE_CELL = re.compile(r"<td\b[^>]*>.*?</td><td\b[^>]*>.*?(?=</td>)", re.S)
#: A comparison's row: its node is its second cell (the cells are labelled later, on the page).
_NODE_ROW = re.compile(r'<tr data-node-row="[^"]*"[^>]*><td\b[^>]*>.*?</td><td\b[^>]*>(.*?)</td>.*?</tr>', re.S)


def _nested_row(rid: str, head: str, href: str, parent: str, depth: int, cols: int, side: str = "") -> str:
    from onetrace_console.trace_panel import code_or_fold
    where = f'<a href="{escape(href)}">open its page</a>' if href else escape(NOT_LOADED)
    said = f"{escape(side)}: " if side else ""
    return (f'<tr data-nested-run="{escape(rid)}" data-child-of="{escape(parent)}" data-depth="{depth}">'
            f'<td colspan="{cols}">{said}{escape(NESTED)} <code>{escape(rid)}</code>, its head recorded as '
            f'{code_or_fold(head)} · {where}</td></tr>')


def _marked(row: str, opening: str, parent: str, depth: int, cell_end: re.Pattern) -> str:
    """`row` marked as a child of `parent`, "inside `parent`" put at the end of the step's cell
    (`cell_end` finds where that cell closes)."""
    row = row.replace(opening, f'{opening[:-1]} data-child-of="{escape(parent)}" data-depth="{depth}">', 1)
    m = cell_end.search(row)
    at = m.end() if m else -1
    note = f'<div class="inside">{escape(INSIDE)} <code>{escape(parent)}</code></div>'
    return row[:at] + note + row[at:] if at >= 0 else row


def _placed(order: list[str], rows: dict[str, str], receipts: dict[str, dict], nested_for, opening_of,
            cell_end: re.Pattern) -> list[str] | None:
    """The rows in ladder order, or None where nothing moves and nothing is added. `order`: the keys
    as the table holds them; `receipts`: key -> that step's receipt."""
    name_key = {_name(r): k for k, r in receipts.items()}
    parent_of = {k: str(r.get("parent")) for k, r in receipts.items()
                 if r.get("parent") and str(r.get("parent")) in name_key and k in rows}
    if not parent_of and not any(nested_for(k) for k in order):
        return None
    out: list[str] = []
    done: set[str] = set()

    def emit(key: str, depth: int, parent: str) -> None:
        done.add(key)
        out.append(_marked(rows[key], opening_of(key), parent, depth, cell_end) if depth else rows[key])
        receipt = receipts.get(key) or {}
        name = _name(receipt)
        kids = [name_key.get(str(c)) for c in receipt.get("children") or []] if isinstance(
            receipt.get("children"), list) else []
        kids += [k for k in order if parent_of.get(k) == name and k not in kids]
        for k in kids:
            if k in rows and k not in done and parent_of.get(k) == name:
                emit(k, depth + 1, name)
        out.extend(nested_for(key, depth + 1, name))

    for key in order:
        if key not in done and key not in parent_of:
            emit(key, 0, "")
    out += [rows[k] for k in order if k not in done]
    return out


def _tbody(page: str, row: re.Pattern) -> tuple[int, int] | None:
    first = row.search(page)
    if first is None:
        return None
    start = page.rfind("<tbody>", 0, first.start())
    end = page.find("</tbody>", first.start())
    return (start + len("<tbody>"), end) if start >= 0 and end >= 0 else None


def run_ladder(page: str, steps: list[dict], held: dict[str, str]) -> str:
    """A run page's table of steps with each step's children under it and its nested runs.
    `steps`: [{index, file, receipt}]; `held`: {run id: the href of its page}."""
    span = _tbody(page, _STEP_ROW)
    if span is None:
        return page
    body = page[span[0]:span[1]]
    found = list(_STEP_ROW.finditer(body))
    rows = {m.group(1): m.group(0) for m in found}
    order = [m.group(1) for m in found]
    receipts = {str(s.get("index")): s.get("receipt") or {} for s in steps if str(s.get("index")) in rows}
    head = page[:span[0]]
    cols = len(re.findall(r"<th\b", head[head.rfind("<thead>"):]))

    def nested(key, depth=1, parent=""):
        return [_nested_row(rid, h, held.get(rid, ""), parent, depth, cols)
                for rid, h in nested_inputs(receipts.get(key) or {})]
    placed = _placed(order, rows, receipts, nested, lambda k: f'<tr data-step="{k}">', _STEP_CELL)
    if placed is None:
        return page
    return page[:span[0]] + "".join(placed) + page[span[1]:]


def diff_ladder(table: str, receipts_a: list[dict], receipts_b: list[dict], held: dict[str, str]) -> str:
    """A comparison's table of nodes, each child under its calling step (from the candidate's record,
    else the baseline's), and under a step that started a run, each run's nested run."""
    span = _tbody(table, _NODE_ROW)
    if span is None:
        return table
    body = table[span[0]:span[1]]
    found = list(_NODE_ROW.finditer(body))
    node = lambda m: html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()  # noqa: E731
    rows = {node(m): m.group(0) for m in found}
    order = [node(m) for m in found]
    by_name = {}
    for r in list(receipts_a) + list(receipts_b):
        if isinstance(r, dict):
            by_name[_name(r)] = r
    receipts = {k: by_name[k] for k in order if k in by_name}
    sides = (("baseline", {_name(r): r for r in receipts_a if isinstance(r, dict)}),
             ("candidate", {_name(r): r for r in receipts_b if isinstance(r, dict)}))
    head = table[:span[0]]
    cols = len(re.findall(r"<th\b", head[head.rfind("<thead>"):]))

    def nested(key, depth=1, parent=""):
        return [_nested_row(rid, h, held.get(rid, ""), parent or key, depth, cols, side)
                for side, mine in sides for rid, h in nested_inputs(mine.get(key) or {})]

    def opening(key):
        m = re.match(r"<tr [^>]*>", rows[key])
        return m.group(0)
    placed = _placed(order, rows, receipts, nested, opening, _NODE_CELL)
    if placed is None:
        return table
    return table[:span[0]] + "".join(placed) + table[span[1]:]
