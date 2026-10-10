"""The "Decisions cited" panel, tested on the
synthetic receipts in tests/fixtures/synthetic_receipts/ (the SDK does not emit
decision_refs yet). One test per state, plus the join-trusts-the-receipt sabotage.
"""
from __future__ import annotations

import json

import pytest

from onetrace_console.onedoor_ext.decision_refs import (STATE_MATCH, STATE_MISMATCH,
                                                         STATE_MISSING, STATE_NONE,
                                                         STATE_UNKNOWN, citation_incidents,
                                                         join_run, join_stage, render_panel)
from onetrace_console.onedoor_ext.decisions import (DecisionRow, StoredDecisionExport,
                                                    accept_export)
from tests.test_upload_hardening import _member, _tar


@pytest.fixture
def ingested(onedoor_fixture_dir, store):
    jsonl = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes()
    sidecar = (onedoor_fixture_dir / "onedoor-export.jsonl.sha256").read_bytes()
    archive = _tar(_member("onedoor-export.jsonl", jsonl),
                   _member("onedoor-export.jsonl.sha256", sidecar))
    accept_export(archive, store)
    return store


@pytest.fixture
def five_states(synthetic_receipts_dir):
    return json.loads((synthetic_receipts_dir / "five_states.json").read_text(encoding="utf-8"))


def _by_stage(citations, stage):
    return next(c for c in citations if c.stage == stage)


def test_state_1_a_matching_citation(ingested, five_states, examined):
    citations = join_run(five_states["stages"], ingested)
    examined(1, "stages whose citation matches the export")
    c = _by_stage(citations, "notify_ops")
    assert c.state == STATE_MATCH
    assert c.request_id == "e5504d65-cfd0-494e-b98e-9a49f77207b3"
    assert c.verdict == "executed"          # onedoor's own row word, not a translation


def test_state_2_a_mismatched_citation(ingested, five_states, examined):
    citations = join_run(five_states["stages"], ingested)
    examined(1, "stages whose citation's digest disagrees with the export")
    c = _by_stage(citations, "apply_patch")
    assert c.state == STATE_MISMATCH


def test_state_3_a_citation_naming_no_ingested_decision(ingested, five_states, examined):
    citations = join_run(five_states["stages"], ingested)
    examined(1, "stages citing a request_id no export carries")
    c = _by_stage(citations, "rollback")
    assert c.state == STATE_UNKNOWN


def test_state_4_a_gated_stage_with_no_citation(ingested, five_states, examined):
    citations = join_run(five_states["stages"], ingested)
    examined(1, "gated stages with no decision_ref")
    c = _by_stage(citations, "escalate")
    assert c.state == STATE_MISSING


def test_state_5_neither_cited_nor_gated_shows_nothing(ingested, five_states, examined):
    citations = join_run(five_states["stages"], ingested)
    examined(1, "stages neither cited nor gated")
    c = _by_stage(citations, "log_only")
    assert c.state == STATE_NONE
    panel = render_panel(citations)
    assert "log_only" not in panel


def test_the_panel_shows_all_five_states_and_the_limit_sentence(ingested, five_states, examined):
    citations = join_run(five_states["stages"], ingested)
    panel = render_panel(citations)
    examined(5, "stages rendered onto the panel")
    assert "Decisions cited" in panel
    assert "matches export" in panel
    assert "does not match the export" in panel
    assert "not in any ingested export" in panel
    assert "no decision cited" in panel
    assert "does not show that every action was gated" in panel


def test_the_words_allowed_and_authorised_appear_nowhere(ingested, five_states, examined):
    citations = join_run(five_states["stages"], ingested)
    panel = render_panel(citations).lower()
    examined(1, "renders of the panel")
    assert "allowed" not in panel
    assert "authorised" not in panel
    assert "authorized" not in panel


def test_states_2_and_4_raise_incidents_and_no_other_state_does(ingested, five_states, examined):
    citations = join_run(five_states["stages"], ingested)
    incidents = citation_incidents("run-key", citations)
    examined(len(incidents), "incidents raised from the five-state fixture")
    rules = {i.rule for i in incidents}
    assert rules == {"I-ONEDOOR-CITATION-MISMATCH", "I-ONEDOOR-CITATION-MISSING"}
    assert len(incidents) == 2


# ------------------------------------------------------- a request_id naming
# more than one row

def _store_with_two_rows_one_request_id(store):
    """The exact adversarial shape onedoor's own `tests/test_decision_ref_checker.py`
    uses (`ROW_PROPOSE`/`ROW_RESUME`, both `request_id="req-c"`): two rows, one
    `request_id`, different content and therefore different digests. Built by
    hand because the real fixture's own propose and resumption do NOT share a
    request_id (onedoor mints a fresh one per `docs/decision-ref.md`) -- this
    case is rare-to-adversarial in practice and still has to join correctly.
    """
    propose_line = ('{"decision":"proposed","id":3,"kind":"decision",'
                    '"request_id":"req-c"}')
    resume_line = ('{"decision":"executed","id":4,"kind":"exec_intent",'
                   '"request_id":"req-c"}')
    propose = DecisionRow(raw_line=propose_line)
    resume = DecisionRow(raw_line=resume_line)
    assert propose.decision_digest != resume.decision_digest, \
        "the two hand-built rows must actually differ"
    #: A real delivery holding exactly these two lines: rows are shown only after their
    #: stored copy is checked against the delivery, so an export whose
    #: delivery was never stored could not be joined at all.
    delivery = store.put((propose_line + "\n" + resume_line + "\n").encode("utf-8"))
    #: Filed under its delivery's own key, as ingest files every export: a record is
    #: checked against the delivery its filename names.
    export = StoredDecisionExport(
        key=delivery, export_object=delivery, received_at="now",
        rows=(propose, resume))
    store.put_decision_export(export)
    return propose, resume


def test_a_request_id_naming_two_rows_resolves_each_reference_to_its_own_row(
        store, examined):
    propose, resume = _store_with_two_rows_one_request_id(store)

    ref_for_propose = {"request_id": "req-c", "decision_digest": propose.decision_digest}
    ref_for_resume = {"request_id": "req-c", "decision_digest": resume.decision_digest}
    examined(2, "references to two different rows sharing one request_id")

    c_propose = join_stage("s1", ref_for_propose, True, store)
    c_resume = join_stage("s2", ref_for_resume, True, store)

    assert c_propose.state == STATE_MATCH and c_propose.verdict == "proposed"
    assert c_resume.state == STATE_MATCH and c_resume.verdict == "executed"

    #: A digest that names neither row must never match either one.
    neither = {"request_id": "req-c", "decision_digest": "sha256:" + "f" * 64}
    c_neither = join_stage("s3", neither, True, store)
    assert c_neither.state == STATE_MISMATCH


def test_sabotage_picking_the_first_row_found_breaks_the_resumptions_own_citation(
        store, examined):
    """The sabotage for a request_id naming more than one row: pick `rows[0]`
    regardless of digest. A reference correctly naming the SECOND row (the
    resumption) must then be misread as matching the FIRST (the propose) -- a
    false match with the wrong verdict, not merely a wrong state.
    """
    propose, resume = _store_with_two_rows_one_request_id(store)
    ref_for_resume = {"request_id": "req-c", "decision_digest": resume.decision_digest}
    examined(1, "a reference to the second of two same-request_id rows")

    sabotaged = join_stage("s2", ref_for_resume, True, store, _pick_first_row=True)
    assert sabotaged.state == STATE_MATCH
    assert sabotaged.verdict == "proposed", \
        "the sabotage should have returned the FIRST row's (propose) verdict, " \
        "wrongly, for a reference that actually names the resumption"


# --------------------------------------------------------------------- sabotage

def test_sabotage_trusting_the_receipts_own_verdict_breaks_states_2_and_3(
        ingested, five_states, examined):
    """The specified sabotage: make the join accept `ref["verdict"]` on its own
    word, without checking the export. States 2 (mismatch) and 3 (unknown) must
    become unreachable -- both stages report MATCH instead, which is exactly the
    false "everything cited is fine" reading the real join exists to prevent.
    """
    sabotaged = join_run(five_states["stages"], ingested, _trust_receipt_verdict=True)
    examined(2, "stages whose real state the sabotaged join gets wrong")
    assert _by_stage(sabotaged, "apply_patch").state == STATE_MATCH   # really MISMATCH
    assert _by_stage(sabotaged, "rollback").state == STATE_MATCH      # really UNKNOWN
