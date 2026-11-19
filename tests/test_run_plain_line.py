"""Each run's page opens with one plain line, by its record's state: what this console checked, what that means, and
what it does not say (`views.RUN_PLAIN`); the record's format terms come below it. Where the record carries no anchor,
a short line says what "Not anchored" is, and that it is not a fault.

Read on the public demo, on both views (What changed and Proof) of three runs: p1-01 (its record and files agree),
p1-14 (an output's bytes changed after it was recorded) and p1-16 (checked without its output files).

The words say only what the check establishes: none says "true", "safe" or "correct".
"""

from __future__ import annotations

import re
from html import unescape

from onetrace_console.views import RUN_PLAIN, RUN_PLAIN_NOT_ANCHORED
from tests.test_run_page_order import _pages_of

RUNS = {
    "p1-01-baseline-set1": "yes",
    "p1-14-candidate-set3-byte-changed": "no",
    "p1-16-candidate-set5-no-artifacts": "not-checked",
}
NEVER = re.compile(r"\b(true|truth|safe|correct|correctly|correctness)\b", re.I)


def test_each_run_s_page_opens_with_its_state_s_plain_line_above_the_format_terms(shared_demo, examined):
    seen = 0
    for run_id, state in RUNS.items():
        for name, page in _pages_of(shared_demo, run_id).items():
            seen += 1
            line = re.search(r'<p class="plain" data-section="run-plain" data-state="([^"]+)">(.*?)</p>', page, re.S)
            assert line, (run_id, name)
            assert line.group(1) == state and unescape(line.group(2)) == RUN_PLAIN[state], (run_id, name)
            head = page.index('data-section="run-head"')
            sub = page.index('<p class="sub">', head)
            assert head < line.start() < sub, (run_id, name)
    examined(seen, "run views")


def test_a_run_without_an_anchor_says_what_that_is(shared_demo, examined):
    page = _pages_of(shared_demo, "p1-01-baseline-set1")["case.html"]
    examined(1, "run view")
    said = re.search(r'data-section="run-plain-anchor">(.*?)</p>', page, re.S)
    assert said and unescape(said.group(1)) == RUN_PLAIN_NOT_ANCHORED
    assert "not a fault" in RUN_PLAIN_NOT_ANCHORED


def test_no_plain_line_says_true_safe_or_correct(examined):
    lines = [*RUN_PLAIN.values(), RUN_PLAIN_NOT_ANCHORED]
    examined(len(lines), "lines")
    assert [x for x in lines if NEVER.search(x)] == []
    #: Each says what this console checked, and what it does not show or say.
    assert all(x.startswith("This console ") for x in RUN_PLAIN.values())
    assert all(re.search(r"\b(does not|do not)\b", x) for x in RUN_PLAIN.values())


def test_the_two_checked_lines_say_only_what_the_check_shows(examined):
    """The check compares the output files with what the record says; whether the record itself is the original is
    the anchor's question. The two lines of a check that compared files say no more than that."""
    examined(2, "lines")
    assert RUN_PLAIN["yes"] == (
        "This console checked the run's output files against its record, and they match what the record says. It "
        "does not show when the record was made (see Anchored), and it does not judge the outputs."
    )
    assert RUN_PLAIN["no"] == (
        "This console checked the run's output files against its record, and they do not match: a file differs from "
        "what the record says, or is missing. So this page does not compare the run step by step: Proof says which "
        "file."
    )
    #: Neither says the files are unchanged since the run, or that the record changed: the check does not show that.
    assert not any(re.search(r"unchanged since|the record changed", RUN_PLAIN[k]) for k in ("yes", "no"))
