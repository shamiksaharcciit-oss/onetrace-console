"""Benchmarks (`benchmarks`): the mark, the badge, "What changed?"'s order, and a benchmark's variation.

1. The public demo's benchmarks are its build's: each compared pipeline's baseline, marked in the
   store by the build and never in a record; a public console refuses `POST /benchmark`.
2. On a local console, "Mark as benchmark" and its undo are `POST /benchmark` with the CSRF token:
   the mark (who, when, the note) lands in the store, the run's record and its bundle are the bytes
   they were, and the pages are drawn again with the badge.
3. The badge reads "benchmark", never "correct", wherever a run is listed, its note on hover; no
   rung, check or count reads differently for a marked run. What its pipeline's runs are read
   against follows the marks (`verdicts`), and nothing else on a run's page does.
4. "What changed?" takes a benchmark first at each rule, names the rule, says when it took one over
   the run the rules take without benchmarks, badges its list, and says how many other runs have
   the same inputs, opening the index on them.
5. A benchmark recorded again on the same configuration shows onetrace's variation profile on its
   page, over it and the repeats whose records agree; a run that is not marked shows none.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request

import pytest

from onetrace_console.demo_store import BENCHMARKS

#: Four of the demo's benchmarks, read by name by the tests below.
NAMED = ("p1-02-baseline-set2", "p5-32-pump-baseline", "p8-42-invoice-tolerance-2pct", "p9-46-torque-baseline")


@pytest.fixture(scope="module")
def demo(shared_demo, tmp_path_factory):
    """Its own copy of the demo build: marks are made and removed here."""
    from onetrace_console.store import Store
    from tests.conftest import demo_copy
    folder = demo_copy(shared_demo, tmp_path_factory.mktemp("benchmarks") / "demo")
    store = Store(folder / "store" / "store")
    return folder, store, {r.run_id: r for r in store.runs()}


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _section(page: str, name: str) -> str:
    m = re.search(rf'<section data-section="{name}".*?</section>', page, re.S)
    return m.group(0) if m else ""


# ------------------------------------------------------------------ 1. the demo's marks

def test_the_demo_s_benchmarks_are_each_compared_pipeline_s_baseline(demo, examined):
    from onetrace_console import benchmarks
    from onetrace_console.demo_store import COMPARISONS
    _folder, store, runs = demo
    marks = benchmarks.marks(store)
    examined(len(runs), "runs")
    assert set(NAMED) <= set(BENCHMARKS)
    assert len(BENCHMARKS) == len({a.split("-")[0] for a, _b in COMPARISONS})
    folders = {k: r.folder.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for k, r in ((r.key, r) for r in runs.values())}
    assert sorted(folders[k] for k in marks) == sorted(BENCHMARKS)
    for key, m in marks.items():
        assert (m["who"], m["note"]) == (benchmarks.DEMO_WHO, benchmarks.DEMO_NOTE)


def test_a_mark_is_in_the_store_never_in_the_record(demo, examined):
    from onetrace_console import benchmarks
    from onetrace_console.ingest import bundle
    folder, store, runs = demo
    run = runs["p1-08-candidate-set2"]
    record = (store.root / "runs" / f"{run.key}.json").read_bytes()
    before = hashlib.sha256(bundle(run, store)).hexdigest()
    benchmarks.mark(store, run, who="a tester", note="the one to compare against")
    try:
        examined(2, "the run's record and bundle, before and after a mark")
        assert (store.root / "benchmarks" / f"{run.key}.json").is_file()
        assert (store.root / "runs" / f"{run.key}.json").read_bytes() == record
        assert hashlib.sha256(bundle(store.get_run(run.key), store)).hexdigest() == before
    finally:
        benchmarks.unmark(store, run.key)
    assert benchmarks.mark_of(store, run.key) is None


def test_a_note_past_its_length_is_refused(demo, examined):
    from onetrace_console import benchmarks
    _folder, store, runs = demo
    examined(1, "mark")
    with pytest.raises(benchmarks.MarkError, match="at most 280"):
        benchmarks.mark(store, runs["p1-08-candidate-set2"], who="a tester", note="x" * 281)


# ------------------------------------------------------------------ 3. the badge, no verdict

def test_the_badge_says_benchmark_never_correct_wherever_a_run_is_listed(demo, examined):
    folder, store, runs = demo
    pages = folder / "store" / "pages"
    listing = {"executions-all.html": (pages / "executions-all.html").read_text(encoding="utf-8"),
               "pipeline-p1.html": (pages / "pipeline-p1.html").read_text(encoding="utf-8"),
               "choose-p1.html": (pages / "choose-p1.html").read_text(encoding="utf-8")}
    examined(len(listing), "lists of runs")
    p1 = runs["p1-02-baseline-set2"]
    for name, page in listing.items():
        badges = re.findall(r'<span class="pill neu" data-benchmark title="([^"]*)">([^<]*)</span>', page)
        assert badges, name
        assert {b for _t, b in badges} == {"benchmark"}, name
        assert all("The baseline this demo compares" in t for t, _b in badges), name
        assert "correct" not in " ".join(b for _t, b in badges).lower()
        row = re.search(rf'<(?:tr|li) data-(?:run|key)="[^"]*"[^>]*>(?:(?!</(?:tr|li)>).)*{p1.key}(?:(?!</(?:tr|li)>).)*</(?:tr|li)>', page, re.S)
        assert row and "data-benchmark" in row.group(0), name


def test_no_verdict_rung_or_count_reads_differently_for_a_marked_run(demo, examined):
    """The run's page less the benchmark's own sections and the verdict against the reference the marks
    choose (`verdicts`), and every count, are the same marked or not."""
    from onetrace_console import benchmarks, records
    from onetrace_console.config import Config
    from onetrace_console.serve import _render_all_pages, _render_run_pages
    folder, store, runs = demo
    run = runs["p1-14-candidate-set3-byte-changed"]
    config = Config(public=True)
    pages = folder / "store" / "pages"

    def drawn():
        _render_run_pages(run, store, folder / "store", config)
        _render_all_pages(store, folder / "store", config)
        case = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
        #: The benchmark's own sections, its mark and its profile, are what a mark adds; the verdict
        #: section reads against the reference the marks choose, so it follows them too.
        case = re.sub(r'<section data-section="(?:benchmark|profile|verdict)".*?</section>', "", case, flags=re.S)
        case = re.sub(r"<!--fingerprint-->[0-9a-f]{64}<!--/fingerprint-->", "", case)
        home = (pages / "home.html").read_text(encoding="utf-8")
        return (_text(re.sub(r'<span class="pill neu" data-benchmark.*?</span>', "", case)),
                re.findall(r'data-count="[^"]*"[^>]*>[^<]*', home),
                records.state(store.get_run(run.key), store), store.get_run(run.key).check_verdict)
    before = drawn()
    benchmarks.mark(store, run, who="a tester")
    try:
        after = drawn()
    finally:
        benchmarks.unmark(store, run.key)
        drawn()
    examined(4, "readings of one run, marked and not")
    assert before[2:] == after[2:] == (records.NO, "contradicts")
    assert before[1] == after[1]
    #: Less the times the page was drawn at, which differ between two drawings.
    clock = re.compile(r"\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d)?(?:\+00:00| UTC)?")
    assert clock.sub("", before[0]) == clock.sub("", after[0])


def test_sabotage_a_badge_that_said_correct_is_caught(examined):
    from onetrace_console import benchmarks
    examined(1, "badge word")
    assert benchmarks.BADGE == "benchmark"
    planted = '<span class="pill neu" data-benchmark title="x">correct</span>'
    assert {b for _t, b in re.findall(r'data-benchmark title="([^"]*)">([^<]*)</span>', planted)} != {"benchmark"}


# ------------------------------------------------------------------ 4. "What changed?"

def test_what_changed_takes_a_benchmark_first_and_names_its_rule(demo, examined):
    from onetrace_console import what_changed as wc
    folder, store, runs = demo
    want = {"p8-43-invoice-tolerance-5pct": ("p8-42-invoice-tolerance-2pct", wc.BENCHMARK_INPUTS),
            "p1-08-candidate-set2": ("p1-02-baseline-set2", wc.BENCHMARK_INPUTS)}
    examined(len(want), "runs' choices")
    for name, (other, rule) in want.items():
        got = wc.choose(runs[name], store, public=True)
        assert (got[0].run_id, got[1]) == (other, rule), name
        case = (folder / "store" / "pages" / "runs" / runs[name].key / "case.html").read_text(encoding="utf-8")
        sec = _section(case, "what-changed")
        assert f'data-rule="{rule}"' in sec and wc.rule_words(rule, True) in _text(sec), name
        assert "data-benchmark" in sec, name


def test_a_benchmark_taken_over_a_nearer_run_is_said(demo, examined):
    """Marked, an earlier run with the same inputs is taken over the one the rules take without it."""
    from onetrace_console import benchmarks
    from onetrace_console import what_changed as wc
    _folder, store, runs = demo
    run, far = runs["p1-08-candidate-set2"], runs["p1-01-baseline-set1"]
    plain = wc.choose(run, store, public=False)
    benchmarks.mark(store, far, who="a tester")
    try:
        got = wc.choose(run, store, public=False)
        sec = wc.section(run, store, public=False)
    finally:
        benchmarks.unmark(store, far.key)
    examined(2, "choices, with and without the mark")
    assert got[0].key in (far.key, runs["p1-02-baseline-set2"].key)
    assert got[1] == wc.BENCHMARK_INPUTS
    if got[0].key != wc.without_benchmarks(run, store, public=False).key:
        assert "A benchmark, taken over" in _text(sec)
    assert plain[1] == wc.BENCHMARK_INPUTS


def test_without_benchmarks_the_rules_are_as_before(demo, examined):
    from onetrace_console import what_changed as wc
    _folder, store, runs = demo
    examined(len(runs), "runs' candidates")
    for run in runs.values():
        found = wc.candidates(run, store, with_benchmarks=False) or []
        assert all(rule in (2, 3, 4) for _r, rule in found), run.run_id


def test_other_runs_with_the_same_inputs_opens_the_index(demo, examined):
    from urllib.parse import unquote
    from onetrace_console import run_index
    from onetrace_console import what_changed as wc
    folder, store, runs = demo
    index = run_index.read(folder / "store")
    seen = 0
    for run in runs.values():
        case = (folder / "store" / "pages" / "runs" / run.key / "case.html").read_text(encoding="utf-8")
        m = re.search(r'<p data-what-changed="same-inputs"><a href="\.\./\.\./search\?q=([^&"]*)&amp;run=([0-9a-f]{64})">'
                      r"Other runs with the same inputs: (\d+)</a></p>", case)
        if not run_index.first_inputs(next(r for r in index["runs"] if r["key"] == run.key)):
            assert m is None, run.run_id
            continue
        assert m, run.run_id
        q = unquote(m.group(1))
        assert q == f"inputs:same-as:{wc.run_ref(store, run)}" and m.group(2) == run.key
        assert int(m.group(3)) == len(run_index.query(index, q)) == run_index.same_inputs_count(index, run.key)
        seen += 1
    examined(seen, "runs' same-inputs lines")


# ------------------------------------------------------------------ 5. variation

def test_a_benchmark_recorded_again_shows_onetrace_s_profile(demo, examined):
    from onetrace_console import benchmarks
    from onetrace_console.stage_pages import _stage_name, _steps
    folder, store, runs = demo
    run = runs["p1-02-baseline-set2"]
    found = benchmarks.repeats(run, store)
    examined(len(found), "repeats")
    assert [o.run_id for o, _how in found] == ["p1-17-baseline-set2-unsigned"]
    case = (folder / "store" / "pages" / "runs" / run.key / "case.html").read_text(encoding="utf-8")
    sec = _section(case, "profile")
    assert "onetrace's profile of 2 runs" in _text(sec)
    assert 'data-scroll="profile"' in sec
    assert re.findall(r'<tr data-step="([^"]+)">', sec) == [_stage_name(s["receipt"]) for s in _steps(run, store)]


def test_the_reference_takes_only_repeats_whose_records_agree(demo, examined):
    """Each repeat found is in the reference's set or left out of it, and one left out is one whose
    records were not checked as agreeing."""
    from onetrace_console import benchmarks, records, verdicts
    _folder, store, runs = demo
    from pathlib import Path
    by_folder = {Path(str(r.folder)).name: r for r in runs.values()}
    examined(len(BENCHMARKS), "benchmarks")
    for name in BENCHMARKS:
        run = by_folder[name]
        found = {o.key for o, _h in benchmarks.repeats(run, store)}
        pick = verdicts.chosen(verdicts.pipeline_of(run, store), store)
        kept, left = {o.key for o in pick["repeats"]}, {o.key for o in pick["left_out"]}
        assert found == kept | left and not kept & left, name
        assert all(records.state(store.get_run(k), store) != records.YES for k in left), name
        assert all(records.state(store.get_run(k), store) == records.YES for k in kept), name


def test_a_run_not_marked_shows_no_profile(demo, examined):
    folder, store, runs = demo
    run = runs["p1-17-baseline-set2-unsigned"]
    case = (folder / "store" / "pages" / "runs" / run.key / "case.html").read_text(encoding="utf-8")
    examined(1, "page")
    assert 'data-section="profile"' not in case


def test_the_local_mark_says_it_moves_the_pipeline_s_reference(demo, examined):
    """Beside "Mark as benchmark": the press moves the pipeline's reference, and every verdict in the
    pipeline is then read against the new one; beside its undo, where the reference goes. A public
    console has neither control nor line."""
    import html as _html
    from onetrace_console import benchmarks, verdicts
    _folder, store, runs = demo
    unmarked, marked = runs["p1-14-candidate-set3-byte-changed"], runs["p1-02-baseline-set2"]
    label = verdicts.pipeline_of(unmarked, store).label
    said = {}
    for name, run in (("mark", unmarked), ("undo", marked)):
        sec = benchmarks.mark_section(run, store, public=False)
        said[name] = [_html.unescape(x) for x in re.findall(r"<p data-benchmark-moves>(.*?)</p>", sec)]
    examined(2, "local controls")
    assert said["mark"] == [benchmarks.MARK_MOVES.format(pipeline=label)]
    assert said["mark"][0].startswith(f"Marking this run moves {label}'s reference")
    assert f"every verdict in {label} is then read against the new one" in said["mark"][0]
    assert said["undo"] == [benchmarks.UNMARK_MOVES.format(pipeline=label)]
    assert "data-benchmark-moves" not in benchmarks.mark_section(marked, store, public=True)


# ------------------------------------------------------------------ 2. local POST, public refusal

def test_mark_and_undo_on_a_local_console(demo, tmp_path, examined):
    from tests.test_folder_load import _Console, _free_port
    folder, store, runs = demo
    port = _free_port()
    config = tmp_path / "local.json"
    config.write_text(json.dumps({"host": "127.0.0.1", "port": port, "store_root": str(folder / "store"),
                                  "trust_file": str(folder / "trust.json"), "sign_in": {"enabled": False}}),
                      encoding="utf-8")
    run = runs["p9-47-torque-tool-firmware-changed"]
    base = f"http://127.0.0.1:{port}"

    def post(query: str, body: bytes = b"") -> tuple[int, dict]:
        req = urllib.request.Request(f"{base}/benchmark?{query}", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    c = _Console(tmp_path, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config)})
    try:
        c.until("onetrace-console serving on")
        marked = post(f"run={run.key}&mark=yes", json.dumps({"note": "after the firmware change"}).encode())
        mark_file = json.loads((store.root / "benchmarks" / f"{run.key}.json").read_text(encoding="utf-8"))
        with urllib.request.urlopen(f"{base}/runs/{run.key}/case.html", timeout=60) as r:
            page = r.read().decode("utf-8")
        refused = [post(f"run={run.key}&mark=maybe"), post("run=nope&mark=yes"),
                   post(f"run={run.key}&mark=yes", b"[1]")]
        undone = post(f"run={run.key}&mark=no")
    finally:
        c.stop()
    examined(6, "presses")
    assert marked == (200, {"run_key": run.key, "benchmark": True})
    assert mark_file["note"] == "after the firmware change" and mark_file["run"] == run.key
    sec = _section(page, "benchmark")
    assert "after the firmware change" in sec and "data-benchmark-post" in sec
    assert [s for s, _ in refused] == [400, 400, 400]
    assert undone == (200, {"run_key": run.key, "benchmark": False})
    assert not (store.root / "benchmarks" / f"{run.key}.json").exists()


def test_a_public_console_has_no_mark_control_and_refuses_the_post(shared_cli_demo, examined):
    from tools import container_check
    from tests.test_public_mode import _pages
    built = shared_cli_demo["folder"]
    pages = _pages(built)
    examined(len(pages), "public pages")
    for rel in pages:
        page = (built / "store" / "pages" / rel).read_text(encoding="utf-8")
        assert "data-benchmark-post" not in page and "Mark as benchmark" not in page, rel
    #: And its POST is refused unread, with every other write (tests/test_public_mode.py).
    assert any(r.startswith("/benchmark?") for r in container_check.ROUTES)
