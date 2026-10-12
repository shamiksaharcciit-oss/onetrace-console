"""The Overview (v6 board 1), on Home.

The Overview has no permit or decision figures; its cards are runs, records agree, changed
vs baseline, and open incidents. It orders what needs attention by a rule stated on the
page, and shows a pipelines table from the data already stored. Its count cards merge the
7+N items only if nothing is lost; otherwise the list is kept and the page says why.

Every number on the Overview is a count with its denominator, and every count of runs opens
the list of exactly those runs (the rule Home was built on).

WHAT THE STORE CAN AND CANNOT SAY, AND SO WHAT THE PAGE SAYS
------------------------------------------------------------
- **Pipelines.** No record names its pipeline (not the manifest, not a receipt), and the
  stored `pipeline` field is the manifest's digest -- one per run. So a pipeline here is a
  **declared stage list**, and the page says so.
- **Changed vs baseline.** The console picks no baseline (no automatic
  partner-finding). A run is "changed vs baseline" when it is the candidate of a stored
  comparison -- one somebody asked for -- whose diff found a first difference; the baseline
  is the run it was compared with.
- **Incidents.** An incident has no open or closed state in this console, so none is called
  open: the card counts incidents raised.
"""
from __future__ import annotations

import re
from dataclasses import replace
from html import unescape

import pytest

from onetrace_console.words import short_time

from onetrace_console.checks import CONTRADICTS, COULD_NOT_CHECK, HOLDS
from onetrace_console.render import COUNTS, HOME, render_all
from tests.test_home_and_diff import GENERATED_AT, _fake_run, diverging, compared, ten_runs  # noqa: F401


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def _section(page: str, name: str) -> str:
    """The inner HTML of the element carrying `data-section="name"`, whatever its tag."""
    m = re.search(rf'<(\w+)[^>]*\sdata-section="{name}"[^>]*>(.*?)</\1>', page, re.S)
    assert m, f"no {name} section on the Overview"
    return m.group(2)


def _rows(page: str) -> int:
    return len(re.findall(r'<tr data-run="', page))


def _card(home: str, name: str) -> str:
    m = re.search(rf'<div data-card="{name}">(.*?)</div>', home, re.S)
    assert m, f"no {name} card"
    return m.group(1)


# ------------------------------------------------------------------------ the model

def test_a_pipeline_is_a_declared_stage_list(ten_runs, examined):
    from onetrace_console.overview import pipelines
    store, made = ten_runs
    other = _fake_run(store, made[0], run_id="other-pipeline", verdict=HOLDS)
    store.put_run(replace(other, declared_stages=("fetch", "answer"), stage_count=2,
                          recorded_count=2))
    found = pipelines(store)
    examined(len(found), "pipelines found by declared stage list")
    assert [p.label for p in found] == ["P1", "P2"]
    assert found[0].stages == made[0].declared_stages and len(found[0].runs) == len(made)
    assert found[1].stages == ("fetch", "answer") and len(found[1].runs) == 1


def test_changed_vs_baseline_is_the_candidate_of_a_stored_comparison_that_diverged(diverging):
    from onetrace_console.overview import vs_baseline
    comparison, store = diverging
    baseline, candidate = store.get_run(comparison.run_a), store.get_run(comparison.run_b)
    assert vs_baseline(candidate, store) == ("changed", "First difference · stage 4 · split")
    assert vs_baseline(baseline, store) == ("not-compared", "Not compared"), \
        "a baseline is not itself changed; only the candidate side is"


def test_a_comparison_that_found_no_difference_reads_same(compared):
    from onetrace_console.overview import vs_baseline
    comparison, store = compared
    assert vs_baseline(store.get_run(comparison.run_b), store) == ("same", "Same")


def test_needs_attention_follows_its_stated_rule(ten_runs, examined):
    """Contradicts itself, then couldn't check, then not checked, then a declared stage
    missing, then changed vs baseline; newest first within each. Runs that hold, complete and
    unchanged are not on it."""
    from onetrace_console.overview import ATTENTION_RULE, needs_attention
    store, made = ten_runs
    #: Arrival order made explicit, so "newest first" is tested and not left to a tie.
    for i, run in enumerate(store.runs()):
        store.put_run(replace(run, received_at=f"2026-09-2{i % 10}T10:00:00+00:00"))
    short = _fake_run(store, made[0], run_id="short-1", verdict=HOLDS)
    #: Missing a stage as its own page decides it, which is what the record keeps.
    store.put_run(replace(short, recorded_count=short.stage_count - 1, nothing_missing="no",
                          received_at="2026-09-01T00:00:00+00:00"))
    listed = needs_attention(store)
    examined(len(listed), "runs needing attention")
    kinds = [kind for kind, _ in listed]
    order = ["contradicts", "couldnt-check", "not-checked", "missing-stage", "changed"]
    assert kinds == sorted(kinds, key=order.index), kinds
    assert set(kinds) == {"contradicts", "couldnt-check", "not-checked", "missing-stage"}
    for kind in set(kinds):
        times = [r.received_at for k, r in listed if k == kind]
        assert times == sorted(times, reverse=True), (kind, times)
    assert all(r.check_verdict != HOLDS or k == "missing-stage" for k, r in listed)
    assert "then" in ATTENTION_RULE and "newest first" in ATTENTION_RULE


# ------------------------------------------------------------------------ the cards

def test_the_overview_has_four_cards_in_the_rulings_order(ten_runs):
    store, _ = ten_runs
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    cards = re.findall(r'<div data-card="([^"]+)">', _section(home, "cards"))
    assert cards == ["runs", "records-agree", "changed-vs-baseline", "incidents"]


def test_every_run_card_opens_exactly_the_runs_it_counts(diverging, examined):
    """Read off the page and compared with the rows of the page the card's link opens."""
    comparison, store = diverging
    pages = render_all(store, generated_at=GENERATED_AT)
    home = pages[HOME]
    total = len(store.runs())
    for name in ("records-agree", "changed-vs-baseline"):
        card = _card(home, name)
        href = re.search(r'<a href="([^"]+)"', card).group(1)
        lead = re.search(r'<p class="lead">(.*?)</p>', card, re.S).group(1)
        shown = re.search(r"(\d+) of (\d+) runs?", _text(lead))
        examined(1, f"the {name} card")
        assert (int(shown.group(1)), int(shown.group(2))) == (_rows(pages[href]), total), name
    changed = _card(home, "changed-vs-baseline")
    assert re.search(r"1 of 2 runs changed vs baseline", _text(changed)), _text(changed)


def test_the_runs_card_names_its_pipelines_and_what_a_pipeline_is_here(ten_runs):
    store, _ = ten_runs
    card = _text(_card(render_all(store, generated_at=GENERATED_AT)[HOME], "runs"))
    assert f"{len(store.runs())} runs stored" in card and "Stored in 1 pipeline." in card
    assert "declared stage list" in card


def test_no_incident_is_called_open(ten_runs):
    """The console keeps no open or closed state for an incident."""
    from onetrace_console.incidents import derive
    store, _ = ten_runs
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    card = _text(_card(home, "incidents"))
    assert f"{len(derive(store))} incident" in card
    assert not re.search(r"\bopen incidents?\b|\d+\s+open\b", card.lower()), card
    assert "none is called open" in card, "and the card says why"


def test_the_full_list_of_counts_is_kept_and_says_why(ten_runs):
    """Merge into cards only if nothing is lost; otherwise keep the list and say why."""
    from onetrace_console.home import incident_tallies, tallies
    store, _ = ten_runs
    pages = render_all(store, generated_at=GENERATED_AT)
    #: The list is on its own page, All counts, one link from the Overview.
    home, page = pages[HOME], pages[COUNTS]
    assert f'<a href="{COUNTS}">All counts</a>' in _section(home, "all-counts")
    assert 'data-tally="' not in home, "the list is on the All counts page, not also here"
    #: From the list's opening tag to the footer: the list nests lists, so no tag-matching
    #: pattern bounds it reliably.
    counts = page[page.index('data-section="counts"'):page.index("<footer>")]
    for t in tallies(store) + incident_tallies(store):
        assert f'data-tally="{t.slug}"' in counts, t.slug
        assert t.href in pages, f"{t.slug}'s count opens nothing"
    assert "kept whole" in _text(_section(page, "counts-why"))
    assert "below the cards" not in page, "on a page of its own the list is not below the cards"


def test_the_new_counts_are_lists_home_opens(diverging, examined):
    """Changed vs baseline, needing attention, a declared stage missing, and one per
    pipeline: each is a tally, so the existing checks (every number equals its list, every
    list states its denominator) run over them too."""
    from onetrace_console.home import tallies
    _, store = diverging
    slugs = {t.slug for t in tallies(store)}
    examined(len(slugs), "tallies")
    assert {"changed-vs-baseline", "needs-attention", "missing-a-declared-stage",
            "pipeline-p1"} <= slugs


# ------------------------------------------------------------ needs attention first

def test_needs_attention_states_its_count_and_its_rule(ten_runs):
    from onetrace_console.overview import ATTENTION_RULE, needs_attention
    store, _ = ten_runs
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    panel = _text(_section(home, "needs-attention"))
    n, total = len(needs_attention(store)), len(store.runs())
    assert f"Needs attention first · {n} of {total} runs" in panel
    assert ATTENTION_RULE in panel


def test_needs_attention_lists_the_first_five_in_rule_order_each_linked_to_its_run(ten_runs):
    from onetrace_console.overview import ATTENTION_WORDS, needs_attention
    store, _ = ten_runs
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    panel = _section(home, "needs-attention")
    items = re.findall(r'<li data-attention="([^"]+)">(.*?)</li>', panel, re.S)
    expected = needs_attention(store)[:5]
    assert [k for k, _ in items] == [k for k, _ in expected]
    for (kind, html), (_, run) in zip(items, expected):
        assert ATTENTION_WORDS[kind] in _text(html)
        assert f'href="runs/{run.key}/case.html"' in html
    assert 'href="executions-needs-attention.html"' in panel, "all of them, one link away"


def test_a_store_where_nothing_needs_attention_says_so(store):
    """Never blank: an empty panel says the rule found nothing."""
    from onetrace_console.checks import run_and_record
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    from tests.test_compare import EXAM, _deliver, _require_exam
    _require_installed()
    _require_exam()
    #: A 0.1-format run that holds. Until 0.2.0 this was `ingest-r1/run_C`; that is a preview-format
    #: run, which the 0.2.0 verifier reads as NOT VERIFIED, so it now rightly
    #: needs attention ("Couldn't check") and can't be the store where nothing does.
    run = run_and_record(_deliver(EXAM / "dag-r37" / "run_R", store), store, ran_at=FIXED_RAN_AT)
    assert run.check_verdict == HOLDS
    panel = _text(_section(render_all(store, generated_at=GENERATED_AT)[HOME], "needs-attention"))
    assert "Needs attention first · 0 of 1 run" in panel
    assert "No run needs attention by this rule." in panel


# ------------------------------------------------------------------- recent runs

def test_recent_runs_show_what_each_run_records_and_how_it_compares(ten_runs):
    from onetrace_console.home import MOST_RECENT, VERDICT_LABELS, verdict_of
    from onetrace_console.overview import pipelines, ran_at, vs_baseline
    store, _ = ten_runs
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    table = _section(home, "recent-runs")
    rows = re.findall(r'<tr data-recent="([^"]+)">(.*?)</tr>', table, re.S)
    recent = store.runs()[:MOST_RECENT]
    assert [k for k, _ in rows] == [r.key for r in recent], "newest arrival first"
    label = {r.key: p.label for p in pipelines(store) for r in p.runs}
    for (key, cells), run in zip(rows, recent):
        tds = [_text(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", cells, re.S)]
        #: Declared stages delivered.
        assert tds == [run.run_id, label[key],
                       f"{run.delivered_stages} of {run.stage_count} declared stages"
                       + (f"; {run.retries} retr{'y' if run.retries == 1 else 'ies'} recorded"
                          if run.retries else ""),
                       vs_baseline(run, store)[1], VERDICT_LABELS[verdict_of(run)],
                       short_time(ran_at(run)) if ran_at(run) else "not recorded",
                       short_time(run.received_at)], tds
        assert f'datetime="{run.received_at}"' in cells, "the time's whole value is in its <time>"
        assert f'href="runs/{key}/case.html"' in cells
    heading = _text(table.split("<table")[0])
    assert f"Recent runs · {len(recent)} of {len(store.runs())}" in heading


# --------------------------------------------------------------------- pipelines

def test_the_pipelines_table_states_what_a_pipeline_is_and_counts_each_one(ten_runs, examined):
    from onetrace_console.overview import PIPELINE_RULE, pipelines
    store, made = ten_runs
    #: Built from a fake with no stored check report (made[1]): a "contradicts" verdict over
    #: the real run's report, which holds, would be a state no check could produce.
    other = _fake_run(store, made[1], run_id="other-pipeline", verdict=CONTRADICTS)
    store.put_run(replace(other, declared_stages=("fetch", "answer"), stage_count=2,
                          recorded_count=2, received_at="2027-01-01T00:00:00+00:00"))
    pages = render_all(store, generated_at=GENERATED_AT)
    section = _section(pages[HOME], "pipelines")
    assert PIPELINE_RULE in _text(section)
    rows = re.findall(r'<tr data-pipeline="([^"]+)">(.*?)</tr>', section, re.S)
    found = pipelines(store)
    examined(len(rows), "pipeline rows")
    assert [label for label, _ in rows] == [p.label for p in found] == ["P1", "P2"]
    total = len(store.runs())
    for (label, cells), p in zip(rows, found):
        tds = [_text(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", cells, re.S)]
        n = len(p.runs)
        assert tds[0] == label and tds[1] == " → ".join(p.stages)
        assert tds[2] == f"{n} of {total}"
        href = re.search(r'<a href="([^"]+)"', cells).group(1)
        assert _rows(pages[href]) == n, "the count opens exactly its runs"
        counts = [re.fullmatch(r"(\d+) of (\d+)", td) for td in tds[3:7]]
        assert all(c and int(c.group(2)) == n for c in counts), tds
        assert sum(int(c.group(1)) for c in counts) == n, "every run is in one verdict column"
        latest = max(r.received_at for r in p.runs)
        assert tds[7] == short_time(latest) and f'datetime="{latest}"' in cells


# ------------------------------------------------------ verdicts by day, and the marker

@pytest.fixture
def three_days(store):
    """Day 1: ingest-r1's run_A. Day 2: its run_B, whose split stage records other settings.
    Day 3: run_B's receipts again. So the recorded digests change once, between days 1 and 2."""
    from tests.test_checks import _require_installed
    from tests.test_compare import EXAM, _deliver, _require_exam
    _require_installed()
    _require_exam()
    a = _deliver(EXAM / "ingest-r1" / "run_A", store)
    b = _deliver(EXAM / "ingest-r1" / "run_B", store)
    store.put_run(replace(a, received_at="2026-09-20T09:00:00+00:00"))
    store.put_run(replace(b, received_at="2026-09-21T09:00:00+00:00"))
    again = _fake_run(store, b, run_id="run-b-again", verdict=HOLDS)
    store.put_run(replace(again, received_at="2026-09-22T09:00:00+00:00"))
    return store


def test_the_days_are_the_days_received_and_the_section_says_so(three_days):
    """"verdicts by day" by day of arrival. Label it "by day received"."""
    section = _section(render_all(three_days, generated_at=GENERATED_AT)[HOME], "by-day")
    assert "<h2>Verdicts by day received</h2>" in section
    assert "<th>Day received</th>" in section
    assert "counts of the runs received that day" in section
    assert "<h2>Verdicts by day</h2>" not in section and "<th>Day</th>" not in section


def test_each_day_shows_its_verdicts_as_counts_of_that_days_runs(three_days, examined):
    home = render_all(three_days, generated_at=GENERATED_AT)[HOME]
    section = _section(home, "by-day")
    days = re.findall(r'<tr data-day="([^"]+)">(.*?)</tr>', section, re.S)
    examined(len(days), "days")
    assert [d for d, _ in days] == ["2026-09-20", "2026-09-21", "2026-09-22"]
    for _, cells in days:
        tds = [_text(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", cells, re.S)]
        n = int(tds[1])
        counts = [re.fullmatch(r"(\d+) of (\d+)", td) for td in tds[2:6]]
        assert all(c and int(c.group(2)) == n for c in counts), tds
        assert sum(int(c.group(1)) for c in counts) == n
    assert not re.search(r"\d+(?:\.\d+)?\s*%", _text(section)), "counts, never percentages"


def test_the_change_marker_stands_only_where_consecutive_days_record_different_digests(
        three_days, examined):
    """The marker (`data-change-marker`) appears only where two consecutive
    days carry different recorded digests, never inferred from the verdict counts."""
    home = render_all(three_days, generated_at=GENERATED_AT)[HOME]
    section = _section(home, "by-day")
    order = re.findall(r'<tr (data-day="[^"]+"|data-change-marker="[^"]*")', section)
    examined(len(order), "rows of the by-day table")
    assert [o.split("=")[0] for o in order] == [
        "data-day", "data-change-marker", "data-day", "data-day"], order
    marker = re.search(r'<tr data-change-marker="[^"]*">(.*?)</tr>', section, re.S).group(1)
    text = _text(marker)
    assert "P1" in text and "split" in text and "settings" in text, text
    assert re.search(r"sha256:[0-9a-f]{64}", text), "the digests, whole"


def test_the_by_day_table_draws_no_direction(three_days):
    """No arrows, and no word implying a direction, a score or a forecast."""
    section = _text(_section(render_all(three_days, generated_at=GENERATED_AT)[HOME], "by-day"))
    for word in ("trend", "rising", "falling", "improved", "regressed", "↑", "↓", "→", "▲", "▼"):
        assert word not in section.lower(), word


# ------------------------------------------- the Diff page: other runs with the same change

def test_other_runs_with_the_same_change_are_counted_by_a_stated_rule(diverging, examined):
    """A separate section below the pair; the matching rule on the page, by
    exact equality; counts with denominators; a plain list of run ids; never "caused"."""
    from onetrace_console.render import render_diff
    comparison, store = diverging
    a, b = store.get_run(comparison.run_a), store.get_run(comparison.run_b)
    same = [_fake_run(store, b, run_id=f"same-{i}", verdict=HOLDS) for i in (1, 2)]
    _fake_run(store, a, run_id="like-the-baseline", verdict=HOLDS)
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    section = _section(page, "same-change")
    text = _text(section)
    examined(len(store.runs()), "stored runs searched for the same change")
    assert text.startswith("Other runs with the same change")
    assert "same settings digest at stage 4 · split, by exact equality" in text
    assert re.search(r"sha256:[0-9a-f]{64}", text), "the digest matched, whole"
    assert "2 other runs in P1 carry it, of 5 runs in P1" in text
    listed = re.findall(r'<li data-run="([^"]+)">', section)
    assert sorted(listed) == sorted(r.key for r in same)
    assert 'href="#same-change-list"' in section
    for causal in ("caused", "because", "as a result", "led to", "due to"):
        assert causal not in text.lower(), causal


def test_a_pair_with_no_difference_has_no_change_to_look_for(compared):
    from onetrace_console.render import render_diff
    comparison, store = compared
    text = _text(_section(render_diff(comparison, store, generated_at=GENERATED_AT),
                          "same-change"))
    assert "The two runs do not differ, so there is no change to look for." in text


def test_a_pair_whose_receipts_cannot_be_read_matches_nothing(diverging, monkeypatch):
    """Never a guess: with the pair's receipts unreadable, no other run is matched."""
    import onetrace_console.overview as overview
    from onetrace_console.render import render_diff
    comparison, store = diverging
    monkeypatch.setattr(overview, "recorded_digests", lambda run, store: None)
    text = _text(_section(render_diff(comparison, store, generated_at=GENERATED_AT),
                          "same-change"))
    assert "could not be read at stage 4 · split, so no other run is matched" in text


# ------------------------------------------- what the evidence establishes, across runs

def test_the_overview_carries_the_evidence_ladder_across_runs(ten_runs, examined):
    """v6 board 1: each rung a separate question over the stored runs, counts with their
    denominators, and release 1's authorization rung in its own words -- never a count."""
    from onetrace_console.home import tallies
    store, _ = ten_runs
    pages = render_all(store, generated_at=GENERATED_AT)
    section = _section(pages[HOME], "evidence")
    total = len(store.runs())
    assert f"What the evidence establishes · {total} runs" in _text(section)
    rows = re.findall(r'<tr data-rung="([^"]+)">(.*?)</tr>', section, re.S)
    examined(len(rows), "rungs across runs")
    assert [k for k, _ in rows] == ["records-agree", "signed", "nothing-missing", "reproduced",
                                    "authorized", "anchored"]
    by = {k: _text(v) for k, v in rows}
    t = {x.slug: x for x in tallies(store)}
    #: As the confirmation review held it: only a check with the output files
    #: required counts as agreeing; one that held without them is said beside the count.
    without = t["holds"].count - t["records-agree"].count
    assert f"{t['records-agree'].count} of {total}" in by["records-agree"]
    assert f"{without} held without their output files required" in by["records-agree"]
    assert f"{t['could-not-check'].count} couldn't check" in by["records-agree"]
    assert f"{t['contradicts'].count} contradict" in by["records-agree"]
    #: Each signing form as each run's own page reads it, over all runs stored,
    #: zeros left out (tests/test_signed_surfaces.py holds each rule).
    from onetrace_console.home import SIGNATURE_FORMS
    signing = [(t[f"signed-{slug}"], words) for slug, _r, words in SIGNATURE_FORMS]
    assert by["signed"] == "Signed by a known recorder? " + " · ".join(
        f"{x.count} {w}" for x, w in signing if x.count)
    assert sum(x.count for x, _ in signing) == total
    #: Rung 3 as each run's page decides it: yes, no, and neither established.
    missing = t["missing-a-declared-stage"].count
    assert f"{t['nothing-missing'].count} of {total}" in by["nothing-missing"]
    assert f"{missing} missing a declared stage" in by["nothing-missing"]
    assert f"{t['missing-not-established'].count} not established" in by["nothing-missing"]
    assert (t["nothing-missing"].count + missing + t["missing-not-established"].count == total)
    assert "not checked" in by["reproduced"]
    assert "No records · This console does not record authorization." in by["authorized"]
    assert not re.search(r"\d+ of \d+", by["authorized"]), "authorization is never counted"
    #: Each form as each run's own page reads it, zeros left out, then the runs without the
    #: check inline (tests/test_overview_anchoring.py holds each rule).
    from onetrace_console.home import ANCHOR_FORMS
    forms = [(t[f"anchored-{r}"], w) for r, w in ANCHOR_FORMS] + [(t["anchored-not-checked"],
                                                                  "not checked")]
    assert by["anchored"] == "Committed by a known time? " + " · ".join(
        f"{x.count} {w}" for x, w in forms if x.count)
    assert sum(x.count for x, _ in forms) == total
    for key in ("records-agree", "nothing-missing"):
        href = re.search(r'<a href="([^"]+)"', dict(rows)[key]).group(1)
        assert href in pages, (key, href)


def test_the_overview_has_no_unsigned_banner_once_a_run_is_signed_by_a_trusted_key(ten_runs):
    """ten_runs holds a run that reads Yes on "Signed by a known recorder?", so
    there is no banner (tests/test_overview_banner.py holds each case)."""
    store, _ = ten_runs
    assert any(r.signed == "yes" for r in store.runs()), "the premise"
    assert 'data-section="banner"' not in render_all(store, generated_at=GENERATED_AT)[HOME]
