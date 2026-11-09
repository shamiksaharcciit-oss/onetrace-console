"""The public demo's bundled app traces: example data, labelled as such, shown on the pages.

1. The build writes an app export for P10's agent runs and P3's triage runs, beside onetrace's own
   export of each, its resource saying it is example data; a sub-agent run, which records no calls,
   gets none, and the onetrace export in each file is as it was.
2. P10's candidate step page shows its spans joined by the recorded trace context, a tool call's two
   retries and its status error, and the first model call checked against its record (they agree)
   and the second against a record that reports no model (nothing to check).
3. P3's retried lookup: the first lookup's HTTP call reads status error, and does whenever the two lookups
   are recorded within one millisecond (a receipt's times are to the millisecond): the demo's invented
   calls keep the chain's order then, not their span ids'.
4. A held comparison of P10's agent runs carries the ranked differences, the retries and the status
   error first; no span view on the public demo links to a tracing tool.
5. A build from that build writes each export once.
"""
from __future__ import annotations

import html
import json
import re

import pytest

from onetrace_console.demo_store import app_traces


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    return folder, store, {r.run_id: r for r in store.runs()}


def _app(doc: dict) -> list[dict]:
    return [rs for rs in doc["resourceSpans"]
            if {"key": "service.name", "value": {"stringValue": app_traces.SERVICE}} in rs["resource"]["attributes"]]


def test_the_build_bundles_labelled_app_traces_for_p10_and_p3(demo, examined):
    folder, _store, runs = demo
    traces = folder / "runs" / "traces"
    docs = {p.stem: json.loads(p.read_bytes()) for p in sorted(traces.glob("*.json"))}
    bundled = sorted(n for n, d in docs.items() if _app(d))
    examined(len(bundled), "bundled app traces")
    assert bundled == sorted(n for n in docs if n.startswith("p3-") or (n.startswith("pz-5") and "subagent" not in n))
    assert any(n.startswith("p3-") for n in bundled) and any(n.startswith("pz-5") for n in bundled)
    for name in bundled:
        (res,) = _app(docs[name])
        assert {"key": "demo.note", "value": {"stringValue": app_traces.NOTE}} in res["resource"]["attributes"]
        #: onetrace's own export of the run, still there beside it.
        assert any(rs not in _app(docs[name]) for rs in docs[name]["resourceSpans"])


def _step_page(folder, run, stage: str, nth: int = 1) -> str:
    pages = sorted((folder / "store" / "pages" / "runs" / run.key).glob("stage-*.html"),
                   key=lambda p: int(re.search(r"\d+", p.name).group(0)))
    found = [p.read_text(encoding="utf-8") for p in pages
             if re.search(rf'<span class="mono">{re.escape(stage)}</span>', p.read_text(encoding="utf-8"))]
    return found[nth - 1]


def test_p10_s_candidate_step_shows_its_spans_and_the_checks(demo, examined):
    from onetrace_console import span_tree
    folder, _store, runs = demo
    page = _step_page(folder, runs["pz-53-agent-amount-changed"], "agent_step")
    examined(1, "step page")
    section = re.search(r'<section data-section="span-tree".*?</section>', page, re.S).group(0)
    assert span_tree.LABELLED.format(note=app_traces.NOTE) in _text(section)
    assert 'data-span-tree="joined"' in section
    tool = re.search(r'<tr data-span="[0-9a-f]{16}" data-depth="1" data-what="tool call"[^>]*>.*?</tr>', section, re.S)
    assert 'data-status="error"' in tool.group(0) and 'data-retries="2"' in tool.group(0)
    checks = re.findall(r'<li data-agree="([a-z]+)">', section)
    assert checks == ["agrees", "nothing", "agrees"], checks
    for line in span_tree.NON_CLAIMS:
        assert line in _text(section)


def test_p3_s_retried_lookup_reads_status_error_on_its_first_call(demo, examined):
    folder, _store, runs = demo
    run = runs["p3-28-t-3-rules1-lookup-retried"]
    first, second = (_step_page(folder, run, "lookup_account", n) for n in (1, 2))
    examined(2, "step pages")
    row = lambda p: re.search(r'<tr data-span="[0-9a-f]{16}" data-depth="1" data-what="HTTP call"[^>]*>', p).group(0)  # noqa: E731
    assert 'data-status="error"' in row(first) and 'data-status="error"' not in row(second)


def _recorded_on_a_clock_that_stands_still(tmp_path, monkeypatch) -> tuple[list[dict], list]:
    """P3's retried run recorded with onetrace's clock frozen: only the pipeline's own wait moves it on
    (`time.sleep`, by what it waits), so every step that does not wait is stamped in one millisecond, as
    on a fast enough machine. The two lookups' receipts, and their step trees from the demo's calls."""
    import datetime
    from onetrace import emit
    from onetrace_console.demo_store import ticket_triage
    from onetrace_console.span_tree import read_export, step_tree
    now = [datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)]
    monkeypatch.setattr(emit, "_now", lambda: now[0].isoformat(timespec="milliseconds"))
    import time
    monkeypatch.setattr(time, "sleep", lambda s: now.__setitem__(0, now[0] + datetime.timedelta(seconds=s)))
    from onetrace_console.demo_store import traceparent_for
    run = tmp_path / "p3-28-t-3-rules1-lookup-retried"
    monkeypatch.setenv("TRACEPARENT", traceparent_for(run.name))  # as the demo records it, inside a span
    ticket_triage.main(run, run.name, "T-3", "1", fault="lookup-once")
    manifest = json.loads((run / "MANIFEST.json").read_text(encoding="utf-8"))
    receipts = [json.loads((run / e["file"]).read_text(encoding="utf-8")) for e in manifest["chain"]]
    lookups = [r for r in receipts if r["stage"]["name"] == "lookup_account"]
    spans = read_export(json.dumps({"resourceSpans": [{"resource": {"attributes": []}, "scopeSpans": [
        {"spans": app_traces.spans_for(run)}]}]}).encode())
    return lookups, [step_tree(spans, r) for r in lookups]


def test_the_retry_is_recorded_after_the_failed_lookup_however_fast_the_machine(tmp_path, monkeypatch, examined):
    """The retry starts in a later recorded millisecond than the failed lookup ended, so each lookup's
    step page holds its own call: the failed one's HTTP call reads status error, the retry's does not."""
    from onetrace_console.span_tree import _ns
    (failed, retry), (first, second) = _recorded_on_a_clock_that_stands_still(tmp_path, monkeypatch)
    examined(2, "lookups recorded on a clock only the pipeline's wait moves")
    assert _ns(retry["time"]["started"]) > _ns(failed["time"]["ended"]), (failed["time"], retry["time"])
    calls = lambda tree: [s.status for s, depth in tree.rows if depth == 1 and s.name == "GET"]  # noqa: E731
    assert calls(first) == ["error"] and calls(second) == ["unset"], (calls(first), calls(second))


def test_a_held_p10_comparison_ranks_the_retries_and_the_status_error_first(demo, examined):
    folder, store, runs = demo
    p10 = {runs[n].key for n in runs if n.startswith("pz-5") and "subagent" not in n}
    found = []
    for p in sorted((folder / "store" / "pages" / "diff").glob("*.html")):
        page = p.read_text(encoding="utf-8")
        section = re.search(r'<section data-section="span-differences".*?</section>', page, re.S)
        if section and any(k in page for k in p10):
            found.append(section.group(0))
    examined(len(found), "P10 comparison pages with span differences")
    assert found
    for section in found:
        first = re.search(r'<li data-rank="([a-z]+)">([^<]*)</li>', section)
        assert first.group(1) == "status"
        assert re.match(r"(candidate|baseline): 2 retries on price_lookup, status error, ", html.unescape(first.group(2)))
        assert "data-trace-link" not in section and "<a " not in section


def test_a_build_from_that_build_writes_each_export_once(demo, tmp_path, examined):
    import shutil
    folder, _store, _runs = demo
    runs = tmp_path / "runs"
    shutil.copytree(folder / "runs", runs)
    names = sorted(p.name for p in runs.iterdir() if p.is_dir())
    app_traces.write(runs, names)
    again = {p.stem: json.loads(p.read_bytes()) for p in (runs / "traces").glob("*.json")}
    built = {p.stem: json.loads(p.read_bytes()) for p in (folder / "runs" / "traces").glob("*.json")}
    examined(len(again), "trace files")
    assert again == built
