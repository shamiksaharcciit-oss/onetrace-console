"""The "Ran as approved" rung, in the console.

The rung is the viewer's (re-vendored); the console's part is to run the check that has the
rows. Under 0.1.2 there was no plan row, and the rung said so. Now the console runs the 0.2.0
CLI and reads its rows from `--json`, so a graph run that followed its plan reads yes. A
straight-line run's rung has no state word, only its line.
"""
from __future__ import annotations

import re
from html import unescape
from importlib.metadata import version

from tests.test_run_page_marks import _case, runs  # noqa: F401  P, Q and R, delivered and checked


def _rung(page: str) -> tuple[str, str]:
    found = re.search(r'<tr data-rung="approved" data-state="([^"]+)">(.*?)</tr>', page, re.S)
    assert found, "no Ran as approved rung"
    #: Inline tags (a quotation, the state word's span) end without a space; cells with one.
    cells = re.sub(r"</?(?:q|span)\b[^>]*>", "", found.group(2))
    return found.group(1), " ".join(unescape(re.sub(r"<[^>]+>", " ", cells)).split())


def test_a_graph_run_checked_by_the_pinned_verifier_ran_as_approved(runs, examined):  # noqa: F811
    """The console's check is the installed CLI, and its rows are read from `--json`, where the
    two graph rows (no subject) can be read. So on the exam's three graph runs, which follow
    their plan, the rung says yes in its own words -- where, read from the text
    alone, it could only say the check that ran can't say."""
    from tests.test_pins import PINNED_VERIFY_VERSION
    found, store = runs
    assert version("onetrace-verify") == PINNED_VERIFY_VERSION
    examined(len(found), "graph runs' case pages read for the plan rung")
    for name, run in found.items():
        state, said = _rung(_case(run, store))
        assert state == "yes", (name, state, said)
        assert said == ("Ran as approved Yes · the check's plan row and its edges row both passed, "
                        "and the run itself verified"), (name, said)


def test_a_straight_line_run_s_rung_is_its_line_alone(store):
    """The exam's ingest-r1 run A has no `edges`: no state word, only the line."""
    from pathlib import Path
    from onetrace_console.checks import run_and_record
    from onetrace_console.pages import CASE, RUN_PROOF, render_execution
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    from tests.test_compare import _deliver
    _require_installed()
    folder = (Path(__file__).resolve().parent.parent / ".sdk-fixtures" / "exam" / "fixtures"
              / "ingest-r1" / "run_A")
    run = run_and_record(_deliver(folder, store), store, ran_at=FIXED_RAN_AT)
    #: The ladder is on "What changed", or on "Proof" for a run whose records don't hold up.
    drawn = render_execution(run, store, generated_at="2026-10-04T12:00:00+00:00").pages
    page = drawn[CASE] + drawn[RUN_PROOF]
    state, said = _rung(page)
    assert state == "not-a-graph-run", (state, said)
    assert said == "Ran as approved a straight-line run: there is no plan to compare", said


def test_a_graph_run_that_recorded_no_plan_reads_no_plan_recorded(examined):
    """onetrace-verify 0.5.0 leaves the plan row out for a graph run whose manifest declares no
    plan (an agent's run with a step inside it): the rung reads what the record holds, no approved
    plan recorded, never that the check couldn't say. A manifest that declares a plan, checked
    without a plan row, still reads can't check."""
    from onetrace_console.viewer.model import EDGES_ROW, CheckRows, ran_as_approved
    rows = CheckRows(((EDGES_ROW, "pass", ""),), "0", "pass")
    examined(2, "graph runs, one without a declared plan")
    edges = [{"from": "a", "to": "b"}]
    assert ran_as_approved({"edges": edges}, rows, own_check=True, verifier="onetrace-verify 0.5.0").state == "no-plan"
    assert ran_as_approved({"edges": edges, "declared_edges": edges}, rows, own_check=True,
                           verifier="onetrace-verify 0.5.0").state == "cant-check"


def test_the_demo_s_agent_runs_read_no_approved_plan_recorded(shared_demo, examined):
    import re
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    agents = [r for r in store.runs() if r.run_id.startswith("pz-")]
    examined(len(agents), "agent and sub-agent runs")
    assert agents
    for run in agents:
        case = (folder / "store" / "pages" / "runs" / run.key / "case.html").read_text(encoding="utf-8")
        row = re.search(r'<tr data-rung="approved" data-state="([^"]+)">(.*?)</tr>', case, re.S)
        assert row and row.group(1) == "not-declared" and "no approved plan recorded" in row.group(2), run.run_id
