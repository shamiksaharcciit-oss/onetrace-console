"""Console 0.6.1 item 11: a check the page already ran reads as run.

Where the console holds a check's result -- the stage's text diff, in the comparison's own run of
`onetrace diff --text` -- the check's row reads "Run on this page", its one-line result and a link to that
section, in place of its Run button. A check the console does not hold keeps its button. A check is
matched to a held result by its command and arguments, never by its words.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from tests.test_explain_panel import _diff, _fake, _panel, pair  # noqa: F401  (pair: a fixture)


def _rows(panel: str) -> dict[str, str]:
    return dict(re.findall(r'<li data-check="(\d+)"([^>]*>.*?)</li>', panel, re.S))


def test_a_held_text_check_reads_as_run_with_its_result_and_a_link(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")          # checks: text score#1, for decide#1, match candidate, mask
    explain.explain(comparison, store, send=True)
    page = _diff(store, comparison)
    rows = _rows(_panel(page))
    held = rows["0"]
    assert " data-held>" in held and "Run on this page" in held
    assert re.search(r"the text diff of score#1: (First difference|Changed after it|Same|Same again|Couldn&#x27;t check)", held)
    assert '<a href="#text-diff">see it</a>' in held
    assert '<section data-section="text-diff"><h2 id="text-diff">' in page, "the link's section is on the page"
    assert "<button" not in held


def test_an_unheld_check_keeps_its_button(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store, send=True)
    rows = _rows(_panel(_diff(store, comparison)))
    #: localize --for decide#1 and match: the comparison holds neither command's result.
    for i in ("1", "2"):
        assert "Run</button>" in rows[i] and "Run on this page" not in rows[i]


def test_matched_by_command_and_arguments_never_by_words(pair):
    from onetrace_console import explain
    store, comparison, _config = pair
    assert explain.held_check(comparison, store, {"check": "text", "node": "score#1"}) is not None
    #: The same stage in a check of another command, or a stage the text diff does not hold: not held.
    assert explain.held_check(comparison, store, {"check": "for", "node": "score#1"}) is None
    assert explain.held_check(comparison, store, {"check": "text", "node": "no-such-stage"}) is None
    assert explain.held_check(comparison, store, {"check": "mask", "setting": "threshold"}) is None
    #: Words naming a text diff do not make a check held: only its command does.
    assert explain.held_check(comparison, store, {"check": "match", "run": "candidate",
                                                  "words": "onetrace diff a b --text --stage score#1"}) is None


def test_a_comparison_with_no_text_diff_holds_nothing():
    from onetrace_console import explain
    no_text = SimpleNamespace(verb=lambda name: None, verbs=())
    assert explain.held_check(no_text, None, {"check": "text", "node": "score#1"}) is None
