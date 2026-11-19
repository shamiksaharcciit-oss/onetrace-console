"""Format 0.5's store state on a run's pages (`store_state`): each step's page has a section with the store data it
read and wrote, `state_cut` above the entries and a kept value labelled as the store's bytes; the run's head names the
stores' revisions at open. Each present, absent, not kept and failed by the verifier, on the runs in
`tests/format_05_state/`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_step_kinds import OLDER, _pages, _text

HERE = Path(__file__).resolve().parent / "format_05_state"
AGENTS = HERE.parent / "format_05_agents" / "agents-kept"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _section(page: str) -> str:
    m = re.search(r'<section data-section="store-state">.*?</section>', page, re.S)
    return m.group(0) if m else ""


def _head(pages) -> str:
    m = re.search(
        r'<p class="sub" data-section="state-at-open".*?</p>|<div data-section="state-at-open".*?</div>',
        pages["proof.html"],
        re.S,
    )
    return _text(m.group(0)) if m else ""


def test_present_each_entry_the_kept_values_the_cut_and_the_head(tmp_path, examined):
    from onetrace_console.step_kinds import prose
    from onetrace_console.store_state import AT_OPEN_LEAD, HEADING, KEPT_LABEL, NON_CLAIMS

    pages = _pages(HERE / "state-kept", tmp_path / "k")
    cut = _pages(HERE / "accept" / "A41-state-cut", tmp_path / "c")
    stage_pages = {n: p for n, p in pages.items() if n.startswith("stage-")}
    examined(len(stage_pages) + 2, "the run's head, its step pages and a cut step's page")
    assert _head(pages) == f"{AT_OPEN_LEAD}: orders_db.orders at 0/16B3700 (lsn); tickets.notes at 6 (declared)"
    assert all(HEADING in _section(p) and prose(NON_CLAIMS) in _section(p) for p in stage_pages.values())
    lookup = _text(_section(stage_pages["stage-2.html"]))
    assert "orders_db.orders ( postgres ) key sha256:57225e68" in lookup
    assert "version 0/16B3748 ( lsn ) sql-rows/1 · sha256:42846907" in lookup
    assert "kb.articles ( document )" in lookup and "version not observed docs/1" in lookup
    assert (
        "replies.cache ( kv ) key A-1001 , kept in plain version not observed found: false , the read found nothing"
        in lookup
    )
    assert lookup.count(KEPT_LABEL) == 2 and '{"columns":["id","status"],"rows":[["A-1001","shipped"]]}' in lookup
    search = _text(_section(stage_pages["stage-3.html"]))
    assert "version 42 ( declared ) not observed: the search gave its first page, not the whole result" in search
    note = _text(_section(stage_pages["stage-5.html"]))
    assert "Written tickets.notes ( document )" in note and KEPT_LABEL in note
    cut_section = _section(cut["stage-1.html"])
    assert "2 more entries were counted and not recorded" in _text(cut_section)
    assert cut_section.index("data-state-cut") < cut_section.index("data-state-entry")
    assert cut_section.count("data-state-entry=") == 1000


def test_absent_no_store_state_recorded_nothing_read_and_an_earlier_format(tmp_path, examined):
    from onetrace_console.store_state import NONE_RECORDED, NOT_RECORDED, READ_NOTHING, WROTE_NOTHING

    pages = _pages(HERE / "state-kept", tmp_path / "k")
    agents = _pages(AGENTS, tmp_path / "a")
    older = _pages(OLDER, tmp_path / "o")
    examined(4, "a step with no state, one with empty lists, a run with no revisions at open, a format 0.4 run")
    draft = _text(_section(pages["stage-4.html"]))
    assert NONE_RECORDED in draft and "touched no store" not in draft
    assert f"Read {READ_NOTHING} Written {WROTE_NOTHING}" in _text(_section(pages["stage-6.html"]))
    assert f"Written {NOT_RECORDED}" in _text(_section(pages["stage-3.html"]))
    assert _head(agents) == ""
    assert not any('data-section="store-state"' in p or 'data-section="state-at-open"' in p for p in older.values())


def test_not_kept_a_run_that_kept_no_values_shows_none(tmp_path, examined):
    pages = _pages(HERE / "state-not-kept", tmp_path)
    examined(1, "a run that kept no store values")
    assert "data-state-kept" not in "".join(pages.values())
    assert "sql-rows/1 · sha256:42846907" in _text(_section(pages["stage-2.html"]))


def test_malformed_a_member_the_verifier_fails_is_not_drawn_its_row_is(tmp_path, examined):
    entries = _pages(HERE / "reject" / "R51-state-digest-out-of-form", tmp_path / "e")
    writes = _pages(HERE / "reject" / "R60-state-writes-labelled-read", tmp_path / "w")
    kept = _pages(HERE / "reject" / "R61-state-kept-does-not-recompute", tmp_path / "k")
    copy = _pages(HERE / "reject" / "R70-state-at-open-copy-differs", tmp_path / "c")
    later = _pages(HERE / "reject" / "R71-state-at-open-not-first", tmp_path / "l")
    examined(5, "runs whose entries, writes, kept value and revisions at open the verifier fails")
    page = _section(entries["stage-1.html"])
    assert "[FAIL ] receipts/01-sql.json: state entries -- state_reads[1]: digest 'sha256:00' is out of form" in _text(
        page
    )
    assert "data-state-entry" not in page and "sha256:00" not in page.split("out of form")[1]
    page = _section(writes["stage-2.html"])
    assert "[FAIL ] receipts/02-object.json: state_writes against effect_label" in _text(page)
    assert 'data-state-entry="writes-' not in page
    page = _section(kept["stage-1.html"])
    assert (
        "[FAIL ] receipts/01-s.json: state kept -- state_reads[1]: the kept file's sha256 is not its digest"
        in _text(page)
    )
    assert "data-state-kept" not in page and 'data-state-entry="reads-1"' in page
    assert "[FAIL ] state at open -- the manifest's copy differs from the first receipt's" in _head(copy)
    assert "[FAIL ] state at open -- receipts/02-b.json holds it, and it is not the first receipt" in _head(later)


def test_sabotage_a_console_that_draws_a_failed_entry_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import store_state

    monkeypatch.setattr(store_state, "failed", lambda rows, subject, names: [])
    entries = _pages(HERE / "reject" / "R51-state-digest-out-of-form", tmp_path)
    examined(1, "a run whose state entry the verifier fails, drawn from anyway")
    assert "sha256:00" in _section(entries["stage-1.html"])
