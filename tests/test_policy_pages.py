"""The Policy page, over the real fixture export."""
from __future__ import annotations

import pytest

from onetrace_console.onedoor_ext.decisions import accept_export
from onetrace_console.onedoor_ext.policy_pages import (all_decisions, render_decision_detail,
                                                       render_policy, render_policy_pages)
from tests.test_upload_hardening import _member, _tar


@pytest.fixture
def ingested(onedoor_fixture_dir, store):
    jsonl = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes()
    sidecar = (onedoor_fixture_dir / "onedoor-export.jsonl.sha256").read_bytes()
    archive = _tar(_member("onedoor-export.jsonl", jsonl),
                   _member("onedoor-export.jsonl.sha256", sidecar))
    accept_export(archive, store)
    return store


def test_the_policy_page_shows_one_row_per_request_id_not_per_audit_row(ingested, examined):
    decisions = all_decisions(ingested)
    examined(len(decisions), "distinct request_ids grouped for the Policy page")
    #: 7 audit rows, 5 distinct request_ids -- the permit and its resumption each
    #: contribute an exec_intent/exec_result pair sharing one request_id (the
    #: finding in tests/fixtures/onedoor/PROVENANCE.md), now checked at the
    #: page-grouping layer.
    assert len(decisions) == 5
    html = render_policy(ingested, generated_at="now")
    assert html.count("<tr data-request-id=") == 5


def test_two_row_decisions_show_the_exec_result_as_their_representative(
        ingested, examined):
    """The permit and its resumption are each a two-row decision (exec_intent then
    exec_result); both must pick exec_result as their representative row.
    """
    decisions = all_decisions(ingested)
    two_row = [d for d in decisions if len(d.rows) == 2]
    examined(len(two_row), "two-row decisions (the permit and its resumption)")
    assert len(two_row) == 2
    for d in two_row:
        assert d.representative.kind == "exec_result"
        assert d.verdict == "executed"


def test_verdicts_are_onedoor_s_own_words_never_allowed_or_authorised(ingested, examined):
    html = render_policy(ingested, generated_at="now")
    examined(1, "renders of the Policy list page")
    assert "allowed" not in html.lower()
    assert "authorised" not in html.lower()
    assert "authorized" not in html.lower()
    for word in ("executed", "denied", "proposed"):
        assert word in html


def test_the_detail_page_shows_a_decision_digest_per_row(ingested, examined):
    d = next(dd for dd in all_decisions(ingested) if len(dd.rows) == 1 and dd.verdict == "denied")
    html = render_decision_detail(d, ingested, generated_at="now")
    examined(1, "detail pages checked for their decision_digest")
    assert "decision_digest: " in html
    assert "sha256:" in html


def test_a_tampered_stored_row_is_reported_as_not_matching_not_shown_altered(
        ingested, examined):
    """Sabotage: flip one byte of the STORED record (not the content-addressed
    object) and confirm the detail page refuses to show the row's fields or verdict.
    """
    import dataclasses

    from onetrace_console.onedoor_ext.decisions import DecisionRow, StoredDecisionExport

    export = ingested.decision_exports()[0]
    tampered_row = dataclasses.replace(
        export.rows[0],
        raw_line=export.rows[0].raw_line.replace('"decision":"', '"decision":"TAMPERED_'))
    tampered = StoredDecisionExport(
        key=export.key, export_object=export.export_object,
        received_at=export.received_at,
        rows=(tampered_row,) + export.rows[1:])
    ingested.put_decision_export(tampered)

    d = next(dd for dd in all_decisions(ingested) if dd.request_id == export.rows[0].request_id)
    examined(1, "decisions whose stored record was tampered after ingest")
    html = render_decision_detail(d, ingested, generated_at="now")
    import html as _html
    assert "couldn't check: stored record changed since delivery" in _html.unescape(html)
    assert "TAMPERED" not in html


#: The fixture's single-row deny, and an executed request to forge towards.
DENIED = "395fa044-08d1-4b41-a649-619f1e3731a3"
OTHER = "b8274738-c0dd-4040-b704-1b6ddfafdcad"


def _stored_record(store):
    import json

    export = store.decision_exports()[0]
    path = store.root / "decision_exports" / f"{export.key}.json"
    return export, path, json.loads(path.read_text(encoding="utf-8"))


def _write_record(path, record) -> None:
    import json

    path.write_text(json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


@pytest.mark.parametrize("column,forged", [("decision", "executed"), ("request_id", OTHER)])
def test_a_fields_only_tamper_never_reaches_a_page_or_the_join(ingested, examined,
                                                              column, forged):
    """`fields` must equal `json.loads(raw_line)` on every path
    that displays or joins on them. The existing tamper test changes `raw_line` only; this
    one changes only the stored `fields` of the deny, leaving its `raw_line` intact."""
    import json
    import re

    from onetrace_console.onedoor_ext.decision_incidents import derive_decision_incidents
    from onetrace_console.onedoor_ext.decision_refs import STATE_MATCH, join_stage

    export, path, record = _stored_record(ingested)
    i = next(n for n, r in enumerate(record["rows"])
             if json.loads(r["raw_line"])["request_id"] == DENIED)
    raw_before = record["rows"][i]["raw_line"]
    forged_fields = json.loads(raw_before)
    forged_fields[column] = forged
    record["rows"][i]["fields"] = forged_fields
    _write_record(path, record)
    assert json.loads(path.read_text(encoding="utf-8"))["rows"][i]["raw_line"] == raw_before

    pages = render_policy_pages(ingested, generated_at="now")
    examined(6, "paths that display or join on a row, after a fields-only tamper")
    assert len(all_decisions(ingested)) == 5
    #: Bounded to the deny's own row: an unbounded `.*?` could pass on a later row's cell.
    assert re.search(rf'<tr data-request-id="{DENIED}">(?:(?!</tr>).)*?'
                     rf'<td data-verdict="denied">', pages["policy.html"], re.S)
    assert DENIED in pages.get("policy-verdict-denied.html", "")
    assert DENIED not in pages.get("policy-verdict-executed.html", "")
    detail = pages[f"policy/{DENIED}.html"]
    assert 'data-verdict="denied"' in detail and "executed" not in detail
    assert DENIED in {x.subject for x in derive_decision_incidents(ingested)}
    digest = next(r for r in export.rows if r.request_id == DENIED).decision_digest
    assert join_stage("s", {"request_id": DENIED, "decision_digest": digest}, True,
                      ingested).verdict == "denied"
    assert join_stage("s", {"request_id": OTHER, "decision_digest": digest}, True,
                      ingested).state != STATE_MATCH


def test_a_stored_row_that_no_longer_parses_is_counted_not_dropped(ingested, examined):
    """Deriving `fields` from `raw_line` means a stored `raw_line` that no longer parses
    has no fields at all. The pages must still render, and the row must be counted as
    unreadable with its denominator, never silently left off."""
    export, path, record = _stored_record(ingested)
    total = len(record["rows"])
    record["rows"][2]["raw_line"] = "{not json"
    _write_record(path, record)

    pages = render_policy_pages(ingested, generated_at="now")
    examined(total, "stored rows, one of them unreadable")
    assert f"1 of {total} stored rows couldn't be checked" in pages["policy.html"]
    assert f"{export.key[:12]}" in pages["policy.html"]


#: The fixture's first request: an exec_intent (line 1) and its exec_result (line 2).
SPLIT = "e5504d65-cfd0-494e-b98e-9a49f77207b3"


def _delivery(name: str, data: bytes) -> bytes:
    import hashlib

    sidecar = f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode("utf-8")
    return _tar(_member(name, data), _member(f"{name}.sha256", sidecar))


def _fixture_lines(onedoor_fixture_dir) -> list[str]:
    return (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes().decode("utf-8") \
        .split("\n")[:-1]


def _ingest_lines(store, name: str, lines: list[str], received_at: str) -> None:
    accept_export(_delivery(name, ("\n".join(lines) + "\n").encode("utf-8")), store,
                  received_at=received_at)


@pytest.fixture
def split(onedoor_fixture_dir, store):
    """One request_id split across two exports: export 1 holds only its exec_intent."""
    import json

    lines = _fixture_lines(onedoor_fixture_dir)
    first = json.loads(lines[0])
    assert (first["request_id"], first["kind"]) == (SPLIT, "exec_intent")
    _ingest_lines(store, "onedoor-export-1.jsonl", lines[:1], "2026-09-28T00:00:01+00:00")
    _ingest_lines(store, "onedoor-export-2.jsonl", lines[1:], "2026-09-28T00:00:02+00:00")
    return store


def test_a_request_id_split_across_two_exports_renders_every_row(split, examined):
    """#23: a row the first export does not hold made the detail page raise ValueError."""
    exports = split.decision_exports()
    holding = [e for e in exports if any(r.request_id == SPLIT for r in e.rows)]
    assert len(holding) == 2, "the fixture is not actually split"
    d = next(x for x in all_decisions(split) if x.request_id == SPLIT)
    examined(len(d.rows), "rows of one request_id held by two different exports")

    html = render_decision_detail(d, split, generated_at="now")
    assert html.count("<section data-kind=") == 2 and "couldnt-check" not in html
    for e in holding:
        for r in e.rows:
            if r.request_id == SPLIT:
                assert r.decision_digest in html
    assert f"policy/{SPLIT}.html" in render_policy_pages(split, generated_at="now")


def test_overlapping_exports_show_each_distinct_row_once(onedoor_fixture_dir, store, examined):
    """The same rows delivered twice (a full export, then a subset of it) are one row
    each on the detail page, not one per delivery."""
    lines = _fixture_lines(onedoor_fixture_dir)
    _ingest_lines(store, "full.jsonl", lines, "2026-09-28T00:00:01+00:00")
    _ingest_lines(store, "subset.jsonl", lines[:3], "2026-09-28T00:00:02+00:00")
    by_id = {d.request_id: d for d in all_decisions(store)}
    examined(len(by_id), "request_ids across two overlapping exports")
    assert len(by_id) == 5
    assert render_decision_detail(by_id[SPLIT], store, generated_at="now") \
        .count("<section data-kind=") == 2
    assert render_decision_detail(by_id[DENIED], store, generated_at="now") \
        .count("<section data-kind=") == 1


def test_a_tampered_copy_held_by_a_second_export_is_checked_against_that_export(
        onedoor_fixture_dir, store, examined):
    """Each copy is verified against the export that holds it, not the first one found."""
    import json

    lines = _fixture_lines(onedoor_fixture_dir)
    _ingest_lines(store, "full.jsonl", lines, "2026-09-28T00:00:01+00:00")
    _ingest_lines(store, "subset.jsonl", lines[:3], "2026-09-28T00:00:02+00:00")
    subset = next(e for e in store.decision_exports() if len(e.rows) == 3)
    path = store.root / "decision_exports" / f"{subset.key}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    i = next(n for n, r in enumerate(record["rows"])
             if json.loads(r["raw_line"])["request_id"] == DENIED)
    record["rows"][i]["raw_line"] = record["rows"][i]["raw_line"].replace(
        '"decision":"denied"', '"decision":"executed"')
    assert '"decision":"executed"' in record["rows"][i]["raw_line"]
    _write_record(path, record)

    d = next(x for x in all_decisions(store) if x.request_id == DENIED)
    examined(len(d.rows), "distinct rows of the deny, one stored copy of it tampered")
    html = render_decision_detail(d, store, generated_at="now")
    import html as _html
    text = _html.unescape(html)
    #: The tampered copy is found by checking it against the export that holds it (the
    #: subset), and is named by that export. By the literal rule the row is then
    #: withheld altogether, although the full export's copy is intact.
    assert f"couldn't check: stored record changed since delivery (export {subset.key[:12]}" \
        in text
    good = next(r for r in next(e for e in store.decision_exports() if len(e.rows) == 7).rows
                if r.request_id == DENIED)
    assert good.decision_digest not in html and "<tbody>" not in html


def test_every_policy_page_passes_the_prohibitions(ingested, examined):
    """No percentage and no score on the policy and decision pages. Counted
    by kind, so a kind that stops rendering fails here instead of passing on the rest."""
    from onetrace_console.onedoor_ext.policy_pages import POLICY
    from tests.test_pages import assert_the_prohibitions

    pages = render_policy_pages(ingested, generated_at="now")
    listing = [p for p in pages if p == POLICY]
    filtered = [p for p in pages if p.startswith(("policy-verdict-", "policy-issuer-"))]
    detail = [p for p in pages if p.startswith("policy/")]
    examined(len(detail), "decision detail pages checked against the prohibitions")
    assert sorted(listing + filtered + detail) == sorted(pages), "a page of an unknown kind"
    assert (len(listing), len(filtered), len(detail)) == (1, 4, 5)
    for name, page in pages.items():
        assert_the_prohibitions(name, page)


def test_the_policy_page_with_an_unreadable_row_passes_the_prohibitions(ingested, examined):
    """The Policy page's own "K of T" sentence, which only renders when a stored row no
    longer parses, is held to the same prohibitions."""
    from tests.test_pages import assert_the_prohibitions

    _, path, record = _stored_record(ingested)
    record["rows"][2]["raw_line"] = "{not json"
    _write_record(path, record)
    page = render_policy_pages(ingested, generated_at="now")["policy.html"]
    examined(1, "Policy list pages carrying the unreadable-rows sentence")
    assert 'data-section="couldnt-check"' in page
    assert_the_prohibitions("policy.html", page)


def test_render_policy_pages_covers_every_decision_and_every_verdict(ingested, examined):
    pages = render_policy_pages(ingested, generated_at="now")
    decisions = all_decisions(ingested)
    examined(len(pages), "pages rendered for the Policy feature")
    assert "policy.html" in pages
    for d in decisions:
        assert any(p.startswith("policy/") for p in pages if d.request_id and d.request_id in p)
    for v in {d.verdict for d in decisions if d.verdict}:
        assert any(p.startswith("policy-verdict-") for p in pages)
