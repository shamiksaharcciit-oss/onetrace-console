"""A run page's head, in the console only: who the run is, its chips, its times, the four
questions a reader asks first, and the tabs to the run's other pages.

Everything here is read from what the page already says or the store already holds: the run's id
and pipeline, the comparison its graph is marked from (and only that one,
naming its baseline), the record's own start time and format, the time this console received it,
and the page's own ladder rungs. Nothing is counted that the record does not hold, so a stage's
domain counts ("chunks", "vectors") never appear. The answer page draws the same head.
"""
from __future__ import annotations

import re

from onetrace_console import tones, twins
#: The viewer's one escape: HTML, and a record's words shown by its display rule (control and
#: direction characters drawn visibly), as every run page draws them.
from onetrace_console.viewer.page import escape
from onetrace_console.store import Store, StoredRun

#: The four rungs the head shows first, in the ladder's own words, each as the ladder states it.
HEAD_RUNGS = ("records-agree", "approved", "signed", "anchored")
#: What the head reads from the record's contents, rather than says about the record, carries
#: `data-from="contents"`: a run's "What changed" view withholds it where the record does not
#: hold up (`views.split`). Of the four rungs, "Ran as approved" compares the paths the record
#: holds with its plan; whether the records agree, are signed and are anchored is said of the
#: record itself. The comparison and declined chips, and the count of declared stages, are read
#: from its contents too.
HEAD_FROM_CONTENTS = {"approved"}
FROM_CONTENTS = ' data-from="contents"'

#: The tabs: each a page this run already has, or a place on this page.
TAB_GRAPH, TAB_TABLE, TAB_IO, TAB_RECEIPT, TAB_COMPARE = (
    "Graph", "Table", "Inputs & outputs", "Receipt", "Compare")
#: The run's page as run A, the baseline: the pipeline's other runs as run B (`choose_pages`).
TAB_CHOOSE = "Choose as run A"

HEAD_CSS = """
:is(.shell .page,.cp) [data-section=run-head]{display:flex;flex-direction:column;gap:10px;margin:0 0 6px}
:is(.shell .page,.cp) [data-section=run-head] .crumbs{margin:0;font-size:var(--fs-small);color:var(--ink-muted)}
:is(.shell .page,.cp) [data-section=run-head] .title{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
:is(.shell .page,.cp) [data-section=run-head] .chips{display:contents}
:is(.shell .page,.cp) [data-section=run-head] .run-title{margin:0;overflow-wrap:anywhere;
  font-size:var(--fs-h1);font-weight:600}
:is(.shell .page,.cp) [data-section=run-head] .pill{display:inline-block;font-size:var(--fs-small);
  font-weight:500;padding:3px 8px;border-radius:var(--r-pill);text-decoration:none}
:is(.shell .page,.cp) [data-section=run-head] .ok{background:var(--ok-bg);color:var(--ok-ink)}
:is(.shell .page,.cp) [data-section=run-head] .cc{background:var(--cc-bg);color:var(--cc-ink)}
:is(.shell .page,.cp) [data-section=run-head] .bad{background:var(--bad-bg);color:var(--bad-ink)}
:is(.shell .page,.cp) [data-section=run-head] .neu{background:var(--neu-bg);color:var(--neu-ink)}
:is(.shell .page,.cp) [data-section=run-head] .fd{background:var(--cc-ink);color:var(--page)}
:is(.shell .page,.cp) [data-section=run-head] .ca{background:transparent;color:var(--cc-ink);
  outline:1px solid var(--cc-ink);outline-offset:-1px}
:is(.shell .page,.cp) [data-section=run-head] .dec{background:transparent;color:var(--accent);
  outline:1px solid var(--accent);outline-offset:-1px}
:is(.shell .page,.cp) [data-section=run-head] .sub{margin:0;color:var(--ink-muted);overflow-wrap:anywhere}
:is(.shell .page,.cp) :is([data-section=run-head] .seals,.seals[data-section=answers]){display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
  margin:0;padding:0;list-style:none;border:1px solid var(--line);border-radius:var(--r-card);
  background:var(--surface)}
:is(.shell .page,.cp) :is([data-section=run-head] .seals,.seals[data-section=answers])>li{display:flex;flex-direction:column;gap:4px;
  padding:10px 14px;border-right:1px solid var(--line)}
:is(.shell .page,.cp) :is([data-section=run-head] .seals,.seals[data-section=answers])>li:last-child{border-right:none}
:is(.shell .page,.cp) :is([data-section=run-head] .seals,.seals[data-section=answers]) .q{font-size:var(--fs-small);color:var(--ink-muted)}
:is(.shell .page,.cp) [data-section=run-head] nav.tabs{display:flex;flex-wrap:wrap;gap:6px 24px;
  border-bottom:1px solid var(--line)}
:is(.shell .page,.cp) [data-section=run-head] nav.tabs a{padding:8px 2px;text-decoration:none;color:var(--ink-muted)}
:is(.shell .page,.cp) [data-section=run-head] nav.tabs a:hover{color:var(--ink)}
"""


def _chip(tone: str, words: str, href: str = "") -> str:
    if href:
        return f'<a class="pill {tone}" href="{escape(href)}">{escape(words)}</a>'
    return f'<span class="pill {tone}">{escape(words)}</span>'


def _time(value: str) -> str:
    from onetrace_console.words import short_time
    return (f'<time datetime="{escape(value)}" title="{escape(value)}">'
            f"{escape(short_time(value))}</time>")


def compared_with(model) -> tuple[str, str, bool] | None:
    """(the baseline's name, the comparison page's link, whether its report was read) for the
    comparison the page's graph is marked from; None where there is none."""
    if not model.graph_source:
        return None
    baseline, _at, href, readable = model.graph_source
    return baseline, href, readable


def comparison_chip(model) -> str:
    """The comparison chip: only where the run is a comparison's candidate, naming that
    comparison's baseline. "First difference at <stage>" only where the comparison found one;
    otherwise what it found, in the compare page's words."""
    source = compared_with(model)
    if source is None:
        return ""
    baseline, href, readable = source
    if not readable:
        return _chip(tones.tone(tones.DIFF, "COULD NOT CHECK"), f"Couldn't check the comparison with {baseline}", href)
    first = [n for n in model.graph_nodes if n.mark == "first"]
    if first:
        from onetrace_console.viewer.model import name_shown
        stage = name_shown(first[0].name)
        return _chip(tones.tone(tones.DIFF, "FIRST DIFFERENCE"), f"Changed vs {baseline} · first difference at {stage}", href)
    return _chip(tones.tone(tones.DIFF, "same"), f"No difference found vs {baseline}", href)


def declined_chip(run) -> str:
    """"Declined at <step>" where the run stopped at a step's own rule, in the declined outline;
    nothing otherwise. From the run's stored reading, as the runs list and the Overview read it."""
    from onetrace_console.overview import declined
    from onetrace_console.viewer.model import name_shown
    from onetrace_console.viewer.sentences import template
    found = declined(run)
    if found is None:
        return ""
    return (f'<span class="pill {tones.tone(tones.STOPPED, "declined")}" data-declined="true">'
            f'{escape(template("declined.chip").format(stage=name_shown(found["stage"])))}</span>')


def _rungs(model) -> str:
    from onetrace_console.viewer.page import _line
    from onetrace_console.viewer.sentences import template
    items = []
    for key in HEAD_RUNGS:
        found = [r for r in model.ladder if r.key == key]
        if not found:
            continue
        r = found[0]
        if r.state_key:
            said = _chip(tones.tone(tones.RUNG, r.state), template(r.state_key))
        else:
            said = " ".join(_line(e) for e in r.evidence)
        mark = FROM_CONTENTS if key in HEAD_FROM_CONTENTS else ""
        items.append(f'<li data-head-rung="{escape(key)}" data-state="{escape(r.state)}"{mark}>'
                     f'<span class="q">{escape(template("rung." + key))}</span> <span>{said}</span></li>')
    return f'<ul class="seals">{"".join(items)}</ul>'


def run_head(run: StoredRun, store: Store, model, *, stage_page: str = "", receipt: str = "",
             page: str = "", title_tag: str = "h1", rungs: bool = True,
             up: str = "../../") -> str:
    """The head, as HTML. `stage_page` and `receipt` are the run's sibling pages, where it has them."""
    from onetrace_console.overview import pipelines, ran_at
    label = next((p.label for p in pipelines(store) for r in p.runs if r.key == run.key), "")
    #: No one-word verdict beside the title: the ladder's questions are separate, and a "Verified"
    #: chip beside "Records agree: Not checked" (a check that held without the output files) would
    #: read as one answer the page does not give. The comparison chip is the only chip.
    chips = comparison_chip(model) + declined_chip(run)
    chips = f'<span class="chips"{FROM_CONTENTS}>{chips}</span>' if chips else ""
    ran = ran_at(run)
    count = (f"{run.delivered_stages} of {run.stage_count} declared stages"
             + (f"; {run.retries} retr{'y' if run.retries == 1 else 'ies'} recorded" if run.retries else ""))
    sub = [f'recorded in the format <span class="mono">{escape(run.format)}</span>' if run.format else "",
           f"ran {_time(ran)}" if ran else "the record gives no time it ran",
           f"received by this console {_time(run.received_at)}"]
    source = compared_with(model)
    #: `page`: the run page's file, where the head is on another of the run's pages.
    tabs = [(TAB_GRAPH, f"{page}#graph"), (TAB_TABLE, f"{page}#timeline")]
    tabs += [(TAB_IO, stage_page)] if stage_page else []
    tabs += [(TAB_RECEIPT, receipt)] if receipt else []
    tabs += [(TAB_COMPARE, source[1])] if source else []
    if label:
        from onetrace_console.choose_pages import pair_href
        tabs += [(TAB_CHOOSE, f"{up}{pair_href(label, run.key)}")]
    #: The run's id as the viewer quotes a record word: capped, with what was left out said and
    #: the whole record offered, as the viewer's own header did.
    from onetrace_console.viewer.page import _RECORD_HREF, _named, _rest
    token = _RECORD_HREF.set(getattr(model, "record_href", None))
    try:
        rest = _rest(run.run_id)
    finally:
        _RECORD_HREF.reset(token)
    crumbs = (f'<p class="crumbs"><a href="{up}executions-all.html">Runs</a>'
              + (f" / {escape(label)}" if label else "")
              + f' / <span class="mono" data-words="record">{_named(run.run_id)}</span></p>')
    return (f'<section data-section="run-head">{crumbs}'
            f'<div class="title"><{title_tag} class="run-title"><span class="mono" data-words="record">'
            f"{_named(run.run_id)}</span>"
            + (f" · {escape(label)}" if label else "") + f"</{title_tag}>{rest}{chips}</div>"
            f'<p class="sub"><span{FROM_CONTENTS}>{count} · </span>{" · ".join(s for s in sub if s)}</p>'
            #: Another folder carrying the same run and chain head: each is read on its own, and
            #: the page says which folder this is and how the other's files compare.
            + "".join(f'<p class="sub" data-twin="true">{escape(t)}</p>' for t in twins.sentences(run, store))
            #: Without its four answers on the authorization page, which must never read as a
            #: pass: "Ran as approved: Yes" there would read as the action approved.
            + (_rungs(model) if rungs else "") +
            f'<nav class="tabs" aria-label="This run\'s pages">'
            + " ".join(f'<a href="{escape(h)}">{escape(t)}</a>' for t, h in tabs)
            + "</nav></section>")


_TOP = re.compile(r'<header class="top">.*?</header>', re.S)


def with_head(page: str, head: str, anchors: bool = True) -> str:
    """`page` with the viewer's header replaced by the head, and the graph and the step table
    given the ids the tabs link to. Exactly one of each, or the page is refused: a splice that
    found nothing would leave a page that says less than it should, silently."""
    if len(_TOP.findall(page)) != 1:
        raise RuntimeError("the run page does not carry exactly one header")
    page = _TOP.sub(lambda _m: head, page, count=1)
    if not anchors:
        return page
    #: Each tab's target is an empty anchor just before its section: the section's own tag stays
    #: as the viewer draws it.
    for section in ("graph", "timeline"):
        old = f'<section data-section="{section}">'
        if page.count(old) != 1:
            raise RuntimeError(f"the run page does not carry exactly one {section} section")
        page = page.replace(old, f'<span id="{section}"></span>{old}')
    return page
