"""The runs list's "Kinds" column and the run index's `kind:` and `agent:` terms (`step_kinds`, `run_index`): the
kinds and agents a format 0.5 run records, each once, a member the verifier fails left out; "not recorded" for a
0.5 run with none, and nothing for a run in an earlier format. The runs list's search finds runs by them."""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

from tests.test_format_03 import _tar

HERE = Path(__file__).resolve().parent / "format_05_agents"
OLDER = Path(__file__).resolve().parent / "onetrace_runs" / "0.7.1" / "refund-closed"
RAN_AT = "2026-11-11T00:00:00+00:00"
KEPT = "decision · retrieval · model call · tool call; agents support-desk, triage, researcher"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


@pytest.fixture(scope="module")
def stored(tmp_path_factory):
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store

    store = Store(tmp_path_factory.mktemp("kinds") / "store")
    runs = {}
    for name, folder in (
        ("kept", HERE / "agents-kept"),
        ("not-kept", HERE / "agents-not-kept"),
        ("kind-failed", HERE / "reject" / "R41-step-kind-outside-list"),
        ("older", OLDER),
    ):
        runs[name] = run_and_record(accept(_tar(folder), store).run, store, ran_at=RAN_AT)
    return store, runs


def _cells(store, runs) -> dict[str, str]:
    from onetrace_console.pages import runs_table

    table = runs_table([store.get_run(r.key) for r in runs.values()], store)
    out = {}
    for name, run in runs.items():
        row = re.search(rf'<tr [^>]*data-key="{run.key}">.*?</tr>', table, re.S).group(0)
        cell = re.search(r'<td[^>]*data-answer="kinds"[^>]*>(.*?)</td>', row, re.S).group(1)
        out[name] = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", cell)).split())
    return out


def test_the_runs_list_has_a_kinds_column_read_from_each_run_s_record(stored, examined):
    from onetrace_console.pages import KINDS_COLUMN, runs_table

    store, runs = stored
    cells = _cells(store, runs)
    heads = re.findall(r"<th>([^<]*)</th>", runs_table([store.get_run(r.key) for r in runs.values()], store))
    examined(len(cells), "runs in the list")
    assert heads[heads.index("Closed") + 1] == KINDS_COLUMN
    assert cells["kept"] == cells["not-kept"] == KEPT
    assert cells["older"] == ""
    #: The vector's decision step records a kind the verifier fails ('tool'): left out, and the other seven kept.
    assert "tool call" in cells["kind-failed"] and "decision" not in cells["kind-failed"]
    assert cells["kind-failed"].split(";")[0].split(" · ")[-1] == "other"


def test_a_list_where_no_run_records_a_kind_or_an_agent_has_no_kinds_column(stored, examined):
    """On such a list every cell would read the same: the demo's lists, whose runs record none, are as before."""
    from onetrace_console.pages import KINDS_COLUMN, RUN_COLUMNS, runs_table

    store, runs = stored
    table = runs_table([store.get_run(runs["older"].key)], store)
    examined(1, "a list of a run that records no kind")
    assert re.findall(r"<th>([^<]*)</th>", table) == list(RUN_COLUMNS) and KINDS_COLUMN not in RUN_COLUMNS
    assert 'data-answer="kinds"' not in table


def test_a_0_5_run_with_no_kind_and_no_agent_reads_not_recorded(examined):
    from onetrace_console import step_kinds

    examined(2, "kept summaries")
    assert "not recorded" in step_kinds.cell('{"agents": [], "kinds": []}')
    assert step_kinds.cell("") == ""


def test_the_runs_search_finds_runs_by_kind_and_by_agent(stored, examined):
    from onetrace_console import run_index

    store, runs = stored
    index = run_index.build(store)
    found = {
        q: sorted(r.run["run_id"] for r in run_index.query(index, q))
        for q in ("kind:tool-call", "kind:decision", "agent:triage", "agent:support-desk")
    }
    examined(len(found), "queries")
    ids = {name: run.run_id for name, run in runs.items()}
    assert found["kind:tool-call"] == sorted([ids["kept"], ids["not-kept"], ids["kind-failed"]])
    assert found["kind:decision"] == sorted([ids["kept"], ids["not-kept"]])
    assert found["agent:triage"] == found["agent:support-desk"] == sorted([ids["kept"], ids["not-kept"]])
    with pytest.raises(run_index.QueryError, match="kind takes one of"):
        run_index.parse("kind:robot")


def test_the_changelog_names_the_run_index_s_move_under_changed(examined):
    """The release's notes name the index's new format under Changed, and what a console does with an older one."""
    from onetrace_console import run_index

    text = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.index("## [0.9.0]")  # `## [Unreleased]` until its version was set
    section = text[start : text.index("\n## [", start + 1)]
    changed = section[section.index("### Changed") :]
    end = changed.find("\n### ", 1)
    changed = changed if end < 0 else changed[:end]  # this subsection only
    examined(1, "the next release's Changed")
    assert f"`{run_index.FORMAT}`" in changed
    assert "`kind:`" in changed and "`agent:`" in changed
    assert "store writes" in changed and changed.count("\n- ") == 3
    assert "origin-<run id>.html" in changed
    assert "build it again" in changed and "when it next draws its pages" in changed


#: The CHANGELOG's line for the hosted demo, word for word.
HOSTED_DEMO = (
    "The hosted demo no longer records the P10 pair a second time beside the kept runs, so it shows four runs and one "
    "comparison fewer."
)


def test_the_changelog_names_the_hosted_demo_s_change_under_changed(examined):
    text = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.index("## [0.9.0]")  # `## [Unreleased]` until its version was set
    section = text[start : text.index("\n## [", start + 1)]
    changed = " ".join(section[section.index("### Changed") :].split())
    examined(1, "the next release's Changed")
    assert HOSTED_DEMO in changed
