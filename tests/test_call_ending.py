"""How a model call ended, and a self-hosted call's engine, from a `model-call-record/1.1` record, on its step's page.

On onetrace 0.8.0's own vectors (`tests/format_04_item8/`): hosted calls at L1 and L2 (A13), self-hosted vLLM calls
at L1 to L3 (A17), and a hosted call that failed after post (A205). Read where a 1.1 record holds the field; absent
and silent where it doesn't, and nothing for a record in 1.0.
"""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent / "format_04_item8" / "accept"
RAN_AT = "2026-11-13T00:00:00+00:00"


def _records(name: str) -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((HERE / name).glob("artifacts/*/model_call.json"))
    ]


def test_how_each_call_ended_is_said_as_its_record_states_it(examined):
    from onetrace_console.call_ending import ended_line

    said = {
        name: [unescape(re.sub(r"<[^>]+>", "", ended_line(r))) for r in _records(name)]
        for name in (
            "A13-model-call-1-1",
            "A17-model-call-1-1-self-hosted",
            "A205-model-call-failed",
        )
    }
    examined(sum(len(v) for v in said.values()), "records")
    assert said["A13-model-call-1-1"] == ["How the request ended: stop"] * 2
    assert said["A17-model-call-1-1-self-hosted"][-1] == "How the request ended: stop-string"
    assert said["A205-model-call-failed"] == ["How the request ended: not observed: the call failed after post"]


def test_a_self_hosted_call_names_its_engine_and_a_hosted_one_does_not(examined):
    from onetrace_console.call_ending import engine_line

    l3 = _records("A17-model-call-1-1-self-hosted")[-1]
    text = unescape(re.sub(r"<[^>]+>", "", engine_line(l3)))
    examined(2, "records")
    assert text.startswith("The engine: vllm; model_runner "), text
    for key in ("engine.settings.model_runner", "engine.settings.engine_core", "engine.settings.executor"):
        assert l3[key]["value"] in text, key
    assert engine_line(_records("A13-model-call-1-1")[0]) == ""


def test_absent_and_silent_where_the_record_does_not_hold_it(examined):
    from onetrace_console.call_ending import lines

    record = _records("A13-model-call-1-1")[0]
    examined(3, "records")
    assert lines({k: v for k, v in record.items() if k != "output.finish"}) == ""
    assert lines({**record, "format": "model-call-record/1.0"}) == ""
    assert lines({"format": "model-call-record/1.1"}) == ""


@pytest.fixture(scope="module")
def held(tmp_path_factory):
    from tests.test_checks import _require_installed

    _require_installed()
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from tests.test_format_03 import _tar

    store = Store(tmp_path_factory.mktemp("calls") / "store")
    runs = {
        n: run_and_record(accept(_tar(HERE / n), store).run, store, ran_at=RAN_AT)
        for n in ("A13-model-call-1-1", "A17-model-call-1-1-self-hosted", "A205-model-call-failed")
    }
    return store, runs


def test_each_record_s_step_page_says_it_above_its_fields(held, examined):
    from onetrace_console.pages import render_execution

    store, runs = held
    seen = 0
    for name, run in runs.items():
        pages = render_execution(run, store, generated_at=RAN_AT).pages
        for rel, page in pages.items():
            if not rel.startswith("stage-") or 'data-section="model-call"' not in page:
                continue
            seen += 1
            section = page[page.index('data-section="model-call"') :]
            assert "data-call-ended=" in section, (name, rel)
            #: Above the record's fields.
            assert section.index("data-call-ended=") < section.index("data-model-call-table"), (name, rel)
            if name.startswith("A17"):
                assert 'data-call-engine="vllm"' in section, (name, rel)
    examined(seen, "steps' pages with a 1.1 record")
    assert seen >= 6
