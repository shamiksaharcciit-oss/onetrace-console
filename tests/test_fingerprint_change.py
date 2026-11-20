"""The model fingerprint across runs: a pipeline's page says on which day its runs' model identity changed, with the
runs either side, and its drift page marks the run where the change was first seen.

The identity is three fields of each model-call record, as onetrace's comparator groups them: `provider.fingerprint`,
`model.reported`, `model.files_digest`. P12's runs (example data): the fourth run's provider fingerprint differs from
the third's. The page says plainly that a fingerprint change says the provider's system changed, not that the output got
worse.
"""

from __future__ import annotations

import html
import re

import pytest

GENERATED_AT = "2026-11-18T23:30:00+00:00"


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.fixture(scope="module")
def held(tmp_path_factory):
    from onetrace_console import demo_store
    from onetrace_console.checks import run_and_record
    from onetrace_console.demo_store import onedoor_demo
    from onetrace_console.overview import pipelines
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver

    folder = tmp_path_factory.mktemp("fingerprint")
    runs, store = folder / "runs", Store(folder / "store")
    runs.mkdir()
    issuer = onedoor_demo.Issuer()
    specs = [s for s in demo_store.runs() if s.pipeline == "p12"]
    for spec in specs:
        demo_store._record(spec, runs / spec.folder, issuer)
    issuer.write_beside(runs)
    stored = [run_and_record(_deliver(runs / s.folder, store, outputs=True), store, ran_at=FIXED_RAN_AT) for s in specs]
    (pipeline,) = [p for p in pipelines(store) if any(r.key == stored[0].key for r in p.runs)]
    return store, pipeline, stored


def test_the_pipeline_page_says_the_day_the_fingerprint_changed_and_the_runs_either_side(held, examined):
    from onetrace_console.frame import rendering
    from onetrace_console.pipeline_pages import render_pipeline

    store, pipeline, stored = held
    with rendering(onedoor=False, sign_in=False, public=False):
        page = render_pipeline(pipeline, store, generated_at=GENERATED_AT)
    section = re.search(r'<section data-section="fingerprint-change">.*?</section>', page, re.S).group(0)
    text = _text(section)
    examined(1, "pipeline page")
    (item,) = re.findall(r'<li data-fingerprint-changed="([^"]+)"', section)
    assert item == stored[3].key
    day = str(stored[3].received_at)[:10]
    assert f"This pipeline's model fingerprint changed on {day}" in text
    assert stored[2].run_id in text and stored[3].run_id in text
    assert "provider.fingerprint fp_example_7c1d → fp_example_9e40" in text
    assert "not that the output got worse" in text or "does not say the output got worse" in text


def test_the_drift_page_marks_the_run_where_it_changed(held, examined):
    from onetrace_console.drift import render_drift
    from onetrace_console.frame import rendering

    store, pipeline, stored = held
    with rendering(onedoor=False, sign_in=False, public=False):
        page = render_drift(pipeline, store, generated_at=GENERATED_AT)
    examined(1, "drift page")
    marks = re.findall(r'<tr data-run="(\d+)">(?:(?!</tr>).)*data-fingerprint-mark="([^"]+)"', page, re.S)
    assert marks == [("4", str(stored[3].received_at)[:10])], marks


def test_runs_whose_identity_is_the_same_say_no_change(held, examined):
    from onetrace_console import fingerprint_change

    store, _pipeline, stored = held
    examined(3, "runs")
    found, stated = fingerprint_change.changes(stored[:3], store)
    assert stated and found == []
    page = fingerprint_change.section(stored[:3], store, lambda r: "#")
    assert 'data-fingerprint-change="none"' in page


def test_a_run_with_no_model_call_record_compares_nothing(examined):
    from onetrace_console import fingerprint_change

    examined(1, "pipeline without records")
    assert 'data-fingerprint-change="not-recorded"' in fingerprint_change.section([], None, lambda r: "#")
