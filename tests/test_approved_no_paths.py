""""Ran as approved" where a plan is declared and no path was observed: couldn't check, never yes.

A run that declares approved paths (`declared_edges`) and records no path it took (`edges` empty)
has nothing its plan can be compared with. A LangGraph graph's nodes pass their state on as fresh
values, so the SDK links no stage to another and the record lists no edges at all: a check that
"conforms to the plan" then conforms vacuously. The rung reads "Couldn't check", with the reason
"no paths were observed" -- on the run page and in the runs list.

The run is recorded here by the pinned SDK, in a subprocess, with no network calls: three stages,
each given a fresh copy of the state, under a run declaring three approved edges.
"""
from __future__ import annotations

import html
import os
import re
import subprocess
import sys
from pathlib import Path

GENERATED_AT = "2026-01-01T00:00:00+00:00"

GRAPH_RUN = '''
import onetrace as ot
from onetrace.emit import Instrument


def inst(name):
    return Instrument(name, "tool", "1.0.0", {}, "true")


@ot.stage("plan", instrument=inst("planner"), repeats=True)
def plan(state):
    return {**state, "draft": "The returns window is 30 days.", "tries": state["tries"] + 1}


@ot.stage("check", instrument=inst("checker"), repeats=True)
def check(state):
    return {**state, "ok": "30 days" in state["draft"]}


@ot.stage("act", instrument=inst("actor"))
def act(state):
    return {**state, "draft": state["draft"] + " [acted]"}


@ot.run(stages=["plan", "check", "act"],
        declared_edges=[{"from": "plan", "to": "check"}, {"from": "check", "to": "act"},
                        {"from": "check", "to": "plan"}])
def graph():
    state = {"q": "What is the returns window?", "draft": "", "tries": 0, "ok": False}
    return act(dict(check(dict(plan(dict(state))))))


graph()
'''


def _text(page: str) -> str:
    page = re.sub(r"<style.*?</style>|<script.*?</script>", " ", page, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _record(tmp_path: Path) -> Path:
    """The graph run, recorded into `tmp_path/runs/graph-1` by the pinned SDK."""
    script = tmp_path / "graph_run.py"
    script.write_text(GRAPH_RUN, encoding="utf-8")
    env = {**os.environ, "ONETRACE_RUN_ID": "graph-1"}
    p = subprocess.run([sys.executable, "-I", str(script)], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stdout + p.stderr
    return tmp_path / "runs"


def test_a_graph_run_with_no_observed_path_reads_couldnt_check_with_its_reason(tmp_path, examined):
    import json

    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.pages import CASE, render_execution, run_answers
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    runs = _record(tmp_path)
    manifest = json.loads((runs / "graph-1" / "MANIFEST.json").read_bytes())
    assert manifest["edges"] == [] and len(manifest["declared_edges"]) == 3, manifest
    store = Store(tmp_path / "store")
    run = load_folder(runs, store, Config()).runs[0].run
    examined(1, "graph run with no observed path")
    assert run.check_verdict == "holds", run
    assert run.approved == "no-paths", run.approved
    assert run_answers(run, store)["approved"] == "couldnt-check"
    page = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
    assert re.search(r'data-head-rung="approved" data-state="couldnt-check"', page)
    assert "no paths were observed" in _text(page)


#: The pinned verifier's own row for such a run: a plan declared, no path observed, nothing checked.
NO_EDGES_ROW = ("[NOT-RUN] edges conform to declared_edges -- no edges observed: the run declares an "
                "approved plan, but no stage read another stage's output as such, so no path was "
                "checked against it")


def test_the_verifier_s_own_row_says_so_on_proof_and_the_rung_still_reads_couldnt_check(tmp_path, examined):
    """The verifier now says it too, in its own NOT-RUN row: the run's check output on Proof shows
    the row as it wrote it, and the rung's reading and reason are the console's, unchanged."""
    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.pages import CASE, RUN_PROOF, render_execution
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    store = Store(tmp_path / "store")
    run = load_folder(_record(tmp_path), store, Config()).runs[0].run
    drawn = render_execution(run, store, generated_at=GENERATED_AT).pages
    examined(2, "views of the graph run")
    assert NO_EDGES_ROW in _text(drawn[RUN_PROOF]), "the verifier's row, on Proof"
    assert re.search(r'data-head-rung="approved" data-state="couldnt-check"', drawn[CASE] + drawn[RUN_PROOF])
    assert "no paths were observed" in _text(drawn[CASE])


def test_the_plan_and_edges_rows_passing_over_no_observed_path_is_never_yes(examined):
    """Where a check's plan row and edges row both pass, as a check that compares an empty list of
    paths with a plan passes: still couldn't check."""
    from onetrace_console.viewer.model import EDGES_ROW, PLAN_ROW, CheckRows, ran_as_approved
    rows = CheckRows(((PLAN_ROW, "pass", ""), (EDGES_ROW, "pass", "")), "0", "pass")
    declared = [{"from": "a", "to": "b"}]
    examined(3, "manifests read")
    assert ran_as_approved({"edges": [], "declared_edges": declared}, rows, own_check=True,
                           verifier=None).state == "no-paths"
    assert ran_as_approved({"edges": [{"from": "a", "to": "b"}], "declared_edges": declared}, rows,
                           own_check=True, verifier=None).state == "approved"
    assert ran_as_approved({"edges": [], "declared_edges": []}, rows, own_check=True,
                           verifier=None).state == "approved"


def test_a_departure_or_an_edges_mismatch_still_says_no(examined):
    from onetrace_console.viewer.model import EDGES_ROW, PLAN_ROW, CheckRows, ran_as_approved
    declared = [{"from": "a", "to": "b"}]
    manifest = {"edges": [], "declared_edges": declared}
    examined(2, "failing rows read")
    failed_plan = CheckRows(((PLAN_ROW, "fail", "x"), (EDGES_ROW, "pass", "")), "1", "fail")
    failed_edges = CheckRows(((PLAN_ROW, "pass", ""), (EDGES_ROW, "fail", "y")), "1", "fail")
    assert ran_as_approved(manifest, failed_plan, own_check=True, verifier=None).state == "departed"
    assert ran_as_approved(manifest, failed_edges, own_check=True,
                           verifier=None).state == "edges-mismatch"
