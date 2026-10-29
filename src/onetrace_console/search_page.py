"""The index's search: a box on the Runs page and on each run's page, and the page of results.

The box is a plain `GET` form to `/search` (`q`, and on a run's page `run`, the run it was asked
from). The results page reads the index the store root holds (`run_index`) and nothing else, and
draws each matching run with the fields that matched, as recorded, its benchmark badge, and "Compare
with this run" against the run it was asked from: the held comparison where the console holds one;
on a local console, a press that makes it; on a public console, the held pairs only. A query runs
no check, no comparison and no model, on either console.
"""
from __future__ import annotations

from urllib.parse import quote

from onetrace_console.words import escape

PATH = "search"
TITLE = "Search the runs"
LABEL = "Search the runs by recorded field"
BUTTON = "Search"
NO_INDEX = ("This console holds no index of its runs yet. It is built from the records whenever the "
            "console draws its pages.")
NONE_FOUND = "No run matches every term."
COMPARE = "Compare with this run"
NOT_HELD = "not compared on this demo"
ASKED_FROM = "Compared with {run}, the run this search was asked from."
#: The longest query read; the rest of a longer one is not read.
MOST_CHARS = 1000
EXAMPLES = ("setting:*.chunk_size=512", "first_diff:any:setting", "benchmark:yes", "verdict:FAIL")


def box(*, up: str = "", run_key: str = "", q: str = "") -> str:
    """The search box: a `GET` form to the results page, holding the run it is asked from. A static
    export leaves it out (`export_static.without_run_tools`): a file has no console to ask."""
    hidden = f'<input type="hidden" name="run" value="{escape(run_key)}">' if run_key else ""
    return (f'<form method="get" action="{up}{PATH}" role="search" class="search-box" data-search-box>'
            f'<label>{escape(LABEL)} <input type="search" name="q" value="{escape(q)}" '
            f'placeholder="{escape(EXAMPLES[0])}" spellcheck="false" autocomplete="off"></label>{hidden}'
            f' <button type="submit">{escape(BUTTON)}</button></form>')


def _grammar() -> str:
    from onetrace_console.run_index import GRAMMAR
    rows = "".join(f"<li><code>{escape(t)}</code>: {escape(w)}</li>" for t, w in GRAMMAR)
    return (f'<details data-search="grammar"><summary>What can be asked</summary><p>Each term is a field '
            f"the record names; every term must match. Values are matched exactly, as recorded.</p>"
            f'<ul class="plain">{rows}</ul></details>')


def _held(store, a_key: str, b_key: str):
    from onetrace_console.what_changed import held
    return held(store, a_key, b_key)


def _compare_cell(store, result: dict, asked: dict | None, *, public: bool) -> str:
    """"Compare with this run": against the run asked from, earlier run first as the baseline."""
    if asked is None or asked["key"] == result["key"]:
        return ""
    a, b = (asked, result) if asked["order"] < result["order"] else (result, asked)
    c = _held(store, a["key"], b["key"])
    if c is not None:
        return f'<a href="diff/{escape(c.key)}.html" data-search="compare">{escape(COMPARE)}</a>'
    if public:
        return f'<span data-search="not-held">{escape(NOT_HELD)}</span>'
    from onetrace_console.compare_script import COMPARE_SCRIPT
    return (f'<button type="button" hidden data-compare-post="/compare?a={escape(a["key"])}&amp;b={escape(b["key"])}">'
            f"{escape(COMPARE)}</button><span data-compare-said></span>{COMPARE_SCRIPT}")


def _asked_from(index: dict, run_key: str, terms) -> dict | None:
    """The run the search was asked from: its page's run, or the run a same-as term names."""
    from onetrace_console.run_index import QueryError, find_run
    if run_key:
        return next((r for r in index.get("runs") or [] if r["key"] == run_key), None)
    for t in terms:
        if t.field in ("inputs", "diff"):
            try:
                return find_run(index, t.value)
            except QueryError:
                return None
    return None


def body(index: dict | None, q: str, run_key: str, store, *, public: bool) -> str:
    from onetrace_console.benchmarks import BADGE
    from onetrace_console.run_index import QueryError, parse, query
    head = f'<h1>{escape(TITLE)}</h1>{box(q=q, run_key=run_key)}{_grammar()}'
    if index is None:
        return head + f'<p data-search="no-index">{escape(NO_INDEX)}</p>'
    if not q.strip():
        examples = ", ".join(f'<a href="{PATH}?q={quote(e, safe=":*")}"><code>{escape(e)}</code></a>'
                             for e in EXAMPLES)
        return head + f'<p data-search="empty">Ask by a recorded field, for example {examples}.</p>'
    try:
        terms = parse(q)
        results = query(index, q)
    except QueryError as e:
        return head + f'<p data-search="refused" role="alert">Not asked: {escape(str(e))}.</p>'
    asked = _asked_from(index, run_key, terms)
    said = (f'<p data-search="asked-from">{escape(ASKED_FROM.format(run=asked["run_id"]))}</p>'
            if asked is not None else "")
    if not results:
        return head + said + f'<p data-search="none">{escape(NONE_FOUND)}</p>'
    rows = []
    for r in results:
        run, matched = r.run, r.matched
        badge = (f' <span class="pill neu" data-benchmark title="{escape(run["benchmark"]["note"])}">{BADGE}</span>'
                 if run.get("benchmark") else "")
        fields = "".join(f"<li><code>{escape(m)}</code></li>" for m in matched)
        rows.append(f'<tr data-run="{escape(run["run_id"])}" data-key="{escape(run["key"])}">'
                    f'<td><a href="runs/{escape(run["key"])}/case.html"><span class="mono">{escape(run["run_id"])}</span>'
                    f'</a>{badge}</td><td>{escape(run["pipeline_label"])}</td><td><ul class="plain">{fields}</ul></td>'
                    f"<td>{_compare_cell(store, run, asked, public=public)}</td></tr>")
    n = len(results)
    table = (f'<table class="timeline" data-section="search-results"><thead><tr><th>Run</th><th>Pipeline</th>'
             f"<th>What matched, as recorded</th><th>{escape(COMPARE)}</th></tr></thead><tbody>{''.join(rows)}"
             f"</tbody></table>")
    from onetrace_console.words import scroll_region
    return (head + said + f'<p data-search="count">{n} run{"" if n == 1 else "s"} match every term.</p>'
            + scroll_region(table, "The runs that match", "search-results"))


def page(index: dict | None, q: str, run_key: str, store, *, public: bool) -> str:
    """The whole results page, its frame empty for the server to fill as it does every page's."""
    from onetrace_console.render import _document
    return _document(TITLE, f'<div class="cp">{body(index, q, run_key, store, public=public)}</div>')
