"""An incident page whose run's own page cannot be drawn shows the store's answers, all of them.

`incident_pages.render_incident_page` draws the run page's four answers; where that page cannot be
drawn (`_four_answers` gives ("", {})) it draws the answers the store keeps per run
(`pages.run_answers`) instead, as the lists read them. "Ran as approved" joined those answers with
the runs list's column; the fallback's names did not, so the page raised `KeyError: 'approved'`
and its build logged a traceback in its place. The demo never takes the fallback, so only a run
built to take it shows it.
"""
from __future__ import annotations

import re
from html import unescape

GENERATED_AT = "2026-10-06T12:00:00+00:00"


def _fallback_page(store, monkeypatch):
    import onetrace_console.incident_pages as incident_pages
    from onetrace_console.incidents import derive
    from tests.test_rows_unreadable_console import _broken_rows
    run = _broken_rows(store)
    (incident,) = [i for i in derive(store) if i.subject == run.key and i.rule == "I-CONTRADICTS"]
    monkeypatch.setattr(incident_pages, "_four_answers", lambda run, store, generated_at: ("", {}))
    return incident_pages.render_incident_page(incident, store, generated_at=GENERATED_AT), run, store


def test_the_store_s_answers_include_ran_as_approved_with_its_words(store, monkeypatch):
    from onetrace_console.pages import run_answers
    from onetrace_console.viewer.sentences import template
    page, run, store = _fallback_page(store, monkeypatch)
    strip = page[page.index('data-section="answers"'):]
    strip = strip[:strip.index("</ul>")]
    rungs = re.findall(r'data-head-rung="([^"]+)" data-state="([^"]+)"', strip)
    assert rungs == list(run_answers(run, store).items()), rungs
    assert ("approved", run_answers(run, store)["approved"]) in rungs
    text = unescape(re.sub(r"<[^>]+>", " ", strip))
    assert template("rung.approved") in text


def test_sabotage_a_fallback_without_the_approved_rung_is_caught(store, monkeypatch):
    """The check above, against the strip with "approved" taken out: it must fail."""
    from onetrace_console.pages import run_answers
    page, run, store = _fallback_page(store, monkeypatch)
    sabotaged = re.sub(r'<li data-head-rung="approved".*?</li>', "", page, flags=re.S)
    assert sabotaged != page
    rungs = re.findall(r'data-head-rung="([^"]+)" data-state="([^"]+)"', sabotaged)
    assert rungs != list(run_answers(run, store).items())
