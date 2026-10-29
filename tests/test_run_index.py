"""The exact run index (`run_index`) and its search (`search_page`), over the demo as built.

1. The index is a derived file beside the store: deleting it and rebuilding it gives the same bytes
   and the same answers; a build writes it, and a later drawing of the pages writes it again.
2. What it holds, per run, is the record's own: ids, chain head, each step's outcome, instrument,
   settings, inputs and outputs by name and digest, the manifest's declarations, the verifier's
   verdict and its FAIL and NOT-RUN rows, the model-call records' fields; per held comparison, the
   first differing step and what differed. No text: no kept input's bytes are in it.
3. Each term of the grammar answers the runs the record says, each with the fields that matched;
   a sabotaged index answers differently, so the answers are read from it.
4. A query the grammar does not hold is refused in words.
5. The results page: the box on the Runs page and on each run's page, the matched fields shown,
   "Compare with this run" opening a held comparison; a public console's query writes nothing.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

P1_CANDIDATE = "p1-08-candidate-set2"
P1_BASELINE = "p1-02-baseline-set2"


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console import run_index
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    index = run_index.read(folder / "store")
    assert index is not None, "the build wrote no index"
    return folder, store, index


def _run(index, run_id):
    return next(r for r in index["runs"] if r["run_id"] == run_id)


def _ids(results):
    return [r.run["run_id"] for r in results]


# ------------------------------------------------------------------- 1. derived, rebuilt

def test_deleting_the_index_and_rebuilding_it_gives_the_same_file_and_answers(shared_demo, tmp_path, examined):
    from tests.conftest import demo_copy
    from onetrace_console import run_index
    from onetrace_console.store import Store
    folder = demo_copy(shared_demo, tmp_path / "demo")
    path = folder / "store" / run_index.FILE_NAME
    before = path.read_bytes()
    queries = ["setting:*.chunk_size=512", "benchmark:yes", "verdict:FAIL", "first_diff:any:setting",
               f"inputs:same-as:{P1_BASELINE}", "pipeline:P8 gated:approve_payment"]
    answers = [_ids(run_index.query(run_index.read(folder / "store"), q)) for q in queries]
    path.unlink()
    assert run_index.read(folder / "store") is None
    run_index.write(Store(folder / "store" / "store"), folder / "store")
    examined(len(queries) + 1, "the index's bytes and answers, before and after a rebuild")
    assert path.read_bytes() == before
    assert [_ids(run_index.query(run_index.read(folder / "store"), q)) for q in queries] == answers


def test_drawing_the_pages_writes_the_index(shared_demo, tmp_path, examined):
    from tests.conftest import demo_copy
    from onetrace_console import run_index
    from onetrace_console.config import Config
    from onetrace_console.serve import _render_all_pages
    from onetrace_console.store import Store
    folder = demo_copy(shared_demo, tmp_path / "demo")
    path = folder / "store" / run_index.FILE_NAME
    before = path.read_bytes()
    path.unlink()
    _render_all_pages(Store(folder / "store" / "store"), folder / "store", Config(public=True))
    examined(1, "index written by a drawing of the pages")
    assert path.read_bytes() == before


# ------------------------------------------------------------------- 2. what it holds

def test_a_run_s_entry_is_its_record_s_own(demo, examined):
    from onetrace_console.stage_pages import _steps
    _folder, store, index = demo
    run = store.runs_with_id(P1_CANDIDATE)[0]
    entry = _run(index, P1_CANDIDATE)
    steps = _steps(run, store)
    examined(len(steps), "steps of one run against its receipts")
    assert (entry["key"], entry["chain_head"], entry["pipeline_label"]) == (run.key, run.chain_head, "P1")
    assert [s["name"] for s in entry["steps"]] == [s["receipt"]["stage"]["name"] for s in steps]
    for got, s in zip(entry["steps"], steps):
        r = s["receipt"]
        assert got["outcome"] == r["outcome"]["class"]
        assert got["instrument"] == {"id": r["instrument"]["id"], "version": r["instrument"]["version"]}
        assert got["settings"] == (r.get("assertions") or {}).get("constants", {})
        assert got["inputs"] == [[i["name"], i["digest"]] for i in r["inputs"]]
        assert got["outputs"] == [[o["name"], o["digest"]] for o in r["outputs"]]
    assert entry["steps"][1]["settings"]["chunk_size"] == "512"
    assert entry["declared"].get("outputs_kept") == "all"


def test_the_verdict_and_rows_are_the_verifier_s(demo, examined):
    from onetrace_console.info_mark import rows_of
    from onetrace_console.pages import _envelope
    _folder, store, index = demo
    seen = 0
    for entry in index["runs"]:
        run = store.get_run(entry["key"])
        envelope = _envelope(run, store, required=False)
        rows = rows_of(envelope)
        doc = json.loads(envelope["rows_json"]["stdout"])
        assert entry["verdict"] == doc["summary"]["result"], entry["run_id"]
        for result in ("FAIL", "NOT-RUN"):
            assert entry["rows"].get(result, []) == [r["name"] for r in rows if r["result"] == result]
        seen += 1
    examined(seen, "runs' verdicts and rows")
    assert {e["verdict"] for e in index["runs"]} == {"PASS", "FAIL"}


def test_each_held_comparison_s_first_difference_is_its_short_answer_s(demo, examined):
    from onetrace_console.render import short_headline
    _folder, store, index = demo
    held = {c.key: c for c in store.comparisons()}
    examined(len(index["comparisons"]), "held comparisons")
    assert len(index["comparisons"]) == len(held)
    for c in index["comparisons"]:
        first = c["first_diff"]
        headline = short_headline(held[c["key"]], store)
        if first["steps"]:
            assert any(f"`{s}`" in headline for s in first["steps"]), (headline, first)
        for name in first["settings"]:
            assert f"`{name}`" in headline, (headline, first)
    p1 = next(c for c in index["comparisons"]
              if (c["a"], c["b"]) == (store.runs_with_id(P1_BASELINE)[0].key, store.runs_with_id(P1_CANDIDATE)[0].key))
    assert p1["first_diff"] == {"steps": ["split"], "kinds": ["setting"], "settings": ["chunk_size"], "inputs": []}


def test_model_call_fields_are_read_as_the_record_states_them(demo, examined):
    _folder, _store, index = demo
    calls = [(r["run_id"], c) for r in index["runs"] for s in r["steps"] for c in s.get("model_calls", [])]
    examined(len(calls), "model-call records")
    assert calls
    first = next(c for _r, c in calls if c["file"] == "model_call.json")
    #: The demo's records are example data: what a call would name is declared, nothing observed.
    assert first["fields"]["engine"] == {"status": "declared, not observed", "value": "vllm"}
    assert first["fields"]["weights"]["value"].startswith("sha256:")


def test_no_kept_input_s_bytes_are_in_the_index(demo, examined):
    """The index holds digests, never the text the runs read: no kept input file's contents."""
    folder, _store, index = demo
    text = (folder / "store" / "run_index.json").read_text(encoding="utf-8")
    kept = [p for p in sorted((folder / "runs").rglob("*.json"))
            if p.parent.name == "inputs" or p.name in ("questions.json", "documents.json")]
    examined(len(kept), "kept input files")
    assert kept
    for p in kept:
        for value in _strings(json.loads(p.read_text(encoding="utf-8"))):
            if len(value) >= 12 and not value.startswith("sha256:"):
                assert value not in text, (p.name, value[:40])


def _strings(doc):
    if isinstance(doc, str):
        yield doc
    elif isinstance(doc, dict):
        for v in doc.values():
            yield from _strings(v)
    elif isinstance(doc, list):
        for v in doc:
            yield from _strings(v)


# --------------------------------------------------------------------- 3. the grammar

def test_each_term_answers_the_runs_the_record_says(demo, examined):
    from onetrace_console import run_index as ri
    _folder, store, index = demo
    by_id = {r["run_id"]: r for r in index["runs"]}
    want = {
        "setting:split.chunk_size=512": [r for r in by_id if r.startswith("p1-") and "candidate" in r],
        "setting:*.chunk_size=1024": [r for r in by_id if r.startswith("p1-") and "baseline" in r],
        "first_diff:split": [P1_CANDIDATE],
        "first_diff:any:setting": [P1_CANDIDATE, "demo-run-2", "p3-27-t-1-rules2", "p8-43-invoice-tolerance-5pct"],
        "verdict:fail": [r for r, e in by_id.items() if e["verdict"] == "FAIL"],
        "pipeline:p9": ["p9-46-torque-baseline", "p9-47-torque-tool-firmware-changed", "p9-48-torque-one-bolt-low"],
        "since:pz-53-agent-amount-changed": ["pz-54-agent-amount-changed-subagent"],
        "engine:vllm": ["pz-51-agent-baseline", "pz-53-agent-amount-changed"],
        "benchmark:yes": [r for r, e in by_id.items() if e["benchmark"]],
        "gated:approve_payment": [r for r in by_id if r.startswith("p8-")],
    }
    for q, runs in want.items():
        assert _ids(ri.query(index, q)) == [r for r in by_id if r in runs], q
    same = ri.query(index, f"inputs:same-as:{P1_BASELINE}")
    mine = ri.first_inputs(by_id[P1_BASELINE])
    assert _ids(same) == [r for r, e in by_id.items() if r != P1_BASELINE and ri.first_inputs(e) == mine]
    digest = by_id[P1_CANDIDATE]["steps"][0]["inputs"][0]
    assert P1_CANDIDATE in _ids(ri.query(index, f"input:{digest[0]}={digest[1]}"))
    row = by_id["p1-15-candidate-set4-file-deleted"]["rows"]["FAIL"][0]
    assert _ids(ri.query(index, f'row:"{row}"=FAIL')) == ["p1-15-candidate-set4-file-deleted"]
    weights = next(c for s in by_id["pz-51-agent-baseline"]["steps"] for c in s.get("model_calls", [])
                   if "weights" in c["fields"])["fields"]["weights"]["value"]
    assert _ids(ri.query(index, f"model:weights={weights}")) == ["pz-51-agent-baseline", "pz-53-agent-amount-changed"]
    examined(len(want) + 4, "queries")


def test_every_result_names_what_matched_as_recorded(demo, examined):
    from onetrace_console import run_index as ri
    _folder, _store, index = demo
    got = ri.query(index, "pipeline:P1 setting:split.chunk_size=512 benchmark:no")
    examined(len(got), "results")
    assert got
    for r in got:
        assert r.matched == ("pipeline P1", "setting split.chunk_size = 512", "not marked as a benchmark")


def test_diff_same_as_finds_runs_that_first_differ_the_same_way(demo, examined):
    """`diff:same-as:X`: the runs whose held comparison has X's baseline and X's first difference."""
    from onetrace_console import run_index as ri
    _folder, _store, index = demo
    index = copy.deepcopy(index)
    p5 = [c for c in index["comparisons"] if c["first_diff"]["steps"] == ["calibrate"]]
    assert p5
    twin = copy.deepcopy(p5[0])
    other = next(r for r in index["runs"] if r["pipeline_label"] == "P5" and r["key"] not in (twin["a"], twin["b"]))
    twin["b"], twin["key"] = other["key"], "0" * 64
    index["comparisons"].append(twin)
    named = next(r for r in index["runs"] if r["key"] == p5[0]["b"])["run_id"]
    got = ri.query(index, f"diff:same-as:{named}")
    examined(len(got), "results")
    assert _ids(got) == [other["run_id"]]
    assert got[0].matched[0].endswith(f"as {named} does")


def test_sabotage_a_changed_index_answers_differently(demo, examined):
    """The answers are the index's: a setting changed in it changes what a query finds."""
    from onetrace_console import run_index as ri
    _folder, _store, index = demo
    planted = copy.deepcopy(index)
    _run(planted, P1_CANDIDATE)["steps"][1]["settings"]["chunk_size"] = "999"
    examined(2, "queries over the index and a planted copy")
    assert P1_CANDIDATE in _ids(ri.query(index, "setting:split.chunk_size=512"))
    assert P1_CANDIDATE not in _ids(ri.query(planted, "setting:split.chunk_size=512"))
    assert _ids(ri.query(planted, "setting:split.chunk_size=999")) == [P1_CANDIDATE]


# ------------------------------------------------------------------------ 4. refused

@pytest.mark.parametrize("q, words", [
    ("nonsense", "is not a term"),
    ("colour:blue", "has no field 'colour'"),
    ("setting:chunk_size=512", "setting takes <step>.<name>=<value>"),
    ('row:"x"=PASS', "keeps the rows that read FAIL or NOT-RUN"),
    ("first_diff:any:mood", "first_diff:any: takes"),
    ("benchmark:maybe", "benchmark takes yes or no"),
    ("model:colour=red", "model's fields are"),
    ("inputs:same-as:no-such-run", "no run is named"),
])
def test_a_query_the_grammar_does_not_hold_is_refused_in_words(demo, q, words, examined):
    from onetrace_console import run_index as ri
    _folder, _store, index = demo
    examined(1, "query")
    with pytest.raises(ri.QueryError, match=words.replace("*", r"\*").replace("<", ".").replace(">", ".")):
        ri.query(index, q)


# ------------------------------------------------------------------------ 5. the page

def test_the_box_is_on_the_runs_page_and_every_run_s_page(demo, examined):
    folder, store, _index = demo
    pages = folder / "store" / "pages"
    runs_page = (pages / "executions-all.html").read_text(encoding="utf-8")
    assert 'data-section="runs-search"' in runs_page and 'action="search"' in runs_page
    runs = store.runs()
    examined(len(runs) + 1, "pages")
    for run in runs:
        case = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
        assert 'data-section="run-search"' in case and f'name="run" value="{run.key}"' in case, run.run_id


def test_the_results_page_shows_the_matches_and_opens_held_comparisons(demo, examined):
    from onetrace_console import run_index, search_page
    _folder, store, index = demo
    asked = store.runs_with_id(P1_BASELINE)[0]
    page = search_page.page(index, "setting:split.chunk_size=512", asked.key, store, public=True)
    examined(1, "results page")
    assert "10 runs match every term." in page
    assert page.count("setting split.chunk_size = 512") == 10
    held = next(c for c in store.comparisons() if c.run_a == asked.key)
    assert f'href="diff/{held.key}.html" data-search="compare"' in page
    assert 'data-search="not-held"' in page and "data-compare-post" not in page
    local = search_page.page(index, "setting:split.chunk_size=512", asked.key, store, public=False)
    assert "data-compare-post" in local
    assert run_index.QueryError.__name__ and 'data-search="refused"' in search_page.page(index, "x", "", store, public=True)


def test_a_public_console_s_query_writes_nothing_and_answers(shared_cli_demo, tmp_path, examined):
    from tests.test_public_mode import _config, _tree
    from tests.test_folder_load import _Console
    import urllib.request
    built = shared_cli_demo["folder"]
    config = _config(tmp_path, built, compare_cache=str(tmp_path / "compared"))
    port = json.loads(config.read_text(encoding="utf-8"))["port"]
    before = _tree(built)
    c = _Console(tmp_path, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config)})
    try:
        c.until("onetrace-console serving on")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/search?q=benchmark%3Ayes", timeout=30) as r:
            page = r.read().decode("utf-8")
            status = r.status
    finally:
        c.stop()
    examined(1, "query on a public console")
    assert status == 200 and "10 runs match every term." in page and 'data-frame="banner"' in page
    assert _tree(built) == before
