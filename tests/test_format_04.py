"""Format 0.4, as onetrace 0.7 writes it: stored, checked and drawn, and a run written before reads as
it did.

Every run onetrace 0.7 closes ends with a **close receipt** (onetrace's `docs/format.md`, "The close
receipt"): stage and instrument `onetrace.close`, of kind `close`, and every receipt declares that
stage last. It is not a step. The verbs set it aside before they compare, and so does this console
(`viewer.record.is_close`): a 0.4 run's steps, its declared stages, its counts and its "nothing
missing" read as the same run's do written in 0.3, and its completeness is read off its last receipt,
the close receipt (the format's second reading rule). What differs is only what the record and the
check say themselves: the receipts' own bytes, and onetrace-verify's own rows, among them its rows
about the close receipt.

The runs are `tests/onetrace_runs/` (`tests/test_onetrace_runs.py`): each 0.7.1 run beside its 0.6.1
twin, the same pipeline ended the same way.
"""
from __future__ import annotations

import difflib
import html
import re
from pathlib import Path

import pytest

from tests.test_format_03 import _tar

RUNS = Path(__file__).resolve().parent / "onetrace_runs"
GENERATED_AT = "2026-10-04T12:00:00+00:00"
RAN_AT = "2026-09-26T12:00:00+02:00"
TWINS = ("refund-closed", "refund-raised", "refund-killed")
#: What a stored run keeps about itself, read on Home and in the run list.
KEPT = ("declared_stages", "stage_count", "recorded_count", "delivered_stages", "retries", "check_verdict",
        "check_exit", "nothing_missing", "agree", "agree_why", "approved", "signed", "anchored", "declined")


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed
    _require_installed()


def _stored(folder: Path, store):
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    got = accept(_tar(folder), store)
    assert getattr(got, "run", None) is not None, getattr(got, "body", got)
    return run_and_record(got.run, store, ran_at=RAN_AT)


def _pages(folder: Path, store) -> tuple[object, dict[str, str]]:
    from onetrace_console.pages import render_execution, render_executions
    run = _stored(folder, store)
    pages = dict(render_execution(run, store, generated_at=GENERATED_AT).pages)
    pages["the run list"] = render_executions([store.get_run(run.key)], store, generated_at=GENERATED_AT)
    return store.get_run(run.key), pages


def _the_ending_set_aside(page: str) -> str:
    """`page` with the run's ending, wherever it is drawn, said as one line: it is onetrace-verify's own
    row `the close receipt`, in its words, with the record's value marked (`closing.html`), so a 0.3
    run and its 0.4 twin say it otherwise as the check does."""
    from onetrace_console import closing
    from onetrace_console.words import escape
    out = page
    for words, slot in ((closing.CLOSED, "{ended_by}"), (closing.NOT_CLOSED, "{last}")):
        before, after = (escape(x) for x in words.split(slot, 1))
        out = re.sub(re.escape(before) + r'<span class="mono" data-words="record">[^<]*</span>' + re.escape(after),
                     "<the ending, in the check's words>", out)
    for words in (closing.NOT_CLOSED_UNREAD, closing.CLOSED_UNSTATED):
        out = out.replace(escape(words), "<the ending, in the check's words>")
    return _the_0_4_press_set_aside(out)


#: The press that asks onetrace-verify about an expectations file declared after the run, with no file
#: declared yet: offered on a format 0.4 run only (`expectations_after.FORMATS`), drawn as nothing on a
#: 0.3 run. A section that holds a declared file (its `from` line) is compared as any other.
_PRESS_ONLY = re.compile(r'<section data-section="expectations-after"[^>]*>(?:(?!</section>).)*</section>', re.S)


def _the_0_4_press_set_aside(page: str) -> str:
    return _PRESS_ONLY.sub(lambda m: "" if 'data-expectations-after="from"' not in m.group(0) else m.group(0), page)


def _text(page: str) -> list[str]:
    """A page's text, line by line, with what differs between any two runs made apart said once:
    fingerprints, times, the SDK's version and the format's minor; and the run's ending, the
    check's own words, as one line."""
    t = html.unescape(re.sub(r"<[^>]+>", "\n", _the_ending_set_aside(page)))
    t = re.sub(r"sha256:[0-9a-f]{64}|[0-9a-f]{12,64}", "<digest>", t)
    t = re.sub(r"\d{4}-\d\d-\d\dT[\d:.]+(Z|[+-]\d\d:\d\d)?", "<time>", t)
    t = re.sub(r"(\d{4}-\d\d-\d\d )?\d\d:\d\d:\d\d(\.\d+)?( UTC)?", "<time>", t)
    t = re.sub(r"0\.7\.1|0\.6\.1", "<version>", t)
    t = re.sub(r"(stage-receipt(?:-chain)?)/0\.[34]\b", r"\1/<minor>", t)
    return [ln.strip() for ln in t.splitlines() if ln.strip()]


#: The close receipt's own line in the lists of what was checked: its label, then what it holds.
CLOSE_LINE = re.compile(r"The close receipt$")


def _the_record_or_the_check(line: str) -> bool:
    """A line the record or the check says itself: a receipt as recorded, a size it records, one of
    onetrace-verify's rows or counts, or a line about the close receipt."""
    return (line.startswith(("{", "[PASS", "[NOT-RUN", "[FAIL")) or re.fullmatch(r"(· )?\d+( bytes)?", line) is not None
            or "onetrace-verify's rows" in line or re.fullmatch(r"\d+ pass, \d+ fail, \d+ not-run\s+->\s+\w+", line) is not None
            or re.fullmatch(r"Records agree: \w+ · \d+ of \d+ checks", line) is not None
            or "onetrace-close.json" in line or "the close receipt" in line)


def _without_the_close_line(lines: list[str]) -> list[str]:
    """`lines` less the close receipt's own line in a list of what was checked, which a 0.3 run has
    no receipt for: its label, then its parts (a dash, a count, what it holds, its info mark)."""
    out, inside = [], False
    for ln in lines:
        if CLOSE_LINE.match(ln):
            inside = True
            continue
        if inside and (ln in ("—", "i") or ln.isdigit() or ln.startswith(("checks made", "— "))):
            continue
        inside = False
        out.append(ln)
    return out


def twin_problems(before: list[str], after: list[str]) -> list[str]:
    """Each difference between a 0.3 run's page and its 0.4 twin's that is not the record's or the
    check's own: a line of the console's that reads otherwise."""
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        gone, came = before[i1:i2], _without_the_close_line(after[j1:j2])
        out += [f"0.3 says {ln!r}" for ln in gone if not _the_record_or_the_check(ln)]
        out += [f"0.4 says {ln!r}" for ln in came if not _the_record_or_the_check(ln)]
    return out


def _twins(name: str, tmp_path) -> dict[str, tuple]:
    from onetrace_console.store import Store
    return {v: _pages(RUNS / v / name, Store(tmp_path / v)) for v in ("0.6.1", "0.7.1")}


@pytest.mark.parametrize("name", TWINS)
def test_a_0_4_run_reads_as_its_0_3_twin(name, tmp_path, examined):
    """Every page the console draws for one run, and its row in the run list: the same, but for what
    the record and the check say themselves."""
    twins = _twins(name, tmp_path)
    (old, old_pages), (new, new_pages) = twins["0.6.1"], twins["0.7.1"]
    examined(len(old_pages), f"pages of {name} beside its 0.3 twin")
    assert (old.format, new.format) == ("stage-receipt-chain/0.3", "stage-receipt-chain/0.4")
    assert {k: getattr(new, k) for k in KEPT} == {k: getattr(old, k) for k in KEPT}
    assert sorted(new_pages) == sorted(old_pages)
    assert {p: twin_problems(_text(old_pages[p]), _text(new_pages[p])) for p in old_pages} == {p: [] for p in old_pages}


def test_sabotage_a_console_that_reads_the_close_receipt_as_a_step_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console.viewer import record
    monkeypatch.setattr(record, "is_close", lambda receipt: False)
    twins = _twins("refund-closed", tmp_path)
    (old, old_pages), (new, new_pages) = twins["0.6.1"], twins["0.7.1"]
    examined(1, "closed run, read with no close receipt")
    found = [x for p in old_pages if p in new_pages for x in twin_problems(_text(old_pages[p]), _text(new_pages[p]))]
    assert any("step 1 of 4" in x for x in found), found
    assert new.recorded_count == 4 and old.recorded_count == 3, (new.recorded_count, old.recorded_count)


def test_a_closed_run_s_completeness_is_its_close_receipt_s(tmp_path, examined):
    """No step of a 0.4 run reads `complete`: only its close receipt can. A closed run read off its
    last step, not its last receipt, would read as one with part of it missing."""
    from onetrace_console.viewer.record import read_record
    rec = read_record(RUNS / "0.7.1" / "refund-closed")
    examined(len(rec.receipts), "receipts of a closed 0.4 run")
    assert [s.data["coverage"]["completeness"] for s in rec.steps] == ["incomplete"] * 3
    assert rec.close is not None and rec.close.data["coverage"]["completeness"] == "complete"
    assert [s.manifest_stage for s in rec.steps] == ["intake", "retrieve", "answer"]
    from onetrace_console.store import Store
    run, _ = _pages(RUNS / "0.7.1" / "refund-closed", Store(tmp_path / "s"))
    assert run.nothing_missing == "yes", run.nothing_missing


def test_a_killed_0_4_run_has_no_close_receipt_and_reads_as_a_killed_0_3_run(examined):
    from onetrace_console.viewer.model import missing_stages
    from onetrace_console.viewer.record import read_record
    killed, twin = read_record(RUNS / "0.7.1" / "refund-killed"), read_record(RUNS / "0.6.1" / "refund-killed")
    examined(2, "killed runs")
    assert killed.close is None and len(killed.steps) == 2
    assert missing_stages(killed) == missing_stages(twin) == ("answer",)


def test_only_a_0_4_receipt_of_the_close_instrument_is_a_close_receipt(examined):
    """The format's first reading rule: before 0.4 the name was not reserved, so a stage of that name
    in an earlier run is a step, and so is a 0.4 receipt of another instrument."""
    from onetrace_console.viewer.record import is_close, stage_names
    close = {"format": "stage-receipt/0.4", "instrument": {"id": "onetrace.close", "kind": "close"},
             "coverage": {"declared_stages": ["a", "onetrace.close"]}}
    cases = {
        "0.4, the close instrument": (close, True),
        "0.5, the close instrument": (dict(close, format="stage-receipt/0.5"), True),
        "0.3, the close instrument": (dict(close, format="stage-receipt/0.3"), False),
        "0.4, another kind": (dict(close, instrument={"id": "onetrace.close", "kind": "tool"}), False),
        "0.4, another instrument": (dict(close, instrument={"id": "mine", "kind": "close"}), False),
        "not a receipt": ("onetrace.close", False),
    }
    examined(len(cases), "receipts read for the close")
    assert {k: is_close(r) for k, (r, _) in cases.items()} == {k: want for k, (_, want) in cases.items()}
    assert stage_names(close, "declared_stages") == ["a"]
    assert stage_names(dict(close, format="stage-receipt/0.3"), "declared_stages") == ["a", "onetrace.close"]


@pytest.mark.parametrize("name", ("refund-closed", "refund-raised", "refund-killed", "auto-orders", "auto-bound"))
def test_each_0_4_run_stores_reads_back_and_is_checked_as_holding(name, store, examined):
    from onetrace_console.checks import HOLDS
    run = _stored(RUNS / "0.7.1" / name, store)
    examined(1, f"0.4 run {name} through the store")
    assert run.format == "stage-receipt-chain/0.4"
    assert store.get_run(run.key) == run
    assert run.check_verdict == HOLDS, (run.check_verdict, run.check_exit)


def test_sabotage_a_store_without_0_4_is_named(store, monkeypatch, examined):
    from onetrace_console import ingest
    from onetrace_console.ingest import Rejection, accept
    monkeypatch.setattr(ingest, "MANIFEST_FORMATS", tuple(f for f in ingest.MANIFEST_FORMATS if not f.endswith("/0.4")))
    examined(1, "0.4 run, sabotaged store")
    assert isinstance(accept(_tar(RUNS / "0.7.1" / "refund-closed"), store), Rejection)


#: A count of checks on a run page, as `tests/test_run_panels.py` reads it.
_COUNT = re.compile(r'<span class="value" data-words="value">\d+</span> checks? made — (?:all hold|it holds)\.')


def test_the_close_receipt_s_count_of_checks_has_its_note_as_each_step_s_does(tmp_path, examined):
    """The close receipt's "N checks made" carries the mark each step's does, its note read from
    onetrace-verify's rows about the close receipt's own file."""
    from onetrace_console.store import Store
    _run, pages = _pages(RUNS / "0.7.1" / "refund-closed", Store(tmp_path / "s"))
    drawn = {name: page for name, page in pages.items() if name != "the run list"}
    counts = [(page, m) for page in drawn.values() for m in _COUNT.finditer(page)]
    examined(len(counts), "counts of checks on a closed 0.4 run's pages")
    bare = [page[max(0, m.start() - 120):m.end()] for page, m in counts if not page.startswith('<span class="info"', m.end())]
    assert len(counts) > 1 and bare == [], bare
    assert any("onetrace-verify's rows about receipts/04-onetrace-close.json that held: " in html.unescape(p)
               for p in drawn.values())
