"""Step 3: the receipt's anchor row and its
"Anchored" pill are the run page's own "Committed by a known time" rung, read by the viewer from
the console's own check -- never "not available until onetrace 0.2.0" once 0.2.0 checks anchors,
and never a second reading that could disagree with the run page.

The FAIL case is the pinned verifier's own verdict on a placeholder anchor; the PASS and NOT-RUN
cases edit that stored report's one anchor row (the viewer's own tests hold each rule; here it is
the console's wiring that is tested).
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from html import unescape

import pytest

from tests.test_receipt_page import _pills, _receipt, _row
from tests.test_stage_pages import demo  # noqa: F401

FAIL_ROW = re.compile(r"^\[FAIL   \] anchors/1\.json: originality -- .*$", re.M)
SUMMARY = re.compile(r"^(\d+) pass, (\d+) fail, (\d+) not-run  ->  (PASS|FAIL)$", re.M)
BITCOIN = "bitcoin block 840000, attested block time 2024-04-20T00:09:27Z"


@pytest.fixture
def anchored(tmp_path):
    """Day 1 delivered with a placeholder anchor beside its chain, checked by the pinned verifier."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    from tests.test_reference_demo import RUNS, _delivery
    _require_installed()
    store = Store(tmp_path / "store")
    accepted = accept(_delivery(RUNS / "day-1", {"anchors/1.json": b'{"placeholder":"anchor"}'}),
                      store)
    assert getattr(accepted, "run", None) is not None, getattr(accepted, "rows", accepted)
    return run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT), store


@pytest.fixture
def declared(tmp_path, monkeypatch):
    """The demo pipeline recorded by the SDK with a record that declares itself
    anchored (its `anchor` block, state "anchored", in every receipt and the manifest) and no
    `anchors/` file -- a declaration nothing committed, delivered whole and checked."""
    import functools
    import sys
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    from tests.test_reference_demo import DEMO, _delivery
    _require_installed()
    monkeypatch.syspath_prepend(str(DEMO))
    import demo as pipeline
    monkeypatch.setattr(pipeline, "Recorder", functools.partial(pipeline.Recorder, anchor={
        "kind": "demo", "reference": "declared only, never committed", "cadence": "per-run",
        "heads": ["sha256:" + "ab" * 32], "index": 0}))
    out = tmp_path / "declared"
    pipeline.main(str(out), "exec-declared", 1, "2026-09-28T10:00:00.000+00:00")
    sys.modules.pop("demo", None)
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["anchor"]["state"] == "anchored", "the premise: it declares an anchor"
    assert not (out / "anchors").exists(), "the premise: no anchor record beside the chain"
    store = Store(tmp_path / "store")
    accepted = accept(_delivery(out), store)
    assert getattr(accepted, "run", None) is not None, getattr(accepted, "rows", accepted)
    return run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT), store


def _anchor_row_as(run, store, status: str, detail: str):
    """The stored check with its one anchor row given `status` and `detail`, the counts and exit
    moved to match."""
    envelope = json.loads(store.get(run.check_report).decode("utf-8"))
    out = envelope["stdout"]
    assert len(FAIL_ROW.findall(out)) == 1, "the premise: the verifier FAILed the one anchor"
    tag = {"PASS": "PASS   ", "NOT-RUN": "NOT-RUN"}[status]
    out = FAIL_ROW.sub(f"[{tag}] anchors/1.json: originality -- {detail}", out)
    p, f, n, _ = SUMMARY.search(out).groups()
    p, f, n = int(p) + (status == "PASS"), int(f) - 1, int(n) + (status == "NOT-RUN")
    summary = f"{p} pass, {f} fail, {n} not-run  ->  {'FAIL' if f else 'PASS'}"
    if status == "NOT-RUN":
        #: The verifier counts a record beside the chain not run, before the caveat.
        from onetrace_console.viewer.report import BESIDE_NOT_RUN_NOTE
        summary += f"\nrecords beside the chain: 1 not run -- {BESIDE_NOT_RUN_NOTE}"
    out = SUMMARY.sub(summary, out)
    envelope["stdout"], envelope["exit_status"] = out, "1" if f else "0"
    #: The same row and counts in its --json run, which the viewer holds the text to.
    rows = envelope["rows_json"]
    doc = json.loads(rows["stdout"])
    (row,) = [r for r in doc["rows"] if r["name"] == "anchors/1.json: originality"]
    row["result"], row["detail"] = status, detail
    doc["summary"].update({"pass": p, "fail": f, "not_run": n, "exit": 1 if f else 0,
                           "result": "FAIL" if f else "PASS"})
    rows["stdout"] = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    rows["exit_status"] = envelope["exit_status"]
    _read_by_the_viewer(envelope)
    return replace(run, check_report=store.put(json.dumps(envelope).encode("utf-8")))


def _read_by_the_viewer(envelope: dict) -> None:
    """The premise: the viewer reads this report row by row, so the rung is the verifier's, not
    what the record declares (which is all an unreadable report leaves)."""
    from onetrace_console.viewer.report import parse
    assert parse(envelope).rows_readable


def _case_rung(run, store) -> str:
    from onetrace_console.pages import CASE, render_execution
    from tests.test_stage_pages import GENERATED_AT
    case = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
    found = re.search(r'<tr data-rung="anchored"[^>]*><td>.*?</td><td>(.*?)</td></tr>', case, re.S)
    assert found, "no anchored rung on the case page"
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", found.group(1)))).strip()


def _says(run, store) -> tuple[str, str, str]:
    """(the receipt's anchor row, its "Anchored" pill, the case page's rung)."""
    row = _row(_receipt(run, store), "anchor")
    pill = re.search(r"Anchored: (.*)$", _pills(run, store)).group(1)
    return row, pill, _case_rung(run, store)


def test_a_run_with_no_anchor_reads_not_anchored_as_its_run_page_does(demo):  # noqa: F811
    run, store = demo
    _read_by_the_viewer(json.loads(store.get(run.check_report).decode("utf-8")))
    row, pill, rung = _says(run, store)
    assert row == "Anchor Not anchored · no anchor beside the chain" and pill == "Not anchored", (row, pill)
    assert row == f"Anchor {rung}"


def test_a_record_declaring_an_anchor_it_does_not_have_reads_not_anchored(declared):
    """What the record declares is not read; the verifier found no anchor row."""
    run, store = declared
    _read_by_the_viewer(json.loads(store.get(run.check_report).decode("utf-8")))
    row, pill, rung = _says(run, store)
    assert row == "Anchor Not anchored · no anchor beside the chain" and pill == "Not anchored", (row, pill)
    assert row == f"Anchor {rung}"


def test_an_anchor_the_verifier_fails_reads_no_with_its_words(anchored):
    run, store = anchored
    _read_by_the_viewer(json.loads(store.get(run.check_report).decode("utf-8")))
    row, pill, rung = _says(run, store)
    assert row.startswith("Anchor No · the check says: malformed anchor record"), row
    assert pill == "No" and row == f"Anchor {rung}"


def test_an_anchor_that_passes_reads_yes_existed_by_its_attested_time(anchored):
    run, store = anchored
    run = _anchor_row_as(run, store, "PASS", BITCOIN)
    row, pill, rung = _says(run, store)
    assert row == "Anchor Yes · existed by 2024-04-20T00:09:27Z · bitcoin block 840000", row
    assert pill == "Yes" and row == f"Anchor {rung}"


def test_an_anchor_not_run_reads_couldnt_check_with_the_verifiers_reason(anchored):
    run, store = anchored
    run = _anchor_row_as(run, store, "NOT-RUN", "needs block headers")
    row, pill, rung = _says(run, store)
    assert row == "Anchor Couldn't check · the check says: needs block headers", row
    assert pill == "Couldn't check" and row == f"Anchor {rung}"


def test_the_signature_row_and_pill_are_the_run_pages_signing_rung(anchored):
    """Since the Signed half: this run carries a placeholder anchor and no
    signature, so it reads Unsigned (tests/test_signed_surfaces.py holds each state)."""
    run, store = anchored
    assert _row(_receipt(run, store), "signature") == (
        "Signature Unsigned · no signature beside the chain")
    assert "Signed: Unsigned" in _pills(run, store)
