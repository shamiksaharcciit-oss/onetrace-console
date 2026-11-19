"""Format 0.5's expectations checked during the run on a run's page (`expectations`): beside each of the verifier's
rows, what the record says was checked as the step returned, its mode and reader; a batch's "failed N of M"; both
shown where they differ, the verifier's the one that counts; the run's stop row; and a run stopped by an expectation
reading its ending as the check prints it. Each present, absent, not kept and failed, on `tests/format_05_expect/`."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from tests.test_format_05_agents_runs import _verify
from tests.test_step_kinds import _pages, _text

HERE = Path(__file__).resolve().parent / "format_05_expect"
RECORDED = ("expect-record", "expect-stop")


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _section(pages: dict[str, str]) -> str:
    m = re.search(r'<section data-section="expectations".*?</section>', pages["case.html"] + pages["proof.html"], re.S)
    return m.group(0) if m else ""


def _items(section: str) -> dict[str, str]:
    return {
        _text(m.group(2)): _text(m.group(0))
        for m in re.finditer(
            r'<li data-expectation="([^"]+)">.*?<span data-words="check">(.*?)</span>.*?</li>', section, re.S
        )
    }


def test_every_file_is_the_one_its_provenance_names_and_each_run_reads_as_made(examined):
    said = {}
    for line in (HERE / "PROVENANCE.md").read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"- `((?:accept|reject)/[^`]+)`: `sha256:([0-9a-f]{64})`", line.strip())
        if m:
            said[m.group(1)] = m.group(2)
    have = {
        p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for d in ("accept", "reject")
        for p in (HERE / d).rglob("*")
        if p.is_file()
    }
    made = json.loads((HERE / "MADE.json").read_text(encoding="utf-8"))
    examined(len(have) + 2, "vector files and recorded runs")
    assert have and have == said
    assert made["versions"]["onetrace"] == "0.8.0" and sorted(made["runs"]) == sorted(RECORDED)
    assert _verify(HERE / "expect-record") == (1, "FAIL", ["expect score.low"])
    assert _verify(HERE / "expect-stop") == (1, "FAIL", ["expect score.low"])


def test_present_each_row_with_what_was_checked_during_the_run_and_a_batch_s_count(tmp_path, examined):
    from onetrace_console.expectations import CHECKED, CHECKED_NON_CLAIMS, DIFFERS
    from onetrace_console.step_kinds import prose

    section = _section(_pages(HERE / "expect-record", tmp_path))
    items = _items(section)
    examined(len(items), "expectations")
    assert sorted(items) == ["expect score.low", "expect score.ok", "score.scores batch"]
    assert f"{CHECKED}: PASS · record · read by onetrace-verify 0.8.0 — 9 within [0, 500]" in items["expect score.ok"]
    assert f"{CHECKED}: FAIL · record" in items["expect score.low"]
    assert "failed 2 of 4" in items["score.scores batch"]
    assert DIFFERS not in section and prose(CHECKED_NON_CLAIMS) in section


def test_a_run_stopped_by_an_expectation_reads_its_ending_as_the_check_prints_it(tmp_path, examined):
    pages = _pages(HERE / "expect-stop", tmp_path)
    head = re.search(r'<section data-section="run-head">.*?</section>', pages["proof.html"], re.S).group(0)
    examined(2, "the stopped run's head and its expectations")
    assert "closed: by unhandled exception: ExpectationStopped at score: expect low: 9 is outside [0, 5]" in _text(head)
    assert "[PASS ] the run's stop -- stopped at score: expect low" in _text(_section(pages))


def test_where_the_written_outcome_differs_both_are_shown_and_the_verifier_s_counts(tmp_path, examined):
    from onetrace_console.expectations import DIFFERS

    items = _items(_section(_pages(HERE / "reject" / "R107-batch-outcome-against-count", tmp_path)))
    examined(1, "a batch written PASS that the verifier reads FAIL")
    row = items["s.scores batch"]
    assert row.startswith("FAIL s.scores batch") and "Checked during the run: PASS" in row and DIFFERS in row


def test_not_kept_the_written_result_stands_beside_the_verifier_s_not_run(tmp_path, examined):
    from onetrace_console.expectations import CHECKED_NON_CLAIMS, DIFFERS
    from onetrace_console.step_kinds import prose

    section = _section(_pages(HERE / "accept" / "A67-expect-not-kept", tmp_path))
    row = _items(section)["expect s.low"]
    examined(1, "an expectation on a run that kept no outputs")
    assert row.startswith("NOT-RUN expect s.low — the output was not kept")
    assert "<the value is not kept> is outside [0, 5]" in row and DIFFERS in row
    assert "the result written during the run cannot be re-read" in _text(prose(CHECKED_NON_CLAIMS))


def test_absent_an_expectation_not_checked_during_the_run_gets_no_such_line(tmp_path, examined):
    from onetrace_console.expectations import CHECKED

    section = _section(_pages(HERE / "accept" / "A72-expect-off-identical", tmp_path))
    examined(1, "expectations checked after the run only")
    assert section and CHECKED not in section and 'data-expectations="checked-non-claims"' not in section


def test_malformed_the_verifier_s_fail_on_a_count_or_a_stop_is_shown_as_it_wrote_it(tmp_path, examined):
    counts = _section(_pages(HERE / "reject" / "R105-batch-count-differs", tmp_path / "c"))
    stop = _section(_pages(HERE / "reject" / "R104-stop-not-stopped", tmp_path / "s"))
    examined(2, "a batch whose count differs, and a stop that did not stop")
    row = _items(counts)["s.scores batch"]
    assert "written 1 of 4 by onetrace-verify 0.7.1, read 2 of 4 by onetrace-verify 0.9.0" in row
    assert "failed 1 of 4" in row
    assert "[FAIL ] the run's stop -- expect low read FAIL in stop at s, and the run ended by 'exit'" in _text(stop)


def test_sabotage_a_page_that_drops_what_was_checked_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import expectations

    monkeypatch.setattr(expectations, "_checked", lambda r: "")
    section = _section(_pages(HERE / "expect-record", tmp_path))
    examined(1, "a page drawn without what was checked during the run")
    assert expectations.CHECKED not in section
