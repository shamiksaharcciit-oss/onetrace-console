"""A preview-format run, checked with the pinned verifier, is NOT VERIFIED (exit 2): the console
says "Couldn't check", never "doesn't hold", with the fixed one-line reason, and the run stays
stored and viewable. A 0.1-format run checks normally.

The reason names the format, not a verifier version, so it stays true for any version. Runs stored
with the earlier reason, which named a version, are still read as preview runs, and every page
shows the current words for them.

Before 0.2.0 this path was not reachable end to end, and the check runner stored such a check with
no reason -- a record the store itself then refused to read back (found by the 0.2.0 probe).
"""
from __future__ import annotations

from onetrace_console.checks import (COULD_NOT_CHECK, HOLDS, PREVIEW_CHAIN_FORMAT, PREVIEW_REASON,
                                     run_and_record)
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_compare import EXAM, RUN_C, _deliver, _require_exam

RULED = ("This run is in the preview record format (stage-receipt/0.0-preview), and onetrace-verify "
         "does not check that format, so its receipts couldn't be checked.")
#: The reason runs stored before were given, still recognised.
STORED_BEFORE = ("This run uses the preview record format, which the 0.2.0 verifier doesn't check. "
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
OVERVIEW_LINE = ("1 run is in the preview record format (stage-receipt/0.0-preview), and "
                 "onetrace-verify does not check that format, so its receipts couldn't be checked.")
OVERVIEW_LINES = ("{n} runs are in the preview record format (stage-receipt/0.0-preview), and "
                  "onetrace-verify does not check that format, so their receipts couldn't be checked.")


def test_the_overview_line_for_one_and_for_several():
    from onetrace_console.checks import preview_overview_line
    assert preview_overview_line(1) == OVERVIEW_LINE
    assert preview_overview_line(2) == OVERVIEW_LINES.format(n=2)
    assert preview_overview_line(13) == OVERVIEW_LINES.format(n=13)


def test_the_overview_shows_the_plural_for_two_preview_runs(store, examined):
    from html import unescape

    from onetrace_console.render import HOME, render_all
    from tests.test_compare import RUN_C_POPPLER24
    _preview(store)
    run_and_record(_deliver(RUN_C_POPPLER24, store), store, ran_at=FIXED_RAN_AT)
    examined(1, "Overview read with two preview runs")
    home = unescape(render_all(store, generated_at="2026-10-06T12:00:00+00:00")[HOME])
    assert OVERVIEW_LINES.format(n=2) in home


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
    assert "preview record format" not in home


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


# ----------------------------------------------------- the words: no version named

def test_no_preview_sentence_names_a_version(examined):
    import re

    from onetrace_console.checks import preview_overview_line
    from onetrace_console.preview import PREVIEW_NOT_INGESTED
    said = [PREVIEW_REASON, preview_overview_line(1), preview_overview_line(2), PREVIEW_NOT_INGESTED]
    examined(len(said), "sentences")
    for s in said:
        assert re.search(r"\b\d+\.\d+\.\d+\b|\b0\.\d\b", s.replace("0.0-preview", "")) is None, s
        assert "stage-receipt/0.0-preview" in s and "onetrace-verify does not check that format" in s, s


# ----------------------------------------------------- a store written with the earlier reason

def _stored_before(store):
    """The preview run as a store written before kept it: the same run, its reason the earlier one."""
    from dataclasses import replace
    run = replace(_preview(store), check_note=STORED_BEFORE)
    store.put_run(run)
    return store.get_run(run.key)


def test_a_run_stored_with_the_earlier_reason_is_still_a_preview_run(store, examined):
    from html import unescape

    from onetrace_console.checks import is_preview_not_verified
    from onetrace_console.incidents import derive
    from onetrace_console.overview import needs_attention
    from onetrace_console.render import HOME, render_all
    run = _stored_before(store)
    examined(4, "recognition, incident, attention and Overview line")
    assert run.check_note == STORED_BEFORE, "the stored reason is left as it was written"
    assert is_preview_not_verified(run)
    assert [i for i in derive(store) if i.subject == run.key and i.rule == "I-COULD-NOT-CHECK"] == []
    assert needs_attention(store) == [], needs_attention(store)
    home = unescape(render_all(store, generated_at="2026-10-06T12:00:00+00:00")[HOME])
    assert OVERVIEW_LINE in home


def test_a_run_stored_with_the_earlier_reason_shows_the_current_words(store, examined):
    from html import unescape

    from onetrace_console.home import tallies
    from onetrace_console.receipt_page import _agree
    from onetrace_console.render import HOME, render_all
    run = _stored_before(store)
    cnc = next(t for t in tallies(store) if t.slug == "could-not-check")
    rung = _agree(run, store)
    home = unescape(render_all(store, generated_at="2026-10-06T12:00:00+00:00")[HOME])
    examined(3, "places the reason is shown")
    assert cnc.reasons == (RULED,), cnc.reasons
    assert rung == f"Records agree: couldn't check. {RULED}", rung
    assert "0.2.0" not in home and STORED_BEFORE not in home


def test_another_reason_naming_the_preview_format_is_not_recognised(store, examined):
    """Recognised by the two fixed sentences only, nothing wider."""
    from dataclasses import replace

    from onetrace_console.checks import is_preview_not_verified
    run = _preview(store)
    examined(2, "reasons")
    assert not is_preview_not_verified(replace(run, check_note=STORED_BEFORE + " "))
    assert not is_preview_not_verified(replace(run, check_note="This run uses the preview record format."))


def _receipt_page_text(run, store) -> str:
    import html
    import re

    from onetrace_console.pages import render_execution
    page = render_execution(run, store, generated_at="2026-10-06T12:00:00+00:00").pages["receipt.html"]
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def test_the_run_s_receipt_page_shows_the_reason(store, examined):
    text = _receipt_page_text(_preview(store), store)
    examined(1, "receipt page")
    assert f"Records agree: couldn't check. {RULED}" in text


def test_the_receipt_page_of_a_run_stored_with_the_earlier_reason_shows_the_current_words(store, examined):
    text = _receipt_page_text(_stored_before(store), store)
    examined(1, "receipt page")
    assert f"Records agree: couldn't check. {RULED}" in text
    assert STORED_BEFORE not in text and "0.2.0" not in text
