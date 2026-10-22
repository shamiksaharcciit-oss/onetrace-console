"""The Diff page and the Home page.

The Diff page's checks:
  - the verdicts and counts on the page equal the stored report's;
  - the page passes the five-prohibition tests;
  - it opens offline with 0 requests on the probe control (the browser half is
    `tools/offline_check.py`; the structural half is here).

The Home page's checks:
  - every number on Home equals the size of the filtered list its link opens, over a store
    of **at least 10 runs covering every state**;
  - the page passes the five-prohibition tests;
  - it opens offline.

Every check reports what it examined.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
from html import escape, unescape
from dataclasses import replace
from pathlib import Path

import pytest

from onetrace_console.checks import CONTRADICTS, COULD_NOT_CHECK, HOLDS, run_and_record
from onetrace_console.compare import DIFF, compare, report_text
from onetrace_console.home import MOST_RECENT, NOT_CHECKED, tallies, verdict_of
from onetrace_console.ingest import RUN_ID_REUSED, SUMS_NAME, accept
from onetrace_console.render import (COUNTS, DIFF_PAGE, HOME, render_all, render_counts,
                                     render_diff, render_home)
from onetrace_console.store import StoredRun
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_compare import EXAM, RUN_C, RUN_C_POPPLER24, _deliver, _require_exam
from tests.test_pages import FORBIDDEN_WORDS, INFERENCE_WORDS, _body

GENERATED_AT = "2026-09-26T12:00:00+02:00"


# ------------------------------------------------------------------ the Diff page

@pytest.fixture
def compared(store):
    _require_installed()
    _require_exam()
    a = _deliver(RUN_C, store)
    b = _deliver(RUN_C_POPPLER24, store)
    return compare(a, b, store, ran_at=FIXED_RAN_AT), store


@pytest.fixture
def diverging(store):
    """runs A and B of the ingest fixture: the first difference is at stage 4 (split),
    whose recorded settings differ; stages 1-3 are the same; 5-9 differ after it."""
    _require_installed()
    _require_exam()
    a = _deliver(EXAM / "ingest-r1" / "run_A", store)
    b = _deliver(EXAM / "ingest-r1" / "run_B", store)
    return compare(a, b, store, ran_at=FIXED_RAN_AT), store


def _diff_json(comparison, store) -> dict:
    return json.loads(store.get(dict(comparison.verb(DIFF).reports)["diff.json"]))


def _diff_rows(page: str) -> list[tuple[str, str]]:
    from html import unescape
    table = re.search(r'<table data-section="changes" data-verb="diff".*?</table>', page, re.S)
    return [(v, unescape(cells)) for v, cells in
            re.findall(r'<tr data-verdict="([^"]*)"[^>]*>(.*?)</tr>', table.group(0), re.S)]




def _unlabelled(html: str) -> str:
    """The page without the narrow screen's column labels (`words.labelled`), so a table reads as
    its cells were drawn before them; nothing else changes."""
    import re as _re
    return _re.sub(r' data-label="[^"]*"', "", html)


def test_the_first_difference_is_marked_in_the_table(diverging, examined):
    """Board 6: the first differing stage is marked in the table itself, not only in a
    sentence under it. Later rows say they changed AFTER it -- the ladder establishes the
    order, not that the first difference caused them."""
    comparison, store = diverging
    page = _unlabelled(render_diff(comparison, store, generated_at=GENERATED_AT))
    rows = _diff_rows(page)
    examined(len(rows), "rows of the diverging pair's changes table")
    words = [re.findall(r'<td data-result="[^"]*">([^<·]*)', cells)[0].strip() for _, cells in rows]
    assert words == ["Same"] * 3 + ["First difference"] + ["Changed after it"] * 5, words
    #: Each changes table (diff's, and localize's own ladder) marks exactly one row, and it
    #: is the row the SDK called the first difference.
    tables = re.findall(r'<table data-section="changes".*?</table>', page, re.S)
    assert tables
    for table in tables:
        marked = re.findall(r'<tr ([^>]*data-first-difference="true"[^>]*)>', table)
        #: Since 0.1.1, diff's table rows carry the anchor the comparison graph's boxes link to.
        marked = [re.sub(r' id="step-\d+"$', "", m) for m in marked]
        assert marked == ['data-verdict="FIRST DIFFERENCE" data-first-difference="true"'], marked
    assert "as a result" not in page.lower()


def _settings_cell(cells: str) -> str:
    return re.search(r'<td data-section="settings">(.*?)</td>', _unlabelled(cells), re.S).group(1)


def test_the_settings_column_names_each_changed_setting(diverging, compared, examined):
    """Board 6's settings column, from the report's own annotations: each changed field by its
    short name (its whole path in its tooltip), as "old → new", the values verbatim and whole. A stage whose output is the same but whose settings
    changed carries it too (the poppler pair). A compared stage with no annotation says no
    recorded setting differs -- not "same", because the SDK also annotates nothing when a
    stage recorded no settings to compare."""
    for pair in (diverging, compared):
        comparison, store = pair
        report = _diff_json(comparison, store)
        rows = _diff_rows(render_diff(comparison, store, generated_at=GENERATED_AT))
        notes = {a["index"]: a["differs"] for a in report["annotations"]}
        assert notes, "each fixture pair carries at least one annotation"
        examined(len(rows), "settings cells checked against the report's annotations")
        for i, (_, cells) in enumerate(rows, start=1):
            settings = _settings_cell(cells)
            if str(i) not in notes:
                assert settings == "no recorded setting differs", (i, settings)
                continue
            text = unescape(re.sub(r"<[^>]+>", "", settings))
            for field, (old, new) in notes[str(i)].items():
                #: Shown by its short name, its whole path in the tooltip; its values whole.
                short = field.rsplit(".", 1)[-1]
                assert f"{short} {old} → {new}" in text, (i, field)
                assert f'data-setting-path="{escape(field)}" title="{escape(field)}">{escape(short)}<' \
                    in settings, (i, field)


def test_a_stage_the_sdk_did_not_compare_says_so_in_the_settings_column():
    """A COULD NOT CHECK row never reached the SDK's settings comparison, so its cell says
    "not compared" rather than claiming nothing differs."""
    from types import SimpleNamespace

    from onetrace_console.render import _ladder_table
    row = SimpleNamespace(index="3", stage="cleaned", baseline=None, candidate=None,
                          verdict="COULD NOT CHECK", reason="nothing recorded to compare")
    table = _ladder_table(SimpleNamespace(ladder=[row]), "diff", annotations=[])
    assert _settings_cell(table) == "not compared", table


def _refused_on_the_page(page: str, why: str) -> None:
    """A report the viewer refuses is refused ON the page, not raised
    past it. Nothing is drawn from it, the page says why, and the report's own words follow."""
    block = re.search(r'<section data-section="diff-unreadable".*?</section>', page, re.S)
    assert block, "the page does not say the report was refused"
    assert why in block.group(0), block.group(0)
    assert 'data-verb="diff"' not in page, "a changes table was drawn from the refused report"
    assert _summary(page) is None, "a summary was drawn from the refused report"
    #: Relabelled: the words it copies from records are escaped inside it.
    assert "The diff report as the SDK wrote it, with names from the records escaped" in page


@pytest.mark.parametrize("annotations", [
    {"index": "4"},                                                    # not a list
    [{"index": 4, "stage": "split", "differs": {"x": ["1", "2"]}}],    # index not a string
    [{"index": "4", "stage": "split", "differs": {"x": ["1"]}}],       # not an old/new pair
    [{"index": "4", "stage": "split", "differs": ["x"]}],              # differs not a mapping
    [{"index": "4", "stage": "split"}],                                # differs missing
])
def test_annotations_it_cannot_read_are_refused_not_half_rendered(diverging, annotations):
    """The F16 lesson at the input, as the viewer's strict reader applies it to the rest of
    the report: an annotation shape this console has not been taught refuses the report --
    on the page (it used to raise out of `render_diff`)."""
    from onetrace_console.compare import LOCALIZE
    comparison, store = diverging
    report = _diff_json(comparison, store)
    report["annotations"] = annotations
    edited = store.put(json.dumps(report).encode("utf-8"))
    verbs = tuple(
        replace(v, reports=tuple((n, edited if n == "diff.json" else k) for n, k in v.reports))
        if v.verb == DIFF else v for v in comparison.verbs if v.verb != LOCALIZE)
    _refused_on_the_page(
        render_diff(replace(comparison, verbs=verbs), store, generated_at=GENERATED_AT),
        "annotations")


def _summary(page: str) -> str | None:
    from html import unescape
    found = re.findall(r'<section data-section="first-difference">(.*?)</section>', page, re.S)
    assert len(found) <= 1, "one summary per page"
    return unescape(found[0]) if found else None


def test_the_summary_names_the_first_difference_and_what_is_not_established(
        diverging, examined):
    """Board 6's stage-level summary: where the first difference is, how many stages were
    identical before it (with its denominator), one plain sentence of what differs (each setting
    by its short name with both values, how many stages after it changed). With a setting
    recorded as differing at the stage, it no longer adds that why its output differs is not
    established: the recorded change is named instead. No causal word: the ladder gives order,
    and settings differing beside an output differing is not evidence that one produced the other."""
    comparison, store = diverging
    report = _diff_json(comparison, store)
    first = report["first_difference"]
    block = _summary(render_diff(comparison, store, generated_at=GENERATED_AT))
    examined(1, "the first-difference summary of the diverging pair")
    before = int(first["index"]) - 1
    assert f"stage {first['index']} · {first['stage']}" in block
    assert f"Stages identical before it: {report['stages_identical_before_first_difference']} " \
           f"of {before}" in block
    assert "is not established by this evidence." not in block
    #: One plain sentence (the Compare board's): each differing setting by its short name, with
    #: both values, never its whole path; the stages the same before it; how many changed after.
    note = next(a for a in report["annotations"] if a["index"] == first["index"])
    text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", block)))
    assert f"{first['stage']}'s settings differ in " in text
    for field, (old, new) in note["differs"].items():
        if re.fullmatch(r"sha256:[0-9a-f]{64}", str(old)) or re.fullmatch(r"sha256:[0-9a-f]{64}", str(new)):
            assert old not in text and new not in text, f"a digest in the sentence: {field}"
            continue
        assert f"{field.rsplit('.', 1)[-1]}: {old} → {new}" in text, field
        assert field not in text or "." not in field, f"the whole path {field}"
    same = [r["stage"] for r in report["ladder"]
            if int(r["index"]) < int(first["index"]) and r["verdict"] == "same"]
    assert all(s in text for s in same) and "the same in both" in text
    after = [r for r in report["ladder"] if int(r["index"]) > int(first["index"])]
    changed = sum(r["verdict"] == "downstream" for r in after)
    assert (f"all {changed} stages after it changed too" if changed == len(after)
            else f"{changed} of the {len(after)} stages after it changed too") in text
    for causal in ("as a result", "caused", "because", "led to", "due to"):
        assert causal not in block.lower(), causal


def test_a_pair_with_no_difference_has_no_first_difference_summary(compared, examined):
    comparison, store = compared
    assert _diff_json(comparison, store)["first_difference"] is None
    examined(1, "the Diff page of a pair with no first difference")
    assert _summary(render_diff(comparison, store, generated_at=GENERATED_AT)) is None


@pytest.mark.parametrize("identical", [None, 3, "three", "-1", "4", ""])
def test_a_count_before_the_first_difference_it_cannot_read_is_refused(diverging, identical):
    """The count carries a denominator (the stages before the first difference), so a count
    that is missing, not in the SDK's digit-string form, or larger than that denominator
    refuses the report -- on the page."""
    from onetrace_console.compare import LOCALIZE
    comparison, store = diverging
    report = _diff_json(comparison, store)
    report["stages_identical_before_first_difference"] = identical
    edited = store.put(json.dumps(report).encode("utf-8"))
    verbs = tuple(
        replace(v, reports=tuple((n, edited if n == "diff.json" else k) for n, k in v.reports))
        if v.verb == DIFF else v for v in comparison.verbs if v.verb != LOCALIZE)
    _refused_on_the_page(
        render_diff(replace(comparison, verbs=verbs), store, generated_at=GENERATED_AT),
        "stages_identical_before_first_difference")


@pytest.mark.parametrize("field,value,why", [
    ("ladder", "x", "not a list of objects"),
    ("first_difference", "4 split", "neither an object nor null"),
    ("carried", 7, "not a list of objects"),
])
def test_a_report_shape_the_viewer_refuses_is_stated_not_raised(diverging, field, value, why):
    """Before, `read_report` raised `AttributeError`/`TypeError` on
    some of these, and a clean refusal still escaped `render_diff` -- a 500 at compare time,
    and a restart over the store that never reached its listener."""
    from onetrace_console.compare import LOCALIZE
    comparison, store = diverging
    report = _diff_json(comparison, store)
    report[field] = value
    edited = store.put(json.dumps(report).encode("utf-8"))
    verbs = tuple(
        replace(v, reports=tuple((n, edited if n == "diff.json" else k) for n, k in v.reports))
        if v.verb == DIFF else v for v in comparison.verbs if v.verb != LOCALIZE)
    _refused_on_the_page(
        render_diff(replace(comparison, verbs=verbs), store, generated_at=GENERATED_AT), why)


def test_the_localized_set_heading_carries_no_count(run_folder, examined):
    """No honest denominator exists for this set, so the number goes and
    the heading stays."""
    from onetrace_console.render import _localized
    from onetrace_console.viewer.verbs import SingleRunDag, read_report

    report = read_report(run_folder / "localize")
    assert isinstance(report, SingleRunDag) and report.nodes
    block = _localized(report)
    examined(len(report.nodes), "nodes in the localized set")
    heading = re.search(r"<h3>(.*?)</h3>", block).group(1)
    assert heading == "The set it localized", heading
    assert sorted(re.findall(r'<li class="mono">(.*?)</li>', block)) == \
        sorted(n.node for n in report.nodes)


def test_the_diff_page_renders(compared, examined):
    comparison, store = compared
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    examined(len(page.splitlines()), "lines of the rendered Diff page")
    assert page.lstrip().startswith("<!"), page[:80]
    assert 'data-section="changes"' in page, "no changes table on the Diff page"
    assert 'data-section="localized"' in page, "no localized block on the Diff page"


def test_the_changes_table_is_the_sdks_ladder_row_for_row_in_its_own_order(compared,
                                                                          examined):
    """Step 3's first check, over the table itself rather than a summary of it.

    Every ladder row in the stored report must appear once, in the report's order, with the
    SDK's own verdict. The console re-sorts nothing.
    """
    import tempfile

    from onetrace_console.viewer.verbs import read_report

    comparison, store = compared
    run = comparison.verb(DIFF)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for name, key in run.reports:
            (folder / name).write_bytes(store.get(key))
        report = read_report(folder)

    page = _unlabelled(render_diff(comparison, store, generated_at=GENERATED_AT))
    #: Scoped to the DIFF table. The page carries one per verb, and `localize` over two runs
    #: has a ladder too — the first version of this test counted both and found 18 rows for
    #: 9, which was the page being more complete than the test.
    table = re.search(r'<table data-section="changes" data-verb="diff".*?</table>', page, re.S)
    assert table, "no diff changes table on the page"
    rows = re.findall(r'<tr data-verdict="([^"]*)"[^>]*>(.*?)</tr>', table.group(0), re.S)
    examined(len(rows), "rendered changes-table rows for diff")
    assert len(rows) == len(report.ladder), (
        f"{len(rows)} rendered rows against {len(report.ladder)} ladder rows")

    #: The header names every column and every row must fill all of them. Dropping the
    #: SDK's `reason` was a sabotage this test once missed, because on this fixture every
    #: reason is empty -- so the SHAPE is asserted as well as the content. The SDK's own
    #: verdict stays verbatim in `data-verdict`; the result column words it for a reader and
    #: carries the reason.
    headers = re.findall(r"<th>(.*?)</th>", table.group(0))
    examined(len(headers), "columns in the changes table")
    assert headers == ["#", "stage", "baseline", "candidate", "settings", "result"], headers

    #: Stage ORDER, not just membership. "never re-orders what the SDK returned" is the claim,
    #: and a per-row comparison cannot see a reversal on its own.
    assert [row.stage for row in report.ladder] == re.findall(
        r"<td>\d+</td><td>(.*?)</td>", table.group(0)), "the table re-ordered the ladder"

    for rendered, row in zip(rows, report.ladder):
        verdict, cells = rendered
        assert verdict == row.verdict, f"stage {row.stage}: page says {verdict!r}"
        assert f"<td>{row.stage}</td>" in cells or row.stage in cells, row.stage
        assert row.index in cells
        if row.reason:
            assert escape(row.reason) in cells, f"stage {row.stage}: its reason is not shown"
        assert len(re.findall(r"<td", cells)) == len(headers), (
            f"stage {row.stage}: {len(re.findall(r'<td', cells))} cells for "
            f"{len(headers)} columns")


def test_the_envelope_and_exit_on_the_page_are_the_reports(compared, examined):
    import tempfile

    from onetrace_console.viewer.verbs import read_report

    comparison, store = compared
    run = comparison.verb(DIFF)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for name, key in run.reports:
            (folder / name).write_bytes(store.get(key))
        report = read_report(folder)

    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    examined(2, "report fields compared with the page")
    from onetrace_console.render import DIFF_ENVELOPES
    line = re.search(r'<p data-section="diff-envelope" data-verdict="([^"]+)">([^<]*)</p>', page)
    assert line and line.group(1) == report.envelope, "the page does not carry the report's envelope"
    assert line.group(2) == DIFF_ENVELOPES[report.envelope], line.group(2)
    #: The exit code is the SDK's own: in its report as it wrote it, not in the page's line.
    sdk = re.search(r'<details data-layer="3"><summary>The diff report as the SDK wrote it.*?</details>',
                    page, re.S).group(0)
    assert f"exit {report.exit_code}" not in line.group(0) and str(report.exit_code) in sdk


def test_the_sdks_own_report_is_on_the_page_whole(compared, examined):
    """A table is a rendering OF the report; the report itself is one layer down, verbatim."""
    comparison, store = compared
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    text = report_text(comparison, DIFF, store)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    examined(len(lines), "lines of the SDK's report that must survive onto the page")
    from html import escape

    from onetrace_console.compare import report_json
    #: The folders it was given, this host's temporary ones, named for what they held.
    for side, given in report_json(comparison, DIFF, store)["inputs"].items():
        text = text.replace(given["path"], f"(the {side} run's folder)")
    assert escape(text) in page, "the SDK's report is not on the page verbatim"


def test_the_command_to_repeat_the_comparison_is_on_the_page(compared, examined):
    """The command a reader types to repeat each verb: the SDK's own (`onetrace <verb>`), over the
    two run folders by their run ids -- never the stored placeholder form (RUN_A RUN_B --out OUT)."""
    from onetrace_console.render import typed_command
    comparison, store = compared
    page = unescape(render_diff(comparison, store, generated_at=GENERATED_AT))
    from onetrace_console.compare import DIFF, LOCALIZE
    #: Each verb's own section; the text diff's command is in the text diff's section.
    shown = {v.verb: typed_command(comparison, store, v.verb) for v in comparison.verbs
             if v.verb in (DIFF, LOCALIZE)}
    examined(len(shown), "repeat commands that must appear")
    for verb, command in shown.items():
        assert command in page, f"{verb}'s repeat command is missing: {command!r}"
    assert "RUN_A" not in page and "--out OUT" not in page


def test_the_diff_page_keeps_the_limit_sentence(compared, examined):
    comparison, store = compared
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    examined(1, "limit sentence")
    assert "not what was ultimately true" in page


# ------------------------------------------------------------------ the Home page

#: The rung 1 reading a check with the run's output files required stores with each verdict.
_AGREE = {HOLDS: "yes", CONTRADICTS: "no", COULD_NOT_CHECK: "couldnt-check", "": ""}


def _fake_run(store, base: StoredRun, *, run_id: str, verdict: str, note: str = "",
              flags: tuple[str, ...] = (), agree: tuple[str, str] | None = None) -> StoredRun:
    """A stored run in a chosen state, for covering states a real store reaches slowly.

    The bytes are a real run's; only the fields Home counts are set. Built through the store
    so it is a genuinely stored run and not a stand-in the page treats differently. Its "Records
    agree" (`agree`, and why) is the one its verdict's check would record with the run's output
    files required, unless given.
    """
    from onetrace_console.store import run_key
    key = run_key(run_id, base.chain_head)
    #: A run the check runner has not reached has no rung 3 recorded either: it is recorded
    #: when the run is checked.
    made = replace(base, key=key, run_id=run_id, check_verdict=verdict,
                   check_note=note, flags=flags,
                   nothing_missing=base.nothing_missing if verdict else "",
                   anchored=base.anchored if verdict else "",
                   signed=base.signed if verdict else "",
                   agree=(agree or (_AGREE[verdict], ""))[0], agree_why=(agree or (_AGREE[verdict], ""))[1])
    store.put_run(made)
    return made


@pytest.fixture
def ten_runs(store):
    """At least ten stored runs covering every state Home counts, as step 4 requires."""
    _require_installed()
    _require_exam()
    real = _deliver(RUN_C, store)
    checked = run_and_record(real, store, ran_at=FIXED_RAN_AT)
    made = [checked]
    plan = [
        ("holds-1", HOLDS, "", ()),
        ("holds-2", HOLDS, "", ()),             # held without its output files required: below
        ("contradicts-1", CONTRADICTS, "", ()),
        ("contradicts-2", CONTRADICTS, "", ()),
        ("cnc-1", COULD_NOT_CHECK, "the report has no summary line", ()),
        ("cnc-2", COULD_NOT_CHECK, "the report has no summary line", ()),
        ("cnc-3", COULD_NOT_CHECK, "a line that is neither a finding nor the summary", ()),
        ("unchecked-1", "", "", ()),
        ("reused-1", HOLDS, "", (RUN_ID_REUSED,)),
        ("reused-2", CONTRADICTS, "", (RUN_ID_REUSED,)),
    ]
    for run_id, verdict, note, flags in plan:
        made.append(_fake_run(store, real, run_id=run_id, verdict=verdict, note=note, flags=flags,
                              agree=("not-checked", "no-outputs") if run_id == "holds-2" else None))
    #: Two more states: a run whose manifest declares a stage its chain holds no
    #: receipt for, and a real comparison whose diff found a first difference -- so the
    #: "missing a declared stage" and "changed vs baseline" counts are never examined empty.
    short = _fake_run(store, real, run_id="short-1", verdict=HOLDS)
    store.put_run(replace(short, recorded_count=short.stage_count - 1, nothing_missing="no"))
    made.append(store.get_run(short.key))
    #: "Records agree": a check that held with the run's output files
    #: required. The pinned verifier (0.1.0) cannot run one, so this run's stored report is
    #: a test double: the real check's, its command carrying `--require-artifacts`.
    envelope = json.loads(store.get(checked.check_report).decode("utf-8"))
    envelope["command"] = list(envelope["command"]) + ["--require-artifacts"]
    agree = _fake_run(store, checked, run_id="agree-1", verdict=HOLDS)
    store.put_run(replace(agree, check_report=store.put(json.dumps(envelope).encode("utf-8"))))
    made.append(store.get_run(agree.key))
    a = _deliver(EXAM / "ingest-r1" / "run_A", store)
    b = _deliver(EXAM / "ingest-r1" / "run_B", store)
    compare(a, b, store, ran_at=FIXED_RAN_AT)
    made += [a, b]
    #: The anchoring forms, so no count is examined empty: three checked runs
    #: given the readings no exam run reaches (the exam runs have no anchor beside their chain).
    for run_id, reading in (("holds-1", "yes"), ("holds-2", "couldnt-check"),
                            ("contradicts-1", "failed")):
        (run,) = [r for r in store.runs() if r.run_id == run_id]
        store.put_run(replace(run, anchored=reading))
    #: The signing forms the same way: four checked runs given the readings no exam
    #: run reaches (no exam run is signed).
    for run_id, reading in (("holds-1", "yes"), ("holds-2", "untrusted"),
                            ("contradicts-1", "failed"), ("contradicts-2", "couldnt-check")):
        (run,) = [r for r in store.runs() if r.run_id == run_id]
        store.put_run(replace(run, signed=reading))
    #: A run stopped by a step's own rule, so "Stopped by a step" is never examined empty: its
    #: stored reading as the check derives one (`ingest.declined_at`).
    stopped = _fake_run(store, real, run_id="stopped-1", verdict=HOLDS)
    store.put_run(replace(stopped, declined=json.dumps(
        {"stage": "answer", "reason": "over the limit", "left": []})))
    made.append(store.get_run(stopped.key))
    #: And one whose rung 3 reads "Not reached", so "stopped at a step" is never examined empty: a
    #: step declined with a declared step after it, as the check derives both.
    not_reached = _fake_run(store, real, run_id="stopped-2", verdict=HOLDS)
    store.put_run(replace(not_reached, nothing_missing="not-reached", declined=json.dumps(
        {"stage": "answer", "reason": "over the limit", "left": ["deliver"]})))
    made.append(store.get_run(not_reached.key))
    made = [store.get_run(r.key) for r in made]
    return store, made


def test_the_fixture_store_covers_every_state_and_has_at_least_ten_runs(ten_runs, examined):
    """The premise step 4's check rests on, asserted before anything is concluded from it."""
    store, made = ten_runs
    runs = store.runs()
    examined(len(runs), "runs in the store")
    assert len(runs) >= 10, f"only {len(runs)} runs; step 4 asks for at least 10"
    states = {verdict_of(r) for r in runs}
    examined(len(states), "distinct verdict states present")
    assert states == {HOLDS, CONTRADICTS, COULD_NOT_CHECK, NOT_CHECKED}, f"states covered: {sorted(states)}"
    assert any(RUN_ID_REUSED in r.flags for r in runs), "no flagged run in the fixture"
    assert any(r.check_note for r in runs), "no could-not-check reason in the fixture"


def test_every_executions_list_states_the_runs_it_was_chosen_from(ten_runs, examined):
    """Counts carry denominators. A list opened from Home is a subset of the
    stored runs, so its count reads "N of T" with T the runs stored -- never "N of N", which
    is what the viewer says of a list that is every run it was given."""
    from html import unescape

    store, _ = ten_runs
    pages = render_all(store, generated_at=GENERATED_AT)
    stored = len(store.runs())
    counted = tallies(store)
    examined(len(counted), "lists opened from Home, each checked for its denominator")
    assert any(len(t.runs) < stored for t in counted), "no list is a subset, so this proves nothing"
    for t in counted:
        listed = pages[t.href]
        rows = len(re.findall(r'<tr data-run="', listed))
        text = unescape(listed)
        if t.slug == "all":
            #: The Runs page itself, in the console's own words.
            assert rows == stored and (f"Runs stored: {stored} of {stored}, and this page "
                                       "lists every one of them.") in text, t.slug
            continue
        #: Every other list, in the console's own words.
        from onetrace_console.pages import runs_in_list
        assert runs_in_list(rows, stored) in text, t.slug


def test_every_number_on_home_equals_the_filtered_list_its_link_opens(ten_runs, examined):
    """Step 4's first check, and the strongest one on the page.

    The count and the list are compared by rendering the page the link opens and counting the
    runs on it — not by recomputing the tally, which would compare two implementations and
    pass whenever they were wrong together.
    """
    store, _ = ten_runs
    pages = render_all(store, generated_at=GENERATED_AT)
    #: Every count, whole, is on the All counts page the Overview links to.
    home = pages[COUNTS]
    assert f'href="{COUNTS}"' in pages[HOME], "the Overview does not link its full list of counts"
    counted = tallies(store)
    examined(len(counted), "tallies on Home")
    assert counted, "Home shows no counts at all"

    for t in counted:
        assert t.href in pages, f"Home links to {t.href}, which was not rendered"
        listed = pages[t.href]
        #: The **rows** the page renders, which is what "the size of the list" means. The
        #: viewer writes one `<tr data-run="…">` per run.
        #:
        #: Counted as rows rather than by matching run ids, because the page renders the
        #: RECORD and the index is not the record: these fixtures share one manifest, so
        #: every row shows the manifest's own run id. The first version of this test matched
        #: ids and found 1 row for 11 runs — the page being right and the test being wrong
        #: about where a run's name comes from.
        rows = re.findall(r'<tr data-run="', listed)
        examined(len(t.runs), f"runs counted by {t.slug!r}")

        #: **The number is read out of Home's own HTML**, and compared with the rows on the
        #: page its link opens. Comparing `len(t.runs)` with the rows compares two values
        #: derived from the same tally: a sabotage making `count` return `len(runs) + 1`
        #: passed this test until it was written this way — the exact two-implementations
        #: trap this file claims to avoid, caught by sabotaging it.
        block = re.search(rf'<li data-tally="{re.escape(t.slug)}">.*?</li>', home, re.S)
        assert block, f"Home has no tally block for {t.slug!r}"
        shown = re.search(r"(\d+) runs? of (\d+)", block.group(0))
        assert shown, f"Home's {t.slug!r} line carries no `N of M`: {block.group(0)[:160]}"
        page_count, page_total = int(shown.group(1)), int(shown.group(2))
        assert page_count == len(rows), (
            f"{t.slug}: Home says {page_count} but {t.href} shows {len(rows)} rows")
        assert page_total == len(store.runs()), (
            f"{t.slug}: Home's denominator is {page_total}, the store holds "
            f"{len(store.runs())}")
        #: Compared in its ESCAPED form: the label naming the flag carries apostrophes
        #: and the page escapes them, which is the escaping working correctly.
        assert escape(t.sentence) in home, (
            f"Home does not carry {escape(t.sentence)!r}")


def test_every_count_carries_its_denominator(ten_runs, examined):
    store, _ = ten_runs
    counted = tallies(store)
    total = len(store.runs())
    examined(len(counted), "tallies checked for a denominator")
    for t in counted:
        assert t.denominator == total, f"{t.slug} counts out of {t.denominator}, not {total}"
        assert f"of {total}" in t.sentence, t.sentence
        #: The unit is written out.
        assert " run of " in t.sentence or " runs of " in t.sentence, t.sentence


def test_could_not_be_checked_carries_its_reasons(ten_runs, examined):
    """A count of runs that could not be checked, without the reasons, is unusable."""
    store, _ = ten_runs
    t = next(t for t in tallies(store) if t.slug == COULD_NOT_CHECK.replace("_", "-"))
    examined(len(t.reasons), "distinct reasons behind the could-not-check count")
    assert t.reasons, "the could-not-check tally carries no reason"
    from html import unescape
    home = render_counts(store, generated_at=GENERATED_AT)
    #: Read as shown: a reason with an apostrophe (such as "doesn't") is escaped in the HTML.
    for reason in t.reasons:
        assert reason in unescape(home), f"Home does not show the reason {reason!r}"


def test_a_run_nobody_checked_is_its_own_state_and_not_folded_into_a_verdict(ten_runs,
                                                                            examined):
    store, _ = ten_runs
    unchecked = [r for r in store.runs() if verdict_of(r) == NOT_CHECKED]
    examined(len(unchecked), "runs the check runner has not reached")
    assert unchecked, "the fixture has no unchecked run, so this proves nothing"
    for r in unchecked:
        assert r.check_verdict == ""
        assert verdict_of(r) not in (HOLDS, CONTRADICTS, COULD_NOT_CHECK)


def test_the_most_recent_list_is_by_arrival_and_is_not_a_ranking(ten_runs, examined):
    store, _ = ten_runs
    t = next(t for t in tallies(store) if t.slug == "most-recent")
    examined(len(t.runs), "runs in the most-recent list")
    assert len(t.runs) == min(MOST_RECENT, len(store.runs()))
    assert list(t.runs) == list(store.runs()[:len(t.runs)]), "the list was re-ordered"


def test_home_shows_no_percentage_trend_or_health(ten_runs, examined):
    """Step 4's "no score, no trend arrow, no health, no recommendation", by shape."""
    store, _ = ten_runs
    #: The Overview and the All counts page its counts moved to.
    body = (_body(render_home(store, generated_at=GENERATED_AT))
            + _body(render_counts(store, generated_at=GENERATED_AT)))
    banned = ("health", "trend", "score", "grade", "↑", "↓", "▲", "▼",
              "improving", "worsening", "recommend")
    found = [w for w in banned if w in body.lower()]
    examined(len(banned), "banned shapes searched for")
    assert not found, f"Home carries {found}"
    percentages = re.findall(r"\d+(?:\.\d+)?\s*%", body)
    assert not percentages, f"Home carries percentages {percentages}"


# ------------------------------------- the five prohibitions, on both new pages

@pytest.fixture
def new_pages(ten_runs, compared) -> dict[str, str]:
    store, _ = ten_runs
    comparison, cstore = compared
    pages = render_all(store, generated_at=GENERATED_AT)
    pages[DIFF_PAGE] = render_diff(comparison, cstore, generated_at=GENERATED_AT)
    return pages


def test_the_new_pages_pass_the_five_prohibitions(new_pages, examined):
    examined(len(new_pages), "pages checked against the five prohibitions")
    assert len(new_pages) >= 2, "fewer pages than expected; this would check almost nothing"
    for name, page in new_pages.items():
        body = _body(page).lower()
        assert not [w for w in FORBIDDEN_WORDS if w in body], f"{name}: score or grade"
        assert not [w for w in INFERENCE_WORDS if w in body], f"{name}: inference"
        assert not re.findall(r"\d+(?:\.\d+)?\s*%", _body(page)), f"{name}: percentage"
        #: The one mechanism a page may carry: the explanation panel's buttons, which a person
        #: presses to ask for a suggestion (`explain`), each posting to one of its three routes.
        panel = re.search(r'<section data-section="explain".*?</section>', body, re.S)
        rest = body.replace(panel.group(0), "") if panel else body
        for mechanism in ("<button", "<form", "<input", "onclick=", "onsubmit="):
            assert mechanism not in rest, f"{name} carries {mechanism!r}"
        if panel:
            for m in ("<form", "<input", "onclick=", "onsubmit="):
                assert m not in panel.group(0), f"{name}'s explanation panel carries {m!r}"
            posts = re.findall(r'<button type="button" data-explain-post="([^"]*)"', panel.group(0))
            assert panel.group(0).count("<button") == len(posts), f"{name}: a button that posts nowhere named"
            assert all(re.fullmatch(r"/explain(/packet|/check)?\?c=[0-9a-f]{64}(&amp;[a-z]=[^&\"]*)*", p)
                       for p in posts), posts
        inline = re.findall(r'style="[^"]*(?:color|background)[^"]*"', page, re.I)
        assert not inline, f"{name} carries inline colour: {inline[:2]}"


def test_no_new_page_references_a_remote_origin(new_pages, examined):
    """The structural half of "opens offline". The browser half is tools/offline_check.py."""
    examined(len(new_pages), "pages checked for a remote reference")
    for name, page in new_pages.items():
        remote = re.findall(r'(?:src|href)\s*=\s*"(https?:|//)[^"]*"', page, re.I)
        assert not remote, f"{name} references {remote[:2]}"
        assert "<script src=" not in page, f"{name} loads an external script"


def test_every_link_on_home_points_at_a_page_that_was_rendered(new_pages, ten_runs, examined):
    """A link to a page nobody generated is a dead end, and on Home it is a dead count."""
    hrefs = re.findall(r'<a href="([^"]+)"', new_pages[HOME])
    examined(len(hrefs), "links on Home")
    assert hrefs, "Home has no links at all, so no count can be opened"
    #: A run's own case page is rendered by `pages.render_execution` (at ingest and on every
    #: restart), not by `render_all`; the Overview links to it by the run's store key. Such a
    #: link is accepted only for a run that is in the store.
    stored = {r.key for r in ten_runs[0].runs()}
    for href in hrefs:
        run = re.fullmatch(r"runs/([0-9a-f]{64})/case\.html", href)
        if run:
            assert run.group(1) in stored, f"Home links to {href}, a run that is not stored"
            continue
        #: A link to a part of Home itself: the part must be there.
        if href.startswith("#"):
            assert f'id="{href[1:]}"' in new_pages[HOME], f"Home links to {href}, which it lacks"
            continue
        assert href in new_pages, f"Home links to {href}, which was not rendered"


def test_home_names_each_records_agree_state_in_its_own_word_and_does_not_summarise_it(ten_runs, examined):
    """Each run's "Records agree" is counted under rung 1's own label for its state, never a
    paraphrase of what it means, and never the verifier's own word for its verdict.

    The labels once read "the trail holds" and "the trail contradicts itself", a summary in the
    console's own voice; then they quoted the stored value ("verdict: holds"); then the verifier's
    word for each verdict ("Verified"), which counted a check that held without the run's output
    files required as verified while that run's own page read Not checked. They are now rung 1's
    labels (`records.LABEL`), counted as each run's page decides it.
    """
    from onetrace_console import records
    from onetrace_console.checks import VERDICTS

    store, _ = ten_runs
    home = (render_home(store, generated_at=GENERATED_AT)
            + render_counts(store, generated_at=GENERATED_AT))
    examined(len(records.STATES), "rung 1 labels checked on Home")

    import html as _html
    for state in records.STATES:
        assert records.LABEL[state] in _html.unescape(home), f"Home does not show {records.LABEL[state]!r}"
    for state in VERDICTS:
        assert f"verdict: {state}" not in home, f"Home shows the stored value {state!r}"
    assert not re.search(r"\bVerified\b", re.sub(r"<[^>]+>", " ", home)), "Home counts runs as 'Verified'"

    #: And the paraphrases are gone from the page itself, not merely from the table.
    for gone in ("the trail holds", "the trail contradicts", "not checked yet",
                 "could not be checked"):
        assert gone not in home, (
            f"Home carries {gone!r}, a summary in this console's own voice")
