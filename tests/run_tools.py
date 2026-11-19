"""The controls console 0.5.0 adds to its pages, each by its exact markup, for the tests that hold a
page to "no form, no button": the index's search box (a `GET` form to the console itself), a local
run page's benchmark mark and its note, "Other runs with the same inputs", a public console's
Compare picker, a pipeline's first-run-to-leave window form, and a comparison page's Swap request, its checks' "Run on
this page" and its text diff's side-by-side or inline switch (console 0.9). `without_run_tools` removes exactly these; anything else a page carries is left for
the test to find, and a control drawn in any other shape is not removed.
"""

from __future__ import annotations

import re

SEARCH_SECTION = re.compile(
    r'<section data-section="(?:runs-search|run-search)"(?: class="run-search")?>'
    r'<form method="get" action="(?:\.\./\.\./)?search" role="search" class="search-box" data-search-box>'
    r'<label>Search the runs by recorded field <input type="search" name="q" value="" '
    r'placeholder="setting:\*\.chunk_size=512" spellcheck="false" autocomplete="off"></label>'
    r'(?:<input type="hidden" name="run" value="[0-9a-f]{64}">)? <button class="btn-primary" data-busy="Searching…" type="submit">Search</button>'
    r"</form></section>"
)
MARK_NOTE = re.compile(
    r'<label hidden data-benchmark-note>Note \(optional\) <input type="text" maxlength="280" '
    r"data-benchmark-note-input></label> "
)
MARK_BUTTON = re.compile(
    r'<button class="btn-secondary" data-busy="[^"]*" type="button" hidden data-benchmark-post="/benchmark\?run=[0-9a-f]{64}&amp;'
    r'mark=(?:yes|no)">(?:Mark as benchmark|Remove the benchmark mark)</button>'
)
SAME_INPUTS = re.compile(
    r'<p data-what-changed="same-inputs"><a href="(?:\.\./\.\./)?search\?q=[^"&]*&amp;run=[0-9a-f]{64}">'
    r"Other runs with the same inputs: \d+</a></p>"
)
PICKER = re.compile(
    r'<form method="post" action="/compare" data-visitor-compare>'
    r'<label class="compare-field"><span class="compare-label">Baseline \(run A\)</span><select name="a">'
    r"(?:<option [^>]*>[^<]*</option>)+</select></label>"
    r'<label class="compare-field"><span class="compare-label">Candidate \(run B\)</span><select name="b">'
    r"(?:<option [^>]*>[^<]*</option>)+</select></label>"
    r'<button class="btn-primary" data-busy="Comparing…" data-busy-wait="the comparison" type="submit">Compare</button></form>'
)
#: A pipeline's first-run-to-leave page: its one window form, a GET to bisect that reads what is kept and
#: runs nothing (console 0.7.0).
BISECT_WINDOW = re.compile(
    r'<form method="get" action="bisect" data-bisect-window><input type="hidden" name="p" '
    r'value="[^"]*"><label>Find the first run to leave after: <input type="text" name="after" '
    r'value="[^"]*" maxlength="64"></label> <button class="btn-primary" data-busy="Finding…" type="submit">Find</button></form>'
)
#: The same, in a static export: shown disabled, with "Needs a running console." (console 0.7.0).
BISECT_WINDOW_EXPORTED = re.compile(
    r"<p data-bisect-window data-needs-console><label>Find the first run to leave "
    r'after: <input type="text" name="after" value="" maxlength="64" disabled>'
    r'</label> <button class="btn-primary" type="button" disabled>Find</button></p>'
)


#: A comparison page's Swap runs where the reverse is not held: Compare's own request, one pair reversed.
SWAP_ASK = re.compile(
    r'<form method="post" action="/compare" data-swap="ask" class="swap">'
    r'(?:<input type="hidden" name="csrf_token" value="" data-csrf-slot>)?'
    r'<input type="hidden" name="a" value="[0-9a-f]{64}"><input type="hidden" name="b" value="[0-9a-f]{64}">'
    r'<button class="btn-secondary" type="submit" data-busy="Comparing…" data-busy-wait="the comparison">'
    r"Swap runs</button></form>"
)
#: Its checks' "Run on this page", a local console's: the comparison and which check.
RUN_HERE = re.compile(
    r' ?<form method="post" action="/compare/check" class="run-here" data-check="(?:text|for)">'
    r'<input type="hidden" name="csrf_token" value="" data-csrf-slot>'
    r'<input type="hidden" name="key" value="[0-9a-f]{64}"><input type="hidden" name="check" value="(?:text|for)">'
    r'<button class="btn-secondary" type="submit" data-busy="Running…" data-busy-wait="the check">'
    r"Run on this page</button></form>"
)
#: Its text diff's switch: two buttons that show one view, and send nothing.
VIEW_SWITCH = re.compile(
    r'<div class="view-switch" data-diff-views hidden role="group" aria-label="Text diff">'
    r'<button type="button" class="btn-secondary" data-view="side" aria-pressed="true">Side by side</button>'
    r'<button type="button" class="btn-secondary" data-view="inline" aria-pressed="false">Inline</button></div>'
)


def without_run_tools(page: str) -> str:
    from onetrace_console.benchmark_script import BENCHMARK_SCRIPT

    for shape in (
        SEARCH_SECTION,
        MARK_NOTE,
        MARK_BUTTON,
        SAME_INPUTS,
        PICKER,
        BISECT_WINDOW,
        BISECT_WINDOW_EXPORTED,
        SWAP_ASK,
        RUN_HERE,
        VIEW_SWITCH,
    ):
        page = shape.sub("", page)
    return page.replace(BENCHMARK_SCRIPT, "")
