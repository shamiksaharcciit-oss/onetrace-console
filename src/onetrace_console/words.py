"""A record's own words on this console's pages: shown as stored, with what cannot be seen escaped.

    Wherever a page shows a record's own words (a run_id, stage names, details, output
    names), show these visibly escaped as \\uXXXX: C0 and C1 control characters (NUL, ESC,
    CR, LF and the rest); the bidirectional controls U+202A-U+202E and U+2066-U+2069; lone
    surrogates. Everything else is shown as stored.

The viewer's `display` decides which characters those are, so the free file and the console
escape exactly the same ones. Every page this console draws escapes through here, its own words
included: they hold none of those characters, so escaping them changes nothing, and a page has
one escape rather than a choice of two.
"""
from __future__ import annotations

from html import escape as _html_escape
import html as _html
import re

#: The authorization rung's evidence on every page: this console records no authorization, and
#: says so plainly.
NO_AUTHORIZATION = "This console does not record authorization."


#: A check's verdict as a reader reads it. The stored values (`checks.HOLDS` and the rest) stay as
#: they are; a page or the command line shows these words for them.
VERDICT_WORDS = {"holds": "Verified", "contradicts": "Contradicts its record",
                 "could_not_check": "Couldn't check"}
NO_VERDICT = "No verdict recorded"


def _instant(value):
    """A recorded time as an instant in UTC, or None where the value does not read as a time
    with its zone -- never guessed at."""
    from datetime import datetime, timezone
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        return None
    return when.astimezone(timezone.utc)


def short_time(value: str) -> str:
    """A recorded time as every page shows it: `YYYY-MM-DD HH:MM:SS UTC`, the same instant in UTC.
    A value that does not read as a time is returned as it is, never guessed at."""
    when = _instant(value)
    return str(value) if when is None else when.strftime("%Y-%m-%d %H:%M:%S UTC")


def clock(value: str) -> str:
    """The time of day alone, in UTC, to the millisecond where the value has them:
    `HH:MM:SS.mmm`. For a table whose date is said once above it."""
    when = _instant(value)
    if when is None:
        return str(value)
    return when.strftime("%H:%M:%S") + (f".{when.microsecond // 1000:03d}"
                                         if "." in str(value).split("T", 1)[-1] else "")


#: The one script a console page may add to its times (the Overview's): after each `<time>`, how
#: long ago it was, worked out in the reader's browser from the time's own `datetime` -- " · 2 h
#: ago". The absolute UTC time is always in the page; without the script, it stands alone. A
#: public console names this script's hash in its Content-Security-Policy (`public.py`).
RELATIVE_TIME_SCRIPT = (
    "<script>document.querySelectorAll('time[datetime]').forEach(function(t){"
    "var d=Date.parse(t.getAttribute('datetime'));if(isNaN(d))return;"
    "var s=Math.floor((Date.now()-d)/1000);if(s<0)return;"
    "var w=s<60?'just now':s<3600?Math.floor(s/60)+' min ago':"
    "s<86400?Math.floor(s/3600)+' h ago':Math.floor(s/86400)+' d ago';"
    "var e=document.createElement('span');e.className='rel';e.textContent=' \u00b7 '+w;"
    "t.after(e)})</script>")


#: The watched folder's notice (`watch.py`): every few seconds it asks the console what the
#: watcher has (`GET /v1/folder`) and, when new runs have been taken in since the page was drawn,
#: shows "2 new runs. Show them" -- never reloading or moving the page under the reader. The line
#: saying when the folder was last read is kept current too. Without the script the page says
#: when it was drawn, and a reload shows the new runs.
WATCH_SCRIPT = (
    "<script>(function(){var s=document.querySelector('[data-section=watched]');if(!s)return;"
    "var v=+s.getAttribute('data-version'),t=+s.getAttribute('data-taken'),"
    "ms=1000*+s.getAttribute('data-interval');function poll(){fetch('/v1/folder',"
    "{cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(d){if(!d)"
    "return;var l=s.querySelector('[data-part=last-read]');if(l&&d.last_read){l.setAttribute("
    "'datetime',d.last_read);l.textContent=d.last_read.replace('T',' ').replace('+00:00',' UTC')}"
    "if(d.version>v){var n=d.taken-t,p=s.querySelector('[data-part=notice]');p.hidden=false;"
    "p.firstChild.textContent=(n>0?n+(n==1?' new run. ':' new runs. '):'The folder changed. ');}"
    "}).catch(function(){})}setInterval(poll,Math.max(ms,1000))})()</script>")


def time_html(value, *, attrs: str = "", text: str | None = None) -> str:
    """A time as a page shows it: the one display form, inside `<time>` carrying the value as
    recorded. A value that does not read as a time is shown escaped as it is, in no `<time>`."""
    if _instant(value) is None:
        return escape(str(value))
    shown = short_time(value) if text is None else text
    return (f'<time{(" " + attrs) if attrs else ""} datetime="{escape(str(value))}" '
            f'title="{escape(str(value))}">{escape(shown)}</time>')


def span_html(started, ended, *, attrs: str = "") -> str:
    """A start and an end: the first in the full form, the second its time alone when it falls
    on the same UTC date, so the date is said once."""
    a, b = _instant(started), _instant(ended)
    second = (short_time(ended)[11:] if a is not None and b is not None and a.date() == b.date()
              else None)
    return f"{time_html(started, attrs=attrs)} → {time_html(ended, attrs=attrs, text=second)}"


def scroll_region(inner: str, label: str, name: str) -> str:
    """A table in a region of its own, named for a screen reader and reached by a keyboard. In the
    console, on a narrow screen, its rows stack, each cell under its column's header (`labelled`),
    so nothing in it is cut off and nothing scrolls sideways; the free file keeps the scroll."""
    return (f'<div class="scroll-frame"><div class="scroll-x" data-scroll="{escape(name)}" '
            f'tabindex="0" role="region" aria-label="{escape(label)}">{labelled(inner)}</div></div>')


_THEAD = re.compile(r"<thead>(.*?)</thead>", re.S)
_TBODY = re.compile(r"(<tbody>)(.*?)(</tbody>)", re.S)
_ROW = re.compile(r"(<tr\b[^>]*>)(.*?)(</tr>)", re.S)
_CELL = re.compile(r"<td\b")


def labelled(inner: str) -> str:
    """`inner` with each body cell of its table labelled by its column's header (`data-label`, the
    header's text), so a stacked row still says what each value is. A table with no header row is
    returned as it is: its first cell is the row's label."""
    head = _THEAD.search(inner)
    if head is None:
        return inner
    labels = [" ".join(_html.unescape(re.sub(r"<[^>]+>", " ", h)).split())
              for h in re.findall(r"<th\b[^>]*>(.*?)</th>", head.group(1), re.S)]
    if not any(labels):
        return inner

    def row(m: re.Match) -> str:
        n = iter(range(10_000))
        cells = _CELL.sub(lambda c: (f'<td data-label="{_html_escape(labels[i], quote=True)}"'
                                     if (i := next(n)) < len(labels) and labels[i] else "<td"),
                          m.group(2))
        return m.group(1) + cells + m.group(3)

    return _TBODY.sub(lambda b: b.group(1) + _ROW.sub(row, b.group(2)) + b.group(3), inner, count=1)


def generated_footer(generated_at) -> str:
    """The footer of a page the console draws: when, and the one product name and version."""
    from onetrace_console import __version__
    return (f"<footer><p>Generated {time_html(generated_at)} by "
            f"onetrace-console {escape(__version__)}.</p></footer>")


def escape(text, quote: bool = True) -> str:
    """HTML-escaped, with a record's control, bidirectional and surrogate characters shown."""
    from onetrace_console.viewer.page import display
    return _html_escape(display(text), quote=quote)


def named(text, href: str | None = None) -> str:
    """A record's word -- a run_id, a stage name -- as a page shows it: escaped, and within the
    viewer's NAME_CAP whole; longer, its first NAME_CAP characters and, in the page's own words,
    how many more there are and that the whole value is in the run's record, a download of it
    where `href` names one. Keys and comparisons use the whole value."""
    from onetrace_console.viewer.model import NAME_CAP
    text = str(text)
    return escape(text[:NAME_CAP]) + rest(text, href)


def rest(text, href: str | None = None) -> str:
    """What `named` adds after a shortened word, in the page's own words; empty for a word shown
    whole. For a word inside a link, where a second link cannot go, it follows the link."""
    from onetrace_console.viewer.model import NAME_CAP
    from onetrace_console.viewer.sentences import template
    text = str(text)
    if len(text) <= NAME_CAP:
        return ""
    more = escape(template("name.more").format(n=str(len(text) - NAME_CAP)))
    whole = escape(template("name.whole"))
    where = f'<a href="{escape(href)}" download>{whole}</a>' if href else whole
    return f'<span data-words="page"> {more} · {where}</span>'


def shown_name(text) -> str:
    """`named` for plain text -- a page title, a sentence built around a name: no markup."""
    from onetrace_console.viewer.model import name_shown
    return name_shown(text)


def record_href(run) -> str:
    """Where a run's own record is served for download (`serve._handle_record`)."""
    return f"/runs/{run.key}/record.tar"


def verbatim_rows(text) -> str:
    """`verbatim` for the verifier's rows a page quotes -- an incident's quoted field -- with each
    row longer than the viewer's NAME_CAP drawn as its first NAME_CAP characters and the same
    marker: a row quotes the record's names, and one run's incidents pages were
    4.9 MB each. The whole row stays in the check report the run keeps."""
    from onetrace_console.viewer.model import NAME_CAP
    from onetrace_console.viewer.sentences import template
    rows = []
    for row in str(text).split("\n"):
        if len(row) > NAME_CAP:
            row = row[:NAME_CAP] + " " + template("name.more").format(n=str(len(row) - NAME_CAP))
        rows.append(row)
    return verbatim("\n".join(rows))


def verbatim(text) -> str:
    """For a layer that shows words as written (`<pre>`): as `escape`, keeping line breaks and
    tabs, which are how those words are laid out."""
    from onetrace_console.viewer.page import display
    return _html_escape(display(text, lines=True))


def run_named(store, key: str) -> str:
    """A run as a page names it -- its run id, then its short store key, in mono:
    `demo-run-2 · 1880b4aa455b` -- so a reader can tell two names are one run. Where the run's
    record cannot be read there is no run id to show, and none is invented: its key alone."""
    from onetrace_console.store import StoreError
    try:
        run = store.get_run(key)
    except StoreError:
        run = None
    short = escape(key[:12])
    if run is None or not run.run_id:
        return f'<span class="mono" data-run-name>{short}</span>'
    #: A run id past the cap is shown capped, with the run's record offered.
    return f'<span class="mono" data-run-name>{named(run.run_id, record_href(run))} · {short}</span>'
