"""Format 0.5, as onetrace 0.8 writes it: stored, checked and drawn, beside the same runs written in 0.4.

The store takes format 0.5 (`ingest.MANIFEST_FORMATS`, `ingest.RECEIPT_FORMATS`) because onetrace 0.8 writes it
and onetrace-verify 0.8 reads it. Its new members are shown as the check's own rows say them; nothing here reads
them from the receipts. Every earlier format is taken as before (`tests/test_format_04.py`,
`tests/test_format_03.py`).

The runs are `tests/onetrace_runs/0.8.0/` (`tests/test_onetrace_runs.py`), each beside its 0.7.1 twin. A closed
run and a raised one read as their twins do, but for what the record and the check say themselves. The killed
run does not have a twin in that sense: in 0.5 a later process recovered it (a `close-recovered` receipt), so it is
held here only to be stored and checked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.test_format_04 import KEPT, _pages, _stored, _tar, twin_problems
from tests.test_format_04 import _text as _text_0_4

RUNS = Path(__file__).resolve().parent / "onetrace_runs"
#: The 0.8.0 runs that end as their 0.7.1 twins end.
TWINS = ("refund-closed", "refund-raised")
ALL = ("refund-closed", "refund-raised", "refund-killed", "auto-orders", "auto-bound")
#: The 0.8.0 runs whose check prints, after its summary, what a format 0.5 section's members do not show.
SECTIONED = ("refund-killed", "auto-orders", "auto-bound")


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


#: What a 0.5 run's pages draw of format 0.5's own members, which its 0.4 twin cannot hold: held by
#: `tests/test_step_kinds.py`, set aside here.
_FORMAT_05_ONLY = re.compile(
    r'<section data-section="step-kind".*?</section>|<p class="sub" data-section="run-agent".*?</p>'
    r'|<div data-section="run-agent".*?</div>|<div class="step" data-step-kind[^>]*>.*?</div>'
    r'|<span[^>]* data-kinds="[^"]*">.*?</span>'
    r'|<section data-section="store-state">.*?</section>|<p class="sub" data-section="state-at-open".*?</p>'
    r'|<div data-section="state-at-open".*?</div>'
    r'|<section data-section="code">.*?</section>|<p class="sub" data-section="rerun-parts".*?</p>',
    re.S,
)


def _text(page: str) -> list[str]:
    """`test_format_04`'s reading of a page, with onetrace 0.8.0's version and format 0.5's minor said as 0.7.1's
    and 0.4's are, and what is drawn of format 0.5's own members set aside."""
    page = _FORMAT_05_ONLY.sub("", page)
    page = re.sub(r"0\.8\.0", "0.7.1", page)
    page = re.sub(r"(stage-receipt(?:-chain)?)/0\.5\b", r"\1/0.4", page)
    return _text_0_4(page)


@pytest.mark.parametrize("name", ALL)
def test_each_0_5_run_stores_reads_back_and_is_checked_as_holding(name, store, examined):
    from onetrace_console.checks import HOLDS

    run = _stored(RUNS / "0.8.0" / name, store)
    examined(1, f"0.5 run {name} through the store")
    assert run.format == "stage-receipt-chain/0.5"
    assert store.get_run(run.key) == run
    assert run.check_verdict == HOLDS, (run.check_verdict, run.check_exit)


@pytest.mark.parametrize("name", TWINS)
def test_a_0_5_run_reads_as_its_0_4_twin(name, tmp_path, examined):
    """Every page the console draws for one run, and its row in the run list: the same, but for what the record
    and the check say themselves."""
    from onetrace_console.store import Store

    (old, old_pages), (new, new_pages) = (_pages(RUNS / v / name, Store(tmp_path / v)) for v in ("0.7.1", "0.8.0"))
    examined(len(old_pages), f"pages of {name} beside its 0.4 twin")
    assert (old.format, new.format) == ("stage-receipt-chain/0.4", "stage-receipt-chain/0.5")
    assert {k: getattr(new, k) for k in KEPT} == {k: getattr(old, k) for k in KEPT}
    assert sorted(new_pages) == sorted(old_pages)
    assert {p: twin_problems(_text(old_pages[p]), _text(new_pages[p])) for p in old_pages} == {p: [] for p in old_pages}


def test_sabotage_a_store_without_0_5_is_named(store, monkeypatch, examined):
    from onetrace_console import ingest
    from onetrace_console.ingest import Rejection, accept

    monkeypatch.setattr(ingest, "MANIFEST_FORMATS", tuple(f for f in ingest.MANIFEST_FORMATS if not f.endswith("/0.5")))
    examined(1, "0.5 run, sabotaged store")
    assert isinstance(accept(_tar(RUNS / "0.8.0" / "refund-closed"), store), Rejection)


def test_a_0_5_run_is_checked_again_with_every_required_stage_asked_for(examined):
    """`checks.COMPLETENESS_FORMATS` names the chains whose check runs again with `--require-complete`. 0.5 is
    one: onetrace-verify 0.8 reads a closed 0.5 run as complete off its close receipt, as it reads a 0.4 run."""
    from onetrace_console.checks import check

    envelope = check(RUNS / "0.8.0" / "refund-closed", ran_at="2026-09-26T12:00:00+02:00").envelope
    examined(1, "the check envelope of a closed 0.5 run")
    assert "completeness_required" in envelope
    said = envelope["completeness_required"]
    rows = [r for r in json.loads(said["stdout"])["rows"] if r.get("name") == "run complete"]
    assert said["exit_status"] == "0", said["exit_status"]
    assert rows == [
        {"detail": "the last receipt says every declared stage emitted", "name": "run complete", "result": "PASS"}
    ]


def test_sabotage_a_completeness_list_without_0_5_is_named(monkeypatch, examined):
    from onetrace_console import checks

    monkeypatch.setattr(checks, "COMPLETENESS_FORMATS", ("stage-receipt-chain/0.3", "stage-receipt-chain/0.4"))
    examined(1, "the check envelope of a closed 0.5 run, sabotaged")
    envelope = checks.check(RUNS / "0.8.0" / "refund-closed", ran_at="2026-09-26T12:00:00+02:00").envelope
    assert "completeness_required" not in envelope


@pytest.mark.parametrize("version", ("0.7.1", "0.8.0"))
def test_a_0_5_run_is_offered_and_checked_against_an_expectations_file_as_a_0_4_run_is(version, store, examined):
    """`expectations_after.FORMATS` names the runs the press is offered on. 0.5 is one: onetrace-verify 0.8 reads a
    0.5 run checked with `--expectations` as it reads a 0.4 run, the same rows for the same file."""
    from onetrace_console import expectations_after
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.pages import render_execution

    expect = RUNS / version / "expect"
    run = run_and_record(accept(_tar(expect / "calibrate-holds"), store).run, store, ran_at="2026-09-26T12:00:00+02:00")
    pages = render_execution(store.get_run(run.key), store, generated_at="2026-10-04T12:00:00+00:00").pages
    examined(1, f"the {version} expectation run, offered and checked")
    assert expectations_after.PRESS in pages["case.html"]
    entry = expectations_after.check(store, run, str(expect / "after-the-run.json"))
    assert [(r["name"].split(" (")[0], r["result"]) for r in entry["rows"]] == [
        ("expectations file", "PASS"),
        ("expect calibrate.after-under-450", "PASS"),
        ("expect calibrate.after-serial", "FAIL"),
        ("expect missing.after-missing-step", "FAIL"),
    ]


def test_the_console_s_section_leads_are_the_installed_verifier_s_in_its_order(examined):
    """The lines after the summary that say what a format 0.5 section's members do not show: each begins with its
    section's lead, the verifier's own constant, and they come in the order the verifier writes them."""
    from onetrace_verify import format05

    from onetrace_console.viewer.report import FORMAT_05_LEADS

    theirs = tuple(
        getattr(format05, f"{name}_LEAD")
        for name in (
            "STATE_NON_CLAIM",
            "NON_CLAIM",
            "MESSAGE_NON_CLAIM",
            "MODEL_NON_CLAIM",
            "FRAMEWORK_NON_CLAIM",
            "LINK_NON_CLAIM",
            "WRITER_NON_CLAIM",
            "EXPECT_NON_CLAIM",
            "RERUN_FROM_NON_CLAIM",
            "CONFIRMATION_NON_CLAIM",
        )
    )
    examined(len(theirs), "section leads")
    assert FORMAT_05_LEADS == theirs


def _envelope(name: str) -> dict:
    from onetrace_console.checks import check

    return dict(check(RUNS / "0.8.0" / name, ran_at="2026-09-26T12:00:00+02:00").envelope)


@pytest.mark.parametrize("name", SECTIONED)
def test_a_0_5_check_s_section_lines_are_read_and_its_rows_kept(name, examined):
    from onetrace_console.viewer.report import FORMAT_05_LEADS, parse

    envelope = _envelope(name)
    said = [ln for ln in envelope["stdout"].splitlines() if ln.startswith(FORMAT_05_LEADS)]
    report = parse(envelope)
    examined(len(said), f"section lines after {name}'s summary")
    assert said and report.rows_readable and report.overall == "pass"
    assert report.output == envelope["stdout"], "the check's text is kept whole, as it said it"


def _planted(envelope: dict, stdout: str) -> dict:
    return dict(envelope, stdout=stdout)


@pytest.mark.parametrize(
    "how",
    ["a line with no lead", "a lead's line changed", "two lines swapped", "a line the --json does not hold"],
)
def test_sabotage_a_section_line_the_verifier_did_not_write_is_refused(how, examined):
    from onetrace_console.viewer.report import FORMAT_05_LEADS, ReportUnreadable, parse

    envelope = _envelope("auto-orders")
    lines = envelope["stdout"].splitlines()
    at = [i for i, ln in enumerate(lines) if ln.startswith(FORMAT_05_LEADS)]
    assert len(at) >= 2, "the run's check names two sections or more"
    if how == "a line with no lead":
        lines.append("this run is correct")
    elif how == "a lead's line changed":
        lines[at[0]] = lines[at[0]] + "; and nothing else"
    elif how == "two lines swapped":
        lines[at[0]], lines[at[1]] = lines[at[1]], lines[at[0]]
    else:
        lines.insert(at[-1] + 1, FORMAT_05_LEADS[-1] + "that the run was approved")
    examined(1, how)
    with pytest.raises(ReportUnreadable):
        parse(_planted(envelope, "\n".join(lines) + "\n"))
