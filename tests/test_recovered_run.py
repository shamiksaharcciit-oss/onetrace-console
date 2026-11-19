"""A run a later process recovered (format 0.5, a close receipt of kind `close-recovered`): its head reads "recovered
by a later process", in the console's words, beside the check's own row on the close receipt, which stays the
authority. A run that closed itself, and one in an earlier format, read as before."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_step_kinds import _pages, _text

RUNS = Path(__file__).resolve().parent / "onetrace_runs"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _head(pages: dict[str, str]) -> str:
    m = re.search(r'<section data-section="run-head">.*?</section>', pages["proof.html"], re.S)
    return m.group(0) if m else ""


def test_a_recovered_run_reads_recovered_by_a_later_process_beside_the_check_s_row(tmp_path, examined):
    from onetrace_console.closing import RECOVERED

    head = _head(_pages(RUNS / "0.8.0" / "refund-killed", tmp_path))
    examined(1, "a run a later process recovered")
    assert f"{RECOVERED} ( [PASS ] the close receipt -- recovered: last confirmed retrieve )" in _text(head)
    assert "not closed" not in _text(head)


def test_a_run_that_closed_itself_and_an_earlier_format_read_as_before(tmp_path, examined):
    from onetrace_console.closing import RECOVERED

    closed = _head(_pages(RUNS / "0.8.0" / "refund-closed", tmp_path / "c"))
    older = _head(_pages(RUNS / "0.7.1" / "refund-closed", tmp_path / "o"))
    examined(2, "a run that closed itself, and its format 0.4 twin")
    assert "closed: by exit" in _text(closed) and RECOVERED not in _text(closed)
    assert "closed: by exit" in _text(older) and RECOVERED not in _text(older)


def test_sabotage_a_head_that_drops_the_check_s_row_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import closing

    monkeypatch.setattr(closing, "CLOSE_ROW", "no such row")
    head = _head(_pages(RUNS / "0.8.0" / "refund-killed", tmp_path))
    examined(1, "a recovered run's head drawn without the check's row")
    assert "last confirmed retrieve" not in _text(head)
