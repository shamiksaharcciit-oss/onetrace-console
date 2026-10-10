"""The Overview's "vs baseline" for a run compared as a graph (found with item 5's demo).

A two-run graph `diff` names no single first difference, only a frontier, so the Overview read
every diverged graph comparison as "Couldn't check": a check that decided, said as one that did
not, in the changed-vs-baseline count, the needs-attention panel and the recent runs. Now:
- a graph report is read only through the viewer's strict reader, as the run page's marks are;
- diverged with a frontier is "changed", naming every frontier node; identical is "same";
  a report that does not pass the reader decides nothing;
- the comparison is the one the run page's marks come from: the Comparisons index's own order
  Not a string sort with ties to the higher key.
On real SDK comparisons of the exam's dag-r37 runs.
"""
from __future__ import annotations

import json
from dataclasses import replace

from onetrace_console.compare import DIFF, compare
from onetrace_console.home import tallies
from onetrace_console.overview import attention_kind, vs_baseline
from onetrace_console.pages import _strict_diff_report
from tests.test_checks import FIXED_RAN_AT
from tests.test_run_page_marks import runs  # noqa: F401  P, Q and R, delivered and checked


def _words(report) -> str:
    names = list(report.first_difference_frontier)
    return ("First difference · " if len(names) == 1 else "First differences · ") + ", ".join(names)


def test_a_diverged_graph_comparison_is_changed_and_names_its_frontier(runs):
    found, store = runs
    c = compare(found["P"], found["R"], store, ran_at=FIXED_RAN_AT)
    report = _strict_diff_report(c, store)
    assert report.envelope == "diverged" and len(report.first_difference_frontier) == 2
    assert vs_baseline(found["R"], store) == ("changed", "First differences · zeta, alpha")
    assert attention_kind(found["R"], store) == "changed"
    changed = next(t for t in tallies(store) if t.slug == "changed-vs-baseline")
    assert [r.key for r in changed.runs] == [found["R"].key]


def test_a_graph_report_that_fails_the_strict_reader_decides_nothing(runs):
    found, store = runs
    c = compare(found["P"], found["R"], store, ran_at=FIXED_RAN_AT)
    run = c.verb(DIFF)
    report = json.loads(store.get(dict(run.reports)["diff.json"]))
    report["counts"]["same"] = "99"  # the frontier itself is untouched, and still not trusted
    bad = store.put(json.dumps(report).encode("utf-8"))
    reports = tuple((n, bad if n == "diff.json" else k) for n, k in run.reports)
    store.put_comparison(replace(c, verbs=tuple(replace(v, reports=reports) if v.verb == DIFF
                                                else v for v in c.verbs)))
    assert vs_baseline(found["R"], store) == ("couldnt-check", "Couldn't check")


def test_the_comparison_is_the_one_the_run_page_s_marks_come_from(runs):
    """Two comparisons stored at one moment: the index's order takes the lower key."""
    found, store = runs
    one = compare(found["P"], found["R"], store, ran_at=FIXED_RAN_AT)
    two = compare(found["Q"], found["R"], store, ran_at=FIXED_RAN_AT)
    lower, higher = sorted((one, two), key=lambda c: c.key)
    words = {c.key: _words(_strict_diff_report(c, store)) for c in (one, two)}
    assert words[lower.key] != words[higher.key], "the two must differ, or this proves nothing"
    assert vs_baseline(found["R"], store) == ("changed", words[lower.key])


def test_a_run_only_ever_the_baseline_is_not_compared(runs):
    found, store = runs
    compare(found["R"], found["P"], store, ran_at=FIXED_RAN_AT)
    assert vs_baseline(found["R"], store) == ("not-compared", "Not compared")
