""""Other runs with the same change" never says a graph comparison found
no first difference.

    "Other runs with the same change" says "This comparison found no first difference, so
    there is no change to look for." But the same page shows a first difference at `model`
    (demo), and at `zeta` and `alpha` (exam). [...] "No first difference" is said only when the
    comparison the page shows found none.

The cause, traced: the panel reads the comparison's `diff.json` (not its localize report), and a
graph comparison's diff report names a frontier of nodes (`first_difference_frontier`) and no
`first_difference`. The panel read that absence as "found none". It now says it doesn't match a
graph comparison's first differences; a report it can't read a first difference from is said as
that; and "no first difference" is left to the one case that found none, two identical runs.
"""
from __future__ import annotations

import re
from html import unescape

from onetrace_console.render import SAME_CHANGE_WORDS, render_diff
from tests.test_compare_graph import dag_pages  # noqa: F401
from tests.test_home_and_diff import GENERATED_AT
from tests.test_reference_demo import loaded  # noqa: F401

FALSE = "found no first difference"


def _holds_for_a_graph_comparison(page: str) -> None:
    """A graph pair draws no panel: why it does not look for other runs is said in the page's one
    closed "Not shown for graph-shaped runs" line, and nowhere says it found no first difference."""
    from onetrace_console.render import NOT_SHOWN_WHY
    assert 'data-section="first-difference"' in page, "the page shows no first difference"
    assert 'data-section="same-change"' not in page, "a graph pair draws the panel"
    folded = re.search(r'<details data-section="not-shown">(.*?)</details>\s*(<p data-section="sdk"|$)',
                       page, re.S)
    assert folded, "no closed line for what is not shown"
    said = unescape(folded.group(1))
    assert NOT_SHOWN_WHY["same-change"] in said
    assert FALSE not in unescape(page) and "no first difference" not in said


def test_the_demos_compare_page(loaded, examined):  # noqa: F811
    store, _, comparison = loaded
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    examined(1, "demo compare page (first difference at model)")
    _holds_for_a_graph_comparison(page)


def test_the_exams_graph_compare_pages(dag_pages, examined):  # noqa: F811
    examined(len(dag_pages), "exam graph compare pages (dag-r37 P/R, P/Q)")
    for name, page in dag_pages.items():
        _holds_for_a_graph_comparison(page)


def test_only_the_identical_case_says_there_is_no_difference(examined):
    examined(len(SAME_CHANGE_WORDS), "states the panel words without a match")
    for state, said in SAME_CHANGE_WORDS.items():
        if state != "none":
            assert "no first difference" not in said and "do not differ" not in said, state
    assert "do not differ" in SAME_CHANGE_WORDS["none"]
