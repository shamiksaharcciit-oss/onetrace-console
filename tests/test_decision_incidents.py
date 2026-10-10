"""A deny or a propose raises a derived incident, in the same store and
with the same rules (machinery) as the existing derived incidents.
"""
from __future__ import annotations

import pytest

from onetrace_console.incident_pages import render_incidents, render_rule_list, rule_href
from onetrace_console.incidents import RULES
from onetrace_console.onedoor_ext.decision_incidents import RULE, derive_decision_incidents
from onetrace_console.onedoor_ext.decisions import accept_export
from onetrace_console.onedoor_ext.policy_pages import all_decisions
from tests.test_upload_hardening import _member, _tar


@pytest.fixture
def ingested(onedoor_fixture_dir, store):
    jsonl = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes()
    sidecar = (onedoor_fixture_dir / "onedoor-export.jsonl.sha256").read_bytes()
    archive = _tar(_member("onedoor-export.jsonl", jsonl),
                   _member("onedoor-export.jsonl.sha256", sidecar))
    accept_export(archive, store)
    return store


def test_the_decision_incident_pages_pass_the_prohibitions(ingested, examined):
    """No percentage and no score on the decision pages. Built exactly as
    serve.py builds them when the extension is on: the merged Incidents page and the
    onedoor rule's own list."""
    from onetrace_console.incident_pages import INCIDENTS
    from tests.test_pages import assert_the_prohibitions

    found = derive_decision_incidents(ingested)
    totals = {"decision": len(all_decisions(ingested))}
    pages = {
        INCIDENTS: render_incidents(ingested, generated_at="now", extra_rules=(RULE,),
                                    extra_incidents=found, extra_totals=totals),
        rule_href(RULE.id): render_rule_list(ingested, RULE.id, generated_at="now",
                                             extra_rules=(RULE,), extra_incidents=found,
                                             extra_totals=totals),
    }
    examined(len(found), "onedoor incidents on the pages checked against the prohibitions")
    for name, page in pages.items():
        assert RULE.id in page, f"{name} does not show the onedoor rule"
        assert_the_prohibitions(name, page)


def test_a_deny_and_a_propose_each_raise_one_incident_the_executed_row_does_not(
        ingested, examined):
    incidents = derive_decision_incidents(ingested)
    examined(len(incidents), "incidents derived from the real fixture's 5 decisions")
    assert len(incidents) == 2
    request_ids = {i.subject for i in incidents}
    assert request_ids == {"395fa044-08d1-4b41-a649-619f1e3731a3",   # denied
                          "dd52541b-6972-457f-a26d-ef8b5230ad65"}   # proposed
    #: The permit (2 rows), its resumption (2 rows), and the observe-mode row all
    #: raise nothing -- 5 distinct request_ids, exactly 2 incidents.


def test_every_incident_is_marked_with_its_source(ingested, examined):
    incidents = derive_decision_incidents(ingested)
    examined(len(incidents), "incidents checked for their source marker")
    assert all(i.subject_kind == "onedoor decision" for i in incidents)


def test_the_incidents_carry_no_severity_score_or_rank(ingested, examined):
    """The same five prohibitions the console's own incidents are held to ('the same
    rules as the existing derived incidents'), checked directly on this rule's own output.
    """
    import dataclasses

    incidents = derive_decision_incidents(ingested)
    examined(len(incidents), "incidents checked for forbidden fields")
    field_names = {f.name for f in dataclasses.fields(incidents[0])}
    for forbidden in ("severity", "score", "rank", "priority"):
        assert forbidden not in field_names


def test_the_incidents_page_shows_the_onedoor_rule_when_merged_in(ingested, examined):
    decision_incidents = derive_decision_incidents(ingested)
    totals = {"decision": len(all_decisions(ingested))}
    html = render_incidents(ingested, generated_at="now", extra_rules=(RULE,),
                            extra_incidents=decision_incidents, extra_totals=totals)
    examined(1, "renders of the merged Incidents page")
    assert "I-ONEDOOR-DECISION" in html
    assert "onedoor decision" in html


def test_a_disabled_console_s_incidents_page_is_unaffected(store, examined):
    """No decisions ingested (as if the extension were off): the merged call with no
    extra incidents renders identically in substance to the plain, core-only call.
    """
    plain = render_incidents(store, generated_at="now")
    merged = render_incidents(store, generated_at="now", extra_rules=(), extra_incidents=())
    examined(1, "renders compared with and without the (empty) onedoor hook")
    assert plain == merged


def test_the_rule_list_page_for_the_onedoor_rule_renders(ingested, examined):
    decision_incidents = derive_decision_incidents(ingested)
    totals = {"decision": len(all_decisions(ingested))}
    html = render_rule_list(ingested, RULE.id, generated_at="now", extra_rules=(RULE,),
                            extra_incidents=decision_incidents, extra_totals=totals)
    examined(1, "renders of the onedoor rule's own list page")
    assert "denied" in html or "proposed" in html or RULE.id in html
