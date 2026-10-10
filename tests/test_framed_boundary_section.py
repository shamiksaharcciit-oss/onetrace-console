"""In the console, the run page's boundary section is dropped in the console's frame.

    "Incidents" on the run page: in the console's frame, dropped -- the run page already lists this
    run's incidents at the top, and the Incidents page covers the rest. In the free file, retitled
    "Where the record stops", keeping its sentence.

The console serves every page inside `frame.rendering(...)`; a page drawn outside it is drawn as the
viewer draws the free file.
"""
from __future__ import annotations

from onetrace_console.frame import rendering
from onetrace_console.pages import CASE, render_execution
from tests.test_run_page_marks import runs  # noqa: F401

GENERATED_AT = "2026-10-04T12:00:00+00:00"


def test_the_served_run_page_has_no_boundary_section(runs, examined):  # noqa: F811
    found, store = runs
    examined(len(found), "stored runs, their case pages served in the frame")
    for run in found.values():
        with rendering(onedoor=False, sign_in=False):
            served = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
        assert 'data-section="incidents"' not in served, run.run_id
        assert "Where the record stops" not in served and "<h2>Incidents</h2>" not in served


def test_outside_the_frame_the_page_is_the_free_file_s(runs):  # noqa: F811
    found, store = runs
    free = render_execution(found["R"], store, generated_at=GENERATED_AT).pages[CASE]
    assert 'data-section="incidents"' in free and "Where the record stops" in free
