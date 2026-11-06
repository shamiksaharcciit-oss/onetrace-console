"""Console 0.6.1 item 3: the ladder marks a drop only where there is one.

`largest_drop` marked the rung with the largest input-minus-output nearness even where every value was
zero or below (outputs nearer than inputs). Now a rung is marked only where its drop is above zero, a
negative drop reads "outputs nearer by 0.387", and a ladder with no drop says "No step's outputs are
further apart than its inputs." Nothing else changes: no verdict, no number, no exact comparison.
"""
from __future__ import annotations

import re

import pytest

from onetrace_console.neighbours.nearness import BY_EMBEDDER, BY_RECORD, Near, Rung, largest_drop


def rung(step, i, o, how_i=BY_EMBEDDER, how_o=BY_EMBEDDER):
    return Rung(step, None if i is None else Near(i, how_i), None if o is None else Near(o, how_o))


#: A pair of the support-agent demo's runs, as its ladder reads: no rung drops.
SUPPORT_PAIR = [rung("intake", None, None), rung("retrieve", 0.427, 0.814), rung("answer", 0.427, 0.865)]


@pytest.fixture
def drawn(monkeypatch):
    """The ladder section as the comparison page draws it, for rungs given here."""
    from onetrace_console import neighbours
    from onetrace_console.neighbours import nearness, pages
    monkeypatch.setattr(neighbours, "here", lambda: True)

    def draw(rungs):
        monkeypatch.setattr(nearness, "ladder", lambda comparison, store: rungs)
        return pages.ladder_section(object(), object())
    return draw


def _marked(html: str) -> list[str]:
    return re.findall(r'<tr data-rung="([^"]+)" data-largest-drop>', html)


def test_the_support_demo_pair_marks_nothing_and_says_so(drawn):
    assert largest_drop(SUPPORT_PAIR) is None
    html = drawn(SUPPORT_PAIR)
    assert _marked(html) == [] and "largest drop" not in html
    assert '<p class="note" data-nearness="no-drop">No step&#x27;s outputs are further apart than its inputs.</p>' in html
    assert "outputs nearer by 0.387" in html and "outputs nearer by 0.438" in html
    #: Never a minus number under "Drop".
    assert not re.search(r'data-label="Drop" class="value">-', html) and "−" not in html


def test_one_positive_among_negatives_is_the_one_marked(drawn):
    rungs = [rung("a", 0.4, 0.8), rung("b", 0.9, 0.5), rung("c", 0.3, 0.6)]
    assert largest_drop(rungs) == 1
    html = drawn(rungs)
    assert _marked(html) == ["b"] and "no-drop" not in html
    assert '<td data-label="Drop" class="value">0.400 <span class="pill neu" data-largest>largest drop</span>' in html


def test_a_tie_between_positive_drops_keeps_the_first(drawn):
    rungs = [rung("a", 0.9, 0.7), rung("b", 0.8, 0.6)]
    assert largest_drop(rungs) == 0


def test_all_not_kept_marks_nothing_and_says_nothing_of_drops(drawn):
    rungs = [rung("a", None, None), rung("b", 0.5, None), rung("c", None, 0.5)]
    assert largest_drop(rungs) is None
    html = drawn(rungs)
    assert _marked(html) == [] and "no-drop" not in html


def test_a_rung_at_exactly_zero_is_not_marked(drawn):
    for rungs in ([rung("a", 0.5, 0.5)], [rung("a", 0.5, 0.4996)], [rung("a", 0.5, 0.5004)]):
        assert largest_drop(rungs) is None
        html = drawn(rungs)
        assert _marked(html) == [] and "no-drop" in html
        assert '<td data-label="Drop" class="value">0.000</td>' in html and "outputs nearer" not in html


def test_one_by_the_record_rungs_have_no_drop_and_are_never_marked(drawn):
    rungs = [rung("a", 1.0, 1.0, BY_RECORD, BY_RECORD), rung("b", 0.6, 0.7)]
    assert rungs[0].drop is None and largest_drop(rungs) is None
    html = drawn(rungs)
    assert _marked(html) == []
    assert re.search(r'<tr data-rung="a">.*?<td data-label="Drop" class="value"></td>', html)


def test_the_ladder_never_says_what_made_a_difference(drawn):
    for rungs in (SUPPORT_PAIR, [rung("b", 0.9, 0.5)]):
        assert not re.search(r"\b(caused?|because|why|culprit)\b", drawn(rungs), re.I)
