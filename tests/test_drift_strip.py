"""The drift timeline, in the Runs page's strip: with one pipeline chosen, each run against the first run this console
received of it, one mark a step, as `onetrace drift` reports it.

- **One design with the Steps strip:** a column "Against the first run", one mark a node in the report's order, each
  its own shape with its words; the run's line in the command's own words ("against 1: diverged, first difference
  b"); the first run itself "the baseline".
- **The order is defined and said:** each run against the first this console received of the pipeline, oldest first,
  as the drift page and the command lay them out.
- **Unknown is never drift-free:** a run the kept report does not hold, or a node a comparison does not reach, reads
  "not compared", with a mark of its own; never "same", never "identical".
- **The first run to leave is marked,** as the short answer's strip marks the first difference: the first run, in that
  order, whose comparison diverged.
- **Every count goes through `runs_page.select`,** the one query function a later release scopes by team.
- **Read from the index alone:** each run's place in its pipeline's kept report is in its list entry.
"""

from __future__ import annotations

import re
from html import unescape

import pytest


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console import run_index
    from onetrace_console.store import Store

    folder = shared_demo["folder"]
    index = run_index.read(folder / "store")
    assert index is not None
    return Store(folder / "store" / "store"), index


def _report(store, label: str) -> tuple[list, dict]:
    from onetrace_console import drift
    from onetrace_console.overview import pipelines

    (p,) = [p for p in pipelines(store) if p.label == label]
    with store.reading():
        rec = drift.drift_record(store, p, "first", compute=False)
        return list(p.runs), drift.report_of(rec, store)


def _rows(page: str) -> dict[str, str]:
    return dict(re.findall(r'<tr data-run="[^"]*" data-key="([0-9a-f]{64})">(.*?)</tr>', page, re.S))


def test_each_run_s_list_entry_holds_its_place_in_the_kept_report(demo, examined):
    store, index = demo
    runs, rep = _report(store, "P1")
    entries = {r["key"]: r["list"] for r in index["runs"]}
    by_cand = {c["candidate"]: c for c in rep["comparisons"]}
    examined(len(runs), "runs of P1")
    for i, run in enumerate(runs, start=1):
        got = entries[run.key]["drift"]
        assert got["index"] == str(i), run.run_id
        if i == 1:
            assert got["baseline"] is True
            continue
        c = by_cand[str(i)]
        assert (got["envelope"], got["first_difference"]) == (c["envelope"], c["first_difference"]), run.run_id
        assert got["nodes"] == [[n["node"], n["verdicts"][i - 2]] for n in rep["nodes"]], run.run_id


def test_the_runs_page_draws_each_run_against_the_first_in_the_strip_s_design(demo, examined):
    from onetrace_console import drift_strip, runs_page

    store, index = demo
    runs, rep = _report(store, "P1")
    page = runs_page.body(index, {"pipeline": "P1", "page": "all"}, public=True)
    assert f'<th scope="col">{drift_strip.COLUMN}</th>' in page
    rows = _rows(page)
    by_cand = {c["candidate"]: c for c in rep["comparisons"]}
    examined(len(runs), "rows")
    for i, run in enumerate(runs, start=1):
        cell = re.search(r'<td[^>]*data-answer="drift"[^>]*>(.*?)</td>', rows[run.key], re.S).group(1)
        said = unescape(
            re.sub(r"<[^>]+>", "", re.search(r"<span class=\"note\" data-drift-said>(.*?)</span>", cell, re.S).group(1))
        )
        if i == 1:
            assert said == drift_strip.BASELINE, said
            continue
        c = by_cand[str(i)]
        want = f"against {c['baseline']}: {c['envelope']}"
        assert said.startswith(want), (run.run_id, said)
        marks = re.findall(r'data-drift-mark="([a-z-]+)"', cell)
        assert marks == [drift_strip.mark_of(n["verdicts"][i - 2]) for n in rep["nodes"]], run.run_id
    assert 'data-answer="drift"' not in runs_page.body(index, {"page": "all"}, public=True)


def test_the_order_is_said(demo, examined):
    from onetrace_console import drift_strip, runs_page

    _store, index = demo
    page = unescape(runs_page.body(index, {"pipeline": "P1"}, public=True))
    examined(1, "page")
    assert drift_strip.ORDER.format(label="P1") in page


def test_a_run_not_in_the_kept_report_is_not_compared_never_drift_free(demo, examined):
    import copy

    from onetrace_console import drift_strip, runs_page

    _store, index = demo
    planted = copy.deepcopy(index)
    p1 = sorted((r for r in planted["runs"] if r["pipeline_label"] == "P1"), key=lambda r: r["order"])
    gone = p1[3]
    del gone["list"]["drift"]
    #: and one node a comparison does not reach
    other = p1[4]["list"]["drift"]
    other["nodes"][0][1] = None
    page = runs_page.body(planted, {"pipeline": "P1", "page": "all"}, public=True)
    rows = _rows(page)
    examined(2, "runs not compared")
    cell = re.search(r'<td[^>]*data-answer="drift"[^>]*>(.*?)</td>', rows[gone["key"]], re.S).group(1)
    text = unescape(re.sub(r"<[^>]+>", " ", cell))
    assert drift_strip.NOT_COMPARED in text and 'data-drift-mark="not-compared"' in cell
    assert not re.search(r"\b(same|identical)\b", text), text
    cell = re.search(r'<td[^>]*data-answer="drift"[^>]*>(.*?)</td>', rows[p1[4]["key"]], re.S).group(1)
    assert re.findall(r'data-drift-mark="([a-z-]+)"', cell)[0] == "not-compared"
    counts = unescape(re.search(r'<p data-runs="drift-counts">(.*?)</p>', page, re.S).group(1))
    assert "1 not compared" in counts, counts


def test_the_first_run_to_leave_is_marked_as_the_strip_marks_it(demo, examined):
    from onetrace_console import drift_strip, runs_page

    store, index = demo
    runs, rep = _report(store, "P1")
    first = next(int(c["candidate"]) for c in rep["comparisons"] if c["envelope"] == "diverged")
    page = runs_page.body(index, {"pipeline": "P1", "page": "all"}, public=True)
    rows = _rows(page)
    marked = [k for k, row in rows.items() if "data-drift-first" in row]
    examined(1, "first run to leave")
    assert marked == [runs[first - 1].key]
    assert drift_strip.FIRST_TO_LEAVE in unescape(rows[marked[0]])


def test_every_count_goes_through_select(demo, monkeypatch, examined):
    from onetrace_console import runs_page

    _store, index = demo
    real = runs_page.select
    p1 = [r for r in index["runs"] if r["pipeline_label"] == "P1"]
    kept = {r["key"] for r in p1[: len(p1) // 2]}

    def fewer(idx, q=""):
        return [r for r in real(idx, q) if r.get("pipeline_label") != "P1" or r["key"] in kept]

    monkeypatch.setattr(runs_page, "select", fewer)
    page = runs_page.body(index, {"pipeline": "P1", "page": "all"}, public=True)
    counts = unescape(re.search(r'<p data-runs="drift-counts">(.*?)</p>', page, re.S).group(1))
    examined(1, "count line")
    assert f"of the {len(kept)} runs listed" in counts, counts
    assert set(_rows(page)) == kept


def test_only_identical_counts_as_not_diverged_refused_and_the_rest_never(demo, examined):
    """A comparison onetrace refused, could not check or found not comparable is counted on its own, never with the runs
    that compared and did not diverge."""
    import copy

    from onetrace_console import drift_strip, runs_page

    _store, index = demo
    planted = copy.deepcopy(index)
    p1 = sorted((r for r in planted["runs"] if r["pipeline_label"] == "P1"), key=lambda r: r["order"])
    entries = [r["list"]["drift"] for r in p1[1:]]
    for e, envelope in zip(
        entries, ("identical", "identical after masking", "refused", "could not check", "not comparable")
    ):
        e["envelope"] = envelope
    page = runs_page.body(planted, {"pipeline": "P1", "page": "all"}, public=True)
    counts = unescape(re.search(r'<p data-runs="drift-counts">(.*?)</p>', page, re.S).group(1))
    rest = entries[5:]
    diverged = sum(1 for e in rest if e.get("envelope") == "diverged")
    same = sum(1 for e in rest if e.get("envelope") in drift_strip.NOT_DIVERGED)
    neither = len(rest) - diverged - same
    examined(5, "envelopes that are not a divergence")
    want = f"{diverged} diverged; {2 + same} identical; {3 + neither} refused, could not check or not comparable"
    assert want in counts, counts
    assert "did not diverge" not in counts
    assert drift_strip.counts([]).startswith("Against the first run, of the 0 runs listed")
