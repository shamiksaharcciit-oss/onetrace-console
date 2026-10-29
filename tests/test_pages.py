"""Two pages, and the five prohibitions on both of them.

    The design note's five prohibitions apply to every page: no score or grade; no
    percentage without its counts; no check button; colour only for verdicts; nothing
    inferred.

The order's checks:

  - each rendered page passes the five-prohibition tests;
  - the Execution page's verdicts equal the stored report's;
  - both pages open offline, with no network requests (the browser half is in
    tools/offline_check.py, which uses an injected-probe control; its result is recorded in
    the work-order report).

The prohibitions are asserted over the rendered HTML of THIS console's pages. The canary
repository has its own versions over its own pages; a rule kept in one repository is not
kept in the other, and the console is the thing a customer looks at.
"""
from __future__ import annotations

import json
import re

import pytest

from onetrace_console.checks import REPEAT_COMMAND, run_and_record
from onetrace_console.ingest import accept
from onetrace_console.pages import (ANSWER, AUTHORIZATION, CASE, EXECUTIONS, RUN_PROOF, PageError,
                                    render_execution, render_executions)
from tests.test_checks import FIXED_RAN_AT, _require_installed

GENERATED_AT = "2026-09-26T12:00:00+02:00"


@pytest.fixture
def checked(delivery, store):
    _require_installed()
    accepted = accept(delivery, store)
    assert accepted.run is not None, getattr(accepted, "rows", accepted)
    return run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT)


@pytest.fixture
def execution(checked, store):
    return render_execution(checked, store, generated_at=GENERATED_AT)


@pytest.fixture
def every_page(execution, checked, store) -> dict[str, str]:
    pages = dict(execution.pages)
    pages[EXECUTIONS] = render_executions([checked], store, generated_at=GENERATED_AT)
    return pages


# ------------------------------------------------------------- the pages render at all

def test_both_pages_render(execution):
    """The viewer's two pages, and the console's authorization page."""
    #: And one stage page per step (board 4).
    stages = {n for n in execution.pages if re.fullmatch(r"stage-\d+\.html", n)}
    #: And the run receipt (board 5).
    from onetrace_console.receipt_page import RECEIPT
    assert stages and set(execution.pages) == {ANSWER, CASE, RUN_PROOF, AUTHORIZATION, RECEIPT} | stages
    for name, html in execution.pages.items():
        assert html.startswith("<!doctype html>") or html.lstrip().startswith("<!"), name
        #: The authorization page links the console's stylesheet, and
        #: its 2000 characters were mostly that stylesheet: measured, 1062 without it. So its
        #: own content is what is held to a size, not its head.
        if name in stages:
            #: A stage page's size is its stage's: held to what it must carry instead.
            for part in ('data-section="banner"', 'data-section="inputs"', 'data-section="outputs"'):
                assert part in html, f"{name} lacks {part}"
            continue
        if name == RECEIPT:
            #: Its size is its record's: held to the sections it must carry instead.
            for part in ('data-section="pills"', 'data-section="receipt"',
                         'data-section="check-yourself"', 'data-section="does-not-say"'):
                assert part in html, f"{name} lacks {part}"
            continue
        if name == AUTHORIZATION:
            main = html[html.index("<main>"):html.index("</main>")]
            assert len(main) > 500, f"{name}'s content is suspiciously small ({len(main)} chars)"
            continue
        assert len(html) > 2000, f"{name} is suspiciously small ({len(html)} chars)"


def test_the_executions_page_lists_the_stored_runs(every_page, checked):
    page = every_page[EXECUTIONS]
    assert checked.run_id in page, "the run this console holds is not on its own list"


def test_a_run_with_no_stored_report_refuses_rather_than_rendering_a_blank(delivery, store):
    """A run this console has not checked must not get a page that looks checked."""
    _require_installed()
    unchecked = accept(delivery, store).run
    with pytest.raises(PageError, match="has not checked"):
        render_execution(unchecked, store, generated_at=GENERATED_AT)


# ---------------------------------------- the Execution page's verdicts are the report's

def test_the_pages_verdicts_equal_the_stored_reports(execution, checked, store):
    """Step 4's second check. The page's counts are compared with the report's own rows.

    Not "the page mentions a verdict" -- the pass and not-run counts on the page are
    compared against the counts taken from the stored report's own text, so a page that
    rendered a different number would fail.
    """
    envelope = json.loads(store.get(checked.check_report).decode("utf-8"))
    lines = [ln for ln in envelope["stdout"].splitlines() if ln.strip()]
    summary = lines[-1]
    m = re.match(r"^(\d+) pass, (\d+) fail, (\d+) not-run  ->  (PASS|FAIL)$", summary)
    assert m, f"the stored report's summary is not the verifier's grammar: {summary!r}"
    n_pass, n_fail, n_not_run, overall = int(m[1]), int(m[2]), int(m[3]), m[4]

    assert checked.check_verdict == ("holds" if overall == "PASS" else "contradicts")
    assert checked.check_exit == ("0" if overall == "PASS" else checked.check_exit)

    #: The check's rows are on the run page's "Proof" view.
    case = execution.pages[RUN_PROOF]
    #: The report's own words are disclosed on the page, so the summary line itself is the
    #: strongest available comparison: if the page carried different numbers, it would be
    #: carrying a different report. Compared in its ESCAPED form -- the page escapes `>`,
    #: so the verifier's `->  PASS` is `-&gt;  PASS` in the HTML. The first version of this
    #: test compared the raw line and failed, which was the escaping working correctly.
    from html import escape
    assert escape(summary) in case, (
        f"the stored report's summary line is not on the page. Expected "
        f"{escape(summary)!r}")
    assert str(n_pass) in case
    if n_not_run:
        assert str(n_not_run) in case


def test_the_command_to_repeat_the_check_is_on_the_page(execution):
    """Step 4: "with the command to repeat the check shown on the page"."""
    case = execution.pages[CASE]
    assert "verify" in case, "no command to repeat the check appears on the case page"
    assert execution.repeat_command == REPEAT_COMMAND


# --------------------------------------------------- the five prohibitions

#: Words that would make a page a grade rather than a record. `score` and `grade` are the
#: two the specification names; the rest are the ways the same thing arrives wearing a hat.
FORBIDDEN_WORDS = ("trust score", "trustscore", "grade", "rating", "out of 10",
                   "confidence score", "risk score", "health score", "reliability score")

#: Words that would make a page a recommendation rather than a count.
INFERENCE_WORDS = ("recommend", "we suggest", "likely cause", "probably", "similarity",
                   "similar runs", "insight:", "predicted", "anomaly score")


@pytest.mark.parametrize("name", [ANSWER, CASE, EXECUTIONS, AUTHORIZATION])
def test_no_score_or_grade(every_page, name):
    page = every_page[name].lower()
    found = [w for w in FORBIDDEN_WORDS if w in page]
    assert not found, f"{name} carries {found}"


def _body(html: str) -> str:
    """The page with its stylesheet removed.

    CSS is full of percentages -- `width:100%` and the like -- and none of them is a claim
    about a record. The first version of this test looked at the whole file and failed on
    exactly those. Measured: with `<style>` stripped, these pages carry **zero**
    percentages, so the assertion below is about the page's own words.
    """
    return re.sub(r"<style>.*?</style>", "", html, flags=re.S | re.I)


@pytest.mark.parametrize("name", [ANSWER, CASE, EXECUTIONS, AUTHORIZATION])
def test_no_percentage_without_its_counts(every_page, name):
    """A percentage is allowed only beside the counts it came from.

    These pages carry none, which is asserted directly. If one is ever added, this fails
    and whoever adds it has to bring its counts.
    """
    percentages = re.findall(r"\d+(?:\.\d+)?\s*%", _body(every_page[name]))
    assert not percentages, (
        f"{name} carries percentages {percentages}. C034 §4 allows one only beside its "
        f"counts; if that is what this is, this test needs to learn the shape you used")


@pytest.mark.parametrize("name", [ANSWER, CASE, EXECUTIONS, AUTHORIZATION])
def test_no_check_button(every_page, name):
    """No button that checks for you. Asserted as the absence of any mechanism to press.

    Not "no `<script>`": these pages carry one, and it opens every `<details>` so that
    printing the page shows what the screen hides. That is a rendering detail and it
    checks nothing. The first version of this test banned `<script>` outright and failed
    on it -- a prohibition that catches the wrong thing teaches whoever hits it to loosen
    it, so it is aimed properly instead: no form, no button, no input, no handler, and no
    script that can reach anything.
    """
    #: Less console 0.5.0's own controls, each by its exact markup (`tests/run_tools.py`): the
    #: index's search box, which reads, and a local run's benchmark mark, which says which run to
    #: compare against; neither checks anything.
    from tests.run_tools import without_run_tools
    page = without_run_tools(every_page[name]).lower()
    for mechanism in ("<button", "<form", "<input", "onclick=", "onsubmit=", "onchange="):
        assert mechanism not in page, f"{name} carries {mechanism!r}"

    scripts = re.findall(r"<script[^>]*>(.*?)</script>", page, re.S)
    for body in scripts:
        for reach in ("fetch(", "xmlhttprequest", "import(", "eval(", "websocket",
                      "navigator.sendbeacon", "src=", "location="):
            assert reach not in body, (
                f"{name} has a script that can reach something: {reach!r} in {body[:120]!r}")
    assert not re.search(r"<script[^>]+src=", page), f"{name} loads an external script"


def assert_the_prohibitions(name: str, page: str) -> None:
    """The prohibitions in one place, the strongest shape used above: no score or
    grade, no inference, no percentage, no mechanism to press, no script that can reach
    anything, no inline colour. For pages the tests above do not render: the no-percentage
    and no-score tests extend to the policy and decision pages."""
    lower = page.lower()
    graded = [w for w in FORBIDDEN_WORDS if w in lower]
    assert not graded, f"{name}: score or grade {graded}"
    inferred = [w for w in INFERENCE_WORDS if w in lower]
    assert not inferred, f"{name}: inference {inferred}"
    percentages = re.findall(r"\d+(?:\.\d+)?\s*%", _body(page))
    assert not percentages, f"{name}: percentage {percentages}"
    for mechanism in ("<button", "<form", "<input", "onclick=", "onsubmit=", "onchange="):
        assert mechanism not in lower, f"{name} carries {mechanism!r}"
    for body in re.findall(r"<script[^>]*>(.*?)</script>", lower, re.S):
        for reach in ("fetch(", "xmlhttprequest", "import(", "eval(", "websocket",
                      "navigator.sendbeacon", "src=", "location="):
            assert reach not in body, f"{name} has a script that can reach {reach!r}"
    assert not re.search(r"<script[^>]+src=", lower), f"{name} loads an external script"
    inline = re.findall(r'style="[^"]*(?:color|background)[^"]*"', page, re.I)
    assert not inline, f"{name}: inline colour {inline[:3]}"


@pytest.mark.parametrize("planted,why", [
    ("<p>3 of 4 decisions (75%)</p>", "percentage"),
    ("<p>risk score: 7</p>", "score or grade"),
    ("<p>we suggest a rollback</p>", "inference"),
    ('<p><button>re-check</button></p>', "'<button'"),
    ('<p style="color:#e25c6e">denied</p>', "inline colour"),
    ("<script>fetch('/x')</script>", "reach"),
])
def test_the_shared_prohibition_check_catches_each_shape(planted, why, examined):
    """The pages it is applied to carry none of these, so it passes there. This is the
    proof that it can fail: each prohibited shape, planted in a clean page, is caught."""
    clean = "<html><head><style>.x{width:100%}</style></head><body><main>" \
            "<p>5 decisions of 5</p></main></body></html>"
    assert_the_prohibitions("clean", clean)
    examined(1, f"planted shape: {why}")
    with pytest.raises(AssertionError, match=re.escape(why)):
        assert_the_prohibitions("planted", clean.replace("</main>", planted + "</main>"))


@pytest.mark.parametrize("name", [ANSWER, CASE, EXECUTIONS, AUTHORIZATION])
def test_colour_only_for_outcomes(every_page, name):
    """Colour is carried by outcome classes and custom properties, never sprinkled inline.

    An inline `style="color: …"` is how colour stops meaning an outcome and starts meaning
    decoration, and once it decorates, a reader cannot use it to read a verdict.
    """
    page = every_page[name]
    inline = re.findall(r'style="[^"]*(?:color|background)[^"]*"', page, re.I)
    assert not inline, f"{name} carries inline colour: {inline[:3]}"


@pytest.mark.parametrize("name", [ANSWER, CASE, EXECUTIONS, AUTHORIZATION])
def test_nothing_inferred_beyond_the_record(every_page, name):
    page = every_page[name].lower()
    found = [w for w in INFERENCE_WORDS if w in page]
    assert not found, f"{name} carries {found}"


@pytest.mark.parametrize("name", [CASE, EXECUTIONS, AUTHORIZATION])
def test_the_limit_sentence_is_on_the_pages_the_viewer_puts_it_on(every_page, name):
    """"…what was verified and evaluated at the time — not what was ultimately true."

    The design note §6 says it stays on every run page. The viewer renders `case.limit` on
    the **case** and **executions** pages and not on the answer page — measured, and it is
    the viewer's fixed arrangement under 019 §2/§3, not something this console may change.
    The answer page is also the frozen reader-session page, so changing it is forbidden
    outright right now. Raised as a question in DESIGN_GAPS.md rather than asserted here.
    """
    assert "not what was ultimately true" in every_page[name], (
        f"{name} has lost the limit sentence")


def test_the_answer_page_carries_no_limit_sentence_and_that_is_recorded(every_page):
    """The discrepancy above, pinned so it cannot drift unnoticed in either direction.

    If the viewer later puts the sentence on the answer page, this fails and the question
    in DESIGN_GAPS.md comes out — the guard reports its own obsolescence.
    """
    assert "not what was ultimately true" not in every_page[ANSWER], (
        "the answer page now carries the limit sentence, so the design-note discrepancy "
        "recorded in DESIGN_GAPS.md is resolved and should be removed from it")


# ------------------------------------------------------------------- offline, by structure

@pytest.mark.parametrize("name", [ANSWER, CASE, EXECUTIONS, AUTHORIZATION])
def test_no_page_references_a_remote_origin(every_page, name):
    """The structural half of "both pages open offline".

    A page with no external reference cannot make a request, and this is cheap and runs
    everywhere. It is NOT the whole check: classifying hosts by name has been got wrong
    before, and the answer was a control at the browser. The browser half with its
    injected-probe control is tools/offline_check.py, and its result belongs in the report,
    not in an assertion here.
    """
    page = every_page[name]
    remote = re.findall(r'(?:src|href)\s*=\s*"(https?:|//)[^"]*"', page, re.I)
    assert not remote, f"{name} references {remote[:3]}"
    for scheme in ("http://", "https://"):
        for m in re.finditer(re.escape(scheme), page):
            context = page[max(0, m.start() - 60):m.start() + 60]
            assert not re.search(r'(?:src|href)\s*=\s*"[^"]*$',
                                 page[max(0, m.start() - 60):m.start()]), context
