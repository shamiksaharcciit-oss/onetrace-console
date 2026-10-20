"""Two linked views of a run page and of a comparison page: "What changed" and "Proof".

"What changed" is the page at its own address: what the reader came for -- the verdicts, the first
difference and what is recorded about it, the settings that changed, the outputs and the text diff,
the no-recorded-cause sentence, and how to repeat it. "Proof" is a sibling file: the checks behind
it -- every check row, signatures and trust, times and anchoring, approvals, completeness, each
fingerprint in full, and the SDK's own report as it wrote it. Two plain links at the top of both
are the tabs: no script, so they work in the served console, the demo and a static export alike.

Each page is split after it is drawn, by its top-level parts, so every part of today's page is on
exactly one of the two views (the page's own head and foot, which carry no finding, on both).

"What changed" always opens with one line saying what the records establish, from the console's own
reading of rung 1 (`records`), with a link to "Proof". Where a run contradicts its record or could
not be checked -- or, for a comparison, either run does -- that line is red and says so first, and
the step-by-step verdicts are not on "What changed": they are on "Proof", under a line that says
why they are there.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser

WHAT, PROOF = "What changed", "Proof"
#: The run page's "Proof" view, a sibling of its page.
RUN_PROOF = "proof.html"
#: Where each top-level part of a run page goes, by its `data-section`: on both views (the page's
#: own head and foot), on "Proof", or among the step-by-step verdicts (on "What changed", or on
#: "Proof" where they are withheld). Any other part is on "What changed".
#: The preview-format label, where a page shows a preview run, is the page's own too: every view
#: of a page that shows such a run carries it (`preview.label`).
RUN_BOTH = {"run-head", "limit", "also", "preview"}
#: The checks behind the run's verdicts -- every check row, and the authorization policy -- are on
#: "Proof". The evidence ladder is the run's verdicts, one row per rung: on "What changed" where
#: the records agree, and withheld with the rest of the step-by-step verdicts where they don't.
RUN_PROOF_PARTS = {"checked", "policy"}
RUN_STEPS = {"ladder", "graph", "timeline", "changed"}
#: Read from the record's contents, so withheld with the steps where they are: the answer trail,
#: the case (its times and its steps) and a declined step. "What could be re-checked" stays: it
#: says how to check the record again.
RUN_READ_FROM = {"strip", "case", "declined"}
#: The answer trail's command to repeat the check is the one line of the trail a red run's "What
#: changed" keeps, with "What could be re-checked": it says nothing read from the record's
#: contents. The copy is marked, so it is told apart from the trail, which stays whole on "Proof".
FROM_TRAIL = 'data-from="trail"'
#: A comparison page's parts: the same three kinds. The localize report's own parts, from its
#: envelope on, are on "Proof" with the SDK's reports as it wrote them.
DIFF_BOTH = {"pair", "limit", "preview"}
DIFF_PROOF_PARTS = {"stage-table", "sdk", "localize-envelope", "localize-repeat"}
DIFF_STEPS = {"first-difference", "graph", "settings-changed", "text-diff", "localized"}

#: The integrity line's words. Each state as `records` defines it, said of this run.
RUN_SAID = {
    "yes": "Records agree: this console's check held, with the run's output files required.",
    "no": "Contradicts its record: this console's check, with the run's output files required, failed.",
    "couldnt-check": "Couldn't check: this console's check could not settle whether the records agree.",
    "not-checked": "Not checked: this console's check did not look at what this needs.",
    "no-verdict": "No verdict recorded: this console's check has not reached this run.",
}
#: Said after the line where the step-by-step verdicts are withheld: of a run, by its state; of a
#: pair, once.
RUN_WITHHELD = {
    "no": "The step-by-step comparison is not shown on this view: the record does not hold up.",
    "couldnt-check": "The step-by-step comparison is not shown on this view: the record could not be checked.",
}
WITHHELD = RUN_WITHHELD["no"]
WITHHELD_PAIR = "Their step-by-step verdicts are not shown on this view."
#: The heading over a run's withheld rows on "Proof".
RUN_ROWS_FROM = {
    "no": "These rows come from a record that does not hold up.",
    "couldnt-check": "These rows come from a record that could not be checked.",
}
#: In the run head on "What changed", where what it reads from the record is withheld.
RUN_NOT_SHOWN = {
    "no": "Not shown: this record does not hold up.",
    "couldnt-check": "Not shown: this record could not be checked.",
}
#: The link's words, after the line.
TO_PROOF = {False: "Every check behind this is on Proof", True: "Proof says why"}
#: At the top of "Proof" where the verdicts were withheld from "What changed".
WITHHELD_HERE = "The step-by-step verdicts are here, not on What changed: {said}"
#: The two states that make the line red and withhold the verdicts.
RED = ("no", "couldnt-check")

VIEWS_CSS = """
:is(.shell .page,.cp) nav[data-section=views]{display:flex;gap:4px 24px;flex-wrap:wrap;margin:0 0 12px;
  border-bottom:1px solid var(--line)}
:is(.shell .page,.cp) nav[data-section=views] a{padding:8px 2px;text-decoration:none;color:var(--ink-muted);
  border-bottom:2px solid transparent}
:is(.shell .page,.cp) nav[data-section=views] a[aria-current=page]{color:var(--ink);border-bottom-color:var(--accent)}
:is(.shell .page,.cp) [data-section=integrity]{margin:0 0 12px;padding:10px 14px;border:1px solid var(--line);
  border-radius:8px;background:var(--surface);color:var(--ink)}
:is(.shell .page,.cp) [data-section=integrity][data-tone=ok]{background:var(--ok-bg);color:var(--ok-ink)}
:is(.shell .page,.cp) [data-section=integrity][data-tone=bad]{background:var(--bad-bg);color:var(--bad-ink);font-weight:600}
:is(.shell .page,.cp) h2[data-section=withheld]{margin:0 0 8px;color:var(--bad-ink)}
"""

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
         "track", "wbr"}


@dataclass(frozen=True)
class Part:
    start: int
    end: int
    tag: str
    attrs: dict


class _Parts(HTMLParser):
    """The top-level children of the first element `is_container` accepts, by offset."""

    def __init__(self, text: str, is_container):
        super().__init__(convert_charrefs=False)
        self.text, self.is_container = text, is_container
        self.lines = [0]
        for line in text.splitlines(keepends=True):
            self.lines.append(self.lines[-1] + len(line))
        self.depth, self.container, self.open = 0, None, None
        self.inner = None
        self.parts: list[Part] = []

    def _at(self) -> int:
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        at = self._at()
        a = dict(attrs)
        if self.container is None and self.is_container(tag, a):
            self.container = self.depth
            self.inner = at + len(self.get_starttag_text())
        elif self.container is not None and self.depth == self.container + 1:
            if tag in _VOID:
                self.parts.append(Part(at, at + len(self.get_starttag_text()), tag, a))
            else:
                self.open = (at, tag, a)
        if tag not in _VOID:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        at = self._at()
        if self.container is not None and self.depth == self.container + 1:
            self.parts.append(Part(at, at + len(self.get_starttag_text()), tag, dict(attrs)))

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        self.depth -= 1
        if self.container is not None and self.depth == self.container + 1 and self.open:
            at = self._at()
            end = self.text.index(">", at) + 1
            start, t, a = self.open
            self.parts.append(Part(start, end, t, a))
            self.open = None


def parts(page: str, is_container) -> tuple[int, list[Part]]:
    """(where the container's content starts, its top-level children in order)."""
    p = _Parts(page, is_container)
    p.feed(page)
    p.close()
    if p.inner is None:
        raise ValueError("the page has no container to split")
    return p.inner, p.parts


def key(part: Part) -> str:
    """A part's name: its `data-section`, else what marks it (an anchor's id, a strip's state, a
    report's layer), else its tag."""
    a = part.attrs
    if a.get("data-section"):
        return a["data-section"]
    if a.get("data-preview"):
        return "preview"
    if "strip" in (a.get("class") or "").split():
        return "strip"
    if part.tag == "span" and a.get("id"):
        return f"#{a['id']}"
    if a.get("data-layer"):
        return f"layer-{a['data-layer']}"
    return part.tag


def _places_run(items: list[Part], red: bool) -> list[str]:
    out = []
    for part in items:
        k = key(part)
        if k in RUN_BOTH or part.tag == "footer":
            out.append("both")
        elif k in RUN_PROOF_PARTS or ((k in RUN_STEPS or k in RUN_READ_FROM) and red):
            out.append("proof")
        else:
            out.append("what")
    #: An empty anchor goes where the part after it goes.
    for i, part in enumerate(items):
        if key(part).startswith("#") and i + 1 < len(items):
            out[i] = out[i + 1]
    return out


def _places_diff(items: list[Part], red: bool) -> list[str]:
    out, localize = [], False
    #: The page's title, wherever it falls (after an incidents block, where the page has one).
    title = next((i for i, part in enumerate(items) if part.tag == "h1"), None)
    for i, part in enumerate(items):
        k = key(part)
        localize = localize or k == "localize-envelope"
        if part.tag == "footer" or k in DIFF_BOTH or i == title:
            out.append("both")
        elif localize and k != "same-change":
            out.append("proof")
        elif k in DIFF_PROOF_PARTS or k.startswith("layer-") or (k in DIFF_STEPS and red):
            out.append("proof")
        else:
            out.append("what")
        if k == "same-change":
            localize = False
    #: A heading goes with the part after it; a command's `<pre>` with the line before it.
    for i, part in enumerate(items):
        if part.tag in ("h2", "h3") and i + 1 < len(items):
            out[i] = out[i + 1]
        elif part.tag == "pre" and not part.attrs and i:
            out[i] = out[i - 1]
    return out


def _tabs(what_href: str, proof_href: str, current: str) -> str:
    links = []
    for words, href in ((WHAT, what_href), (PROOF, proof_href)):
        mark = ' aria-current="page"' if words == current else ""
        links.append(f'<a href="{escape(href, quote=True)}"{mark}>{escape(words)}</a>')
    return f'<nav data-section="views" aria-label="This page\'s views">{"".join(links)}</nav>'


def _line(said: str, red: bool, proof_href: str, tone: str, withheld: str) -> str:
    words = said + (f" {withheld}" if red else "")
    return (f'<p data-section="integrity" data-tone="{tone}">{escape(words)} '
            f'<a href="{escape(proof_href, quote=True)}">{escape(TO_PROOF[red])}</a></p>')


def _marked(html: str, mark: str) -> list[tuple[int, int]]:
    """(start, end) of each element whose start tag carries `mark`, its own tag's nesting counted."""
    out = []
    for m in re.finditer(r"<([a-z0-9]+)\b[^>]*" + re.escape(mark) + r"[^>]*>", html):
        tag, depth, at = m.group(1), 1, m.end()
        for t in re.finditer(rf"<(/?){tag}\b[^>]*>", html[at:]):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                out.append((m.start(), at + t.end()))
                break
        else:
            raise ValueError(f"an unclosed <{tag}> marked {mark}")
    return out


def _withheld_head(head: str, state: str, proof_href: str) -> str:
    """The run head on a red run's "What changed": without what it reads from the record, and one
    line, before its tabs, saying so and linking to "Proof"."""
    from onetrace_console.run_head import FROM_CONTENTS
    for start, end in reversed(_marked(head, FROM_CONTENTS.strip())):
        head = head[:start] + head[end:]
    tabs = '<nav class="tabs"'
    if head.count(tabs) != 1:
        raise ValueError("the run head does not carry exactly one row of tabs")
    line = (f'<p class="sub" data-withheld="true">{escape(RUN_NOT_SHOWN[state])} '
            f'<a href="{escape(proof_href, quote=True)}">{escape(TO_PROOF[True])}</a></p>')
    return head.replace(tabs, line + tabs, 1)


def _repeat(page: str, items: list[Part]) -> str:
    """The answer trail's command to repeat the check, marked as its copy; "" where the trail has none."""
    from onetrace_console.viewer.sentences import template
    trail = next((page[p.start:p.end] for p in items if key(p) == "strip"), "")
    found = re.search(r'<details data-layer="4"><summary>' + re.escape(escape(template("command.verify")))
                      + r"</summary>.*?</details>", trail, re.S)
    return found.group(0).replace("<details ", f"<details {FROM_TRAIL} ", 1) if found else ""


def _with_repeat(reproduce: str, command: str) -> str:
    """"What could be re-checked" with the trail's command at its end."""
    if not command:
        return reproduce
    if not reproduce.endswith("</section>"):
        raise ValueError("What could be re-checked does not end its own section")
    return reproduce[:-len("</section>")] + command + "</section>"


def split(page: str, kind: str, what_href: str, proof_href: str, said: str, state: str,
          withheld: str = WITHHELD) -> tuple[str, str]:
    """(the "What changed" view, the "Proof" view) of a drawn page. `kind` is "run" or "diff";
    `said` is the integrity line's words and `state` the rung 1 state it was read from (for a pair,
    the worse of the two), which makes the line red and withholds the step-by-step verdicts."""
    red = state in RED
    rows_from = ""
    if kind == "run":
        inner, items = parts(page, lambda tag, a: tag == "main" and "page" in (a.get("class") or "").split())
        places = _places_run(items, red)
        command = _repeat(page, items) if red else ""
        if red:
            withheld = RUN_WITHHELD[state]
            rows_from = (f'<h2 data-section="withheld" data-tone="bad">'
                         f'{escape(RUN_ROWS_FROM[state])}</h2>')
    else:
        inner, items = parts(page, lambda tag, a: tag == "div" and "cp" in (a.get("class") or "").split())
        places = _places_diff(items, red)
        command = ""
    tone = "bad" if red else ("ok" if state == "yes" else "neu")
    #: The tabs and the line go right after the page's own head: the run's head, or the pair line.
    after = next((i for i, part in enumerate(items) if key(part) in ("run-head", "pair")), None)
    views = {}
    for view, keep in ((WHAT, ("what", "both")), (PROOF, ("proof", "both"))):
        head = _tabs(what_href, proof_href, view)
        if view == WHAT:
            head += _line(said, red, proof_href, tone, withheld)
        elif red:
            head += (rows_from + f'<p data-section="integrity" data-tone="bad">'
                     f'{escape(WITHHELD_HERE.format(said=said))}</p>')
        out, at = [page[:inner]], inner
        if after is None:
            out.append(head)
        for i, (part, place) in enumerate(zip(items, places)):
            #: What lies between two parts (white space, as drawn) is on both views.
            out.append(page[at:part.start])
            if place in keep and view == WHAT and red and kind == "run" and key(part) == "run-head":
                out.append(_withheld_head(page[part.start:part.end], state, proof_href))
            elif place in keep and view == WHAT and command and key(part) == "reproduce":
                out.append(_with_repeat(page[part.start:part.end], command))
            elif place in keep:
                out.append(page[part.start:part.end])
            if i == after:
                out.append(head)
            at = part.end
        out.append(page[at:])
        views[view] = "".join(out)
    return (_across(views[WHAT], views[PROOF], proof_href),
            _across(views[PROOF], views[WHAT], what_href))


def _across(view: str, other: str, other_href: str) -> str:
    """`view` with each in-page link (`#id`) whose target is on the other view, not this one,
    pointed at the other view's file."""
    def ids(html: str) -> set[str]:
        return set(re.findall(r'\bid="([^"]+)"', html))
    here, there = ids(view), ids(other)
    return re.sub(r'href="#([^"]+)"',
                  lambda m: (f'href="{escape(other_href, quote=True)}#{m.group(1)}"'
                             if m.group(1) not in here and m.group(1) in there else m.group(0)), view)


def retarget(page: str, what: str, proof: str, what_name: str, proof_name: str) -> str:
    """Another page's links into the run page (`<what_name>#id`) pointed at the view that holds
    the id: where it went to "Proof", at that."""
    def ids(html: str) -> set[str]:
        return set(re.findall(r'\bid="([^"]+)"', html))
    on_what, on_proof = ids(what), ids(proof)
    return re.sub(rf'href="{re.escape(what_name)}#([^"]+)"',
                  lambda m: (f'href="{proof_name}#{m.group(1)}"'
                             if m.group(1) not in on_what and m.group(1) in on_proof else m.group(0)), page)


def run_said(run, store) -> tuple[str, str]:
    """(the integrity line's words, the rung 1 state) for a run, as `records` reads it."""
    from onetrace_console import records
    state = records.state(run, store)
    why = records.why(run, store)
    said = RUN_SAID[state]
    return (said[:-1] + f" ({why})." if why else said), state


def pair_said(comparison, store) -> tuple[str, str]:
    """(the integrity line's words, the worse of the two runs' rung 1 states) for a comparison: the
    comparison page's own sentence of what the two records establish."""
    from onetrace_console import records
    from onetrace_console.render import _held, records_words
    states = []
    for k in (comparison.run_a, comparison.run_b):
        run = _held(store, k)
        states.append(records.state(run, store) if run is not None else records.NOT_CHECKED)
    worst = next((s for s in RED if s in states), "yes" if all(s == "yes" for s in states) else "not-checked")
    return records_words(comparison, store), worst


def proof_name(name: str) -> str:
    """The "Proof" sibling of a page's file name: `case.html` -> `proof.html`, `<key>.html` ->
    `<key>-proof.html`."""
    if name == "case.html":
        return RUN_PROOF
    return re.sub(r"\.html$", "-proof.html", name)
