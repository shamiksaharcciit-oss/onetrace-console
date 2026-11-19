"""The Runs page, `/runs`: one page of runs across pipelines, drawn as asked from the run index (`run_index`).

What it shows, and where each comes from:
- **Filters** above the table, one `GET` form with no script. Each filter is a term of the index's query: pipeline
  (`pipeline:`), records agree (`agree:`), against the reference (`word:`), the verifier's verdict (`verdict:`), and
  the record's start (`after:`, `before:`). A filter given writes its term into the search box, so the page and the
  search share one engine and a person learns its grammar by using the form. A filter left empty adds no term, and
  none is on by default, so no run is hidden by a default.
- **The table**, newest first, in the runs list's words (`pages.runs_table`), read from each run's list entry in the
  index (`run_index.LIST`): the run, its pipeline, its recorded start and how long it took, records agree, its
  verdict against its pipeline's reference, and how it closed; a format 0.5 run's kinds where some listed run records
  one. Under each run, "More": how far it got, when this console received it, and the three other answers the runs
  list shows.
- **Paged at 50 runs**: "Runs 1-50 of N", and its pages are links that keep the filters.
- **How many of the runs listed the verifier FAILs**, with the filter that lists them, wherever they fall in the pages.

Every list and every count on the page goes through one function, `select`, so a later release can scope what it
answers (by team) in one place, and nothing on the page says that a run it did not answer exists. The page reads the
index and nothing else: it runs no check, no comparison and no model, on either console.
"""

from __future__ import annotations

from urllib.parse import urlencode

from onetrace_console.authorization_list import gated_words
from onetrace_console.words import escape

PATH = "runs"
TITLE = "Runs"
PER_PAGE = 50
#: The longest value of a parameter read; the rest of a longer one is not read.
MOST_CHARS = 1000
EMPTY = "No run is held here yet."
NONE_FOUND = "No run matches every term."
#: The filters, in the order their terms are written into the search box: (parameter, the term's field, label).
FILTERS = (
    ("pipeline", "pipeline", "Pipeline"),
    ("agree", "agree", "Records agree"),
    ("word", "word", "Against the reference"),
    ("verdict", "verdict", "The verifier's verdict"),
    ("after", "after", "Started after"),
    ("before", "before", "Started before"),
)
COLUMNS = ("Run", "Pipeline", "Started · took", "Steps", "Records agree", "Against the reference", "Closed")
KINDS_COLUMN = "Kinds"
NO_TIMES = "no recorded times"
NEEDS_CONSOLE = "Needs a running console."
NO_VERDICT = "no verdict held"
#: With no one pipeline chosen, where the bisect line would be.
BISECT_NONE = "Choose a pipeline to find the first run to leave its reference."
#: Over the pairs already compared, in the picker's section.
HELD_LEAD = "Compared already:"
OPENS_AT_ONCE = "opens at once"
#: The page's skip link, its first focusable item, to the table.
SKIP = ("Skip to the runs", "the-runs")
#: The parameters that choose a pair in the picker (a busy page's way back names both), never a filter.
PAIR_PARAMS = ("a", "b")
#: An index written before it held each run's list words: a public console reads its build's and never writes one; a
#: local console writes its own when it next draws its pages.
NOT_LISTED_PUBLIC = "This build's index of its runs was written before it held each run's list words; build it again."
NOT_LISTED_LOCAL = (
    "This console's index of its runs was written before it held each run's list words; the console writes it again "
    "when it next draws its pages."
)


def select(index: dict, q: str = "") -> list[dict]:
    """The runs the index answers for the query `q`, newest first: every run where `q` holds no term. The one function
    every list and count on the page reads, so what it answers is all the page can name. `QueryError` where the
    grammar does not hold `q`."""
    from onetrace_console.run_index import query

    runs = [r.run for r in query(index, q)] if q.strip() else list(index.get("runs") or [])
    return sorted(runs, key=lambda r: r.get("order", 0), reverse=True)


def took(ran: str) -> str:
    """How long a run took, from its recorded start and end ("<start> → <end>"), in words; "" where either
    cannot be read or the end is before the start."""
    from onetrace_console.run_index import _instant

    start, _, end = (ran or "").partition(" → ")
    a, b = _instant(start), _instant(end)
    if a is None or b is None or b < a:
        return ""
    seconds = (b - a).total_seconds()
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s" if seconds < 10 else f"{seconds:.0f} s"
    minutes, s = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes} min {s} s"
    hours, m = divmod(minutes, 60)
    return f"{hours} h {m} min"


def _terms(params: dict[str, str]) -> str:
    """The query the page asks: the search box's terms, less any of a field a filter gives, then each filter's term."""
    from onetrace_console.run_index import _TOKEN

    given = {field: params[p].strip() for p, field, _ in FILTERS if (params.get(p) or "").strip()}
    kept = [t for t in _TOKEN.findall(params.get("q") or "") if t.partition(":")[0].lower() not in given]
    return " ".join(kept + [f"{field}:{value}" for field, value in given.items()])


def _options(name: str, values: list[tuple[str, str]], chosen: str) -> str:
    opts = "".join(
        f'<option value="{escape(v)}"{" selected" if v == chosen else ""}>{escape(w)}</option>' for v, w in values
    )
    return f'<select name="{name}">{opts}</select>'


def _form(index: dict, params: dict[str, str], q: str, *, disabled: bool) -> str:
    """The filters and the search box, one `GET` form to this page. The pipelines and verdict words offered are those
    `select` answers, so none offered names a run the page cannot list."""
    from onetrace_console.run_index import AGREE_STATES
    from onetrace_console.search_page import _grammar
    from onetrace_console.viewer.sentences import template

    everything = select(index)
    labels = sorted(
        {r["pipeline_label"] for r in everything if r.get("pipeline_label")},
        key=lambda s: (len(s), s),
    )
    words = sorted({r["list"]["word"] for r in everything if r["list"]["word"]})
    anyone = [("", "Any")]
    chosen = {p: (params.get(p) or "").strip() for p, _f, _l in FILTERS}
    if disabled:
        #: A static export: a file has no console to ask, so it names each filter and carries no control at all.
        named = ", ".join(label for _p, _f, label in FILTERS)
        return (
            f'<div data-runs="filters" data-needs-console><p class="note" data-needs-console>'
            f"{escape(f'Filters: {named}. ' + NEEDS_CONSOLE)}</p></div>" + _grammar()
        )
    #: Each list filter's options, by its parameter's name (a form's, never the run's stored fields).
    offered = dict(
        zip(
            ("pipeline", "agree", "word", "verdict"),
            (
                [(v, v) for v in labels],
                [(s, template("rung.state." + s.replace("-", "_"))) for s in AGREE_STATES],
                [(w, w) for w in words],
                [("PASS", "PASS"), ("FAIL", "FAIL")],
            ),
            strict=True,
        )
    )
    controls = {p: _options(p, anyone + values, chosen[p]) for p, values in offered.items()}
    for p in ("after", "before"):
        value = chosen[p]
        kind = "date" if not value or len(value) == 10 else "text"
        controls[p] = f'<input type="{kind}" name="{p}" value="{escape(value)}">'
    active = sum(1 for v in chosen.values() if v)
    fields = "".join(f'<label data-filter="{p}">{escape(label)} {controls[p]}</label>' for p, _f, label in FILTERS)
    inner = (
        f"<details open><summary>Filter{f' ({active} active)' if active else ''}</summary>"
        f'<fieldset class="filters">{fields}</fieldset></details>'
        f'<fieldset class="search-box"><label>Search the runs by recorded field '
        f'<input type="search" name="q" value="{escape(q)}" spellcheck="false" autocomplete="off"></label>'
        f' <button class="btn-primary" data-busy="Listing…" type="submit">Apply</button></fieldset>'
    )
    return f'<form method="get" action="{PATH}" role="search" data-runs="filters">{inner}</form>' + _grammar()


def _href(params: dict[str, str], page: int) -> str:
    keep = [(p, params[p]) for p, _f, _l in FILTERS if (params.get(p) or "").strip()]
    if (params.get("q") or "").strip():
        keep.append(("q", params["q"]))
    return escape(f"{PATH}?" + urlencode(keep + [("page", str(page))]))


def _chip(state: str) -> str:
    from onetrace_console.pages import rung_chip

    return rung_chip(state)


def _verdict(entry: dict) -> str:
    from onetrace_console import verdicts

    if entry.get("unchecked"):
        return f'<span class="pill neu" data-verdict-word="unchecked">{escape(verdicts.UNCHECKED)}</span>'
    if not entry.get("word"):
        return f'<span class="note">{escape(NO_VERDICT)}</span>'
    said = f"verdict: {entry['word']}" + (f" {entry['word_at']}" if entry.get("word_at") else "")
    seal = entry.get("seal") or ""
    return f'<span class="pill neu" data-verdict-word="{escape(entry["word"])}">{escape(said)}</span>' + (
        f" {verdicts.against_html(seal)}" if seal else ""
    )


def _started(entry: dict, longest: float, label: str = "") -> str:
    """The run's recorded start, how long it took, and its timing bar on the page's scale; "no recorded times", and no
    bar, where its start does not read. With one pipeline chosen (`label`), the start links into the first run to leave
    after it, as on that page."""
    from onetrace_console import step_marks
    from onetrace_console.bisect_page import ask_href
    from onetrace_console.run_index import _instant
    from onetrace_console.words import time_html

    start = (entry.get("ran") or "").partition(" → ")[0].strip()
    if _instant(start) is None:
        return f'<span class="note">{escape(NO_TIMES)}</span>'
    long = took(entry["ran"])
    when = time_html(start)
    return (
        (f'<a href="{ask_href(label, start)}">{when}</a>' if label else when)
        + (f" · took {escape(long)}" if long else "")
        + step_marks.bar(entry["ran"], entry.get("steps"), longest)
    )


def longest(shown: list[dict]) -> float:
    """The page's one scale for its bars: the longest duration among the runs it shows, in seconds; 0 where none
    reads."""
    from onetrace_console.step_marks import seconds

    return max((t for r in shown for t in (seconds(r["list"].get("ran") or ""),) if t is not None), default=0.0)


def _row(r: dict, columns: int, kinds: bool, scale: float, chosen: str, first: str | None = None) -> str:
    from onetrace_console import closing, drift_strip, rerun_label, step_kinds, step_marks
    from onetrace_console.benchmarks import BADGE
    from onetrace_console.pipeline_pages import page_href
    from onetrace_console.run_head import declined_pill
    from onetrace_console.viewer.page import _named
    from onetrace_console.words import time_html

    e = r["list"]
    label = r.get("pipeline_label") or ""
    folder = r.get("folder") or ""
    badge = (
        f' <span class="pill neu" data-benchmark title="{escape(r["benchmark"]["note"])}">{BADGE}</span>'
        if r.get("benchmark")
        else ""
    )
    got = f"{e['delivered']} of {e['stages']} declared stages" + (
        f"; {e['retries']} retr{'y' if e['retries'] == 1 else 'ies'} recorded" if e.get("retries") else ""
    )
    more = (
        f"<dt>How far it got</dt><dd>{escape(got)}"
        + (f" {declined_pill(e['declined'])}" if e.get("declined") else "")
        + "</dd>"
        f'<dt>Received by this console</dt><dd class="value">{time_html(e["received"])}</dd>'
        f'<dt>Signed by a known recorder</dt><dd data-answer="signed">{_chip(e["signed"])}</dd>'
        f'<dt>Committed by a known time</dt><dd data-answer="anchored">{_chip(e["anchored"])}</dd>'
        f'<dt>Ran as approved</dt><dd data-answer="approved">{_chip(e["approved"])}</dd>'
    )
    return (
        f'<tr data-run="{_named(r["run_id"])}" data-key="{escape(r["key"])}">'
        f'<td><a href="runs/{escape(r["key"])}/case.html"><span class="mono" data-words="record">'
        f"{_named(r['run_id'])}</span></a>{badge}"
        + (f"<br>{rerun_label.pill(e.get('rerun'))}" if e.get("rerun") else "")
        #: A run whose record names a gated step: marked, leading to its Authorization page.
        + (
            f'<br><a class="pill neu" data-gated="{int(e["gated"])}" href="runs/{escape(r["key"])}/authorization.html">'
            f"{escape(gated_words(int(e['gated'])))}</a>"
            if isinstance(e.get("gated"), int) and e["gated"] > 0
            else ""
        )
        + (
            f'<br><span class="note mono" data-words="record">{escape(folder)}</span>'
            if folder and folder != r["run_id"]
            else ""
        )
        + "</td>"
        + (f'<td><a href="{page_href(label)}">{escape(label)}</a></td>' if label else "<td></td>")
        + f'<td class="value" data-answer="started">{_started(e, scale, chosen)}</td>'
        f'<td data-answer="steps">{step_marks.cell(e.get("steps"))}</td>'
        f'<td data-answer="records-agree">{_chip(e["records-agree"])}</td>'
        f'<td data-answer="verdict">{_verdict(e)}</td>'
        f'<td data-answer="closed" data-ending="{closing.state(e["ending"])}">{closing.html(e["ending"])}</td>'
        + (f'<td data-answer="kinds">{step_kinds.cell(e.get("kinds") or "")}</td>' if kinds else "")
        + (f'<td data-answer="drift">{drift_strip.cell(e.get("drift"), r["key"] == first)}</td>' if chosen else "")
        + "</tr>"
        f'<tr class="more-row" data-more-of="{escape(r["key"])}"><td colspan="{columns}">'
        f'<details><summary>More</summary><dl class="more">{more}</dl></details></td></tr>'
    )


def _table(shown: list[dict], label: str = "", first: str | None = None) -> str:
    from onetrace_console import drift_strip, step_kinds, step_marks, verdicts
    from onetrace_console.words import RELATIVE_TIME_SCRIPT, scroll_region

    kinds = any(step_kinds.records_any(r["list"].get("kinds") or "") for r in shown)
    columns = COLUMNS + ((KINDS_COLUMN,) if kinds else ()) + ((drift_strip.COLUMN,) if label else ())
    head = "".join(f'<th scope="col">{escape(c)}</th>' for c in columns)
    scale = longest(shown)
    body = "".join(_row(r, len(columns), kinds, scale, label, first) for r in shown)
    said = (
        f'<p class="note" data-runs="scale">{escape(step_marks.SCALE.format(longest=_seconds_said(scale)))}</p>'
        if scale > 0
        else ""
    )
    table = scroll_region(
        f'<table class="timeline" data-section="runs-page" id="{SKIP[1]}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>',
        "The runs",
        "runs-page",
    )
    return (
        said
        + table
        + step_marks.legend()
        + (drift_strip.legend() if label else "")
        + verdicts.seals_note(r["list"].get("seal") or None for r in shown)
        + RELATIVE_TIME_SCRIPT
    )


def _seconds_said(seconds: float) -> str:
    """A duration in seconds in the words `took` uses."""
    from datetime import UTC, datetime, timedelta

    a = datetime(2000, 1, 1, tzinfo=UTC)
    return took(f"{a.isoformat()} → {(a + timedelta(seconds=seconds)).isoformat()}")


def chosen_pipeline(index: dict, params: dict[str, str]) -> str:
    """The one pipeline the filters choose, as `select` offers it; "" where none is chosen or it names none offered."""
    said = (params.get("pipeline") or "").strip()
    return said if said and any(r.get("pipeline_label") == said for r in select(index)) else ""


def _bisect_line(label: str) -> str:
    """Above the table: with one pipeline chosen, the first-run-to-leave page's own form; else what would draw it."""
    from onetrace_console.bisect_page import window_form

    if not label:
        return f'<p class="note" data-runs="bisect">{escape(BISECT_NONE)}</p>'
    return f'<div data-runs="bisect">{window_form(label)}</div>'


def _picker(index: dict, label: str, params: dict[str, str], *, public: bool) -> str:
    """Under the filters, with one pipeline chosen: the pipeline page's picker of two of its runs, from the index, oldest
    first, posting `POST /compare` as it does there; the pairs already compared listed first, each opening at once."""
    from onetrace_console.pipeline_pages import local_picker_of
    from onetrace_console.visitor_compare import picker_of

    runs = sorted((r for r in select(index) if r.get("pipeline_label") == label), key=lambda r: r.get("order", 0))
    named = {r["key"]: r["run_id"] for r in runs}
    held = [c for c in index.get("comparisons") or [] if c.get("a") in named and c.get("b") in named]
    before = (
        f'<div data-runs="held-pairs"><p>{escape(HELD_LEAD)}</p><ul class="plain">'
        + "".join(
            f'<li data-held-pair><a href="diff/{escape(c["key"])}.html"><span class="mono" data-words="record">'
            f'{escape(named[c["a"]])}</span> → <span class="mono" data-words="record">{escape(named[c["b"]])}'
            f"</span></a> · {escape(OPENS_AT_ONCE)}</li>"
            for c in held
        )
        + "</ul></div>"
        if held
        else ""
    )
    chosen = ((params.get("a") or "").strip(), (params.get("b") or "").strip())
    if public:
        return picker_of([r["run_id"] for r in runs], chosen, before=before)
    return local_picker_of(
        [(r["key"], r["run_id"], r["list"].get("received") or "") for r in runs], chosen, before=before
    )


def _not_held(index: dict | None, *, public: bool, found: str | None) -> str:
    """Why there is no list to draw: no index, or one written before it held each run's list words; "" where there is."""
    from onetrace_console.run_index import LIST
    from onetrace_console.search_page import no_index

    if index is None:
        return f'<p data-runs="no-index">{escape(no_index(found, public=public))}</p>'
    if index.get(LIST) is None:
        return f'<p data-runs="not-listed">{escape(NOT_LISTED_PUBLIC if public else NOT_LISTED_LOCAL)}</p>'
    return ""


def body(
    index: dict | None, params: dict[str, str], *, public: bool, found: str | None = None, exported: bool = False
) -> str:
    """The page's content. `params`: the filters (`FILTERS`), `q` and `page` (a number from 1, or `all`). `found`:
    where `index` is None, the format the index beside the console states, if it states one. `exported`: drawn for a
    static export, its form shown disabled, every run on one page."""
    from onetrace_console.run_index import QueryError

    head = f"<h1>{escape(TITLE)}</h1>"
    missing = _not_held(index, public=public, found=found)
    if missing or index is None:
        return head + missing
    q = _terms(params)
    form = _form(index, params, q, disabled=exported)
    label = "" if exported else chosen_pipeline(index, params)
    if not exported:
        form += _picker(index, label, params, public=public) if label else ""
    if not select(index):
        return head + form + f'<p class="zero" data-runs="empty">{escape(EMPTY)}</p>'
    try:
        found_runs = select(index, q)
    except QueryError as e:
        return head + form + f'<p data-runs="refused" role="alert">Not asked: {escape(str(e))}.</p>'
    n = len(found_runs)
    if not n:
        return head + form + f'<p data-runs="none">{escape(NONE_FOUND)}</p>'
    asked = "all" if exported else (params.get("page") or "1").strip()
    pages = (n + PER_PAGE - 1) // PER_PAGE
    if asked == "all":
        number, shown = 0, found_runs
    else:
        number = int(asked) if asked.isdigit() and int(asked) > 0 else 1
        if number > pages:
            return (
                head + form + f'<p data-runs="no-page">There is no page {number}: the runs listed fill {pages} '
                f'page{"" if pages == 1 else "s"}. <a href="{_href(params, 1)}">The first page</a>.</p>'
            )
        shown = found_runs[(number - 1) * PER_PAGE : number * PER_PAGE]
    first = 1 if number == 0 else (number - 1) * PER_PAGE + 1
    count = f'<p data-runs="count">Runs {first}–{first + len(shown) - 1} of {n}</p>'
    fails = sum(1 for r in found_runs if (r.get("verdict") or "").upper() == "FAIL")
    fail_line = ""
    if fails:
        listing = _href({**params, "verdict": "FAIL"}, 1)
        fail_line = (
            f'<p data-runs="fails">{fails} of these {n} run{"" if n == 1 else "s"}: the verifier\'s verdict FAIL. '
            f'<a href="{listing}">List them</a>.</p>'
            if "verdict:fail" not in q.lower()
            else f'<p data-runs="fails">{fails} of these {n} run{"" if n == 1 else "s"}: the verifier\'s verdict FAIL.</p>'
        )
    links = ""
    if pages > 1 and number:
        items = "".join(
            f'<li><a href="{_href(params, p)}"' + (' aria-current="page"' if p == number else "") + f">{p}</a></li>"
            for p in range(1, pages + 1)
        )
        links = f'<nav aria-label="Pages of runs" data-runs="pages"><ul class="plain inline">{items}</ul></nav>'
    bisect = "" if exported else _bisect_line(label)
    drift = ""
    leaving = None
    if label:
        from onetrace_console import drift_strip

        #: The pipeline's runs as `select` answers them, every page's: the first to leave and the counts are of these.
        mine = [r for r in found_runs if r.get("pipeline_label") == label]
        leaving = drift_strip.first_to_leave(mine)
        drift = (
            f'<p class="note" data-runs="drift-order">{escape(drift_strip.ORDER.format(label=label))}</p>'
            f'<p data-runs="drift-counts">{escape(drift_strip.counts(mine))}</p>'
        )
    return head + form + count + fail_line + bisect + drift + _table(shown, label, leaving) + links


def page(
    index: dict | None, params: dict[str, str], *, public: bool, found: str | None = None, exported: bool = False
) -> str:
    """The whole page, its frame empty for the server to fill as it does every page's."""
    from onetrace_console.render import _document

    said = body(index, params, public=public, found=found, exported=exported)
    skip = SKIP if f'id="{SKIP[1]}"' in said else None
    return _document(TITLE, f'<div class="cp">{said}</div>', skip=skip)
