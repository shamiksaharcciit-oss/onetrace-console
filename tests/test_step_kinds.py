"""Format 0.5's step kinds, agents and tool-call records on a run's pages (`step_kinds`): the run's head names the
run's agent, each step's line in the table of steps gives its kind and its own agent, and each step's page has a
section with its kind, its agent and its tool-call record, `requested_by` linked. Each member present, absent and
failed by the verifier, on the runs in `tests/format_05_agents/`."""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

from tests.test_format_03 import _tar

HERE = Path(__file__).resolve().parent / "format_05_agents"
OLDER = Path(__file__).resolve().parent / "onetrace_runs" / "0.7.1" / "refund-closed"
RAN_AT = "2026-11-11T00:00:00+00:00"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _text(h: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", h)).split())


def _pages(folder: Path, tmp_path) -> dict[str, str]:
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store

    store = Store(tmp_path / "store")
    run = run_and_record(accept(_tar(folder), store).run, store, ran_at=RAN_AT)
    return dict(render_execution(store.get_run(run.key), store, generated_at=RAN_AT).pages)


def _head(pages) -> str:
    m = re.search(
        r'<(p|div) class="sub" data-section="run-agent".*?</\1>|<div data-section="run-agent".*?</div>',
        pages["proof.html"],
        re.S,
    )
    return _text(m.group(0)) if m else ""


def _lines(pages) -> list[str]:
    return [_text(m.group(0)) for m in re.finditer(r'<div class="step" data-step-kind.*?</div>', pages["proof.html"])]


def _section(page: str) -> str:
    m = re.search(r'<section data-section="step-kind".*?</section>', page, re.S)
    return m.group(0) if m else ""


def test_present_the_head_the_steps_lines_and_each_step_page(tmp_path, examined):
    from onetrace_console.step_kinds import NON_CLAIMS, prose

    pages = _pages(HERE / "agents-kept", tmp_path)
    stage_pages = {n: p for n, p in pages.items() if n.startswith("stage-")}
    examined(len(stage_pages) + 2, "the run's head, its table of steps and its step pages")
    assert _head(pages) == "The run's agent: support-desk · orchestrator · on example-graph (framework)"
    assert _lines(pages) == [
        "kind not recorded",
        "decision · agent triage",
        "retrieval · agent researcher",
        "model call",
        "tool call",
        "kind not recorded",
    ]
    assert all(prose(NON_CLAIMS) in _section(p) for p in stage_pages.values())
    tool = _section(stage_pages["stage-5.html"])
    assert "Kind: tool call" in _text(tool) and "Agent: the run's, support-desk" in _text(tool)
    assert "Tool: order_status · call id call-1" in _text(tool)
    assert '<a href="stage-4.html">draft</a>' in tool and "Requested by: draft , call id call-1" in _text(tool)
    assert "Agent: triage · router · on example-model 1 (model)" in _text(_section(stage_pages["stage-2.html"]))


def test_absent_a_kind_reads_not_recorded_and_an_earlier_format_gets_nothing(tmp_path, examined):
    pages = _pages(HERE / "agents-kept", tmp_path / "a")
    older = _pages(OLDER, tmp_path / "b")
    examined(2, "a format 0.5 step with no kind, and a format 0.4 run")
    assert "Kind: not recorded" in _text(_section(pages["stage-6.html"]))
    assert "other" not in _text(_section(pages["stage-6.html"])).split("Agent:")[0]
    assert not any('data-section="step-kind"' in p or "data-step-kind" in p for p in older.values())
    assert not any('data-section="run-agent"' in p for p in older.values())


def test_malformed_a_member_the_verifier_fails_is_not_drawn_its_row_is(tmp_path, examined):
    kind = _pages(HERE / "reject" / "R41-step-kind-outside-list", tmp_path / "k")
    agent = _pages(HERE / "reject" / "R47-run-agent-disagrees", tmp_path / "a")
    asked = _pages(HERE / "reject" / "R45-requested-by-not-earlier", tmp_path / "r")
    examined(3, "runs whose kind, run agent and tool request the verifier fails")
    assert "[FAIL ] receipts/04-decision.json: step kind -- 'tool' is outside the eight" in _lines(kind)
    assert "'tool'" not in _text(_section(kind["stage-4.html"])).replace("-- 'tool' is outside", "")
    assert "[FAIL ] run agent -- the receipts disagree on run_agent" in _head(agent)
    section = _section(asked["stage-2.html"])
    assert "[FAIL ] receipts/02-weather.json: tool_call requested_by -- answer is not an earlier step" in _text(section)
    assert "<a href=" not in section.split("Requested by")[1]


def test_sabotage_a_console_that_draws_a_failed_kind_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import step_kinds

    monkeypatch.setattr(step_kinds, "failed", lambda rows, subject, names: [])
    kind = _pages(HERE / "reject" / "R41-step-kind-outside-list", tmp_path)
    examined(1, "a run whose kind the verifier fails, drawn from anyway")
    assert "tool" in _lines(kind)
