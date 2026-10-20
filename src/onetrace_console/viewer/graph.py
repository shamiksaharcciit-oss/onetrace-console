"""The execution graph: a run's recorded nodes and links, laid out and drawn as SVG.

The layout is layered:

- **Layers.** A node's layer is the length of its longest path from a source, along the
  recorded links (the manifest's `edges`) and nothing else.
- **Order inside a layer.** Emission order first; then a fixed number of barycentric passes
  (down, then up, alternately), each moving a box towards the mean row of its neighbours in the
  layer before (or after). Every tie is broken by emission index, then by the box's key -- never
  by the iteration order of a dict or set, so the same record draws the same bytes on any host
  and under any hash seed.
- **Coordinates** are integers computed here, and the drawing is server-side SVG: cubic links
  with arrowheads, every box a real link, boundaries and the authorization node dashed.
- **Folding.** Instances of one stage name (a loop, a retry: `name#a`, `name#b`) fold into one
  box, "name ×n"; its members, failed attempts included, are listed beneath the graph.
- **A run with no `edges`** is drawn as a straight line, in emission order, with no links: a
  line drawn between two boxes would be a link the record does not hold.
- **Never invent a link; never drop one silently.** A recorded link that names a node the run
  did not record is listed in the table and not drawn.
- **Size.** Above MAX_DRAWN boxes the graph gives way to a notice and the table.

Nothing here decides a verdict: the graph draws what the record holds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from html import escape

from onetrace_console.viewer.sentences import sentence, template


def _ordinal(n: int) -> str:
    """An ordinal: st, nd and rd after a last digit of one, two or three, th after the rest and after
    the teens."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def instance_label(node_id: str) -> str:
    """A repeated stage's node, `name#n`, as a table names it beside the graph's "name ×n":
    "name (nth)". Any other node id is shown as it is."""
    name, sep, n = str(node_id).rpartition("#")
    return f"{name} ({_ordinal(int(n))})" if sep and name and n.isdigit() and int(n) > 0 else str(node_id)

#: Barycentric passes, fixed so the result never depends on when a loop happened to settle.
SWEEPS = 6
#: Above 60 nodes the page shows a notice and the table instead. Counted as boxes drawn.
MAX_DRAWN = 60

BOX_W, BOX_H = 184, 40
#: A node's name, wrapped whole: each line at most LABEL_MAX characters, LABEL_LINE_H high.
LABEL_LINE_H = 18
#: A node's state, drawn as a chip: CHIP_H high, CHIP_CHAR wide per character, CHIP_PAD each side.
CHIP_H, CHIP_CHAR, CHIP_PAD = 20, 6.6, 9
#: Characters to a state line (12px sans, about 6.2px a character). The page's own words wrap
#: to as many lines as they take and the box grows to hold them; a quoted line longer than this is
#: shortened, its whole text in its own <title> and in the page's own table.
STATE_MAX = 26
#: Characters to a state line as drawn: 12px mono, 7.2px a character as Chromium draws it, so 22 fit
#: the box within its 10px each side (158px of 164). The page's own words wrap at it; a quoted line
#: is shortened to it, its whole text in its own <title> and in the page's own table.
STATE_WRAP = 22
#: A node's state lines (its verdict in the page's words, then the report's quoted words), each
#: TAG_LINE_H high: the page's own words whole, then quoted lines while the box has fewer than
#: TAG_LINES of its tags. The page's words are in the box's <title>, each quoted line in its own;
#: all of them are in the page's own table.
TAG_LINES, TAG_LINE_H = 2, 16
GAP_X, GAP_Y = 56, 24
MARGIN = 12
#: Characters to a line of a box's name, at the name's 14px mono (about 8.4px a character, within
#: BOX_W less 10px each side); the name is never cut. Four boxes and their gaps fit a 1280 page.
LABEL_MAX = 19


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One recorded node: its id (`name` or `name#instance`), its stage name, its emission
    index, where it links to, and whether it is drawn dashed (a boundary, the authorization
    node) or marked as a failed attempt."""
    node_id: str
    name: str
    index: int
    href: str
    dashed: bool = False
    failed: bool = False
    #: How the page shows the id and the stage name -- capped as every record word is.
    #: Empty means as recorded. Matching is always on `node_id`, never on these.
    label: str = ""
    shown: str = ""
    #: Item 3: short lines the page states about this node (its verdict, its settings), in the
    #: page's own words; and a mark (e.g. "first") a stylesheet can outline. Nothing here
    #: decides either: the caller reads them from the report it holds.
    tags: tuple[str, ...] = ()
    #: A report's own words about this node (a comparison's annotations), shown as quoted words,
    #: never as the page's: each line is marked as quoted and titled with its whole text.
    quoted: tuple[str, ...] = ()
    mark: str = ""
    #: The tone of the node's state, by the console's one colour rule ("ok", "cc", "bad",
    #: "neu"), for a stylesheet to colour the box by; its words stay in `tags`. Empty: no tone.
    tone: str = ""
    #: The node ids whose receipts this node's receipt records reading (its `receipt:<id>`
    #: inputs). A run recorded as a line draws a link only where one of these is recorded.
    reads: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Box:
    """One drawn box: a node, or a fold of one stage's instances."""
    key: str
    label: str
    members: tuple[GraphNode, ...]
    index: int                     # the earliest member's emission index
    layer: int
    row: int
    x: int
    y: int
    href: str
    dashed: bool
    tags: tuple[str, ...] = ()     # the members' states, each once, in member order
    quoted: tuple[str, ...] = ()   # the members' quoted report words, each once, in member order
    mark: str = ""
    tone: str = ""


@dataclass(frozen=True, slots=True)
class Layout:
    linear: bool
    boxes: tuple[Box, ...]
    #: Drawn links, between box keys; every recorded link between recorded nodes; and the
    #: recorded links that name a node the run did not record. Each sorted.
    links: tuple[tuple[str, str], ...]
    recorded: tuple[tuple[str, str], ...]
    outside: tuple[tuple[str, str], ...]
    width: int
    height: int
    box_h: int = BOX_H             # every box in a drawing as tall as its tallest needs
    label_lines: int = 1           # the most lines any box's name wraps onto
    tag_lines: int = TAG_LINES     # at most this many state lines drawn in a box
    chip: bool = False             # whether a box's first state is drawn as a chip


def _fold_key(node: GraphNode, counts: dict[str, int]) -> str:
    return node.name if counts[node.name] > 1 else node.node_id


def _label_lines(label: str) -> list[str]:
    """A name whole, in lines of at most LABEL_MAX characters, each broken after a space, `_`, `-`,
    `.` or `/` where the line has one, and otherwise at LABEL_MAX. Never cut: every character is
    drawn (a record word is already within the page's name cap)."""
    lines, rest = [], label
    while len(rest) > LABEL_MAX:
        cut = max(rest.rfind(c, 1, LABEL_MAX) for c in " _-./")
        cut = cut + 1 if cut > 0 else LABEL_MAX
        lines.append(rest[:cut].rstrip(" "))
        rest = rest[cut:].lstrip(" ")
    return lines + [rest]


def lay_out(nodes, edges, *, wrap: int = 0, wrap_labels: bool = False,
            tag_lines: int = TAG_LINES) -> Layout:
    """The layout of `nodes` (GraphNode) linked by `edges` (the manifest's list of
    {"from", "to"} dicts, or None for a run recorded as a line). `wrap`, for a line only: at
    most that many boxes to a row, the line continuing on the next row, so a long line fits
    its page's width instead of scrolling; 0 keeps one row."""
    nodes = sorted(nodes, key=lambda n: (n.index, n.node_id))
    by_id = {n.node_id: n for n in nodes}
    counts: dict[str, int] = {}
    for n in nodes:
        counts[n.name] = counts.get(n.name, 0) + 1

    members: dict[str, list[GraphNode]] = {}
    for n in nodes:
        members.setdefault(_fold_key(n, counts), []).append(n)
    keys = sorted(members, key=lambda k: (members[k][0].index, k))
    first_index = {k: members[k][0].index for k in keys}

    def order_key(k: str) -> tuple:
        return (first_index[k], k)

    recorded_pairs = sorted({(str(e.get("from")), str(e.get("to"))) for e in (edges or [])})
    recorded = tuple(p for p in recorded_pairs if p[0] in by_id and p[1] in by_id)
    outside = tuple(p for p in recorded_pairs if not (p[0] in by_id and p[1] in by_id))
    fold = {n.node_id: _fold_key(n, counts) for n in nodes}
    links = tuple(sorted({(fold[f], fold[t]) for f, t in recorded if fold[f] != fold[t]},
                         key=lambda p: (order_key(p[0]), order_key(p[1]))))

    if edges is None:
        #: A line has no recorded graph, but each receipt records the receipts it read: those are
        #: its links, listed in the table, and drawn between boxes next to each other in the order.
        reads = sorted({(n2, n.node_id) for n in nodes for n2 in n.reads
                        if n2 in by_id and fold[n2] != fold[n.node_id]})
        recorded = tuple(reads)
        nxt = {a: b for a, b in zip(keys, keys[1:])}
        links = tuple(sorted({(fold[f], fold[t]) for f, t in reads if nxt.get(fold[f]) == fold[t]},
                             key=lambda p: (order_key(p[0]), order_key(p[1]))))
    if edges is None and wrap > 0 and len(keys) > wrap:
        layer = {k: i % wrap for i, k in enumerate(keys)}
        rows = {k: i // wrap for i, k in enumerate(keys)}
        by_layer = [[k for k in keys if layer[k] == c] for c in range(wrap)]
    elif edges is None:
        layer = {k: i for i, k in enumerate(keys)}
        rows = {k: 0 for k in keys}
        by_layer = [[k] for k in keys]
    else:
        layer = _layers(keys, links, order_key)
        by_layer = _rows(keys, links, layer, order_key)
        rows = {k: r for col in by_layer for r, k in enumerate(col)}

    tallest = max((len(col) for col in by_layer), default=0)
    chip = any(n.tags for n in nodes)
    #: The state lines after the chip: the rest of the tags, whole, then the report's quoted words.
    #: Counted per box, over its members' tags and quoted words as the box joins them.
    joined = {k: (tuple(dict.fromkeys(tag for m in members[k] for tag in m.tags)),
                  tuple(dict.fromkeys(q for m in members[k] for q in m.quoted))) for k in keys}
    lines = max((len(_drawn_lines(tags, quoted, tag_lines)) for tags, quoted in joined.values()),
                default=0)
    labels = [(members[k][0].label or members[k][0].node_id) if len(members[k]) == 1 else sentence(
        "graph.fold", name=members[k][0].shown or members[k][0].name, n=str(len(members[k])))
        for k in keys]
    label_lines = max((len(_label_lines(lb)) for lb in labels), default=1)
    box_h = (14 + label_lines * LABEL_LINE_H + (CHIP_H + 8 if chip else 0)
             + lines * TAG_LINE_H + 8)
    boxes = []
    for col_no, col in enumerate(by_layer):
        #: A wrapped line's rows start at the top, as text does; a graph's layers are centred.
        offset = 0 if edges is None else (tallest - len(col)) * (box_h + GAP_Y) // 2
        for k in col:
            ms = tuple(members[k])
            label = (ms[0].label or ms[0].node_id) if len(ms) == 1 else sentence(
                "graph.fold", name=ms[0].shown or ms[0].name, n=str(len(ms)))
            boxes.append(Box(
                key=k, label=label, members=ms, index=first_index[k], layer=col_no,
                row=rows[k], x=MARGIN + col_no * (BOX_W + GAP_X),
                y=MARGIN + offset + rows[k] * (box_h + GAP_Y),
                href=ms[0].href, dashed=any(m.dashed for m in ms),
                tags=joined[k][0], quoted=joined[k][1],
                mark=next((m.mark for m in ms if m.mark), ""),
                tone=next((m.tone for m in ms if m.tone), "")))
    width = MARGIN * 2 + max(len(by_layer), 1) * BOX_W + max(len(by_layer) - 1, 0) * GAP_X
    height = MARGIN * 2 + max(tallest, 1) * box_h + max(tallest - 1, 0) * GAP_Y
    return Layout(edges is None, tuple(boxes), links, recorded, outside, width, height, box_h,
                  label_lines, tag_lines, chip)


def _layers(keys: list[str], links, order_key) -> dict[str, int]:
    """Longest path from a source, in a topological order whose ties go to the order key. A
    cycle cannot come from a record, but a malformed one must not hang or lose a node: what is
    left is placed after every layer, in order-key order."""
    incoming = {k: [] for k in keys}
    outgoing = {k: [] for k in keys}
    for f, t in links:
        incoming[t].append(f)
        outgoing[f].append(t)
    remaining = {k: len(incoming[k]) for k in keys}
    ready = sorted((k for k in keys if not remaining[k]), key=order_key)
    layer: dict[str, int] = {}
    while ready:
        k = ready.pop(0)
        layer[k] = max((layer[p] + 1 for p in incoming[k]), default=0)
        for m in sorted(outgoing[k], key=order_key):
            remaining[m] -= 1
            if remaining[m] == 0:
                ready.append(m)
                ready.sort(key=order_key)
    top = max(layer.values(), default=-1)
    for k in sorted((k for k in keys if k not in layer), key=order_key):
        top += 1
        layer[k] = top
    return layer


def _rows(keys, links, layer, order_key) -> list[list[str]]:
    """Each layer's boxes, top to bottom: emission order, then SWEEPS barycentric passes.

    A box's barycentre is the exact mean (a Fraction, so equal means compare equal) of its
    neighbours' rows in the layer before (passes down) or after (passes up). A box with no such
    neighbour keeps its current row as its barycentre. Ties go to emission index, then key."""
    depth = max(layer.values(), default=-1) + 1
    cols = [sorted((k for k in keys if layer[k] == d), key=order_key) for d in range(depth)]
    ups = {k: sorted((f for f, t in links if t == k), key=order_key) for k in keys}
    downs = {k: sorted((t for f, t in links if f == k), key=order_key) for k in keys}
    for sweep in range(SWEEPS):
        going_down = sweep % 2 == 0
        span = range(1, depth) if going_down else range(depth - 2, -1, -1)
        for d in span:
            pos = {k: r for col in cols for r, k in enumerate(col)}

            def place(item: tuple[int, str], pos=pos, near_of=ups if going_down else downs):
                at, k = item
                near = near_of[k]
                if not near:
                    return (Fraction(at), order_key(k))
                return (Fraction(sum(pos[n] for n in near), len(near)), order_key(k))
            cols[d] = [k for _, k in sorted(enumerate(cols[d]), key=place)]
    return cols


# ------------------------------------------------------------------------------ drawing

def _short(label: str, most: int = LABEL_MAX) -> str:
    return label if len(label) <= most else label[:most - 1] + "…"


def _state_lines(text: str) -> list[str]:
    """The page's own words, whole, in lines of at most STATE_WRAP characters, each broken after a
    space where the line has one, and otherwise at STATE_WRAP. Never cut: every character is drawn."""
    lines, rest = [], text
    while len(rest) > STATE_WRAP:
        cut = rest.rfind(" ", 1, STATE_WRAP + 1)
        cut = cut if cut > 0 else STATE_WRAP
        lines.append(rest[:cut].rstrip(" "))
        rest = rest[cut:].lstrip(" ")
    return lines + [rest]


def _drawn_lines(tags, quoted, tag_lines: int) -> list[tuple[str, bool]]:
    """A box's state lines after its chip, as drawn: each of the page's own tags whole, wrapped;
    then the report's quoted words, one shortened line each, while the box holds fewer than
    `tag_lines` of its tags and quoted lines together."""
    own = [(line, False) for tag in tags[1:] for line in _state_lines(tag)]
    room = max(tag_lines - max(len(tags) - 1, 0), 0)
    return own + [(q, True) for q in quoted[:room]]


def svg(layout: Layout, esc=escape) -> str:
    """The drawing, as one <svg> element. Same layout, same bytes. `esc` escapes record words:
    the page passes its own, which also shows control and bidi characters escaped."""
    at = {b.key: b for b in layout.boxes}
    #: Inline SVG in an HTML page needs no namespace URL, and the page names no scheme at all.
    parts = [f'<svg class="graph" role="group" '
             f'width="{layout.width}" height="{layout.height}" '
             f'viewBox="0 0 {layout.width} {layout.height}">',
             '<defs><marker id="graph-arrow" viewBox="0 0 8 8" refX="8" refY="4" '
             'markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L8,4 L0,8 z"/>'
             '</marker></defs>']
    for f, t in layout.links:
        a, b = at[f], at[t]
        if layout.linear and b.row != a.row:
            #: A wrapped line: down from the row's last box, back along the gap, down into the next.
            x1, x2 = a.x + BOX_W // 2, b.x + BOX_W // 2
            y1, y2 = a.y + layout.box_h, b.y
            mid = y1 + GAP_Y // 2
            parts.append(f'<path class="link" d="M{x1},{y1} L{x1},{mid} L{x2},{mid} L{x2},{y2}" '
                         f'fill="none" marker-end="url(#graph-arrow)"/>')
            continue
        x1, y1 = a.x + BOX_W, a.y + layout.box_h // 2
        x2, y2 = b.x, b.y + layout.box_h // 2
        dx = (x2 - x1) // 2
        parts.append(f'<path class="link" '
                     f'd="M{x1},{y1} C{x1 + dx},{y1} {x2 - dx},{y2} {x2},{y2}" fill="none" '
                     f'marker-end="url(#graph-arrow)"/>')
    for b in layout.boxes:
        dash = ' stroke-dasharray="5 4"' if b.dashed else ""
        failed = ' data-failed="yes"' if any(m.failed for m in b.members) else ""
        #: A box links to its step's row when the page gave it one; a step whose index is
        #: not a number has no `#step-N` anchor to link to, so its box is drawn unlinked.
        mark = f' data-mark="{esc(b.mark)}"' if b.mark else ""
        mark += f' data-tone="{esc(b.tone)}"' if b.tone else ""
        opening, closing = (f'<a href="{esc(b.href)}"{failed}{mark}>', "</a>") if b.href else (
            f"<g{failed}{mark}>", "</g>")
        #: The name whole, on as many lines as it takes; under it the state as a chip, then the
        #: other state lines and the report's quoted words, each shortened with its whole text in
        #: its <title> and in the page's own table.
        names = _label_lines(b.label)
        top = b.y + 14 + LABEL_LINE_H - 4
        chip = ""
        below = top + (layout.label_lines - 1) * LABEL_LINE_H + 6
        if b.tags:
            words = b.tags[0]
            w = min(BOX_W - 20, round(CHIP_PAD * 2 + CHIP_CHAR * len(words)))
            chip = (f'<rect class="chip" x="{b.x + 10}" y="{below}" width="{w}" height="{CHIP_H}" '
                    f'rx="{CHIP_H // 2}"/><text class="chip" x="{b.x + 10 + CHIP_PAD}" '
                    f'y="{below + CHIP_H - 6}">{esc(_short(words, STATE_MAX))}</text>')
        after = below + (CHIP_H + 8 if layout.chip else 0) - 4
        lines = _drawn_lines(b.tags, b.quoted, layout.tag_lines)
        states = "".join(
            f'<text class="state"{' data-words="report"' if quoted else ""} x="{b.x + 10}" '
            f'y="{after + (i + 1) * TAG_LINE_H}">{esc(_short(text, STATE_WRAP) if quoted else text)}'
            f'{f"<title>{esc(text)}</title>" if quoted else ""}</text>'
            for i, (text, quoted) in enumerate(lines))
        title = b.label + "".join(f" · {tag}" for tag in b.tags)
        parts.append(
            f'{opening}'
            f'<rect class="node" x="{b.x}" y="{b.y}" width="{BOX_W}" height="{layout.box_h}" '
            f'rx="10"{dash}/><title>{esc(title)}</title>'
            + "".join(f'<text class="name" x="{b.x + 10}" y="{top + i * LABEL_LINE_H}">{esc(name)}</text>'
                      for i, name in enumerate(names))
            + f'{chip}{states}{closing}')
    parts.append("</svg>")
    return "".join(parts)


def table(layout: Layout, esc=escape) -> str:
    """The graph's text equivalent: every node and every recorded link, in order."""
    node_rows = "".join(
        f'<tr><td class="mono">{esc(instance_label(m.label or m.node_id))}</td>'
        f'<td>{esc(m.shown or m.name)}</td>'
        f'<td class="value">{m.index}</td></tr>'
        for b in layout.boxes for m in b.members)
    link_rows = "".join(
        f'<tr data-link="{n}"><td class="mono">{esc(instance_label(f))}</td>'
        f'<td class="mono">{esc(instance_label(t))}</td><td>'
        f'{"" if (f, t) in layout.recorded else escape(template("graph.link_outside"))}'
        '</td></tr>'
        for n, (f, t) in enumerate(sorted(layout.recorded + layout.outside), start=1))
    return (f'<table class="timeline" data-section="graph-nodes"><thead><tr>'
            f'<th>{escape(template("graph.col_node"))}</th>'
            f'<th>{escape(template("graph.col_stage"))}</th>'
            f'<th>{escape(template("graph.col_index"))}</th></tr></thead>'
            f'<tbody>{node_rows}</tbody></table>'
            f'<table class="timeline" data-section="graph-links"><thead><tr>'
            f'<th>{escape(template("graph.col_from"))}</th>'
            f'<th>{escape(template("graph.col_to"))}</th><th></th></tr></thead>'
            f'<tbody>{link_rows}</tbody></table>')


def _linked(href: str, inner: str, esc=escape) -> str:
    return f'<a href="{esc(href)}">{inner}</a>' if href else inner


def _shortened(text: str, esc=escape) -> str:
    """`text` escaped, each fingerprint in it shown by its first 12 hex characters: the page's own
    table, or the verifier's output on the same page, holds each whole."""
    out, at = [], 0
    for m in re.finditer(r"(sha256:)?([0-9a-f]{64})", text):
        out.append(esc(text[at:m.start()]) + esc((m.group(1) or "") + m.group(2)[:12] + "…"))
        at = m.end()
    return "".join(out) + esc(text[at:])


def _quoted(text: str, esc=escape) -> str:
    """A report's own words, quoted as they are, each fingerprint in them short."""
    return f'<q data-words="report">{_shortened(text, esc)}</q>'


def as_list(layout: Layout, esc=escape) -> str:
    """The same boxes as a list in reading order, for a screen too narrow for the drawing: each
    box's name (linked as in the drawing), its lines, and whether it reads the box before it, as
    its receipt records. Hidden unless a stylesheet shows it."""
    drawn = set(layout.links)
    order = sorted(layout.boxes, key=lambda b: (b.row, b.layer) if layout.linear else (b.index, b.key))
    items = []
    for prev, b in zip([None, *order], order):
        reads = prev is not None and (prev.key, b.key) in drawn
        lines = "".join(f'<span class="state">{_shortened(t, esc)}</span>' for t in b.tags) + "".join(
            f'<span class="state">{_quoted(q, esc)}</span>' for q in b.quoted)
        items.append(f'<li data-reads-previous="{"yes" if reads else "no"}"'
                     + (f' data-list-mark="{esc(b.mark)}"' if b.mark else "")
                     + (f' data-list-tone="{esc(b.tone)}"' if b.tone else "") + ">"
                     + _linked(b.href, esc(b.label), esc) + lines + "</li>")
    return f'<ol class="graph-list">{"".join(items)}</ol>'


def _folds(layout: Layout, esc=escape) -> str:
    """Each fold's members, failed attempts included, as a disclosure: no script."""
    out = []
    for b in layout.boxes:
        if len(b.members) < 2:
            continue
        items = "".join(
            f'<li>{_linked(m.href, esc(instance_label(m.label or m.node_id)), esc)}'
            f'{"".join(" · " + esc(tag) for tag in m.tags)}'
            f'{"".join(" · " + _quoted(q, esc) for q in m.quoted)}'
            f'{" — " + escape(template("graph.failed")) if m.failed else ""}</li>'
            for m in b.members)
        out.append(f'<details data-fold=""><summary>{esc(b.label)}</summary>'
                   f'<ul>{items}</ul></details>')
    return "".join(out)


def render(nodes, edges, *, recorded_order_href: str = "", heading: str = "",
           esc=escape, own_table: bool = True, recorded_order: bool = True,
           lead: str = "", region: str = "graph.region", wrap: int = 0,
           wrap_labels: bool = False, tag_lines: int = TAG_LINES) -> str:
    """The graph section: the drawing (or, past MAX_DRAWN, the notice), the folds, the note,
    the link to the recorded order, and "Show as table". `heading` is HTML, already escaped.
    `region` is the sentence key naming the drawing's scroll region (the comparison page's own).

    A page that already carries the nodes' table (item 3: the compare page's changes table, its
    "Show as table") passes `own_table=False`; a page whose order is not a run's recorded order
    (the comparison's order is the SDK's) passes `recorded_order=False`."""
    layout = lay_out(nodes, edges, wrap=wrap, wrap_labels=wrap_labels, tag_lines=tag_lines)
    #: `lead` (HTML, already escaped): a line the page puts above the drawing (the
    #: comparison a run page's marks come from).
    parts = ['<section data-section="graph">' + (f"<h2>{heading}</h2>" if heading else "")
             + lead]
    if layout.linear:
        parts.append(f'<p data-section="graph-linear">{escape(template("graph.linear"))}</p>')
    if len(layout.boxes) > MAX_DRAWN:
        parts.append(f'<p data-section="graph-too-large">'
                     f'{escape(sentence("graph.too_large", n=str(len(layout.boxes)),
                                       max=str(MAX_DRAWN)))}</p>'
                     + (table(layout, esc) if own_table else ""))
    else:
        #: A scroll region a keyboard can reach and a screen reader can name: the panel scrolls
        #: when the drawing is wider than it, and its fade and scrollbar say so (CSS).
        parts.append(f'<div class="graph-box" tabindex="0" role="region" '
                     f'aria-label="{escape(template(region))}">{svg(layout, esc)}'
                     f'{as_list(layout, esc)}</div>')
        parts.append(_folds(layout, esc))
        if own_table:
            parts.append(f'<details data-section="graph-table"><summary>'
                         f'{escape(template("graph.table"))}</summary>'
                         f'{table(layout, esc)}</details>')
    if layout.outside:
        listed = ", ".join(f"{f} → {t}" for f, t in layout.outside)  # escaped whole, below
        #: The singular for exactly one such link, the plural for more.
        said = (sentence("graph.outside_one", link=listed) if len(layout.outside) == 1
                else sentence("graph.outside", n=str(len(layout.outside)), links=listed))
        parts.append(f'<p data-section="graph-outside">{esc(said)}</p>')
    parts.append(f'<p data-section="graph-note">{escape(template("graph.note"))}</p>')
    #: "Recorded order" goes to where the recorded order starts on the page -- the page names
    #: it (the first step's row); with nothing to point at it is its words alone.
    if recorded_order:
        words = escape(template("graph.recorded_order"))
        parts.append(f"<p>{_linked(recorded_order_href, words, esc)}</p>")
    parts.append("</section>")
    return "".join(parts)
