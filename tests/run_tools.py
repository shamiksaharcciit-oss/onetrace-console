"""The controls console 0.5.0 adds to its pages, each by its exact markup, for the tests that hold a
page to "no form, no button": the index's search box (a `GET` form to the console itself), a local
run page's benchmark mark and its note, "Other runs with the same inputs", and a public console's
Compare picker. `without_run_tools` removes exactly these; anything else a page carries is left for
the test to find, and a control drawn in any other shape is not removed.
"""
from __future__ import annotations

import re

SEARCH_SECTION = re.compile(
    r'<section data-section="(?:runs-search|run-search)"(?: class="run-search")?>'
    r'<form method="get" action="(?:\.\./\.\./)?search" role="search" class="search-box" data-search-box>'
    r'<label>Search the runs by recorded field <input type="search" name="q" value="" '
    r'placeholder="setting:\*\.chunk_size=512" spellcheck="false" autocomplete="off"></label>'
    r'(?:<input type="hidden" name="run" value="[0-9a-f]{64}">)? <button type="submit">Search</button>'
    r"</form></section>")
MARK_NOTE = re.compile(r'<label hidden data-benchmark-note>Note \(optional\) <input type="text" maxlength="280" '
                       r"data-benchmark-note-input></label> ")
MARK_BUTTON = re.compile(r'<button type="button" hidden data-benchmark-post="/benchmark\?run=[0-9a-f]{64}&amp;'
                         r'mark=(?:yes|no)">(?:Mark as benchmark|Remove the benchmark mark)</button>')
SAME_INPUTS = re.compile(r'<p data-what-changed="same-inputs"><a href="(?:\.\./\.\./)?search\?q=[^"&]*&amp;run=[0-9a-f]{64}">'
                         r"Other runs with the same inputs: \d+</a></p>")
PICKER = re.compile(r'<form method="post" action="/compare" data-visitor-compare>'
                    r'<label>Baseline \(run A\) <select name="a">(?:<option [^>]*>[^<]*</option>)+</select></label> '
                    r'<label>Candidate \(run B\) <select name="b">(?:<option [^>]*>[^<]*</option>)+</select></label> '
                    r'<button type="submit">Compare</button></form>')


def without_run_tools(page: str) -> str:
    from onetrace_console.benchmark_script import BENCHMARK_SCRIPT
    for shape in (SEARCH_SECTION, MARK_NOTE, MARK_BUTTON, SAME_INPUTS, PICKER):
        page = shape.sub("", page)
    return page.replace(BENCHMARK_SCRIPT, "")
