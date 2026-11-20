"""Lineage on a step's page (`store_state`, `run_index`): "Other runs that wrote what this step read", from the run
index the pages are drawn with, never the store's records. A run whose indexed write holds an equal version or digest
for the read's store and key is listed and linked; a write the verifier fails is not indexed; an index written before
it held store writes, or none, reads "not indexed for lineage", never an empty list. Lineage says equality, and
nothing of cause."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.test_format_03 import _tar
from tests.test_step_kinds import _text

TESTS = Path(__file__).resolve().parent
KEPT = TESTS / "format_05_state" / "state-kept"
FOLLOWUP = TESTS / "format_05_lineage" / "state-followup"
WRITES_FAILED = TESTS / "format_05_state" / "reject" / "R60-state-writes-labelled-read"
RAN_AT = "2026-11-12T00:00:00+00:00"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


@pytest.fixture
def stored(tmp_path):
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store

    store = Store(tmp_path / "store")
    keys = {}
    for name, folder in (("kept", KEPT), ("followup", FOLLOWUP), ("writes-failed", WRITES_FAILED)):
        keys[name] = run_and_record(accept(_tar(folder), store).run, store, ran_at=RAN_AT).key
    return store, keys


def _page(store, key: str, page: str, index) -> str:
    from contextlib import nullcontext

    from onetrace_console import run_index
    from onetrace_console.pages import render_execution

    with run_index.drawing(index) if index is not None else nullcontext():
        return dict(render_execution(store.get_run(key), store, generated_at=RAN_AT).pages)[page]


def _lineage(page: str) -> str:
    m = re.search(r'<div data-section="lineage">.*?</div>', page, re.S)
    return m.group(0) if m else ""


def test_present_a_run_that_wrote_what_this_step_read_is_listed_and_linked(stored, examined):
    from onetrace_console import run_index
    from onetrace_console.store_state import LINEAGE_HEADING

    store, keys = stored
    index = run_index.build(store)
    block = _lineage(_page(store, keys["followup"], "stage-2.html", index))
    examined(1, "the follow-up step's page")
    assert LINEAGE_HEADING in block
    assert f'href="../{keys["kept"]}/stage-5.html"' in block
    assert "state-kept , step note , wrote tickets.notes with an equal version: 7" in _text(block)
    #: The orders table it also read: no run wrote it, so no run is listed for it.
    assert block.count("data-lineage-run=") == 1 and "orders_db" not in block
    assert not re.search(r"caus|because|led to|made .* behave", _text(block), re.I)


def test_absent_a_step_whose_reads_no_run_wrote_says_so_and_one_with_no_reads_has_none(stored, examined):
    from onetrace_console import run_index
    from onetrace_console.store_state import NO_WRITER

    store, keys = stored
    index = run_index.build(store)
    lookup = _lineage(_page(store, keys["kept"], "stage-2.html", index))
    note = _page(store, keys["kept"], "stage-5.html", index)
    examined(2, "a step that read what no run wrote, and a step that only wrote")
    assert NO_WRITER in _text(lookup) and "data-lineage-run" not in lookup
    assert _lineage(note) == ""


def test_an_index_written_before_it_held_store_writes_or_none_reads_not_indexed(stored, examined):
    from onetrace_console import run_index
    from onetrace_console.store_state import NOT_INDEXED

    store, keys = stored
    earlier = {k: v for k, v in run_index.build(store).items() if k != run_index.LINEAGE}
    for run in earlier["runs"]:
        for step in run["steps"]:
            step.pop("state_writes", None)
    examined(2, "a page drawn with an earlier build's index, and one drawn with none")
    for index in (earlier, None):
        block = _lineage(_page(store, keys["followup"], "stage-2.html", index))
        assert NOT_INDEXED in _text(block) and "data-lineage-run" not in block


def test_malformed_a_write_the_verifier_fails_is_not_indexed(stored, examined):
    from onetrace_console import run_index

    store, keys = stored
    index = run_index.build(store)
    runs = {r["key"]: r for r in index["runs"]}
    examined(2, "the index's entries for a run with good writes and one whose writes fail")
    assert [s["state_writes"] for s in runs[keys["kept"]]["steps"] if "state_writes" in s] == [
        [
            {
                "store": "tickets.notes",
                "key_digest": "sha256:790db8f9fd00694ccd59cb3a4a5cf35dd2f85ce818b8f6842bb690f3f8621260",
                "version": "7",
                "digest": "sha256:a4698a0011bde33add64be1bea14fba7b345288cc9511ad0fa9827618f0fc62e",
            }
        ]
    ]
    #: The vector's step 2 writes and is labelled read: its writes FAIL and are left out. Step 6's pass and are kept.
    failed_run = {s["index"]: s for s in runs[keys["writes-failed"]]["steps"]}
    assert "state_writes" not in failed_run["2"] and "state_writes" in failed_run["6"]
    assert index[run_index.LINEAGE] == "state_writes" and index["format"] == run_index.FORMAT


def test_sabotage_an_index_that_keeps_a_failed_write_is_named(stored, monkeypatch, examined):
    from onetrace_console import run_index

    store, keys = stored
    monkeypatch.setattr(run_index, "WRITE_ROWS", ())
    runs = {r["key"]: r for r in run_index.build(store)["runs"]}
    examined(1, "an index built without the verifier's rows on writes")
    assert "state_writes" in {s["index"]: s for s in runs[keys["writes-failed"]]["steps"]}["2"]


def test_the_lineage_run_is_recorded_from_the_release_wheels_and_verifies(examined):
    from tests.test_format_05_agents_runs import _verify

    made = json.loads((FOLLOWUP.parent / "MADE.json").read_text(encoding="utf-8"))
    examined(1, "the follow-up run verified")
    assert made["versions"]["onetrace"] == "0.8.0" and made["runs"]["state-followup"]["exit"] == 0
    assert "859976cf7aab2bd67bdf171718550304fb0db8ac098d30ba1176d82df7871751" in (
        FOLLOWUP.parent / "PROVENANCE.md"
    ).read_text(encoding="utf-8")
    assert _verify(FOLLOWUP) == (0, "PASS", [])


def test_the_console_s_own_drawing_reads_lineage_from_the_index_it_writes(stored, tmp_path, examined):
    from onetrace_console import run_index
    from onetrace_console.serve import PAGES_DIRNAME, _render_all_pages, _render_run_pages

    store, keys = stored
    root = tmp_path / "site"
    root.mkdir()
    #: The console's start: every page over the store, and the index, then each run's own pages read that index.
    _render_all_pages(store, root)
    _render_run_pages(store.get_run(keys["followup"]), store, root)
    page = (root / PAGES_DIRNAME / "runs" / keys["followup"] / "stage-2.html").read_text(encoding="utf-8")
    written = json.loads((root / run_index.FILE_NAME).read_text(encoding="utf-8"))
    examined(2, "a page and the index the console wrote")
    assert f'href="../{keys["kept"]}/stage-5.html"' in _lineage(page)
    assert written == json.loads(run_index.encode(run_index.build(store)))
    assert "\\" not in _lineage(page)


def test_a_page_drawn_from_the_index_names_its_format_and_when_it_was_written(stored, tmp_path, examined):
    """A run's pages drawn alone read the index the console last wrote: the page names when, so a stale page reads
    as stale."""
    import os

    from onetrace_console import run_index
    from onetrace_console.serve import PAGES_DIRNAME, _render_all_pages, _render_run_pages

    store, keys = stored
    root = tmp_path / "site"
    root.mkdir()
    _render_all_pages(store, root)
    os.utime(root / run_index.FILE_NAME, (1762905600, 1762905600))
    _render_run_pages(store.get_run(keys["followup"]), store, root)
    page = (root / PAGES_DIRNAME / "runs" / keys["followup"] / "stage-2.html").read_text(encoding="utf-8")
    without = _page(store, keys["followup"], "stage-2.html", None)
    examined(2, "a page drawn alone from the index last written, and one drawn with none")
    said = run_index.FROM_INDEX.format(format=run_index.FORMAT, written="2025-11-12 00:00:00 UTC")
    assert said in " ".join(_text(_lineage(page)).split()).replace(" .", ".")
    assert '<time datetime="2025-11-12T00:00:00+00:00"' in _lineage(page)
    assert 'data-section="from-index"' not in without


PLAIN = TESTS / "format_05_lineage" / "state-plain-writer"


def test_a_plain_key_and_a_digest_match_by_the_plain_key_s_digest_and_the_page_says_so(tmp_path, examined):
    from onetrace_console import run_index
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from onetrace_console.store_state import BY_KEY_DIGEST

    store = Store(tmp_path / "store")
    keys = {
        name: run_and_record(accept(_tar(folder), store).run, store, ran_at=RAN_AT).key
        for name, folder in (("followup", FOLLOWUP), ("plain", PLAIN), ("kept", KEPT))
    }
    block = _lineage(_page(store, keys["followup"], "stage-2.html", run_index.build(store)))
    rows = dict(re.findall(r'<li data-lineage-run="([0-9a-f]{64})">(.*?)</li>', block, re.S))
    examined(2, "a writer that keeps its key in plain, and one that keeps its digest")
    assert sorted(rows) == sorted([keys["plain"], keys["kept"]])
    assert BY_KEY_DIGEST in _text(rows[keys["plain"]]) and BY_KEY_DIGEST not in _text(rows[keys["kept"]])


def test_a_plain_key_is_never_compared_with_a_digest_as_text(examined):
    from onetrace_console.run_index import key_digest, key_match

    examined(5, "pairs of keys")
    said = "sha256:" + "a" * 64
    assert key_match({"key": said}, {"key_digest": said}) is None
    assert key_match({"key": "A-1001/1"}, {"key_digest": key_digest("A-1001/1")}) == "digest"
    assert key_match({"key_digest": key_digest("A-1001/1")}, {"key": "A-1001/1"}) == "digest"
    assert key_match({"key": "A-1001/1"}, {"key": "A-1001/1"}) == "exact"
    assert key_match({"key": "A-1001/1"}, {"key": "A-1001/2"}) is None


def test_a_first_start_draws_each_run_s_pages_with_the_index_it_builds(stored, tmp_path, examined):
    """A console's first start (no index on disk yet, as a public build's or a new demo's) draws each run's pages with
    the index it builds, so a step that read what another run wrote says so on the first start, not on the next."""
    from onetrace_console.serve import PAGES_DIRNAME, _render_startup_pages

    store, keys = stored
    root = tmp_path / "first"
    root.mkdir()
    _render_startup_pages(store, root)
    page = (root / PAGES_DIRNAME / "runs" / keys["followup"] / "stage-2.html").read_text(encoding="utf-8")
    examined(1, "a step page drawn on a first start")
    assert 'data-lineage="not-indexed"' not in page
    assert f'href="../{keys["kept"]}/stage-5.html"' in _lineage(page)
