"""A pipeline's page, and the marks every view of a pipeline's runs draws.

A pipeline (`overview.pipelines`) is the runs that declare one stage list. Its page shows that
list as a chain, with under each stage how many of the pipeline's stored comparisons first differ
there, as each comparison's stored report reads (`overview.comparison_reading`); nothing is
compared for the page. Then its runs as tiles, oldest first: each run's "Records agree" as its own
page reads it (`records.state`), and its comparison as the Overview reads it
(`overview.vs_baseline`). Two filters, each its own page, hold exactly the runs the console's
counts hold: those whose records agree, and those that need attention. "Compare two runs" leads to
the pipeline's choice of two runs (`choose_pages`).

A mark is one run's "Records agree", told apart by shape as well as colour: a filled circle where
the records agree, a square with a cross where the run contradicts its record, a ring where it was
not checked, a diamond where it couldn't be checked, a dash where no verdict is recorded. Colour
follows the one rule (`tones.RUNG`); the words are always beside or behind it.
"""
from __future__ import annotations

from onetrace_console import records, tones
from onetrace_console.render import _document, _tag
from onetrace_console.store import Store
from onetrace_console.words import escape, generated_footer, record_href, rest, shown_name

#: The page's views: every run, the runs whose records agree, the runs that need attention.
FILTERS = ("all", "agree", "attention")
FILTER_WORDS = {"all": "All", "agree": "Records agree", "attention": "Need attention"}

#: Each state's shape, drawn in a 14 by 14 box: `f` is filled, `s` stroked.
MARK_SHAPES = {
    records.YES: '<circle class="f" cx="7" cy="7" r="6"/>',
    records.NO: '<rect class="s" x="1.5" y="1.5" width="11" height="11"/>'
                '<path class="s" d="M4.5 4.5L9.5 9.5M9.5 4.5L4.5 9.5"/>',
    records.NOT_CHECKED: '<circle class="s" cx="7" cy="7" r="5.2"/>',
    records.COULDNT: '<path class="s" d="M7 1.5L12.5 7L7 12.5L1.5 7Z"/>',
    records.NO_VERDICT: '<path class="s" d="M2 7H12"/>',
}

#: The sentence over the legend: what a mark is.
LEGEND_LEAD = "Each mark is one run's \"Records agree\", as its own page reads it:"
#: What a page says of a pipeline whose runs were never compared with each other.
NO_COMPARISON = "No comparison stored for this pipeline."
#: A run that no comparison holds as its candidate, but one holds as its baseline.
BASELINE_ONLY = "Baseline of a stored comparison"


def page_href(label: str, which: str = "all") -> str:
    """A pipeline's page, or one of its filters."""
    return f"pipeline-{label.lower()}.html" if which == "all" else f"pipeline-{label.lower()}-{which}.html"


def mark(state: str) -> str:
    """One run's mark, for sighted readers; its words are said beside it or by its group."""
    return (f'<svg class="mark" data-mark="{_tag(state)}" data-tone="{tones.tone(tones.RUNG, state)}" '
            f'viewBox="0 0 14 14" width="14" height="14" aria-hidden="true" focusable="false">'
            f"{MARK_SHAPES[state]}</svg>")


def count_line(runs, store: Store) -> str:
    """The runs' states in one line: each state with runs, as a count of them all."""
    total = len(runs)
    return " · ".join(f"{len(rs)} of {total} {records.counted(s, rs, store)}"
                      for s in records.STATES for rs in (records.runs_in(runs, store, s),) if rs)


def marks(runs, store: Store) -> str:
    """One mark per run, in the order given, as one image whose text is the count line."""
    return (f'<span class="marks" role="img" aria-label="{escape(count_line(runs, store))}">'
            + "".join(mark(records.state(r, store)) for r in runs) + "</span>")


def legend() -> str:
    """What each mark stands for, once on a page that draws them."""
    items = "".join(f'<li>{mark(s)} {escape(records.LABEL[s])}</li>' for s in records.STATES)
    return (f'<div data-section="legend"><p>{escape(LEGEND_LEAD)}</p>'
            f'<ul class="plain legend">{items}</ul></div>')


def name(pipeline) -> str | None:
    """The demo builder's name for the pipeline, on a public demo only and only where every one
    of its runs is the builder's own."""
    from onetrace_console.frame import rendering_public
    if not rendering_public():
        return None
    from onetrace_console import demo_store
    return demo_store.name_of(r.run_id for r in pipeline.runs)


def named(pipeline) -> str:
    """The pipeline's label, and its builder's name where `name` gives one."""
    n = name(pipeline)
    return escape(pipeline.label) + (f' · <span data-name>{escape(n)}</span>' if n else "")


def chain(pipeline, counts: dict | None = None) -> str:
    """The declared stages as a chain of small boxes; with `counts`, each stage's number of
    first differences under it."""
    items = []
    #: A stage is marked by its place in the declared list: its name is shown shortened, and a
    #: list of long names written whole into each mark made the page megabytes.
    for i, s in enumerate(pipeline.stages):
        n = "" if counts is None else f'<span class="n">{counts[s]}</span>'
        attrs = "" if counts is None else f' data-stage="{i}" data-first-differences="{counts[s]}"'
        items.append(f'<li{attrs}><span class="stage">{escape(shown_name(s))}</span>{n}</li>')
    more = ""
    if pipeline.more:
        from onetrace_console.viewer.sentences import template
        more = f'<li class="more">{escape(template("list.more").format(n=str(pipeline.more)))}</li>'
    return f'<ol class="chain" data-section="stage-chain">{"".join(items)}{more}</ol>'


#: The Overview's heading over the pipeline cards.
CARDS_HEADING = "Each pipeline's runs"


def card(pipeline, store: Store) -> str:
    """One pipeline on the Overview, the whole card one link to its page: its label (and its
    builder's name on a public demo), its declared stages, its run count, one mark per run in the
    order the console received them, and its states in one line."""
    n = len(pipeline.runs)
    return (f'<a class="pcard" data-pipeline-card="{_tag(pipeline.label)}" '
            f'href="{_tag(page_href(pipeline.label))}">'
            f"<h3>{named(pipeline)}</h3>{chain(pipeline)}"
            f'<p data-line="runs">{n} run{"" if n == 1 else "s"}</p>{marks(pipeline.runs, store)}'
            f'<p data-line="count">{escape(count_line(pipeline.runs, store))}</p></a>')


def cards_section(store: Store) -> str:
    """The Overview's pipeline cards, in pipeline id order, with the legend once above them."""
    from onetrace_console.overview import pipelines
    found = pipelines(store)
    if not found:
        return ""
    return (f'<section data-section="pipeline-cards" id="pipeline-cards"><div class="head">'
            f"<h2>{escape(CARDS_HEADING)}</h2></div>{legend()}"
            f'<div class="pcards">{"".join(card(p, store) for p in found)}</div></section>')


def held(pipeline, store: Store) -> list:
    """The stored comparisons of two of the pipeline's runs."""
    keys = {r.key for r in pipeline.runs}
    return [c for c in store.comparisons() if c.run_a in keys and c.run_b in keys]


def stage_counts(pipeline, store: Store) -> tuple[dict, int, int, int]:
    """(stage -> first differences there, comparisons, found none, couldn't be read)."""
    from onetrace_console.overview import comparison_reading
    counts = {s: 0 for s in pipeline.stages}
    same = unread = 0
    comparisons = held(pipeline, store)
    for c in comparisons:
        state, stages, _ = comparison_reading(c, store)
        if state == "changed":
            for s in stages:
                if s in counts:
                    counts[s] += 1
        elif state == "same":
            same += 1
        else:
            unread += 1
    return counts, len(comparisons), same, unread


def run_line(run, store: Store) -> str:
    """The run's comparison in one line, as the Overview reads it; a run only ever a stored
    comparison's baseline says so."""
    from onetrace_console.overview import vs_baseline
    state, words = vs_baseline(run, store)
    if state == "not-compared" and any(c.run_a == run.key for c in store.comparisons()):
        return BASELINE_ONLY
    return words


def runs_of(pipeline, store: Store, which: str) -> list:
    """The pipeline's runs a filter holds, oldest first: the console's own counts' runs."""
    if which == "agree":
        return list(records.runs_in(pipeline.runs, store, records.YES))
    if which == "attention":
        from onetrace_console.overview import attention_kind
        return [r for r in pipeline.runs if attention_kind(r, store) is not None]
    return list(pipeline.runs)


def _tile(i: int, run, store: Store) -> str:
    state = records.state(run, store)
    from onetrace_console.viewer.model import NAME_CAP
    return (f'<li data-run="{_tag(run.key)}" data-state="{_tag(state)}">'
            f'<a href="runs/{_tag(run.key)}/case.html"><span class="n">{i}</span> '
            f'<span class="mono" data-words="record">{escape(run.run_id[:NAME_CAP])}</span></a>'
            + rest(run.run_id, record_href(run)) +
            f'<p data-line="state">{mark(state)} {escape(records.said(run, store))}</p>'
            f'<p data-line="vs">{escape(run_line(run, store))}</p></li>')


def render_pipeline(pipeline, store: Store, *, generated_at: str, which: str = "all") -> str:
    """The pipeline's page, or one of its filters."""
    from onetrace_console.choose_pages import choose_href
    from onetrace_console.drift import page_href as drift_href
    counts, n_held, same, unread = stage_counts(pipeline, store)
    if n_held:
        said = (f"Under each stage: how many of this pipeline's {n_held} stored comparison"
                f"{'' if n_held == 1 else 's'} first differ there, as each one's stored report reads."
                + (f" {same} found no difference." if same else "")
                + (f" {unread} couldn't be read." if unread else ""))
    else:
        said = NO_COMPARISON
    number = {r.key: i for i, r in enumerate(pipeline.runs, start=1)}
    shown = runs_of(pipeline, store, which)
    filters = " · ".join(
        (f'<a href="{_tag(page_href(pipeline.label, f))}" aria-current="page">{FILTER_WORDS[f]}</a>'
         if f == which else f'<a href="{_tag(page_href(pipeline.label, f))}">{FILTER_WORDS[f]}</a>')
        for f in FILTERS)
    n = len(pipeline.runs)
    body = [
        '<p class="crumbs" data-section="crumbs"><a href="home.html">Overview</a> / '
        f"{escape(pipeline.label)}</p>",
        f"<h1>{named(pipeline)}</h1>",
        f'<p data-section="what">{n} run{"" if n == 1 else "s"} declaring these stages, oldest first '
        "as this console received them.</p>",
        f'<p data-section="compare"><a href="{_tag(choose_href(pipeline.label))}" '
        'data-link="compare">Compare two runs</a> · '
        f'<a href="{_tag(drift_href(pipeline.label))}" data-link="drift">Drift across its runs</a></p>',
        chain(pipeline, counts),
        f'<p data-section="first-differences">{escape(said)}</p>',
        f'<p data-section="filters">Show: {filters}</p>',
        f'<p data-section="shown">{len(shown)} of {n} run{"" if n == 1 else "s"} shown.</p>',
        legend(),
        '<ol class="tiles" data-section="runs">'
        + "".join(_tile(number[r.key], r, store) for r in shown) + "</ol>",
        generated_footer(generated_at),
    ]
    return _document(f"Pipeline · {pipeline.label}", "\n".join(['<div class="cp">', *body, "</div>"]))


# --------------------------------------------------------------- the public demo's way in

#: The way in's words.
WAY_IN_HEAD = "Start with a pipeline whose records agree"
CAUGHT_HEAD = "Then see what onetrace catches"
CAUGHT_LEAD = ("These runs were broken on purpose when this demo was built. Each shows what was done "
               "to it, and what its own page reads from its record.")
#: Below the heading: the planted runs whose every reading is the clean one.
NOT_FLAGGED_HEAD = "Also planted, and not flagged by any check:"
#: The planted runs' tables' columns.
PLANTED_COLUMNS = ("Run", "What was done to it", "What its page reads")
ALL_PIPELINES = "See all pipelines"


def first_pipeline(store: Store):
    """The pipeline with the most runs whose every run's records agree (`records.state`), the
    lower id first on a tie; None where no pipeline's runs all agree."""
    from onetrace_console.overview import pipelines
    clean = [p for p in pipelines(store) if all(records.state(r, store) == records.YES for r in p.runs)]
    return max(clean, key=lambda p: (len(p.runs), -int(p.label[1:])), default=None)


def flagged(run, store: Store) -> bool:
    """At least one of a planted run's readings is not the clean one: its records do not agree,
    its signer reads other than Yes, or it needs attention."""
    from onetrace_console.overview import attention_kind
    from onetrace_console.pages import run_answers
    return (records.state(run, store) != records.YES or run_answers(run, store)["signed"] != "yes"
            or attention_kind(run, store) is not None)


def _caught(run, line: str, signing: bool, store: Store) -> str:
    """One planted run, a row of three cells: its link; the builder's line; one badge, the run's
    "Records agree" state with its mark and words, and, where the plant is about signing, the
    signing result as its own page reads it (`pages.run_answers`, in the runs list's words)."""
    from onetrace_console.pages import run_answers
    from onetrace_console.viewer.model import NAME_CAP
    from onetrace_console.viewer.sentences import template
    state = records.state(run, store)
    signed = run_answers(run, store)["signed"]
    sign = (f' · <span data-signed="{_tag(signed)}">Signed by a known recorder: '
            f'{escape(template("rung.state." + signed.replace("-", "_")))}</span>' if signing else "")
    return (f'<tr data-planted="{_tag(run.key)}"><td><a href="runs/{_tag(run.key)}/case.html">'
            f'<span class="mono" data-words="record">{escape(run.run_id[:NAME_CAP])}</span></a>'
            f"{rest(run.run_id, record_href(run))}</td><td>{escape(line)}</td>"
            f'<td><span data-reading="{_tag(state)}">{mark(state)} {escape(records.said(run, store))}</span>'
            f"{sign}</td></tr>")


def _planted_table(group: str, label: str, rows: str) -> str:
    """The planted runs of one group, a table of the three columns; on a narrow screen its rows
    stack, each cell under its column's header (`words.scroll_region`)."""
    from onetrace_console.words import scroll_region
    head = "".join(f'<th scope="col">{escape(c)}</th>' for c in PLANTED_COLUMNS)
    return scroll_region(f'<table class="board" data-group="{group}"><thead><tr>{head}</tr></thead>'
                         f"<tbody>{rows}</tbody></table>", label, f"planted-{group}")


def way_in(store: Store) -> str:
    """The public demo's Overview opens here: the pipeline whose every run's records agree, then
    every run the demo builder broke on purpose, then a link to all pipelines. Nothing on a local
    console, nor on a public one whose runs are not the builder's."""
    from onetrace_console.frame import rendering_public
    if not rendering_public():
        return ""
    from onetrace_console import demo_store
    by_id = {r.run_id: r for r in store.runs()}
    specs = [s for s in demo_store.runs() if demo_store.planted(s)]
    if any((s.run_id or s.folder) not in by_id for s in specs):
        return ""
    out = []
    first = first_pipeline(store)
    if first is not None:
        n = len(first.runs)
        out.append(f'<section data-section="way-in" data-pipeline="{_tag(first.label)}">'
                   f"<h2>{escape(WAY_IN_HEAD)}</h2><h3>{named(first)}</h3>{chain(first)}"
                   f"{marks(first.runs, store)}"
                   f'<p data-line="count">{escape(count_line(first.runs, store))}</p>'
                   f'<p><a href="{_tag(page_href(first.label))}">See its {n} run{"" if n == 1 else "s"}</a></p>'
                   "</section>")
    rows = [(by_id[s.run_id or s.folder], demo_store.PLANTED[s.folder], demo_store.about_signing(s))
            for s in specs]
    caught = "".join(_caught(r, line, sg, store) for r, line, sg in rows if flagged(r, store))
    quiet = "".join(_caught(r, line, sg, store) for r, line, sg in rows if not flagged(r, store))
    out.append(f'<section data-section="planted"><h2>{escape(CAUGHT_HEAD)}</h2>'
               f'<p>{escape(CAUGHT_LEAD)}</p>{_planted_table("caught", "The planted runs a check flags", caught)}'
               + (f'<div data-section="not-flagged"><p>{escape(NOT_FLAGGED_HEAD)}</p>'
                  f'{_planted_table("not-flagged", "The planted runs no check flags", quiet)}</div>'
                  if quiet else "")
               + "</section>")
    out.append(f'<p data-section="all-pipelines"><a href="#pipeline-cards">{escape(ALL_PIPELINES)}</a></p>')
    return "".join(out)
