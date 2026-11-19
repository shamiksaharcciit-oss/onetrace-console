"""Where "What changed?" has no comparison held, it says once that the run is not compared, and names the run it would
be compared with as only that.

On the public demo's run that contradicts its record, the section began "Compared with p1-02-baseline-set2, the
nearest earlier benchmark", then said "Not compared": a reader takes both. Read on the public demo as built, p1-14,
and a run whose comparison is held beside it.
"""

from __future__ import annotations

import html
import re

from tests.test_run_page_order import _pages_of


def _section(page: str) -> str:
    found = re.search(r'<section data-section="what-changed".*?</section>', page, re.S)
    assert found, "no What changed? section"
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", found.group(0))).split())


def test_a_run_with_no_comparison_held_says_not_compared_once_and_names_the_run_it_would_use(shared_demo, examined):
    said = _section(_pages_of(shared_demo, "p1-14-candidate-set3-byte-changed")["case.html"])
    examined(1, "section")
    assert "Compared with" not in said, said
    assert said.count("Not compared") + said.count("not compared") == 1, said
    assert (
        "Not compared. The run it would be compared with is p1-02-baseline-set2, the nearest earlier benchmark" in said
    )


def test_a_run_whose_comparison_is_held_still_says_compared_with(shared_demo, examined):
    said = _section(_pages_of(shared_demo, "p1-08-candidate-set2")["case.html"])
    examined(1, "section")
    assert said.startswith("What changed? Compared with p1-02-baseline-set2"), said
    assert "Not compared" not in said
