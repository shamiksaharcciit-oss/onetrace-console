"""The preview banner, in the console's frame, says what its trigger knows.

    "Sample" isn't true of these runs. Fixed words, in the console's frame: "This record is in a
    preview format ({format})." The format is read from the manifest. The free file's own
    wording goes to the next work order with the viewer changes.

The viewer draws its banner when the manifest's format ends in `-preview`; that says what format
the record is in, not where it came from. A run the console stores is a run, not a sample.
The free file was given the same words, so since canary 64c4026 the viewer draws them
itself, on every page, and the console no longer replaces its banner.
"""
from __future__ import annotations

import re

from onetrace_console.pages import ANSWER, CASE, render_execution
from tests.test_checks import _require_installed
from tests.test_home_and_diff import EXAM, GENERATED_AT, _deliver, _require_exam

SAMPLE = "Generated from a preview sample record, not from a production run."
BANNER = re.compile(r'<p class="sample"[^>]*>([^<]*)</p>')


def _pages(folder, store):
    from onetrace_console.checks import run_and_record
    run = run_and_record(_deliver(folder, store), store)
    return run, render_execution(run, store, generated_at=GENERATED_AT).pages


def test_a_preview_runs_pages_say_its_format_and_not_sample(store, examined):
    _require_installed()
    _require_exam()
    run, pages = _pages(EXAM / "ingest-r1" / "run_B", store)
    assert run.format.endswith("-preview"), run.format
    examined(2, "run pages of a preview run (case and answer)")
    for name in (CASE, ANSWER):
        assert BANNER.findall(pages[name]) == [
            f"This record is in a preview format ({run.format})."], name
        assert SAMPLE not in pages[name] and "sample record" not in pages[name], name


def test_a_run_not_in_a_preview_format_has_no_banner(store, examined):
    _require_installed()
    _require_exam()
    run, pages = _pages(EXAM / "dag-r37" / "run_R", store)
    assert not run.format.endswith("-preview"), run.format
    examined(2, "run pages of a non-preview run")
    for name in (CASE, ANSWER):
        assert not BANNER.findall(pages[name]), name


def test_the_free_viewer_file_says_the_same(examined):
    """The free file in the same fixed words, drawn by the viewer itself."""
    _require_exam()
    from onetrace_console.viewer.model import build_model
    from onetrace_console.viewer.page import render_case
    from onetrace_console.viewer.record import read_record
    page = render_case(build_model(read_record(EXAM / "ingest-r1" / "run_B"), None, GENERATED_AT,
                                   own_check=False), "case.html")
    examined(1, "free case page of a preview run")
    assert BANNER.findall(page) == ["This record is in a preview format (stage-receipt-chain/0.0-preview)."]
    assert SAMPLE not in page
