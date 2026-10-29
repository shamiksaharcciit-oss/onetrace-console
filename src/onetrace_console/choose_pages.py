"""Choose two runs: links to the comparisons this console holds, and the request for the rest.

One page per pipeline lists its runs, newest first; each picks that run as run A, the baseline. Run
A's page lists the pipeline's other runs as run B. Where this console holds a comparison of the
pair (run A the baseline, run B the candidate), the row links to it. Where it holds none, the row
says "Not compared yet" and shows the request that makes it, `POST /compare` with both keys
filled in from the store's own values. On a local console the row also has a Compare button: its
script (`compare_script`) sends that same request, with the session's CSRF token, through the same
guards as any other, and opens the comparison the console answers with. No form posts, and no GET
route makes a comparison: a GET that wrote would be the opening a cross-site request needs. Without
the script the button stays hidden and the request stays shown. A public console makes no
comparison, so it lists only the pairs it holds, has no button, and says so.
"""
from __future__ import annotations

from onetrace_console.render import _document, _tag, run_named
from onetrace_console.store import Store, arrival_order
from onetrace_console.viewer.model import LIST_CAP
from onetrace_console.words import escape, generated_footer, scroll_region, time_html


def choose_href(label: str) -> str:
    """The page listing a pipeline's runs as run A."""
    return f"choose-{label.lower()}.html"


def pair_href(label: str, a_key: str) -> str:
    """Run A's page: the pipeline's other runs as run B."""
    return f"choose-{label.lower()}-{a_key}.html"


def b_anchor(b_key: str) -> str:
    """The id of run B's row on run A's page, which a link naming the pair opens at."""
    return f"b-{b_key}"


def compare_request(a_key: str, b_key: str) -> str:
    """The request that compares the pair, as text: run A the baseline, run B the candidate."""
    return f"POST /compare?a={a_key}&b={b_key}"


def _public() -> bool:
    from onetrace_console.frame import rendering_public
    return rendering_public()


def held_comparisons(store: Store) -> dict[tuple[str, str], object]:
    """(run A, run B) -> the newest comparison this console holds of the pair, in that direction."""
    from onetrace_console.render import _newest_first
    out: dict[tuple[str, str], object] = {}
    for c in sorted(store.comparisons(), key=_newest_first):
        out.setdefault((c.run_a, c.run_b), c)
    return out


def _run_link(store: Store, key: str) -> str:
    from onetrace_console.benchmarks import badge
    return f'<a href="runs/{_tag(key)}/case.html">{run_named(store, key)}</a>{badge(store, key)}'


def render_choose(pipeline, store: Store, *, generated_at: str) -> str:
    """A pipeline's runs, newest first by arrival, each picking itself as run A: at most the
    console's list cap, then how many more; any run is offered as run A on its own page too."""
    runs = arrival_order(pipeline.runs, newest_first=True)
    n = len(runs)
    more = n - LIST_CAP
    runs = runs[:LIST_CAP]
    rows = "".join(
        f'<tr data-run="{_tag(r.key)}"><td>{_run_link(store, r.key)}</td>'
        f'<td class="mono">{time_html(r.received_at)}</td>'
        f'<td><a href="{_tag(pair_href(pipeline.label, r.key))}">Choose as run A</a></td></tr>'
        for r in runs)
    listing = scroll_region('<table class="timeline" data-section="choose-a"><thead><tr>'
                            "<th>Run</th><th>Arrived</th><th></th></tr>"
                            f"</thead><tbody>{rows}</tbody></table>",
                            "Runs to choose from, scrolls sideways", "choose-a")
    if more > 0:
        from onetrace_console.viewer.sentences import template
        listing += f'<p data-section="more">{escape(template("list.more").format(n=str(more)))}</p>'
    body = [
        f'<p class="crumbs" data-section="crumbs"><a href="comparisons.html">Comparisons</a> / '
        f"{escape(pipeline.label)}</p>",
        f"<h1>Choose two runs · {escape(pipeline.label)}</h1>",
        f'<p data-section="what">{n} run{"" if n == 1 else "s"} of {escape(pipeline.label)}, newest '
        f"first by arrival, at most {LIST_CAP} of them. Choose run A, the baseline: its page lists "
        f"the other runs of {escape(pipeline.label)} as run B. Any run of {escape(pipeline.label)} "
        "can be chosen as run A from its own page.</p>",
        listing,
        generated_footer(generated_at),
    ]
    return _document(f"Choose two runs · {pipeline.label}", "\n".join(['<div class="cp">', *body, "</div>"]))


def render_pair(pipeline, a_run, store: Store, *, generated_at: str,
                held: dict | None = None) -> str:
    """Run A's page: each other run of the pipeline as run B, with the comparison of the two where
    this console holds one, and otherwise the request that makes it -- or, on a public console,
    only the pairs it holds."""
    public = _public()
    held = held_comparisons(store) if held is None else held
    others = [r for r in arrival_order(pipeline.runs, newest_first=True) if r.key != a_run.key]
    compared = [r for r in others if (a_run.key, r.key) in held]
    #: Every pair this console holds, always, first; then the newest of the rest, at most the
    #: console's list cap, and how many more there are, in the viewer's words.
    rest = [] if public else [r for r in others if (a_run.key, r.key) not in held]
    shown = compared + rest[:LIST_CAP]
    more = len(rest) - LIST_CAP
    rows = []
    for r in shown:
        c = held.get((a_run.key, r.key))
        if c is not None:
            cell = f'<a href="diff/{_tag(c.key)}.html">Open the comparison</a>'
            state = "compared"
        else:
            request = compare_request(a_run.key, r.key)
            cell = (f'<button type="button" hidden '
                    f'data-compare-post="{_tag(request.split(" ", 1)[1])}">Compare</button> '
                    f"Not compared yet. "
                    f'<code class="mono" data-command>{escape(request)}</code>'
                    f'<span data-compare-said role="status"></span>')
            state = "not-compared"
        rows.append(f'<tr data-run="{_tag(r.key)}" data-pair="{state}"><td><span id="{_tag(b_anchor(r.key))}"></span>'
                    f'{_run_link(store, r.key)}</td>'
                    f"<td>{cell}</td></tr>")
    label = escape(pipeline.label)
    if not others:
        listing = f'<p data-section="none">No other run of {label} is stored.</p>'
    elif not shown:
        listing = (f'<p data-section="none">None of the other runs of {label} has been compared '
                   "with this one as run A.</p>")
    else:
        listing = scroll_region('<table class="timeline" data-section="choose-b"><thead><tr>'
                                "<th>Run B</th><th>Comparison</th></tr>"
                                f"</thead><tbody>{''.join(rows)}</tbody></table>",
                                "Runs to compare with run A, scrolls sideways", "choose-b")
        if more > 0:
            from onetrace_console.viewer.sentences import template
            listing += f'<p data-section="more">{escape(template("list.more").format(n=str(more)))}</p>'

    if public:
        how = (f'<p data-section="how">This public console makes no comparison, so it lists only the '
               f"pairs it holds: {len(compared)} of the {len(others)} other runs of {label} "
               f"{'has' if len(compared) == 1 else 'have'} a comparison with this run as run A.</p>")
    else:
        how = ('<p data-section="how">A pair not compared yet has a Compare button, which sends this '
               "console the request shown beside it, with your session's CSRF token, and opens the "
               "comparison. The request can also be sent by hand, as the operator's guide shows.</p>")
    body = [
        f'<p class="crumbs" data-section="crumbs"><a href="comparisons.html">Comparisons</a> / '
        f'<a href="{_tag(choose_href(pipeline.label))}">{label}</a> / run A</p>',
        f"<h1>Choose run B · {label}</h1>",
        f'<p data-section="run-a">Run A, the baseline: {_run_link(store, a_run.key)}. The other runs '
        f"of {label} as run B, the candidate: those compared with it first, then the rest, newest "
        f"first by arrival, at most {LIST_CAP} of them.</p>",
        how,
        listing,
        generated_footer(generated_at),
    ]
    if not public and any('data-pair="not-compared"' in row for row in rows):
        from onetrace_console.compare_script import COMPARE_SCRIPT
        body.append(COMPARE_SCRIPT)
    return _document(f"Choose run B · {pipeline.label}", "\n".join(['<div class="cp">', *body, "</div>"]))


def choose_links(store: Store) -> str:
    """The Comparisons page's way in: one link per pipeline."""
    from onetrace_console.overview import pipelines
    every = pipelines(store)
    if not every:
        return ""
    links = " · ".join(f'<a href="{_tag(choose_href(p.label))}">{escape(p.label)}, '
                       f'{len(p.runs)} run{"" if len(p.runs) == 1 else "s"}</a>' for p in every)
    return (f'<section data-section="choose"><h2>Choose two runs</h2><p>From the runs of one '
            f"pipeline: {links}.</p></section>")
