"""Render the answer view and the case view as self-contained HTML. Decides nothing.

WHAT THIS MODULE MAY REACH
--------------------------
`viewer.model` (what to show), `viewer.sentences` (the table's labels), `viewer.tokens`
(the palette) and `viewer.slot` (the fingerprint slot's text). It imports no hashing module
and neither `viewer.record` nor `viewer.report`: every value on the page arrives through
the model. `viewer/tests/test_structure.py` asserts this, so "never re-derive for display"
is a property of what this file can reach.

THE FENCE (019 §0, §1.3; 021 §3 ruling 1)
------------------------------------------
Static HTML, inline CSS, one small inline script, no external asset of any kind: no link,
no font fetch, no image, no URL. The page opens from disk with the network off.

NO BUTTONS (spec §2.1; 021 §3 ruling 4)
---------------------------------------
Layers 2–4 are native `<details>` elements: the page is the same page with JavaScript off,
only less convenient. The one script opens every layer before printing, so a printout
carries the whole record rather than its summary.

WHOSE WORDS
-----------
A `Text` from the model renders by its source: the page's own words as text, the record's
and the check's words as marked quotations (`data-words`), counts and times as values. The
vocabulary rule (019 §4) is tested over the page's own words only; a quotation is not ours
to translate.
"""
from __future__ import annotations

import contextvars
import re
from html import escape as _html_escape

from onetrace_console.viewer.model import (NAME_CAP, TEXT_CAP, CheckCount, Detail, Item, Line, PageModel, Rung,
                          StepView, Text, VerbSaid, line, name_shown)
from onetrace_console.viewer.graph import render as graph_render
from onetrace_console.viewer.sentences import template
from onetrace_console.viewer.slot import SLOT, STANDALONE_CHECK
from onetrace_console.viewer.tokens import root_css, scale_css, theme_css

CSS = """
*{box-sizing:border-box}
html,body{margin:0;background:var(--page);color:var(--ink);font-family:var(--font-sans);
  font-size:var(--fs-body);line-height:1.55}
.page{max-width:920px;margin:0 auto;padding:28px 20px 40px}
header.top{display:flex;justify-content:space-between;align-items:baseline;gap:16px;
  border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:18px;flex-wrap:wrap}
.kind{color:var(--ink-muted);text-transform:uppercase;letter-spacing:.12em;font-size:12px;
  font-weight:600}
h1{font-size:var(--fs-h1);margin:2px 0 0;font-weight:600}
.meta{font-family:var(--font-mono);font-size:12px;color:var(--ink-muted);text-align:right}
.sample{border:1px dashed var(--line);color:var(--ink-muted);padding:8px 12px;margin:0 0 16px;
  font-size:13px;border-radius:6px}
.strip{border:1px solid var(--line);background:var(--surface);border-radius:8px;
  padding:14px 16px;margin-bottom:22px}
.strip.ok{border-color:var(--line);background:var(--ok-bg)}
.strip.bad{border-color:var(--line);background:var(--bad-bg)}
.strip .lead{font-size:15px;font-weight:600}
.strip.ok .lead{color:var(--ok-ink)} .strip.bad .lead{color:var(--bad-ink)}
.strip .beside{color:var(--ink);margin-top:6px}
section{margin:0 0 24px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-muted);
  font-weight:600;margin:0 0 10px}
.card{background:var(--surface);border:1px solid var(--line-soft);border-radius:8px;
  padding:12px 14px;margin:0 0 10px}
.card h3{font-size:15px;margin:0 0 4px;font-weight:600}
.card .step{color:var(--ink-faint);font-family:var(--font-mono);font-size:12px}
.card p{margin:4px 0}
.grid{display:grid;grid-template-columns:170px 1fr;gap:4px 12px;font-size:13px;margin:6px 0}
.grid .k{color:var(--ink-faint);text-transform:uppercase;font-size:12px;letter-spacing:.06em;
  padding-top:2px}
.mono,.value,code,pre{font-family:var(--font-mono);font-variant-numeric:tabular-nums}
.fp{font-family:var(--font-mono);font-size:12px;overflow-wrap:anywhere}
q[data-words]{quotes:"\\201C" "\\201D";color:var(--ink);font-style:italic}
q[data-words="check"]{font-style:normal;font-family:var(--font-mono);font-size:13px}
details{margin:6px 0}
summary{cursor:pointer;color:var(--ink-muted);font-size:13px}
pre{background:var(--surface-sunk);border:1px solid var(--line-soft);border-radius:6px;
  padding:10px;overflow-x:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;
  margin:6px 0}
ul.plain{list-style:none;padding:0;margin:0}
ul.plain li{margin:0 0 8px}
table.timeline{width:100%;border-collapse:collapse;font-size:13px}
table.timeline th{color:var(--ink-faint);text-align:left;font-weight:500;font-size:12px;
  text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--line);
  padding:6px 8px}
table.timeline td{border-bottom:1px solid var(--line-soft);padding:8px;vertical-align:top}
.said{margin:0 0 10px}
.said .step{color:var(--ink-faint);font-family:var(--font-mono);font-size:12px}
.limit{border-top:1px solid var(--line);padding-top:14px;font-style:italic}
footer{border-top:1px solid var(--line);margin-top:28px;padding-top:12px;color:var(--ink-muted);
  font-size:13px}
.graph-box{overflow-x:auto;margin:0 0 8px}
.graph-list{display:none}
.declined{border:1px solid var(--accent);color:var(--ink);border-radius:6px;padding:8px 12px;margin:0 0 12px}
details.fingerprint{display:inline}
details.fingerprint>summary{display:inline;cursor:pointer;list-style:none}
details.fingerprint>summary::-webkit-details-marker{display:none}
details.fingerprint>span{display:block;overflow-wrap:anywhere}
.last-failed{background:var(--cc-bg);color:var(--cc-ink);border-radius:6px;padding:8px 12px;
  margin:10px 0;font-weight:600}
.graph-box::-webkit-scrollbar{height:12px}
.graph-box::-webkit-scrollbar-track{background:var(--surface-sunk);border-radius:6px}
.graph-box::-webkit-scrollbar-thumb{background:var(--line-strong);border-radius:6px}
@supports not selector(::-webkit-scrollbar){.graph-box{scrollbar-width:auto;
  scrollbar-color:var(--line-strong) var(--surface-sunk)}}
.graph-box:focus-visible{outline:none}
/* A long unbroken value -- a digest, a key -- wraps at a narrow width rather than widening the
   page; it breaks only where it would overflow, and copies as the same characters. */
.mono,q[data-words]{overflow-wrap:break-word}
.scroll-x{overflow-x:auto;max-width:100%}
.scroll-x::-webkit-scrollbar{height:12px}
.scroll-x::-webkit-scrollbar-track{background:var(--surface-sunk);border-radius:6px}
.scroll-x::-webkit-scrollbar-thumb{background:var(--line-strong);border-radius:6px}
@supports not selector(::-webkit-scrollbar){.scroll-x{scrollbar-width:auto;
  scrollbar-color:var(--line-strong) var(--surface-sunk)}}
.scroll-x:focus-visible{outline:none}
.scroll-frame:has(>.scroll-x:focus-visible){outline:2px solid var(--accent);outline-offset:2px}
[data-section=graph]:has(>.graph-box:focus-visible){outline:2px solid var(--accent);
  outline-offset:2px}
/* The panel's focus ring is drawn on its section: the fade's mask clips whatever the
   panel paints outside its own box, its outline included. */
@property --graph-fade-start{syntax:'<length>';inherits:false;initial-value:0px}
@property --graph-fade-end{syntax:'<length>';inherits:false;initial-value:0px}
@keyframes graph-box-fade{from{--graph-fade-start:0px;--graph-fade-end:48px}
  to{--graph-fade-start:48px;--graph-fade-end:0px}}
@supports (animation-timeline:scroll()){.graph-box,.scroll-x{-webkit-mask-image:linear-gradient(to right,
  transparent,currentColor var(--graph-fade-start),currentColor calc(100% - var(--graph-fade-end)),transparent),
  linear-gradient(currentColor,currentColor);mask-image:linear-gradient(to right,transparent,
  currentColor var(--graph-fade-start),currentColor calc(100% - var(--graph-fade-end)),transparent),
  linear-gradient(currentColor,currentColor);-webkit-mask-size:100% calc(100% - 12px),100% 12px;
  mask-size:100% calc(100% - 12px),100% 12px;-webkit-mask-position:top,bottom;
  mask-position:top,bottom;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;
  animation:graph-box-fade linear both;animation-timeline:scroll(self inline)}}
svg.graph{shape-rendering:geometricPrecision;text-rendering:geometricPrecision}
svg.graph .node{fill:var(--surface);stroke:var(--line-node);stroke-width:1}
svg.graph .link{stroke:var(--ink-faint);stroke-width:1.5}
svg.graph marker path{fill:var(--ink-faint)}
svg.graph text{fill:var(--ink);font-family:var(--font-mono);font-size:12px}
svg.graph text.name{font-size:14px;font-weight:500}
svg.graph text.state{fill:var(--ink-muted)}
svg.graph rect.chip{fill:var(--neu-bg)}
svg.graph text.chip{fill:var(--neu-ink);font-family:var(--font-sans);font-weight:600}
@media print{details>summary{display:none}}
"""

#: The console's frame -- a shell holding the navigation beside the page. Only
#: the console's stylesheet (/static/console.css) carries these rules; the free file never has a
#: frame, so its embedded stylesheet does not either.
#: Board 1's navigation and boards 2 and 3's pages, for pages drawn inside the
#: console's frame only (the free file never carries FRAME_CSS): the nav at board 1's sizes; the
#: page at the board's width and padding, not the free file's 920px column; each section a panel;
#: the tables as board 1's. Each rung's state is a chip of the console's one chip family
#: (`frame.CHIP_CSS`), coloured by its state (`tones.RUNG`). The
#: brand's 20px is a token, `--nav-brand-size`, defined once on the frame's navigation:
#: the skin's own block is the sealed v1, which the viewer does not edit.
#: Board 1's 15px headings stay a literal, as accepted.
FRAME_CSS = """
.shell{display:flex;min-height:100vh}
.shell>main{flex:1 1 auto;min-width:0}
nav.frame{--nav-brand-size:20px;flex:0 0 var(--nav-width);background:var(--nav-bg);
  color:var(--nav-ink);font-size:var(--fs-nav);padding:20px 14px;display:flex;
  flex-direction:column;gap:4px}
nav.frame .brand{color:var(--nav-on-ink);font-weight:600;font-size:var(--nav-brand-size);
  padding:0 14px 18px}
nav.frame a{color:var(--nav-ink);text-decoration:none;display:block;padding:9px 14px;
  border-radius:var(--r-ctl)}
nav.frame a[aria-current]{background:var(--nav-on-bg);color:var(--nav-on-ink)}
nav.frame footer{margin-top:auto;border:0;padding:16px 14px 0;color:var(--nav-ink-faint);
  font-size:var(--fs-small)}
.shell .page{max-width:none;margin:0;padding:26px 36px}
.shell .page a{color:var(--accent)}
.shell .page h2{font-size:15px;font-weight:600;color:var(--ink);text-transform:none;
  letter-spacing:0;margin:0 0 8px}
.shell .page>section:not(.strip){background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-card);padding:14px 18px;margin:0 0 16px}
.shell .page table.timeline th{font-size:var(--fs-small);color:var(--ink-muted);font-weight:500;
  text-transform:none;letter-spacing:0;padding:10px 12px;border-bottom:1px solid var(--line)}
.shell .page table.timeline td{font-size:var(--fs-body);padding:11px 12px;
  border-bottom:1px solid var(--line-soft)}
.shell .page table.timeline tr:last-child td{border-bottom:none}
@media (max-width:760px){.shell{flex-direction:column}nav.frame{flex-basis:auto}}
@media print{nav.frame{display:none}}
"""

#: Each rung state's chip colour is not decided here: `onetrace_console.tones` holds the one rule
#: for every page, and `frame.CHIP_CSS` draws it. The chip's words carry the state; the colour
#: never says more.

#: The marker a framed page's nav holds; the console's server puts the navigation and the footer
#: in its place when it serves the page, since only it knows the session and its extensions.
FRAME_NAV = "<!--frame-nav-->"

#: The stylesheet a framed page links, or None for the free file. A context variable, as
#: _RECORD_HREF is, so pages drawn at once on different threads never take each other's.
_FRAME: contextvars.ContextVar[str | None] = contextvars.ContextVar("frame", default=None)


class framed:
    """`with framed("/static/console.css"):` -- pages drawn inside the block link that stylesheet
    and sit in the console's frame (10-01cl §3). Outside it, every page is the free file."""

    def __init__(self, stylesheet: str):
        self.stylesheet = stylesheet

    def __enter__(self):
        self._token = _FRAME.set(self.stylesheet)
        return self

    def __exit__(self, *exc):
        _FRAME.reset(self._token)
        return False


def _body(view: str, body: str) -> str:
    """`<main>` for a page, inside the console's frame when one was asked for."""
    main = f'<main class="page" data-view="{view}">{body}</main>'
    if _FRAME.get() is None:
        return f"<body>\n{main}\n"
    return f'<body>\n<div class="shell"><nav class="frame" data-frame>{FRAME_NAV}</nav>{main}</div>\n'


PRINT_SCRIPT = ("<script>addEventListener('beforeprint',function(){"
                "document.querySelectorAll('details').forEach(function(d){d.open=true})})"
                "</script>")


# -------------------------------------------------------------------------- primitives

#: The characters a record's own words may not bring onto a page as
#: they are -- C0 and C1 controls, the bidirectional controls, lone surrogates. A page shows each
#: visibly escaped as \uXXXX; everything else as stored.
_UNSHOWN = re.compile("[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069\ud800-\udfff]")


def display(text: str, *, lines: bool = False) -> str:
    """`text` as a page shows it, with `_UNSHOWN` characters escaped as \\uXXXX. `lines=True`
    keeps line breaks and tabs, for the layers that show a file or an output as written.

    For a word (`lines=False`) the escaping is one-to-one: a backslash
    already in it is shown doubled, so the six characters `\\u000d` written in a record and a raw
    CR no longer draw alike -- the ambiguity behind NB2-a. The verbatim layers (`lines=True`: a
    receipt's own JSON, the verifier's own output) are left as written; JSON cannot hold a raw
    control inside a string, so they are not ambiguous."""
    def one(m: re.Match) -> str:
        c = m.group(0)
        return c if lines and c in "\n\r\t" else f"\\u{ord(c):04x}"
    text = str(text)
    if not lines:
        text = text.replace("\\", "\\\\")
    return _UNSHOWN.sub(one, text)


def escape(text: str, quote: bool = True) -> str:
    """The page's one escape: HTML, and a record's words shown by `display` (NEW-11)."""
    return _html_escape(display(text), quote=quote)


def _escape_rows(text: str) -> str:
    """For a layer of the verifier's rows -- its output, a step's findings: `_escape_lines`, with
    each row longer than NAME_CAP drawn as its first NAME_CAP characters and the same marker as a
    record word. A row quotes the record's words, and 100 names of 50,000
    characters wrote 24.9 MB of run pages. The whole row stays in the check report the run keeps."""
    rows = []
    for row in str(text).split("\n"):
        if len(row) > NAME_CAP:
            row = row[:NAME_CAP] + " " + template("name.more").format(n=str(len(row) - NAME_CAP))
        rows.append(row)
    return _escape_lines("\n".join(rows))


def _escape_word_text(text: str) -> str:
    """A whole output drawn as one word (30bv §3.3): every control character and line break
    escaped one-to-one, a backslash doubled first, at most TEXT_CAP characters of it."""
    text = str(text)
    if len(text) <= TEXT_CAP:
        return _html_escape(display(text))
    return _html_escape(display(text[:TEXT_CAP])) + " " + _t("text.more", n=str(len(text) - TEXT_CAP))


def _escape_lines(text: str) -> str:
    """For the verbatim layers -- a receipt's bytes, the check's output -- keeping line breaks,
    and drawing at most TEXT_CAP characters of them."""
    text = str(text)
    if len(text) <= TEXT_CAP:
        return _html_escape(display(text, lines=True))
    return (_html_escape(display(text[:TEXT_CAP], lines=True)) + "\n"
            + _t("text.more", n=str(len(text) - TEXT_CAP)))


#: A fingerprint as the record writes it: `sha256:` and 64 hex characters, or the 64 alone.
_FINGERPRINT = re.compile(r"(sha256:)?([0-9a-f]{64})")
#: How many hex characters of a fingerprint a page's text and tables show.
FINGERPRINT_SHOWN = 12


def fingerprint_html(value, *, words: str = "") -> str:
    """A fingerprint as a page's text and tables show it: its first FINGERPRINT_SHOWN hex
    characters, then the whole value as plain, selectable text in a closed Details beside it --
    nothing to press but the fold, no script. `words` marks whose words it is (`data-words`).
    A value that is not a fingerprint is quoted as recorded. The record's own words, in the
    as-written block, are never shortened."""
    text = str(value)
    m = _FINGERPRINT.fullmatch(text)
    marked = f' data-words="{escape(words)}"' if words else ""
    if not m:
        return f"{_named(text)}{_rest(text)}"
    short = (m.group(1) or "") + m.group(2)[:FINGERPRINT_SHOWN] + "…"
    return (f'<details class="fingerprint"{marked}><summary class="mono">{escape(short)}</summary>'
            f'<span class="mono" data-fingerprint="whole">{escape(text)}</span></details>')


def shortened_in_text(text) -> tuple[str, str]:
    """Running text -- a report's words, say -- escaped as the page escapes it, each fingerprint in
    it shown short; and, apart, a closed Details holding each one whole, for the caller to put
    after the text (a fold cannot sit inside a quotation). ("", "") parts where there is none."""
    text, out, wholes, at = str(text), [], [], 0
    for m in _FINGERPRINT.finditer(text):
        short = (m.group(1) or "") + m.group(2)[:FINGERPRINT_SHOWN] + "…"
        out.append(escape(text[at:m.start()]) + f'<span class="mono">{escape(short)}</span>')
        wholes.append(m.group(0))
        at = m.end()
    inline = "".join(out) + escape(text[at:])
    if not wholes:
        return inline, ""
    return inline, ('<details class="fingerprint"><summary>' + escape(template("fingerprint.whole"))
                    + "</summary>" + "".join(f'<span class="mono" data-fingerprint="whole">{escape(w)}</span>'
                                             for w in dict.fromkeys(wholes)) + "</details>")


def fingerprints_in_text(text) -> str:
    """`shortened_in_text`'s two parts together, for a place a fold may follow the text in."""
    inline, folded = shortened_in_text(text)
    return inline + folded


def _t(key: str, **values: str) -> str:
    return escape(template(key).format(**values))


def _when(started: str, ended: str) -> str:
    """A step's start and end as every page shows a time, the date said once. A value that does
    not read as a time is quoted as recorded."""
    from onetrace_console.words import _instant, span_html
    if _instant(started) is None or _instant(ended) is None:
        return f"{_named(started)}{_rest(started)} → {_named(ended)}{_rest(ended)}"
    return span_html(started, ended)


def _ran(case_ran: str) -> str:
    """A run's "started → ended", as `_when` shows it; quoted as recorded where it is not that."""
    parts = str(case_ran).split(" → ")
    if len(parts) != 2:
        return f"{_named(case_ran)}{_rest(case_ran)}"
    return _when(*parts)


def _day(value: str):
    from onetrace_console.words import _instant
    when = _instant(value)
    return when.date() if when is not None else None


def _step_when(started: str, ended: str, day) -> str:
    """A step's times in the step table, whose run's date is said once above it: the time of day
    to the millisecond, `10:00:00.000 → 10:00:01.000`, the whole value in each `<time>`. A step on
    another date than the run's first gives its date too; a value that is not a time is quoted."""
    from onetrace_console.words import _instant, clock, escape as _esc
    out = []
    for value in (started, ended):
        when = _instant(value)
        if when is None:
            out.append(f"{_named(value)}{_rest(value)}")
            continue
        shown = clock(value) if when.date() == day else f"{when.date().isoformat()} {clock(value)}"
        out.append(f'<time datetime="{_esc(str(value))}" title="{_esc(str(value))}">{_esc(shown)}</time>')
    return " → ".join(out)


def _region(table: str, label_key: str, name: str) -> str:
    """A wide table in a scroll region of its own, named for a screen reader (`words.scroll_region`)."""
    from onetrace_console.words import scroll_region
    return scroll_region(table, template(label_key), name)


def _is_shared(x: Line) -> bool:
    """A step's line that is the reason every unanchored step shares (`check.not_run.originality`)."""
    return "".join(t.text for t in x) == template("check.not_run.originality")


def _generated(when: str, generator: str) -> str:
    """The footer's line: when, as every page shows a time, and the one product name and version."""
    from onetrace_console.words import time_html
    return (escape(template("footer.generated"))
            .replace("{date}", time_html(when)).replace("{generator}", escape(generator)))


#: Where the run's own record can be downloaded, for the page being drawn. Set per page
#: and per list row by the render functions, from the model; a context variable, so pages drawn at
#: once on different threads never take each other's.
_RECORD_HREF: contextvars.ContextVar[str | None] = contextvars.ContextVar("record_href",
                                                                          default=None)


def _named(text) -> str:
    """A record word as a page quotes it: whole within NAME_CAP characters, otherwise
    its first NAME_CAP. `_rest` says, outside the quotation, what was left out."""
    text = str(text)
    return escape(text if len(text) <= NAME_CAP else text[:NAME_CAP])


def _rest(text, *, whole: bool = True) -> str:
    """After a shortened record word, in the page's own words: how many characters are left out,
    and that the whole value is in the run's record -- a download of it where there is one."""
    more = len(str(text)) - NAME_CAP
    if more <= 0:
        return ""
    if not whole:
        return f'<span data-words="page"> {_t("name.more", n=str(more))}</span>'
    href = _RECORD_HREF.get()
    where = (f'<a href="{escape(href)}" download>{_t("name.whole")}</a>' if href
             else _t("name.whole"))
    return f'<span data-words="page"> {_t("name.more", n=str(more))} · {where}</span>'


def _id_cell(run_id: str, tag: str, href: str | None = None) -> str:
    """A run_id's cell: the same markup as always when it is shown whole; when it is shortened,
    the record's words and the page's are told apart."""
    name = f'<a href="{escape(href)}">{_named(run_id)}</a>' if href else _named(run_id)
    if len(str(run_id)) <= NAME_CAP:
        return f'<{tag} class="mono" data-words="record">{name}</{tag}>'
    return (f'<{tag} class="mono"><span data-words="record">{name}</span>'
            f"{_rest(run_id)}</{tag}>")


def _part(t: Text) -> str:
    if t.source == "page":
        return escape(t.text)
    if t.source == "time":
        #: A time in a headline, short (YYYY-MM-DD HH:MM UTC); the full value in the element.
        from onetrace_console.words import short_time
        return (f'<time class="value" data-words="value" datetime="{escape(t.text)}" '
                f'title="{escape(t.text)}">{escape(short_time(t.text))}</time>')
    if t.source == "value":
        if _FINGERPRINT.fullmatch(t.text):
            return fingerprint_html(t.text, words="value")
        return f'<span class="value" data-words="value">{escape(t.text)}</span>'
    if t.source == "record":
        if _FINGERPRINT.fullmatch(t.text):
            return fingerprint_html(t.text, words="record")
        return f'<q data-words="record">{_named(t.text)}</q>{_rest(t.text)}'
    if t.source == "check":
        #: The verifier's words, which quote the record's: capped the same way, and each
        #: fingerprint in them short -- the verifier's output, whole, is on the same page as it
        #: printed it.
        inline, _folded = shortened_in_text(t.text[:NAME_CAP])
        return f'<q data-words="check">{inline}</q>{_rest(t.text, whole=False)}'
    inline, folded = shortened_in_text(t.text)
    return f'<q data-words="{escape(t.source)}">{inline}</q>{folded}'


def _line(parts: Line) -> str:
    return "".join(_part(p) for p in parts)


def _p(parts: Line, cls: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    #: A line holding a fingerprint is a block: its fold cannot sit inside a <p>.
    folds = any(t.source in ("record", "value") and _FINGERPRINT.fullmatch(t.text) for t in parts)
    tag = "div" if cls == "fp" or folds else "p"
    return f"<{tag}{c}>{_line(parts)}</{tag}>"


def _detail(d: Detail) -> str:
    """A labelled row, or — where there is no label by design — the quotation on its own."""
    if not d.label:
        return f"<div>{_part(d.value)}</div>"
    return f'<div class="k">{_t(d.label)}</div><div>{_part(d.value)}</div>'


def _said(v: VerbSaid) -> str:
    """A table sentence from a verb's report, with the report's own words beside it."""
    details = ("".join(_detail(d) for d in v.details))
    grid = f'<div class="grid">{details}</div>' if details else ""
    step = f' data-step="{escape(v.step)}"' if v.step else ""
    return f'<div class="said"{step}>{_p(v.sentence)}{grid}</div>'


def _code(text: str) -> str:
    return f'<pre data-layer="4"><code>{escape(text)}</code></pre>'


def _details(label_key: str, layer: str, inner: str) -> str:
    return (f'<details data-layer="{layer}"><summary>{_t(label_key)}</summary>'
            f"{inner}</details>")


def _for_cell(m, tag: str) -> str:
    """The declared stages' cell: the first LIST_CAP names, then "…and N more". The same
    markup as before when nothing is left out."""
    if not getattr(m, "case_for_more", 0):
        return f'<{tag} data-words="record">{escape(m.case_for)}</{tag}>'
    return (f'<{tag}><span data-words="record">{escape(m.case_for)}</span> '
            f"{_t('list.more', n=str(m.case_for_more))}</{tag}>")


def _items(items: tuple[Item, ...], none_key: str, with_fingerprints: bool, more: int = 0) -> str:
    if not items:
        return _t(none_key)
    rows = []
    for i in items:
        text = (f'<q data-words="record">{_named(i.name)}</q>{_rest(i.name)} · '
                f'<span class="value" data-words="value">{escape(i.size)}</span> {_t("unit.bytes")}')
        if with_fingerprints:
            text += f'<div class="fp" data-words="record">{fingerprint_html(i.fingerprint)}</div>'
        rows.append(f"<div>{text}</div>")
    if more:
        rows.append(f"<div>{_t('list.more', n=str(more))}</div>")
    return "".join(rows)


# ------------------------------------------------------------------------------ pieces

def _head(title: str) -> str:
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{escape(title)}</title>\n{_style()}</head>\n")


def _style() -> str:
    sheet = _FRAME.get()
    if sheet is None:
        return f"<style>\n{root_css()}\n{scale_css()}\n{theme_css()}\n{CSS}</style>\n"
    #: The console's own icon, beside its stylesheet; the free file, framed by nothing, has none.
    icon = sheet.rsplit("/", 1)[0] + "/favicon.svg"
    #: The console's theme switch: a stored choice applied before the first paint (`frame.py`).
    from onetrace_console.frame import THEME_HEAD_SCRIPT
    return (f"{THEME_HEAD_SCRIPT}\n"
            f'<link rel="stylesheet" href="{escape(sheet)}">\n'
            f'<link rel="icon" href="{escape(icon)}" type="image/svg+xml">\n')


def _top(m: PageModel, kind_key: str, title_key: str) -> str:
    sample = (f'<p class="sample">{_t("sample.label", format=m.preview_format)}</p>'
              if m.is_preview else "")
    return (f'<header class="top"><div><div class="kind">{_t(kind_key)}</div>'
            f"<h1>{_t(title_key)}</h1></div>"
            f'<div class="meta"><span data-words="record">{_named(m.run_id)}</span>'
            f"{_rest(m.run_id)}</div>"
            f"</header>{sample}")


def _declined(m: PageModel) -> str:
    """Where the run stopped at a step's own rule: the step, the reason it recorded, and the
    declared steps left with no receipt. Outlined in the accent, never red: the check ran and a
    rule refused. Nothing where the run did not stop at one."""
    if not m.declined:
        return ""
    from onetrace_console.viewer.model import LIST_CAP, name_shown
    stage, reason, left = m.declined
    #: Each name, and the reason, within the page's caps, as every record word is: a hundred long
    #: step names never make the page as long as the record.
    stage = name_shown(stage)
    said = (_t("declined.banner", stage=stage, reason=name_shown(reason)) if reason.strip()
            else _t("declined.banner_no_reason", stage=stage))
    named = ", ".join(name_shown(s) for s in left[:LIST_CAP])
    if len(left) > LIST_CAP:
        named += " " + template("list.more").format(n=str(len(left) - LIST_CAP)).rstrip(".")
    said += " " + (_t("declined.left", steps=named) if left else _t("declined.none_left"))
    return f'<div data-section="declined"><p class="declined">{said}</p></div>'


def _last_failed(m: PageModel) -> str:
    """The declared stages whose last recorded attempt
    failed, on its own filled-amber line directly below the strip and outside it -- the strip
    states the verifier's verdict, this what the record says a stage did."""
    if not m.last_failed:
        return ""
    if len(m.last_failed) == 1:
        stage, error = m.last_failed[0]
        said = _t("last_failed.one", stage=stage, error=error)
    else:
        said = _t("last_failed.several", n=str(len(m.last_failed)),
                  stages=", ".join(s for s, _ in m.last_failed))
    return f'<div data-section="last-attempt-failed"><p class="last-failed">{said}</p></div>'


def _strip(m: PageModel) -> str:
    beside = "".join(_p(b, "beside") for b in m.strip.beside)
    command = ""
    if m.report_command:
        command = (f'<details data-layer="4"><summary>{_t("command.verify")}</summary>'
                   f'<p>{_t("where." + m.report_where)}</p>'
                   f'{_code(" ".join(m.report_command))}</details>')
    problem = ""
    if m.report_problem:
        problem = f'<pre data-layer="3">{_escape_lines(m.report_problem)}</pre>'
    return (f'<section class="strip {m.strip.tone}" data-state="{m.strip.state}">'
            f'<div class="lead">{_line(m.strip.sentence)}</div>{beside}{problem}{command}'
            "</section>")


def _rung(r: Rung) -> str:
    """One rung: its question, then its state and its evidence together, "state · evidence" --
    so each rung reads as 28n §2 words the authorization rung, "No records · needs an AADP
    policy engine". `data-state` carries the state for a reader of the markup; no rung is
    painted (C034 §4.4: colour for verdicts only)."""
    evidence = " ".join(_line(e) for e in r.evidence)
    #: A rung with no state word -- "Ran as approved" on a straight-line run, drawn
    #: with no badge -- is its evidence alone.
    said = f"<span>{_t(r.state_key)}</span> · {evidence}" if r.state_key else evidence
    return (f'<tr data-rung="{escape(r.key)}" data-state="{escape(r.state)}">'
            f"<td>{_t('rung.' + r.key)}</td>"
            f"<td>{said}</td></tr>")


def _ladder(m: PageModel) -> str:
    """v6 board 2's "What the evidence establishes": seven separate questions, no single verdict."""
    return (f'<section data-section="ladder"><h2>{_t("section.ladder")}</h2>'
            f"<p>{_t('ladder.intro')}</p>"
            + _region(f'<table class="timeline"><tbody>{"".join(_rung(r) for r in m.ladder)}</tbody></table>',
                      "region.ladder", "ladder")
            + f"<p>{_t('ladder.limit')}</p></section>")


def _receipt(s: StepView) -> str:
    """The step's receipt card: its layer-2 disclosure, with the raw receipt and any findings
    one layer further down. The trail's card and the answer card draw the same one."""
    layer2 = (
        '<div class="grid">'
        f'<div class="k">{_t("field.version")}</div><div><q data-words="record">'
        f'{_named(s.instrument_id)}</q>{_rest(s.instrument_id)} · <q data-words="record">'
        f'{_named(s.instrument_version)}</q>{_rest(s.instrument_version)}</div>'
        f'<div class="k">{_t("field.in")}</div><div>{_items(s.inputs, "nothing.in", True, s.inputs_more)}</div>'
        f'<div class="k">{_t("field.out")}</div><div>{_items(s.outputs, "nothing.out", True, s.outputs_more)}</div>'
        f'<div class="k">{_t("field.fingerprint")}</div>'
        f'<div class="fp" data-words="record">{fingerprint_html(s.manifest_fingerprint)}</div>'
        f'<div class="k">{_t("field.constants")}</div>'
        f'<div><pre data-layer="3">{_escape_lines(s.constants)}</pre></div>'
        "</div>")
    layer3 = f'<pre data-layer="3">{_escape_lines(s.raw)}</pre>'
    findings = ""
    if s.findings:
        findings = _details("disclose.report", "3",
                            f'<pre data-layer="3">{_escape_rows(chr(10).join(s.findings))}</pre>')
    return _receipt_details(s, layer2 + _details("disclose.raw", "3", layer3) + findings)


def _receipt_details(s: StepView, inner: str) -> str:
    """A step's receipt disclosure, named for its step, so a reader with several open knows which
    receipt is which: "Receipt · step 1 of 7 · request"."""
    summary = (escape(template("disclose.card")).replace("{n}", escape(s.index))
               .replace("{total}", escape(s.total)).replace("{name}", _named(s.words)))
    return f'<details data-layer="2"><summary>{summary}</summary>{inner}</details>'


def _card(s: StepView, with_check: bool = True, said: tuple[VerbSaid, ...] = ()) -> str:
    sentences = "".join(_p(x) for x in s.sentences)
    check = "".join(_p(x) for x in s.check) if with_check else ""
    return (
        f'<article class="card" data-step="{escape(s.index)}">'
        f'<div class="step">{_t("step.of", n=s.index, total=s.total)}</div>'
        f"<h3>{escape(s.words)}</h3>"
        f'<div class="grid"><div class="k">{_t("field.in")}</div>'
        f'<div>{_items(s.inputs, "nothing.in", False, s.inputs_more)}</div>'
        f'<div class="k">{_t("field.out")}</div><div>{_items(s.outputs, "nothing.out", False, s.outputs_more)}</div>'
        f'<div class="k">{_t("field.time")}</div><div class="value" data-words="record">'
        f"{_when(s.started, s.ended)}</div></div>"
        f"{sentences}{_p(s.ran)}{check}"
        + "".join(_said(v) for v in said if v.step == s.index)
        + _receipt(s)
        + "</article>")


def _footer(m: PageModel, file_name: str) -> str:
    # The verifier is named exactly as the report recorded it, relative to the run's folder,
    # so the line regenerates THIS page rather than a layout we assumed.
    verifier = m.report_verifier or "verify.py"
    regenerate = ("python -m onetrace_console.viewer generate RUN_FOLDER --cli --out OUT_FOLDER"
                  if m.report_cli else
                  f"python -m onetrace_console.viewer generate RUN_FOLDER "
                  f"--verifier RUN_FOLDER/{verifier} --out OUT_FOLDER")
    return (
        "<footer>"
        f"<p>{_generated(m.generated_at, m.generator)}</p>"
        f'<p>{_t("footer.fingerprint")}: <code class="fp">{SLOT}</code></p>'
        f'<details data-layer="4"><summary>{_t("disclose.commands")}</summary>'
        f"<p>{_t('footer.fingerprint_how')}</p>"
        f"{_code(STANDALONE_CHECK.format(file=file_name))}"
        + (f"<p>{_t('command.verify')} — {_t('where.' + m.report_where)}</p>"
           f"{_code(' '.join(m.report_command))}" if m.report_command else "")
        + f"<p>{_t('command.regenerate')}</p>{_code(regenerate)}"
        "</details></footer>")


def _report_block(m: PageModel) -> str:
    if m.report_output is None:
        return ""
    # **The fallback says so, and only the fallback says anything.** A page read from
    # the rows renders exactly what it rendered before the switch, which is what makes
    # the reader's byte-identity check a check and not a restatement.
    note = (f'<p data-source="fallback">{_t("check.source_fallback")}</p>'
            if m.report_is_fallback else "")
    if not m.report_rows_readable:
        # 30bv §3.3: a record's text broke the rows apart, so no line break in the output can be
        # trusted to be the verifier's. The whole output, every character escaped one-to-one.
        return _details("disclose.report", "3",
                        f'{note}<p data-section="rows-unreadable">{_t("rows.unreadable")}</p>'
                        f'<pre data-layer="3" data-rows="unreadable">'
                        f'{_escape_word_text(m.report_output)}</pre>')
    return _details("disclose.report", "3",
                    f'{note}<pre data-layer="3">{_escape_rows(m.report_output)}</pre>')


# ------------------------------------------------------------------------------- views

def _also(sibling: str | None, title_key: str) -> str:
    """A relative link to the other view of this same run, generated beside this one.

    Ruled in by core after C036 item 1 flagged it: *relative links between pages generated
    together, about the same run or the same comparison, are not the fenced application shell*
    — C034 §1 fenced the shell because it needs a backend (search, a signed-in user and
    organisation, navigation between stores), and a link resolved at generation time needs none
    of that. The constraint stays for anything implying a different store or a different run
    set than the one generated.

    The link's words are the destination's own ruled title (`title.answer`/`title.case`,
    adopted by C023 §4), so navigation added no vocabulary. `sibling=None` renders no link,
    which is what a page generated on its own gets.
    """
    if not sibling:
        return ""
    return (f'<p class="also" data-section="also">'
            f'<a href="{escape(sibling)}">{_t(title_key)}</a></p>')


def render_answer(m: PageModel, file_name: str = "answer.html",
                  sibling: str | None = "case.html") -> str:
    """019 §2, the answer view. Unsealed: the fingerprint slot is still zeros."""
    token = _RECORD_HREF.set(getattr(m, "record_href", None))
    try:
        return _render_answer(m, file_name, sibling)
    finally:
        _RECORD_HREF.reset(token)


def _render_answer(m: PageModel, file_name: str, sibling: str | None) -> str:
    answer = "".join(_p(x) for x in m.answer)
    #: The anchor sentence, from the page's own check, under the answer.
    answer += "".join(f'<p data-section="answer-anchor">{_line(x)}</p>' for x in m.answer_anchor)
    question = "".join(_p(x, "fp" if x and x[0].source == "record" else "") for x in m.question)
    #: The receipt disclosure only where a step wrote the answer, holding that
    #: step's receipt card; the question's lines under their own label, only where there are any.
    step = next((s for s in m.steps if m.answer_step and s.index == m.answer_step), None)
    receipt = _receipt(step) if step is not None else ""
    asked = _details("disclose.question", "2", question) if question else ""
    unchecked = "".join(
        "<li>" + "".join(_p(x, "fp" if x and x[0].source == "record" and x[0].text.startswith("sha256:") else "")
                         for x in row) + "</li>"
        for row in m.unchecked)
    body = (
        f"{_top(m, 'kind.answer', 'title.answer')}{_strip(m)}{_last_failed(m)}{_declined(m)}"
        f'<section data-section="answer"><h2>{_t("section.answer")}</h2>'
        f'<div class="card">{answer}{receipt}{asked}</div></section>'
        f'<section data-section="trail"><h2>{_t("section.trail")}</h2>'
        + "".join(_card(s, said=m.reproduced + m.changed) for s in m.steps) + "</section>"
        f'<section data-section="unchecked"><h2>{_t("section.unchecked")}</h2>'
        f'<ul class="plain">{unchecked}</ul></section>'
        + _also(sibling, "title.case")
        + f"{_footer(m, file_name)}")
    return (_head(template("title.answer") + " · " + name_shown(m.run_id))
            + _body("answer", body) + f'{PRINT_SCRIPT}\n</body>\n</html>\n')


def _reproduce_row(m: PageModel, v: VerbSaid) -> str:
    """One re-check row, labelled with the step it is about, as the record names it."""
    step = next((s for s in m.steps if s.index == v.step), None)
    label = (f'{_t("step.of", n=step.index, total=step.total)} · {escape(step.words)}'
             if step else (f'{_t("field.step")} {escape(v.step)}' if v.step else ""))
    head = f'<div class="step">{label}</div>' if label else ""
    return f'<div class="said" data-step="{escape(v.step or "")}">{head}{_p(v.sentence)}' \
           f'{("".join(f"<div class=\"grid\">{_detail(d)}</div>" for d in v.details))}</div>'


def _count_row(c: CheckCount) -> str:
    quotes = "".join(f"<div>{_part(q)}</div>" for q in c.quotes)
    return (f'<li data-state="{c.state}" data-count="{c.count}"><strong>{escape(c.label)}</strong>'
            f" — {_line(c.sentence)}{quotes}</li>")


def _not_checked_rows(items, steps: int) -> str:
    """The "Not checked" list with each reason said once. Items whose reason reads the same are one
    line: "Every step" when they are all of the run's steps, otherwise their labels together. A
    reason only one item has keeps its own line."""
    groups: dict[str, list] = {}
    for c in items:
        groups.setdefault(_line(c.sentence) + "".join(f"<div>{_part(q)}</div>" for q in c.quotes),
                          []).append(c)
    rows = []
    for said, group in groups.items():
        if len(group) == 1:
            rows.append(_count_row(group[0]))
            continue
        first = group[0]
        every = len(group) == steps and all(c.label != template("label.manifest") for c in group)
        label = _t("checks.every_step") if every else escape("; ".join(c.label for c in group))
        if every and _line(first.sentence) == _line(line("check.not_run.originality")):
            said = _line(line("check.not_run.originality_all"))
        rows.append(f'<li data-state="{first.state}" data-count="{sum(c.count for c in group)}" '
                    f'data-items="{len(group)}"><strong>{label}</strong> — {said}</li>')
    return "".join(rows)


def render_executions(models: list[PageModel], generated_at: str, generator: str,
                      file_name: str = "executions.html",
                      hrefs: list[str] | None = None, *, of: int | None = None) -> str:
    """C036 item 2, the Executions list. Unsealed: the fingerprint slot is still zeros.

        Three runs, two of them a deliberate pair, is what there is — render it as a real
        list view over the real corpus, emptiness visible, no synthesized rows to make it
        look fuller. This is explicitly not what a list view is *for*, and the page should
        not pretend otherwise.                         — the list-view decision (036), item 2

    **Each row links to the directory it was generated from**, when the caller supplies the
    paths. Core ruled it: the folder a run's manifest was actually read from is *generation-time
    metadata, not a content claim* — the same category as this file's own name in the footer —
    and a link target is not a rendered assertion, so pointing at it fabricates nothing the
    record does not say. `hrefs=None` renders the rows unlinked, which is what a caller with no
    paths to offer gets.

    The paths are the caller's, resolved at generation time. Nothing is queried and no run
    outside the ones named is reachable from here, which is the constraint core kept when it
    lifted the zero-link rule.

    Every row is a fact the record states. There is no count of failures, no rate, no ordering
    by anything but the run id the records carry, and no row for a run that was not given.

    **The count carries a denominator**. `of` is the size of the set the caller
    chose these runs from, in runs, the same unit as the count. It defaults to the runs given,
    which is what a caller that chose nothing has, and it may not be smaller than them.
    """
    if hrefs is not None and len(hrefs) != len(models):
        raise ValueError("one href per run, or none at all: a row addressed to the wrong "
                         "directory is worse than a row with no link")
    n = len(models)
    total = n if of is None else of
    if total < n:
        raise ValueError(f"a list of {n} runs cannot have been chosen from {total}: a "
                         "denominator smaller than its count is not a denominator")
    cells = []
    for i, m in enumerate(models):
        href = hrefs[i] if hrefs is not None else None
        # The run id is what the record states; the link is where it was read from. They are
        # different kinds of thing, so the id stays the row's words and the path stays an
        # attribute — the reader is never shown a path as though the record had claimed it.
        token = _RECORD_HREF.set(getattr(m, "record_href", None))
        try:
            cell = _id_cell(m.run_id, "td", href)
        finally:
            _RECORD_HREF.reset(token)
        cells.append(
            f'<tr data-run="{escape(m.run_id[:NAME_CAP])}">'
            f'{cell}'
            f'<td class="value" data-words="record">{_ran(m.case_ran)}</td>'
            f'{_for_cell(m, "td")}'
            f'<td class="value">{escape(str(m.step_count))}</td></tr>')
    rows = "".join(cells)
    corpus = (template("executions.one").format(total=total) if n == 1
              else template("executions.corpus").format(n=n, total=total))
    body = (
        f'<header class="top"><div><div class="kind">{_t("kind.executions")}</div>'
        f'<h1>{_t("title.executions")}</h1></div></header>'
        f'<section data-section="executions"><h2>{_t("section.executions")}</h2>'
        f"<p>{escape(corpus)}</p>"
        f'<table class="timeline"><thead><tr><th>{_t("field.run")}</th>'
        f'<th>{_t("field.ran")}</th><th>{_t("field.for")}</th>'
        f'<th>{_t("field.steps")}</th></tr></thead><tbody>{rows}</tbody></table></section>'
        f'<p class="limit" data-section="limit">{_t("case.limit")}</p>'
        "<footer>"
        f"<p>{_generated(generated_at, generator)}</p>"
        f'<p>{_t("footer.fingerprint")}: <code class="fp">{SLOT}</code></p>'
        f'<details data-layer="4"><summary>{_t("disclose.commands")}</summary>'
        f"<p>{_t('footer.fingerprint_how')}</p>"
        f"{_code(STANDALONE_CHECK.format(file=file_name))}</details></footer>")
    return (_head(template("title.executions"))
            + _body("executions", body)
            + f"{PRINT_SCRIPT}\n</body>\n</html>\n")


def render_case(m: PageModel, file_name: str = "case.html",
                sibling: str | None = "answer.html") -> str:
    """019 §3, the case view. Unsealed: the fingerprint slot is still zeros."""
    token = _RECORD_HREF.set(getattr(m, "record_href", None))
    try:
        return _render_case(m, file_name, sibling)
    finally:
        _RECORD_HREF.reset(token)


def _graph(m: PageModel) -> str:
    """The run's execution graph, from `viewer.graph`, between the ladder and
    the timeline it links back to. Edges the record holds in a shape no graph can be drawn
    from are said so, never drawn as a line or as a graph with no links."""
    if m.graph_unreadable:
        return (f'<section data-section="graph"><h2>{_t("section.graph")}</h2>'
                f'<p data-section="graph-unreadable">{_t("graph.unreadable")}</p></section>')
    if not m.graph_nodes:
        return ""
    first = m.steps[0].index if m.steps else ""
    #: In-page links are `#step-N` only, as ruled: the first step's row is where the
    #: recorded order starts.
    return graph_render(m.graph_nodes, m.graph_edges,
                        recorded_order_href=f"#step-{first}" if first.isdigit() else "",
                        heading=_t("section.graph"), esc=escape, lead=_marked_from(m),
                        wrap=m.graph_wrap, wrap_labels=bool(m.graph_wrap),
                        **({"tag_lines": m.graph_tag_lines} if m.graph_tag_lines else {}))


def _marked_from(m: PageModel) -> str:
    """One line above the graph naming the comparison its verdicts come from --
    or, where that comparison's report did not pass the strict reader, saying no verdict is
    marked. Nothing at all where there is no comparison."""
    if not m.graph_source:
        return ""
    baseline, at, href, readable = m.graph_source
    link = f' <a href="{escape(href)}">{_t("graph.open_comparison")}</a>'
    if readable:
        return (f'<p data-section="graph-marked-from">'
                f'{_with_time("graph.marked_from", at, baseline=baseline)}{link}</p>')
    return (f'<p data-section="graph-marks-unreadable">'
            f'{_with_time("graph.marks_unreadable", at, baseline=baseline)}{link}</p>')


def _with_time(key: str, at: str, **values: str) -> str:
    """A sentence with a time in it: its words escaped, and the time as every page shows one."""
    from onetrace_console.words import time_html
    before, mark, after = template(key).partition("{at}")
    return (escape(before.format(**values)) + (time_html(at) if mark else "")
            + escape(after.format(**values)))


def _render_case(m: PageModel, file_name: str, sibling: str | None) -> str:
    rows = []
    #: The run's first date, said once in the case header; a step on another date says its own.
    day = _day(str(m.case_ran).split(" → ", 1)[0])
    #: The reason every step shares, said once above the table when every step has it; a step
    #: that differs keeps its own lines.
    every = bool(m.steps) and all(any(_is_shared(x) for x in s.check) for s in m.steps)
    for s in m.steps:
        check = "".join(_p(x) for x in s.check if not (every and _is_shared(x)))
        rows.append(
            f'<tr data-step="{escape(s.index)}"><td><span id="step-{escape(s.index)}"></span>'
            f'{escape(s.words)}<div class="step">'
            f'{_t("step.of", n=s.index, total=s.total)}</div></td>'
            f'<td class="value" data-words="record">{_step_when(s.started, s.ended, day)}</td>'
            f"<td>{check or '—'}</td><td>{_line(s.outcome_words)}</td></tr>")
        if s.boundary or s.index in m.boundary_steps:
            rows.append(f'<tr data-boundary="{escape(s.index)}"><td colspan="4">'
                        f'{_t("timeline.boundary")}</td></tr>')
    checked = "".join(_count_row(c) for c in m.checked)
    not_checked = _not_checked_rows(m.not_checked, steps=len(m.steps))
    lists = (
        f'<h3>{_t("section.checked_list")}</h3><ul class="plain">{checked or "<li>—</li>"}</ul>'
        f'<h3>{_t("section.not_checked_list")}</h3><ul class="plain">{not_checked or "<li>—</li>"}</ul>'
        if m.report_output is not None and not m.report_problem else "")
    body = (
        f"{_top(m, 'kind.case', 'title.case')}"
        f'<section data-section="case"><h2>{_t("section.case_line")}</h2><div class="card grid">'
        f'<div class="k">{_t("field.run")}</div>{_id_cell(m.run_id, "div")}'
        f'<div class="k">{_t("field.ran")}</div><div class="value" data-words="record">'
        f'{_ran(m.case_ran)}</div>'
        f'<div class="k">{_t("field.for")}</div>{_for_cell(m, "div")}'
        "</div></section>"
        f"{_strip(m)}{_last_failed(m)}{_declined(m)}"
        f"{_ladder(m)}"
        f"{_graph(m)}"
        f'<section data-section="timeline"><h2>{_t("section.timeline")}</h2>'
        + (f'<p data-section="timeline-shared">{_t("check.not_run.originality_all")}</p>'
           if every else "")
        + _region(f'<table class="timeline"><thead><tr><th>{_t("field.step")}</th><th>{_t("field.time")}</th>'
                  f'<th>{_t("section.checked")}</th><th>{_t("field.outcome")}</th></tr></thead>'
                  f'<tbody>{"".join(rows)}</tbody></table>', "region.steps", "steps")
        + "".join(_receipt_details(s, _card(s, with_check=False)) for s in m.steps)
        + "</section>"
        f'<section data-section="changed"><h2>{_t("section.changed")}</h2>'
        + "".join(_said(x) for x in m.changed) + "</section>"
        # 031 §3: the section is on the page whether or not a report reached it.
        + f'<section data-section="reproduce"><h2>{_t("section.reproduce")}</h2>'
        + "".join(_reproduce_row(m, v) for v in m.reproduced) + "</section>"
        + f'<section data-section="checked"><h2>{_t("section.checked")}</h2>{lists}{_report_block(m)}</section>'
        # C036 item 3: Policy and Incidents are named sections carrying an absence sentence,
        # and nothing else. Incidents keeps 019 §4's `verb.not_run.boundary` — the "record
        # stops here" shape C036 directs be reused. Policy says "no authorization records"
        # (release 1's state, wherever authorization would appear, never
        # blank and never a pass). C031 §3 governs the shape: the section is on the page, and
        # says so, rather than being blank.
        + f'<section data-section="policy"><h2>{_t("section.policy")}</h2>'
        + f'<p>{_t("policy.none")}</p></section>'
        #: In the console's frame this section is dropped (the run page lists
        #: the run's incidents at the top, and the console's Incidents page the rest); in the
        #: free file it is "Where the record stops", keeping 019 §4's sentence.
        + ("" if _FRAME.get() is not None else
           f'<section data-section="incidents"><h2>{_t("section.incidents")}</h2>'
           f'<p>{_t("verb.not_run.boundary")}</p></section>')
        + f'<p class="limit" data-section="limit">{_t("case.limit")}</p>'
        + _also(sibling, "title.answer")
        + f"{_footer(m, file_name)}")
    return (_head(template("title.case") + " · " + name_shown(m.run_id))
            + _body("case", body) + f'{PRINT_SCRIPT}\n</body>\n</html>\n')
