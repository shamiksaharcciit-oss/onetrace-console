"""The console's Runs page says what it is.

    In the console the framed Runs page says "It is not a view of a store, and nothing is
    summarised across runs." In the console it is exactly the list of the stored runs. The
    sentence is true in the free viewer file and stays there.
    In the console's frame only, fixed words: "Runs stored: {n} of {n}, and this page lists
    every one of them. Nothing is summarised across runs on this page."

The other lists a count opens (a tally of some of the runs) are not the Runs page and keep the
viewer's words; the decision is about the Runs page.
"""
from __future__ import annotations

import re

from onetrace_console.render import render_all
from tests.test_checks import _require_installed
from tests.test_home_and_diff import (GENERATED_AT, RUN_C, RUN_C_POPPLER24, _deliver,
                                      _require_exam)

FREE = "It is not a view of a store, and nothing is summarised across runs."


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


def test_the_console_runs_page_carries_the_ruled_sentence_and_not_the_free_files(store, examined):
    _require_installed()
    _require_exam()
    for run in (RUN_C, RUN_C_POPPLER24):
        _deliver(run, store)
    n = len(store.runs())
    examined(n, "stored runs")
    page = _text(render_all(store, generated_at=GENERATED_AT)["executions-all.html"])
    assert (f"Runs stored: {n} of {n}, and this page lists every one of them. Nothing is "
            "summarised across runs on this page.") in page
    assert FREE not in page and "not a view of a store" not in page


def test_the_free_viewer_file_keeps_its_sentence(examined):
    from onetrace_console.viewer.page import render_executions
    page = _text(render_executions([], "2026-10-03", "viewer", of=0))
    examined(1, "free Runs page")
    assert FREE in page
    assert "Runs stored:" not in page
    assert "Runs in this list:" not in page


def test_a_filtered_list_carries_its_ruled_sentence_and_not_the_free_files(store, examined):
    """"Runs in this list: {n} of {T} stored, and this page lists every one
    of them. Nothing is summarised across runs on this page." In the console's frame only."""
    from onetrace_console.home import tallies
    _require_installed()
    _require_exam()
    for run in (RUN_C, RUN_C_POPPLER24):
        _deliver(run, store)
    total = len(store.runs())
    pages = render_all(store, generated_at=GENERATED_AT)
    lists = [t for t in tallies(store) if t.slug != "all"]
    examined(len(lists), "filtered lists a count opens")
    assert any(len(t.runs) < total for t in lists), "no list is a subset, so this proves nothing"
    for t in lists:
        page = _text(pages[t.href])
        assert _said(len(t.runs), total) in page, t.slug
        assert FREE not in page and "not a view of a store" not in page, t.slug


#: The corrected words, one test each below for none, one, and two or more; "Nothing is
#: summarised across runs on this page." follows every one.
TAIL = " Nothing is summarised across runs on this page."


def _said(n: int, total: int) -> str:
    from onetrace_console.pages import runs_in_list
    return runs_in_list(n, total)


def test_a_list_of_none_says_none_of_the_stored():
    assert _said(0, 4) == "Runs in this list: none of the 4 stored." + TAIL


def test_a_list_of_one_says_it_lists_it():
    assert _said(1, 4) == "Runs in this list: 1 of 4 stored, and this page lists it." + TAIL


def test_a_list_of_two_or_more_says_it_lists_all_of_them():
    assert _said(2, 4) == "Runs in this list: 2 of 4 stored, and this page lists all 2." + TAIL
    assert _said(4, 4) == "Runs in this list: 4 of 4 stored, and this page lists all 4." + TAIL
