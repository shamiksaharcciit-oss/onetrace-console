"""Tokens and cost, as recorded (`usage`): format 0.5's `model_usage` on a step's page, a run's case page, a
pipeline's page through the run index, and a comparison side by side. A value onetrace marks `not observed` reads
"not recorded", never 0; cost only where a record holds it, never summed across currencies; an entry the verifier
fails is not drawn. Present, absent, not observed and failing, on `tests/format_05_usage/`."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from tests.test_format_03 import _tar
from tests.test_format_05_agents_runs import _verify
from tests.test_step_kinds import OLDER, _pages, _text

HERE = Path(__file__).resolve().parent / "format_05_usage"
RECORDED = ("usage-a", "usage-b")
RAN_AT = "2026-11-12T00:00:00+00:00"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _usage(page: str) -> str:
    m = re.search(r'<section data-section="usage">.*?</section>', page, re.S)
    return m.group(0) if m else ""


def _case(pages: dict[str, str]) -> str:
    return _usage(pages["case.html"] + pages["proof.html"])


def _store(tmp_path, folders):
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store

    store = Store(tmp_path / "store")
    keys = {n: run_and_record(accept(_tar(f), store).run, store, ran_at=RAN_AT).key for n, f in folders.items()}
    return store, keys


def test_every_file_is_the_one_its_provenance_names_and_each_run_verifies(examined):
    said = {}
    for line in (HERE / "PROVENANCE.md").read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"- `((?:accept|reject)/[^`]+)`: `sha256:([0-9a-f]{64})`", line.strip())
        if m:
            said[m.group(1)] = m.group(2)
    have = {
        p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for d in ("accept", "reject")
        for p in (HERE / d).rglob("*")
        if p.is_file()
    }
    made = json.loads((HERE / "MADE.json").read_text(encoding="utf-8"))
    examined(len(have) + 2, "vector files and recorded runs")
    assert have and have == said
    assert made["versions"]["onetrace"] == "0.8.0" and sorted(made["runs"]) == sorted(RECORDED)
    assert all(_verify(HERE / n) == (0, "PASS", []) for n in RECORDED)


def test_present_each_record_s_tokens_on_its_step_and_the_run_s_totals(tmp_path, examined):
    from onetrace_console.step_kinds import prose
    from onetrace_console.usage import NO_COST, NON_CLAIMS

    pages = _pages(HERE / "usage-a", tmp_path)
    step = _text(_usage(pages["stage-1.html"]))
    case = _text(_case(pages))
    examined(2, "a step's tokens and the run's totals")
    assert "model_call.json , model example-model : Input tokens: 12 · Output tokens: 5 · Total tokens: 17" in step
    assert "example-model 2 12 (1 call with none recorded) 5 (1 call with none recorded) 17 (1 call with none" in case
    assert NO_COST in case and prose(NON_CLAIMS) in _case(pages)


def test_not_observed_reads_not_recorded_never_zero(tmp_path, examined):
    from onetrace_console.usage import NOT_RECORDED

    step = _text(_usage(_pages(HERE / "usage-a", tmp_path)["stage-2.html"]))
    examined(1, "a call whose answer reported no tokens")
    assert f"Input tokens: {NOT_RECORDED} · Output tokens: {NOT_RECORDED} · Total tokens: {NOT_RECORDED}" in step
    assert not re.search(r"tokens: 0\b", step)


def test_cost_shows_only_where_recorded_with_its_currency(tmp_path, examined):
    from onetrace_console.usage import NO_COST

    pages = _pages(HERE / "accept" / "A202-model-usage-cost", tmp_path)
    examined(2, "a step and a run whose record holds a cost")
    assert "Cost: 0.0012 USD" in _text(_usage(pages["stage-1.html"]))
    assert "0.0012 USD" in _text(_case(pages)) and NO_COST not in _text(_case(pages))


def test_two_records_on_one_step_are_each_drawn_and_summed(tmp_path, examined):
    pages = _pages(HERE / "accept" / "A203-model-usage-two-records", tmp_path)
    examined(2, "a step with two records")
    assert _usage(pages["stage-1.html"]).count("data-usage-record=") == 2
    assert re.search(r" 2 6 2 8 not recorded", _text(_case(pages)))


def test_costs_are_never_summed_across_currencies(examined):
    from onetrace_console.usage import totals

    entries = [
        {"input_tokens": "1", "output_tokens": "1", "total_tokens": "2", "cost": ["0.5", "USD"]},
        {"input_tokens": "1", "output_tokens": "1", "total_tokens": "2", "cost": ["0.25", "USD"]},
        {"input_tokens": "1", "output_tokens": "1", "total_tokens": "2", "cost": ["0.4", "EUR"]},
    ]
    (row,) = totals({"m": entries})
    examined(3, "costs in two currencies")
    assert row["cost"] == "0.4 EUR; 0.75 USD"


def test_absent_a_run_with_no_model_usage_and_an_earlier_format_get_no_section(tmp_path, examined):
    state = _pages(HERE.parent / "format_05_state" / "state-kept", tmp_path / "s")
    older = _pages(OLDER, tmp_path / "o")
    examined(2, "a format 0.5 run with no model call, and a format 0.4 run")
    assert not any('data-section="usage"' in p for p in state.values())
    assert not any('data-section="usage"' in p for p in older.values())


@pytest.mark.parametrize(
    ("name", "said"),
    [
        ("R301-usage-total-below-part", "total_tokens 2 is less than a part"),
        ("R302-usage-record-not-an-output", "model_call.9.json: not an output of this receipt"),
        ("R304-usage-second-entry", "a second entry for one record"),
    ],
)
def test_malformed_an_entry_the_verifier_fails_is_not_drawn_its_row_is(name, said, tmp_path, examined):
    from onetrace_console import run_index

    pages = _pages(HERE / "reject" / name, tmp_path)
    store, keys = _store(tmp_path / "i", {"run": HERE / "reject" / name})
    section = _usage(pages["stage-1.html"])
    examined(2, f"{name}'s step page and its index entry")
    assert "[FAIL ]" in _text(section) and said in _text(section) and "data-usage-record=" not in section
    assert not any("usage" in s for r in run_index.build(store)["runs"] for s in r["steps"])


def test_a_pipeline_s_totals_across_its_runs_come_through_the_run_index(tmp_path, examined):
    from onetrace_console import run_index
    from onetrace_console.usage import NOT_INDEXED, pipeline_section

    store, keys = _store(tmp_path, {n: HERE / n for n in RECORDED})
    index = run_index.build(store)
    with run_index.drawing(index, "2026-11-12T00:00:00+00:00"):
        across = _text(pipeline_section(list(keys.values())))
    earlier = {k: v for k, v in index.items() if k != run_index.USAGE}
    with run_index.drawing(earlier):
        not_indexed = _text(pipeline_section(list(keys.values())))
    examined(2, "a pipeline's totals from the index, and from an index that holds none")
    assert "example-model 4 32 (2 calls with none recorded) 11 (2 calls with none recorded) 43" in across
    assert "Read from the run index" in across and NOT_INDEXED in not_indexed


def test_a_comparison_shows_each_run_s_totals_side_by_side_and_no_verdict(tmp_path, examined):
    from onetrace_console.usage import comparison_section

    store, keys = _store(tmp_path, {n: HERE / n for n in RECORDED})
    section = _text(comparison_section(store.get_run(keys["usage-a"]), store.get_run(keys["usage-b"]), store))
    examined(2, "two runs' totals")
    assert section.index("Run A: usage-a") < section.index("17 (1 call") < section.index("Run B: usage-b")
    assert "26 (1 call" in section
    assert not re.search(r"\b(more|fewer|less|higher|lower|increase|decrease|regress|better|worse)\b", section, re.I)


def test_sabotage_a_page_that_reads_not_observed_as_zero_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import usage

    real = usage._observed
    monkeypatch.setattr(usage, "_observed", lambda v: real(v) or "0")
    step = _text(_usage(_pages(HERE / "usage-a", tmp_path)["stage-2.html"]))
    examined(1, "a page drawn with not observed read as 0")
    assert re.search(r"tokens: 0\b", step)
