"""A value edited after delivery is never shown as fact.

Every display path and the join read from the original delivery (the content-addressed
bytes `Store.get` digest-checks), after checking the stored line against it. A row whose
stored line differs is not shown: every page that would show it, and the join, read
"couldn't check: stored record changed since delivery" and name the row.
"""
from __future__ import annotations

import json

import pytest

from onetrace_console.onedoor_ext.decisions import (CHANGED, DELIVERY_MISSING, accept_export,
                                                    check_export)
from tests.test_upload_hardening import _member, _tar

#: The fixture's single-row deny, and an executed request an edit can move it towards.
DENIED = "395fa044-08d1-4b41-a649-619f1e3731a3"
OTHER = "b8274738-c0dd-4040-b704-1b6ddfafdcad"

#: Three ways to edit one stored line after delivery: the verdict, the request it belongs
#: to, and the line itself.
EDITS = {
    "decision changed": lambda line: line.replace('"decision":"denied"', '"decision":"executed"'),
    "request_id changed": lambda line: line.replace(DENIED, OTHER),
    "no longer parses": lambda line: "{not json",
}


@pytest.fixture
def ingested(onedoor_fixture_dir, store):
    jsonl = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes()
    sidecar = (onedoor_fixture_dir / "onedoor-export.jsonl.sha256").read_bytes()
    accept_export(_tar(_member("onedoor-export.jsonl", jsonl),
                       _member("onedoor-export.jsonl.sha256", sidecar)), store)
    return store


def _record(store):
    export = store.decision_exports()[0]
    path = store.root / "decision_exports" / f"{export.key}.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _save(path, record) -> None:
    path.write_text(json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def edit_stored_line(store, request_id: str, change) -> int:
    """Edit the stored copy of `request_id`'s line and return its index. The delivery (the
    content-addressed object) is untouched, which is exactly the case §2 is about."""
    path, record = _record(store)
    i = next(n for n, r in enumerate(record["rows"]) if request_id in r["raw_line"])
    before = record["rows"][i]["raw_line"]
    record["rows"][i]["raw_line"] = change(before)
    assert record["rows"][i]["raw_line"] != before, "the edit changed nothing"
    _save(path, record)
    return i


# ------------------------------------------------------------------- the read layer

def test_an_untouched_export_checks_clean_row_by_row(ingested, examined):
    export = ingested.decision_exports()[0]
    checked = check_export(export, ingested)
    examined(len(checked), "stored rows checked against their delivery")
    assert len(checked) == 7
    assert all(c.problem is None for c in checked)
    assert [c.delivered.raw_line for c in checked] == [r.raw_line for r in export.rows]


@pytest.mark.parametrize("edit", sorted(EDITS))
def test_an_edited_stored_line_is_the_only_row_that_cannot_be_checked(ingested, examined, edit):
    i = edit_stored_line(ingested, DENIED, EDITS[edit])
    export = ingested.decision_exports()[0]
    checked = check_export(export, ingested)
    examined(len(checked), "stored rows checked after one was edited")
    assert [c.index for c in checked if c.problem] == [i]
    assert checked[i].problem == CHANGED
    #: The row is named from the delivery, never from the edited copy.
    assert checked[i].delivered.request_id == DENIED
    assert DENIED in checked[i].name and export.key[:12] in checked[i].name
    assert checked[i].couldnt_check == f"couldn't check: {CHANGED} ({checked[i].name})"


def test_a_row_added_to_the_stored_record_taints_every_row(ingested, examined):
    path, record = _record(ingested)
    record["rows"].append({"raw_line": record["rows"][0]["raw_line"]})
    _save(path, record)
    checked = check_export(ingested.decision_exports()[0], ingested)
    examined(len(checked), "stored rows checked when the record holds one more than its delivery")
    assert len(checked) == 8
    assert all(c.problem == CHANGED for c in checked)


COULDNT = f"couldn't check: {CHANGED}"


def _list_rows(page: str) -> dict[str, str]:
    """Each list row's HTML by request id, entities decoded ("couldn't" is escaped)."""
    import html
    import re
    return {rid: html.unescape(body) for rid, body in
            re.findall(r'<tr data-request-id="([^"]+)">(.*?)</tr>', page, re.S)}


# -------------------------------------------------------------------- the list page

@pytest.mark.parametrize("edit", sorted(EDITS))
def test_the_list_reads_couldnt_check_for_the_edited_row_and_nothing_else_changes(
        ingested, examined, edit):
    from onetrace_console.onedoor_ext.policy_pages import render_policy

    before = _list_rows(render_policy(ingested, generated_at="now"))
    edit_stored_line(ingested, DENIED, EDITS[edit])
    page = render_policy(ingested, generated_at="now")
    after = _list_rows(page)
    examined(len(after), "list rows after one stored line was edited")
    assert set(after) == set(before), "a row vanished or appeared"
    assert COULDNT in after[DENIED] and "row 2" in after[DENIED]
    for word in ("denied", "executed"):
        assert word not in after[DENIED], f"a verdict is shown for the edited row: {word}"
    assert all(after[rid] == before[rid] for rid in before if rid != DENIED)
    assert "1 of 7 stored rows couldn't be checked" in page


# ------------------------------------------------------------------ the filter pages

def _filters(pages: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in pages.items() if k.startswith("policy-")}


@pytest.mark.parametrize("edit", sorted(EDITS))
def test_the_filters_read_couldnt_check_for_the_edited_row_and_nothing_else_changes(
        ingested, examined, edit):
    """A verdict or issuer filter would reveal the row's value, so an edited row is on
    none of them. It is on a "couldn't check" filter of its own, and every filter page
    names it. The one page that disappears is the one whose only member was that row:
    keeping it would place the row by the verdict §2 says not to show."""
    import html

    from onetrace_console.onedoor_ext.policy_pages import render_policy_pages

    before = _filters(render_policy_pages(ingested, generated_at="now"))
    edit_stored_line(ingested, DENIED, EDITS[edit])
    after = _filters(render_policy_pages(ingested, generated_at="now"))
    examined(len(after), "filter pages after one stored line was edited")

    held_only_the_deny = {k for k, v in before.items()
                          if set(_list_rows(v)) == {DENIED}}
    assert held_only_the_deny == {"policy-verdict-denied.html"}
    assert set(after) == (set(before) - held_only_the_deny) | {"policy-couldnt-check.html"}

    blocked = _list_rows(after["policy-couldnt-check.html"])
    assert set(blocked) == {DENIED} and COULDNT in blocked[DENIED]
    for name, page in after.items():
        assert "1 of 7 stored rows couldn't be checked" in html.unescape(page), name
        if name == "policy-couldnt-check.html":
            continue
        rows = _list_rows(page)
        assert DENIED not in rows, f"{name} places the edited row by a value"
        assert rows == {rid: body for rid, body in _list_rows(before[name]).items()
                        if rid != DENIED}, f"{name} changed beyond the edited row"


# ------------------------------------------------------------------ the detail pages

@pytest.mark.parametrize("edit", sorted(EDITS))
def test_the_detail_page_reads_couldnt_check_for_the_edited_row_and_nothing_else_changes(
        ingested, examined, edit):
    import html

    from onetrace_console.onedoor_ext.policy_pages import render_policy_pages

    def details(pages):
        return {k: v for k, v in pages.items() if k.startswith("policy/")}

    before = details(render_policy_pages(ingested, generated_at="now"))
    edit_stored_line(ingested, DENIED, EDITS[edit])
    after = details(render_policy_pages(ingested, generated_at="now"))
    examined(len(after), "detail pages after one stored line was edited")
    assert set(after) == set(before)
    page = html.unescape(after[f"policy/{DENIED}.html"])
    assert COULDNT in page and "row 2" in page
    for shown in ("denied", "executed", "decision_digest", "<tbody>"):
        assert shown not in page, f"the edited row's detail page shows {shown!r}"
    assert all(after[k] == before[k] for k in before if k != f"policy/{DENIED}.html")


# --------------------------------------------------------------- the incidents pages

def _incident_pages(store) -> dict[str, str]:
    """Both incident pages exactly as serve.py builds them when the extension is on."""
    from onetrace_console.incident_pages import INCIDENTS, render_incidents, render_rule_list, \
        rule_href
    from onetrace_console.onedoor_ext.decision_incidents import RULE, incident_page_args

    args = incident_page_args(store)
    return {INCIDENTS: render_incidents(store, generated_at="now", **args),
            rule_href(RULE.id): render_rule_list(store, RULE.id, generated_at="now", **args)}


def _incident_items(page: str) -> dict[str, str]:
    import re
    return dict(re.findall(r'<li data-incident="([^"]+)">(.*?)</li>', page, re.S))


@pytest.mark.parametrize("edit", sorted(EDITS))
def test_the_incidents_read_couldnt_check_for_the_edited_row_and_nothing_else_changes(
        ingested, examined, edit):
    import html

    from onetrace_console.onedoor_ext.decision_incidents import derive_decision_incidents

    before = _incident_pages(ingested)
    before_subjects = {i.subject for i in derive_decision_incidents(ingested)}
    assert DENIED in before_subjects, "the deny raised no incident, so this proves nothing"
    edit_stored_line(ingested, DENIED, EDITS[edit])
    after = _incident_pages(ingested)
    raised = derive_decision_incidents(ingested)
    examined(len(after), "incident pages after one stored line was edited")
    #: No incident is raised from a value that cannot be shown; the others are untouched.
    assert {i.subject for i in raised} == before_subjects - {DENIED}
    for name, page in after.items():
        assert COULDNT in html.unescape(page) and "row 2" in html.unescape(page), name
        #: The page keys an incident by the first 12 characters of its id, and shows the
        #: first 12 of its subject.
        kept = _incident_items(page)
        assert kept == {k: v for k, v in _incident_items(before[name]).items()
                        if k in {i.id[:12] for i in raised}}, f"{name} changed beyond the row"
        assert not any(DENIED[:12] in v for v in kept.values()), f"{name} quotes the edited row"


# ------------------------------------------------------------------------- the join

def _refs(onedoor_fixture_dir) -> list[dict]:
    """One citation per delivered row, minted from the delivery's own bytes."""
    import hashlib
    lines = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes().decode("utf-8") \
        .split("\n")[:-1]
    return [{"request_id": json.loads(line)["request_id"],
             "decision_digest": "sha256:" + hashlib.sha256(line.encode("utf-8")).hexdigest()}
            for line in lines]


@pytest.mark.parametrize("edit", sorted(EDITS))
def test_the_join_reads_couldnt_check_for_the_edited_row_and_nothing_else_changes(
        ingested, onedoor_fixture_dir, examined, edit):
    from onetrace_console.onedoor_ext.decision_refs import (STATE_COULDNT_CHECK, STATE_MATCH,
                                                            join_stage)

    refs = _refs(onedoor_fixture_dir)
    before = [join_stage("s", r, True, ingested) for r in refs]
    assert all(c.state == STATE_MATCH for c in before)
    i = edit_stored_line(ingested, DENIED, EDITS[edit])
    after = [join_stage("s", r, True, ingested) for r in refs]
    examined(len(after), "citations joined after one stored line was edited")
    assert after[i].state == STATE_COULDNT_CHECK, after[i]
    assert after[i].reason == f"{COULDNT} (export {ingested.decision_exports()[0].key[:12]}…, " \
                              f"row {i}, request {DENIED})"
    assert after[i].verdict is None
    assert all(after[n] == before[n] for n in range(len(refs)) if n != i)


def test_a_citation_the_console_cannot_find_is_couldnt_check_while_a_delivery_is_unreadable(
        ingested, onedoor_fixture_dir, examined):
    """With a delivery unreadable, its rows cannot even be grouped, so "not in any ingested
    export" cannot be established: the join says couldn't check, never unknown."""
    from onetrace_console.onedoor_ext.decision_refs import STATE_COULDNT_CHECK, join_stage

    _corrupt_delivery(ingested)
    refs = _refs(onedoor_fixture_dir)
    joined = [join_stage("s", r, True, ingested) for r in refs]
    examined(len(joined), "citations joined while their only delivery is unreadable")
    assert all(c.state == STATE_COULDNT_CHECK for c in joined)
    assert all(DELIVERY_MISSING in c.reason for c in joined)


# ---------------------------------------------- the specified sabotage, across every path

def _without_couldnt_check(page: str) -> str:
    """The page with its couldn't-check sentence and filter link taken out: what is left
    must be exactly what the page said before the edit."""
    import re
    page = re.sub(r'<p data-section="couldnt-check">.*?</p>', "", page, flags=re.S)
    return re.sub(r"<p>Couldn&#x27;t check: <a [^>]*>.*?</a></p>", "", page, flags=re.S)


@pytest.mark.parametrize("edit", sorted(EDITS))
def test_sabotage_one_edited_stored_line_reads_couldnt_check_everywhere_and_nothing_else(
        ingested, onedoor_fixture_dir, examined, edit):
    """The sabotage: edit one stored line, then every page and the join show
    "couldn't check" for that row, and nothing else changes."""
    import html

    from onetrace_console.onedoor_ext.decision_refs import (STATE_COULDNT_CHECK, STATE_MATCH,
                                                            join_stage)
    from onetrace_console.onedoor_ext.policy_pages import COULDNT_CHECK, render_policy_pages

    def everything():
        return {**render_policy_pages(ingested, generated_at="now"), **_incident_pages(ingested)}

    refs = _refs(onedoor_fixture_dir)
    before, joined_before = everything(), [join_stage("s", r, True, ingested) for r in refs]
    showed = {k for k, v in before.items() if DENIED[:12] in v}
    i = edit_stored_line(ingested, DENIED, EDITS[edit])
    after, joined_after = everything(), [join_stage("s", r, True, ingested) for r in refs]
    examined(len(showed), "pages that showed the edited row before the edit")
    assert {"policy.html", f"policy/{DENIED}.html", "incidents.html"} <= showed

    for name in showed:
        page = html.unescape(after.get(name) or after[COULDNT_CHECK])
        assert COULDNT in page and f"row {i}" in page, f"{name} does not read couldn't check"
    #: A page naming the row somewhere is not enough: the row itself must show no value.
    #: (A first version checked only the sentence above; a sabotage that showed every row's
    #: value still passed it, because every page also carries the named sentence.)
    for name, page in after.items():
        row = _list_rows(page).get(DENIED)
        assert row is None or (COULDNT in row and "data-verdict" not in row), name
        assert not any(DENIED[:12] in v for v in _incident_items(page).values()), name
    detail = after[f"policy/{DENIED}.html"]
    assert "<tbody>" not in detail and "data-verdict" not in detail
    for name in set(before) - showed:
        assert _without_couldnt_check(after[name]) == before[name], f"{name} changed"
    assert set(after) - set(before) <= {COULDNT_CHECK}

    assert joined_after[i].state == STATE_COULDNT_CHECK
    assert all(joined_after[n] == joined_before[n] for n in range(len(refs)) if n != i)
    assert all(c.state == STATE_MATCH for n, c in enumerate(joined_after) if n != i)


# ------------------------------------- a record is anchored to its own filename (B1, m1)

def _fixture_lines(onedoor_fixture_dir) -> list[str]:
    return (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes().decode("utf-8") \
        .split("\n")[:-1]


def _deliver(store, lines: list[str], name: str = "other.jsonl") -> str:
    """Ingest a second, genuine export and return its key."""
    import hashlib
    data = ("\n".join(lines) + "\n").encode("utf-8")
    sidecar = f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode("utf-8")
    accept_export(_tar(_member(name, data), _member(f"{name}.sha256", sidecar)), store)
    return hashlib.sha256(data).hexdigest()


def _record_of(store, key: str):
    path = store.root / "decision_exports" / f"{key}.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


EXTRA = '{"decision":"executed","id":99,"kind":"decision","request_id":"extra-request"}'


def test_a_record_repointed_at_another_delivery_reads_couldnt_check(
        ingested, onedoor_fixture_dir, examined):
    """The record's own `export_object` is editable, so it cannot say which delivery the
    record is checked against: its filename -- the delivery's content address -- does."""
    from onetrace_console.onedoor_ext.decision_refs import STATE_COULDNT_CHECK, join_stage
    from onetrace_console.onedoor_ext.policy_pages import render_policy

    fixture_key = ingested.decision_exports()[0].key
    other = _deliver(ingested, [EXTRA])
    path, record = _record_of(ingested, fixture_key)
    record["export_object"] = other
    record["rows"] = [{"raw_line": EXTRA}]
    _save(path, record)

    joined = [join_stage("s", r, True, ingested) for r in _refs(onedoor_fixture_dir)]
    examined(len(joined), "citations of the repointed export's genuinely delivered rows")
    assert all(c.state == STATE_COULDNT_CHECK for c in joined), [c.state for c in joined]
    page = render_policy(ingested, generated_at="now")
    rows = _list_rows(page)
    assert COULDNT in rows[DENIED] and "data-verdict" not in rows[DENIED]
    assert f"export {fixture_key[:12]}" in rows[DENIED], "not named by the record's filename"
    assert "7 of 8 stored rows couldn't be checked" in __import__("html").unescape(page)


def test_a_record_pointed_at_a_fabricated_object_reads_couldnt_check(
        ingested, onedoor_fixture_dir, examined):
    """A fabricated object put in the store and named by the record, with matching rows,
    must not become "the delivery": the edited verdict is never shown, never matches."""
    import hashlib

    from onetrace_console.onedoor_ext.decision_refs import STATE_COULDNT_CHECK, join_stage
    from onetrace_console.onedoor_ext.policy_pages import render_policy

    lines = _fixture_lines(onedoor_fixture_dir)
    forged = [EDITS["decision changed"](line) if DENIED in line else line for line in lines]
    fake = ingested.put(("\n".join(forged) + "\n").encode("utf-8"))
    path, record = _record_of(ingested, ingested.decision_exports()[0].key)
    record["export_object"] = fake
    record["rows"] = [{"raw_line": line} for line in forged]
    _save(path, record)

    rows = _list_rows(render_policy(ingested, generated_at="now"))
    examined(len(rows), "list rows after the record was pointed at a fabricated object")
    assert COULDNT in rows[DENIED] and "executed" not in rows[DENIED]
    forged_line = next(line for line in forged if DENIED in line)
    cite_forged = {"request_id": DENIED,
                   "decision_digest": "sha256:" + hashlib.sha256(forged_line.encode()).hexdigest()}
    assert join_stage("s", cite_forged, True, ingested).state == STATE_COULDNT_CHECK
    genuine = next(r for r in _refs(onedoor_fixture_dir) if r["request_id"] == DENIED)
    assert join_stage("s", genuine, True, ingested).state == STATE_COULDNT_CHECK


def test_an_edited_key_never_names_the_row(ingested, examined):
    fixture_key = ingested.decision_exports()[0].key
    path, record = _record_of(ingested, fixture_key)
    record["key"] = "badc0ffee" + "0" * 55
    _save(path, record)
    checked = __import__("onetrace_console.onedoor_ext.decisions", fromlist=["x"]) \
        .check_store(ingested)
    examined(len(checked), "rows of a record whose key was edited")
    assert len(checked) == 7 and all(c.problem == CHANGED for c in checked)
    assert all(f"export {fixture_key[:12]}" in c.name and "badc0ffee" not in c.name
               for c in checked)


# ------------------------- one edited copy is enough to withhold the row (M5, the literal rule)

def test_an_edited_copy_withholds_the_row_even_when_another_export_holds_it_intact(
        ingested, onedoor_fixture_dir, examined):
    """The rule read literally: if the stored line differs from its delivery, the value is
    not shown, and the join never says matches. With two exports holding the same line,
    editing one copy withholds the row everywhere; the intact copy does not vouch for it."""
    import html

    from onetrace_console.onedoor_ext.decision_incidents import derive_decision_incidents
    from onetrace_console.onedoor_ext.decision_refs import STATE_COULDNT_CHECK, join_stage
    from onetrace_console.onedoor_ext.policy_pages import render_policy_pages

    deny_line = next(line for line in _fixture_lines(onedoor_fixture_dir) if DENIED in line)
    _deliver(ingested, [deny_line])
    fixture_key = next(e.key for e in ingested.decision_exports() if len(e.rows) == 7)
    path, record = _record_of(ingested, fixture_key)
    i = next(n for n, r in enumerate(record["rows"]) if DENIED in r["raw_line"])
    record["rows"][i]["raw_line"] = EDITS["decision changed"](record["rows"][i]["raw_line"])
    _save(path, record)

    pages = render_policy_pages(ingested, generated_at="now")
    examined(len(pages), "pages after one of two copies of the deny was edited")
    row = _list_rows(pages["policy.html"])[DENIED]
    assert COULDNT in row and "data-verdict" not in row
    detail = html.unescape(pages[f"policy/{DENIED}.html"])
    assert COULDNT in detail and "<tbody>" not in detail and "verdict (onedoor" not in detail
    assert DENIED not in {x.subject for x in derive_decision_incidents(ingested)}
    genuine = next(r for r in _refs(onedoor_fixture_dir) if r["request_id"] == DENIED)
    assert join_stage("s", genuine, True, ingested).state == STATE_COULDNT_CHECK


# --------------------- no mismatch while any delivery cannot be read (M1)

def test_the_join_never_says_mismatch_while_a_delivery_cannot_be_read(
        ingested, onedoor_fixture_dir, examined):
    """A mismatch claims the cited record differs from what was delivered. With a delivery
    unreadable, the cited row may be in it, so that claim cannot be made."""
    from onetrace_console.onedoor_ext.decision_refs import (STATE_COULDNT_CHECK,
                                                            citation_incidents, join_stage)

    lines = _fixture_lines(onedoor_fixture_dir)
    request = json.loads(lines[0])["request_id"]
    assert json.loads(lines[1])["request_id"] == request, "lines 0-1 are one request's rows"
    _corrupt_delivery(ingested)
    _deliver(ingested, lines[:1])                        # a second export: only row 0
    cite_row_1 = next(r for i, r in enumerate(_refs(onedoor_fixture_dir)) if i == 1)
    c = join_stage("s", cite_row_1, True, ingested)
    examined(1, "a citation of a row only an unreadable delivery holds")
    assert c.state == STATE_COULDNT_CHECK, c
    assert DELIVERY_MISSING in c.reason
    assert citation_incidents("run", (c,)) == ()


# ------------------------------- no page left on disk from an earlier render (M3)

def test_a_policy_page_no_longer_rendered_is_removed_from_disk(ingested, tmp_path, examined):
    """serve writes pages to disk and serves whatever is there. A verdict filter that the
    rule stops rendering must not stay on disk showing the edited row as fact."""
    import html

    from onetrace_console.config import Config
    from onetrace_console.serve import PAGES_DIRNAME, _render_all_pages

    config = Config(extensions={"onedoor": True})
    pages = tmp_path / PAGES_DIRNAME
    _render_all_pages(ingested, tmp_path, config)
    assert (pages / "policy-verdict-denied.html").is_file()

    i = edit_stored_line(ingested, DENIED, EDITS["decision changed"])
    _render_all_pages(ingested, tmp_path, config)
    examined(1, "a verdict filter whose only row was edited, after a second render")
    assert not (pages / "policy-verdict-denied.html").exists(), "stale page still served"
    assert (pages / "policy-couldnt-check.html").is_file()
    for page in pages.rglob("*.html"):
        rows = _list_rows(page.read_text(encoding="utf-8"))
        assert DENIED not in rows or COULDNT in rows[DENIED], page.name

    path, record = _record(ingested)
    record["rows"][i]["raw_line"] = next(
        line for line in (ingested.get(ingested.decision_exports()[0].export_object)
                          .decode("utf-8").split("\n")) if DENIED in line)
    _save(path, record)
    _render_all_pages(ingested, tmp_path, config)
    assert not (pages / "policy-couldnt-check.html").exists(), "stale couldn't-check filter"
    assert COULDNT not in html.unescape((pages / "policy.html").read_text(encoding="utf-8"))


# --------------------- a re-delivery answers from the delivery, not the record (M4)

@pytest.mark.parametrize("edit", ["a row removed and the key edited", "rows is null"])
def test_a_redelivery_reports_the_delivery_not_the_edited_record(
        onedoor_fixture_dir, store, examined, edit):
    """POST /v1/decisions reports accept_export's export key and row count. For a delivery
    already held, those must be the delivery's own, never an edited record's."""
    jsonl = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes()
    sidecar = (onedoor_fixture_dir / "onedoor-export.jsonl.sha256").read_bytes()
    archive = _tar(_member("onedoor-export.jsonl", jsonl),
                   _member("onedoor-export.jsonl.sha256", sidecar))
    first = accept_export(archive, store)
    path, record = _record(store)
    if edit == "rows is null":
        record["rows"] = None
    else:
        record["rows"].pop()
        record["key"] = "0" * 64
    _save(path, record)

    again = accept_export(archive, store)
    examined(len(again.export.rows), "rows reported for a re-delivered export")
    assert not again.created and again.status == 200
    assert again.export.key == first.export.key
    assert len(again.export.rows) == 7


# --------------------------------------- a malformed record reads couldn't check (M2)

MALFORMED = {
    "export_object is null": lambda r: r.update(export_object=None),
    "export_object is a number": lambda r: r.update(export_object=5),
    "key is a number": lambda r: r.update(key=12345),
    "rows is null": lambda r: r.update(rows=None),
    "a row has no raw_line": lambda r: r["rows"].__setitem__(0, {}),
    "received_at is missing": lambda r: r.pop("received_at"),
}


@pytest.mark.parametrize("edit", sorted(MALFORMED) + ["the record is not JSON"])
def test_a_malformed_record_reads_couldnt_check_and_never_crashes(
        ingested, onedoor_fixture_dir, tmp_path, examined, edit):
    """Every one of these used to raise out of rendering, and so out of the server's
    render of all pages -- one bad record taking every page down."""
    import html

    from onetrace_console.config import Config
    from onetrace_console.onedoor_ext.decision_refs import STATE_COULDNT_CHECK, join_stage
    from onetrace_console.onedoor_ext.policy_pages import render_policy_pages
    from onetrace_console.serve import _render_all_pages

    path, record = _record(ingested)
    if edit == "the record is not JSON":
        path.write_text("{this is not json", encoding="utf-8")
    else:
        MALFORMED[edit](record)
        _save(path, record)

    pages = {**render_policy_pages(ingested, generated_at="now"), **_incident_pages(ingested)}
    joined = [join_stage("s", r, True, ingested) for r in _refs(onedoor_fixture_dir)]
    _render_all_pages(ingested, tmp_path, Config(extensions={"onedoor": True}))
    examined(len(pages), "pages rendered from a malformed record")
    assert COULDNT in html.unescape(_list_rows(pages["policy.html"])[DENIED])
    assert all(c.state == STATE_COULDNT_CHECK for c in joined)


def _corrupt_delivery(store) -> None:
    """Change the delivery's own bytes on disk: `Store.get` then refuses to read it (the
    digest no longer matches), which is what an unreadable delivery is."""
    key = store.decision_exports()[0].key
    obj = store.root / "objects" / key[:2] / key
    obj.write_bytes(obj.read_bytes() + b"x")


def test_a_missing_delivery_means_nothing_can_be_checked(ingested, examined):
    from onetrace_console.onedoor_ext.decisions import check_store

    _corrupt_delivery(ingested)
    checked = check_store(ingested)
    examined(len(checked), "stored rows whose delivery cannot be read")
    assert len(checked) == 7
    assert all(c.problem == DELIVERY_MISSING and c.delivered is None for c in checked)
