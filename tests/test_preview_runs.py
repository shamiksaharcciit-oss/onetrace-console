"""A preview-format run, checked with the 0.2.0 verifier, is NOT VERIFIED (exit 2): the console
says "Couldn't check", never "doesn't hold", with the fixed one-line reason, and the run stays
stored and viewable. A 0.1-format run checks normally.

Before 0.2.0 this path was not reachable end to end, and the check runner stored such a check with
no reason -- a record the store itself then refused to read back (found by the 0.2.0 probe).
"""
from __future__ import annotations

from onetrace_console.checks import (COULD_NOT_CHECK, HOLDS, PREVIEW_CHAIN_FORMAT, PREVIEW_REASON,
                                     run_and_record)
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_compare import EXAM, RUN_C, _deliver, _require_exam

RULED = ("This run uses the preview record format, which the 0.2.0 verifier doesn't check. "
         "It was recorded before onetrace 0.1.")


def _preview(store):
    _require_installed()
    _require_exam()
    run = run_and_record(_deliver(RUN_C, store), store, ran_at=FIXED_RAN_AT)
    assert run.format == PREVIEW_CHAIN_FORMAT, run.format
    return run


def test_the_reason_is_the_ruled_sentence():
    assert PREVIEW_REASON == RULED


def test_a_preview_run_is_couldnt_check_with_the_ruled_reason_and_stays_readable(store, examined):
    run = _preview(store)
    examined(1, "preview run checked")
    assert run.check_exit == "2", run.check_exit
    assert run.check_verdict == COULD_NOT_CHECK, run.check_verdict
    assert run.check_note == RULED, run.check_note
    again = store.get_run(run.key)       # the record reads back: nothing is deleted or refused
    assert again.check_verdict == COULD_NOT_CHECK and again.check_note == RULED


def test_the_reason_reaches_home_and_the_rung(store, examined):
    from onetrace_console.home import tallies
    from onetrace_console.receipt_page import _agree
    run = _preview(store)
    cnc = next(t for t in tallies(store) if t.slug == "could-not-check")
    examined(2, "places the reason is shown")
    assert cnc.reasons == (RULED,), cnc.reasons
    rung = _agree(run, store)
    assert rung == f"Records agree: couldn't check. {RULED}", rung
    assert "no" not in rung.split(":")[1].split(".")[0], "a preview run must never read as doesn't hold"


# ----------------------------------------------------- a preview run: no incident, no attention

#: The singular for one run; the fixed words for more.
OVERVIEW_LINE = ("1 run uses the preview record format and can't be checked by 0.2.0; it was "
                 "recorded before onetrace 0.1.")


def test_the_overview_line_for_one_and_for_several():
    from onetrace_console.checks import preview_overview_line
    assert preview_overview_line(1) == OVERVIEW_LINE
    assert preview_overview_line(2) == ("2 runs use the preview record format and can't be "
                                        "checked by 0.2.0; they were recorded before onetrace 0.1.")
    assert preview_overview_line(13).startswith("13 runs use the preview record format")


def test_the_overview_shows_the_plural_for_two_preview_runs(store, examined):
    from html import unescape

    from onetrace_console.render import HOME, render_all
    from tests.test_compare import RUN_C_POPPLER24
    _preview(store)
    run_and_record(_deliver(RUN_C_POPPLER24, store), store, ran_at=FIXED_RAN_AT)
    examined(1, "Overview read with two preview runs")
    home = unescape(render_all(store, generated_at="2026-10-06T12:00:00+00:00")[HOME])
    assert ("2 runs use the preview record format and can't be checked by 0.2.0; they were "
            "recorded before onetrace 0.1.") in home


def test_a_preview_run_raises_no_incident_and_needs_no_attention(store, examined):
    from html import unescape

    from onetrace_console.incidents import derive
    from onetrace_console.overview import needs_attention
    from onetrace_console.render import HOME, render_all
    run = _preview(store)
    examined(3, "incident, attention and Overview line checked")
    assert [i for i in derive(store) if i.subject == run.key and i.rule == "I-COULD-NOT-CHECK"] == []
    assert needs_attention(store) == [], needs_attention(store)
    home = unescape(render_all(store, generated_at="2026-10-06T12:00:00+00:00")[HOME])
    assert "No run needs attention by this rule." in home
    assert OVERVIEW_LINE in home, "the Overview's one line for preview runs is missing"


def test_no_overview_line_without_a_preview_run(store, examined):
    from html import unescape

    from onetrace_console.render import HOME, render_all
    _require_installed()
    _require_exam()
    run_and_record(_deliver(EXAM / "dag-r37" / "run_R", store), store, ran_at=FIXED_RAN_AT)
    examined(1, "Overview read")
    home = unescape(render_all(store, generated_at="2026-10-06T12:00:00+00:00")[HOME])
    assert "use the preview record format" not in home


def test_any_other_not_verified_still_raises_and_needs_attention(store, examined):
    """A NOT VERIFIED with another cause -- here a 0.1 run's record carrying exit 2 and the
    check's own summary -- is not exempt: it raises I-COULD-NOT-CHECK and needs attention."""
    from dataclasses import replace

    from onetrace_console.incidents import derive
    from onetrace_console.overview import needs_attention
    _require_installed()
    _require_exam()
    run = run_and_record(_deliver(EXAM / "dag-r37" / "run_R", store), store, ran_at=FIXED_RAN_AT)
    #: With the "Records agree" a NOT VERIFIED check records: couldn't check.
    other = replace(run, check_verdict=COULD_NOT_CHECK, check_exit="2", agree="couldnt-check", agree_why="",
                    check_note="not verified; the check says: 1 pass, 0 fail, 1 not-run  ->  NOT VERIFIED (x)")
    store.put_run(other)
    examined(2, "incident and attention checked")
    assert [i.quoted for i in derive(store)
            if i.rule == "I-COULD-NOT-CHECK" and i.field_path == "check_note"] == [other.check_note]
    assert [k for k, _ in needs_attention(store)] == ["couldnt-check"]


def test_a_0_1_run_checks_normally(store, examined):
    _require_installed()
    _require_exam()
    run = run_and_record(_deliver(EXAM / "dag-r37" / "run_R", store), store, ran_at=FIXED_RAN_AT)
    examined(1, "0.1-format run checked")
    assert run.format != PREVIEW_CHAIN_FORMAT
    assert run.check_exit == "0" and run.check_verdict == HOLDS and run.check_note == "", run
