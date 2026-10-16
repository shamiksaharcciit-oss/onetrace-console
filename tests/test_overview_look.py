"""The Overview in v6 board 1's look, and the All counts page.

Board 1's source HTML is the authority for the look. What these tests hold is what the look must
not change and what it must carry: the four cards in one grid; what the evidence establishes beside
what needs attention first; each pill's colour from the state it stands for, never from its
words; the large figure being the count its sentence opens with, inside that same sentence; and
the page rules reaching only the pages that carry `.cp`. That the text is unchanged is
`tests/test_visible_text.py`'s, and every count opening exactly what it counted is
`tests/test_home_and_diff.py`'s.
"""
from __future__ import annotations

import re
from html import unescape

from onetrace_console.render import COUNTS, HOME, render_all
from tests.test_home_and_diff import GENERATED_AT, ten_runs  # noqa: F401
from tests.test_overview import _section, _text


def _pages(ten_runs):
    store, _ = ten_runs
    return store, render_all(store, generated_at=GENERATED_AT)


def test_the_overview_is_board_1_s_layout(ten_runs, examined):
    _, pages = _pages(ten_runs)
    home = pages[HOME]
    main = home[home.index("<main>"):home.index("</main>")]
    assert '<div class="cp">' in main and main.count('class="cp"') == 1
    cards = re.findall(r'<div data-card="([^"]+)">', _section(home, "cards"))
    assert cards == ["runs", "records-agree", "changed-vs-baseline", "incidents"]
    panels = re.search(r'<div class="panels">(.*?)</div>\s*<section data-section="recent-runs"',
                       home, re.S)
    assert panels, "no panels row before the recent runs"
    inside = re.findall(r'<section data-section="([^"]+)"', panels.group(1))
    assert inside == ["evidence", "needs-attention"], inside
    order = re.findall(r'data-section="(cards|evidence|needs-attention|recent-runs|pipelines|'
                       r'by-day|all-counts)"', home)
    assert order == ["cards", "evidence", "needs-attention", "recent-runs", "pipelines",
                     "by-day", "all-counts"], order
    examined(len(order), "Overview blocks placed")


def test_each_card_leads_with_one_short_line_and_keeps_its_denominator(ten_runs, examined):
    """Each card opens with its count in one short line, the count set large; what the count rests
    on is said in the card's muted lines below it, word for word as it was, so nothing is lost.
    Every count still says what it is out of."""
    from onetrace_console.home import tallies
    from onetrace_console.incidents import derive
    from onetrace_console.overview import pipelines
    store, pages = _pages(ten_runs)
    home = pages[HOME]
    leads = dict(re.findall(r'<div data-card="([^"]+)"><h3>[^<]*</h3><p class="lead"><a [^>]*>'
                            r'(.*?)</a>', home, re.S))
    examined(len(leads), "cards")
    by = {t.slug: t for t in tallies(store)}
    total, found, every = len(store.runs()), len(pipelines(store)), derive(store)
    raised_from = len({i.subject for i in every if i.subject_kind == "run"})
    unit = "run" if total == 1 else "runs"
    expected = {
        "runs": f"{total} {unit} stored",
        "records-agree": f"{len(by['records-agree'].runs)} of {total} {unit} whose records agree",
        "changed-vs-baseline": f"{len(by['changed-vs-baseline'].runs)} of {total} {unit} changed vs baseline",
        "incidents": f"{len(every)} incident{'' if len(every) == 1 else 's'}",
    }
    #: What each lead used to say beyond its count: now in the card's muted lines, as it was.
    kept = {
        "runs": f"in {found} pipeline{'' if found == 1 else 's'}",
        "records-agree": "the check held, with the run's output files present",
        "changed-vs-baseline": "Changed: the run was the candidate in a stored comparison that found a first difference.",
        "incidents": f"raised from {raised_from} of {total} {unit}",
    }
    assert set(leads) == set(expected)
    for name, lead in leads.items():
        kpi = re.fullmatch(r'<span class="kpi">([^<]*)</span><span class="of">([^<]*)</span>', lead)
        assert kpi, (name, lead)
        assert re.fullmatch(r"\d[\d,]*", kpi.group(1)), (name, kpi.group(1))
        #: Joined with nothing between, the two spans are the line, character for character.
        said = unescape(kpi.group(1) + kpi.group(2))
        assert said == expected[name], (name, said)
        assert len(said) <= 32, f"{name}'s lead is not one short line: {said!r}"
        card = re.search(rf'<div data-card="{name}">(.*?)</div>', home, re.S).group(1)
        muted = " ".join(unescape(re.sub(r"<[^>]+>", "", m)) for m in re.findall(r"<p>(.*?)</p>", card, re.S))
        assert kept[name] in muted, (name, muted)


def test_each_pill_s_colour_comes_from_the_state_it_stands_for(ten_runs, examined, monkeypatch):
    from onetrace_console import home as home_module
    from onetrace_console.checks import CONTRADICTS, COULD_NOT_CHECK, HOLDS
    from onetrace_console import records
    from onetrace_console.overview import ATTENTION_WORDS, vs_baseline
    from onetrace_console.render import ATTENTION_TONE, BASELINE_TONE
    #: Every run in the recent-runs table, so every comparison state the fixture holds is read,
    #: whichever five arrived last.
    monkeypatch.setattr(home_module, "MOST_RECENT", len(ten_runs[0].runs()))
    store, pages = _pages(ten_runs)
    home = pages[HOME]
    #: Every reason a run can need attention, and every comparison state, has a tone.
    assert set(ATTENTION_TONE) == set(ATTENTION_WORDS)
    assert set(BASELINE_TONE) == {"same", "changed", "couldnt-check", "not-compared"}
    assert ATTENTION_TONE["contradicts"] == "bad" and ATTENTION_TONE["changed"] == "neu"
    #: By the one rule (tones.py): a check that couldn't be done, or wasn't, is amber; a stage
    #: found missing is a check that failed, red; a change is no fault, neutral.
    assert ATTENTION_TONE["couldnt-check"] == BASELINE_TONE["couldnt-check"] == "cc"
    assert ATTENTION_TONE["missing-stage"] == "bad"
    assert BASELINE_TONE["couldnt-check"] != BASELINE_TONE["changed"]
    assert ATTENTION_TONE["not-checked"] == "cc"
    items = re.findall(r'<li data-attention="([^"]+)">(.*?)</li>',
                       _section(home, "needs-attention"), re.S)
    assert items, "the fixture needs a run needing attention"
    for kind, html in items:
        pill = re.search(r'<span class="pill (\w+)">([^<]*)</span>', html)
        assert (pill.group(1), unescape(pill.group(2))) == (ATTENTION_TONE[kind],
                                                            ATTENTION_WORDS[kind]), (kind, html)
    rows = dict(re.findall(r'<tr data-recent="([^"]+)">(.*?)</tr>', home, re.S))
    from onetrace_console import tones
    states = set()
    for run in store.runs():
        if run.key not in rows:
            continue
        pills = [(tone, unescape(words)) for tone, words in
                 re.findall(r'<span class="pill (\w+)">([^<]*)</span>', rows[run.key])]
        state, words = vs_baseline(run, store)
        states.add(state)
        assert pills[0] == (BASELINE_TONE[state], words), (run.run_id, pills)
        assert pills[1] == (tones.tone(tones.RUNG, records.state(run, store)),
                            records.said(run, store)), (run.run_id, pills)
    examined(len(items) + len(rows), "pills read")
    assert len(rows) == len(store.runs())
    assert len(states) >= 2, f"the fixture holds one comparison state only: {states}"


def test_the_all_counts_page_is_one_link_from_the_overview_and_carries_every_count(ten_runs):
    from onetrace_console.home import incident_tallies, tallies
    store, pages = _pages(ten_runs)
    assert re.search(rf'<a href="{COUNTS}">All counts</a>', pages[HOME])
    page = pages[COUNTS]
    assert "<h1>All counts</h1>" in page and '<div class="cp">' in page
    slugs = re.findall(r'<li data-tally="([^"]+)">', page)
    assert slugs == [t.slug for t in tallies(store) + incident_tallies(store)]


def test_the_console_page_rules_reach_only_the_pages_that_carry_cp():
    """Scoped, so no other page moves with this part; and in the skin's tokens only."""
    from onetrace_console.frame import PAGE_CSS, stylesheet
    assert PAGE_CSS in stylesheet().decode("utf-8")
    rules = re.findall(r"([^{}]+)\{[^{}]*\}", PAGE_CSS)
    assert len(rules) > 20
    for selectors in rules:
        #: Split on the commas between selectors, not those inside an `:is(...)`.
        for selector in re.split(r",(?![^()]*\))", selectors):
            selector = selector.strip()
            assert selector.startswith(".cp") or selector.startswith(".shell>main:has(>.cp)"), (
                selector)
    sizes = set(re.findall(r"font-size:([^;}]+)", PAGE_CSS))
    #: Board 1's sizes: its tokens, and 15px (the panels' headings and "of N"), which the skin
    #: has no token for.
    assert sizes <= {"var(--fs-h1)", "var(--fs-kpi)", "var(--fs-nav)", "var(--fs-body)",
                     "var(--fs-small)", "15px"}, sizes


def test_the_all_counts_page_is_served_under_overview(server):
    import urllib.request
    base, _ = server
    with urllib.request.urlopen(base + "/counts.html") as resp:
        page = resp.read().decode("utf-8")
    assert "<h1>All counts</h1>" in page
    current = re.findall(r'<a href="([^"]+)" aria-current="page">([^<]*)</a>', page)
    assert [label for _, label in current] == ["Overview"], current


def test_every_page_the_console_draws_carries_the_skin_and_no_viewer_page_does(ten_runs, examined):
    """`.cp` is on the console's own pages (Overview, All counts, Incidents and each rule's list,
    Comparisons, and each compare page), once each, wrapping the whole page; the viewer's pages (each run's, and the
    lists of runs) are not restyled by it -- they move with the viewer's own stylesheet."""
    from onetrace_console.incident_pages import INCIDENTS
    from onetrace_console.pages import render_execution
    from onetrace_console.render import COMPARISONS
    store, pages = _pages(ten_runs)
    console = [HOME, COUNTS, INCIDENTS, COMPARISONS] + [p for p in pages if p.startswith("incidents-")]
    from onetrace_console.render import render_diff
    compared = store.comparisons()
    assert compared, "the fixture holds no comparison, so the compare page is not read"
    pages = {**pages, "diff": render_diff(compared[0], store, generated_at=GENERATED_AT)}
    console.append("diff")
    for name in console:
        main = pages[name][pages[name].index("<main>"):pages[name].index("</main>")]
        assert main.count('class="cp"') == 1, name
        assert re.match(r'<main>\s*(<p data-preview[^>]*>.*?</p>\s*)?<div class="cp">', main, re.S), name
    from onetrace_console.pages import AUTHORIZATION, CASE
    from onetrace_console.unreadable import (render_failed_page, render_unchecked_run,
                                             render_unreadable_run)
    checked = next(r for r in store.runs() if r.check_report)
    run_pages = render_execution(checked, store, generated_at=GENERATED_AT).pages
    #: The authorization page and the notices are the console's own (board 3).
    pages = {**pages, "authorization": run_pages[AUTHORIZATION],
             "unreadable": render_unreadable_run(checked, "a reason", generated_at=GENERATED_AT),
             "unchecked": render_unchecked_run(checked, generated_at=GENERATED_AT),
             "failed": render_failed_page("a reason", generated_at=GENERATED_AT)}
    #: Each stage page (board 4) is the console's own too.
    #: And the run receipt (board 5).
    from onetrace_console.receipt_page import RECEIPT
    stages = sorted(n for n in run_pages if n.startswith("stage-")) + [RECEIPT]
    assert len(stages) > 1, "the run has no stage page, so none is read"
    pages.update({f"run/{n}": run_pages[n] for n in stages})
    console += ["authorization", "unreadable", "unchecked", "failed"] + [f"run/{n}" for n in stages]
    for name in console[-(4 + len(stages)):]:
        main = pages[name][pages[name].index("<main>"):pages[name].index("</main>")]
        assert main.count('class="cp"') == 1, name
    viewer = [p for p in pages if p.startswith("executions-")]
    viewer += [html for name, html in run_pages.items()
               if name not in (AUTHORIZATION, RECEIPT) and not name.startswith("stage-")]
    assert run_pages[CASE] in viewer
    for page in viewer:
        assert 'class="cp"' not in page
    examined(len(console) + len(viewer), "pages read for the skin")


def test_a_needs_attention_item_keeps_its_run_name_on_a_line_and_puts_its_time_under_it(examined):
    """Its time ("· received <date> UTC" and how long ago) never wraps, so beside a long run name it
    squeezed the name until the name broke a few characters to a line. The item wraps instead: the
    name keeps at least 16em, and the time goes under it, to the right, when there is no room."""
    from onetrace_console.frame import stylesheet
    css = stylesheet().decode("utf-8")
    rules = (r"\.cp \[data-attention\]\{flex-wrap:wrap\}",
             r"\.cp \[data-attention\]>span:first-child\{flex:1 1 16em;min-width:0\}",
             r"\.cp \[data-attention\]>\.value\{margin-left:auto\}")
    examined(len(rules), "rules")
    assert all(re.search(r, css) for r in rules), [r for r in rules if not re.search(r, css)]
