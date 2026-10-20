"""Runs are folders, not chain heads: two run folders with the same chain head are read apart.

A folder load reads every run folder on its own. Where two folders carry the same run and the same
chain head:

1. byte-identical folders are both shown, as copies of one run, each with its own reading and its
   own page;
2. folders that differ in any file are each shown with their own reading, and an incident names
   both: "Two folders share a chain head but their contents differ". One folder's reading never
   stands in for the other's, whichever loads first;
3. `--compare` and each run's page address resolve by folder: two folders that share a head have
   two addresses, each one the folder's own.

The twins are copies of the reference demo's first run: one with an output file edited, one with a
receipt deleted, one left as it is.
"""
from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RUN = REPO / "examples" / "reference-demo" / "runs" / "day-1"
#: An output file of the run, and one of its receipts.
OUTPUT = Path("artifacts") / "06-proposal" / "proposal.json"
RECEIPT = Path("receipts") / "05-model.json"
DIFFER = "Two folders share a chain head but their contents differ"


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _folder(tmp_path: Path, *names: str) -> Path:
    """A runs folder holding the reference demo's first run, once under each of `names`."""
    folder = tmp_path / "runs"
    folder.mkdir(parents=True)
    for name in names:
        shutil.copytree(RUN, folder / name)
    return folder


def _edit_output(run_dir: Path) -> None:
    f = run_dir / OUTPUT
    data = f.read_bytes()
    assert data.count(b"{") >= 1
    f.write_bytes(data.replace(b"{", b"{ ", 1))


def _load(folder: Path, root: Path, compare=None):
    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    store = Store(root / "store")
    return store, load_folder(folder, store, Config(), compare=compare)


def _said(loaded, store) -> dict[str, str]:
    """Each folder's line in the start-up list, by folder name."""
    from onetrace_console.folder_load import announce
    lines, _ = announce(Path("runs"), loaded, store)
    out = {}
    for text, _href in lines:
        parts = text.split()
        if len(parts) >= 2 and text.startswith("  "):
            out[parts[0]] = " ".join(parts[1:])
    return out


def _page(run, store) -> str:
    from onetrace_console.pages import CASE, render_execution
    return render_execution(run, store, generated_at="2026-01-01T00:00:00+00:00").pages[CASE]


def _case(run, store) -> str:
    return _text(_page(run, store))


def _rung(page: str) -> str:
    """The state the page's head gives "Records agree"."""
    found = re.findall(r'data-head-rung="records-agree" data-state="([^"]*)"', page)
    assert len(found) == 1, found
    return found[0]


def _incidents(store, rule_words: str = DIFFER):
    from onetrace_console.incidents import derive
    return [i for i in derive(store) if rule_words in i.quoted]


# ------------------------------------------------------------------ 1. a twin that differs

@pytest.mark.parametrize("twin", ["aa-twin", "zz-twin"], ids=["twin-loads-first", "twin-loads-last"])
def test_an_edited_output_file_in_a_twin_reads_contradicts_in_the_list_and_on_its_page(
        tmp_path, examined, twin):
    folder = _folder(tmp_path, "day-1", twin)
    _edit_output(folder / twin)
    store, loaded = _load(folder, tmp_path)
    by_name = {r.name: r.run for r in loaded.runs}
    examined(2, "run folders sharing a chain head")
    assert by_name["day-1"] is not None and by_name[twin] is not None, loaded.runs
    assert by_name["day-1"].key != by_name[twin].key, "one folder's run stood in for the other's"
    assert len(store.runs()) == 2

    said = _said(loaded, store)
    assert said[twin] == "Contradicts its record", said
    assert said["day-1"] == "Records agree", said

    twin_raw, own_raw = _page(by_name[twin], store), _page(by_name["day-1"], store)
    assert (_rung(twin_raw), _rung(own_raw)) == ("no", "yes")
    twin_page = _text(twin_raw)

    raised = _incidents(store)
    assert raised, "no incident names the two folders"
    for i in raised:
        assert "day-1" in i.quoted and twin in i.quoted, i.quoted
    assert DIFFER in twin_page and "day-1" in twin_page
    assert f"this folder, {twin} (Contradicts its record)" in twin_page, twin_page[:900]
    assert "the folder day-1 (Records agree)" in twin_page
    assert f"this folder, day-1 (Records agree), and the folder {twin} (Contradicts its record)" \
        in _text(own_raw)


def test_a_deleted_receipt_in_a_twin_is_read_on_its_own(tmp_path, examined):
    folder = _folder(tmp_path, "day-1", "day-1-copy")
    (folder / "day-1-copy" / RECEIPT).unlink()
    store, loaded = _load(folder, tmp_path)
    by_name = {r.name: r.run for r in loaded.runs}
    examined(2, "run folders sharing a chain head")
    assert by_name["day-1-copy"] is not None, loaded.runs
    assert by_name["day-1"].key != by_name["day-1-copy"].key
    assert by_name["day-1-copy"].recorded_count == by_name["day-1"].recorded_count - 1
    said = _said(loaded, store)
    assert said["day-1"] == "Records agree", said
    assert said["day-1-copy"] != "Records agree", said
    raised = _incidents(store)
    assert raised and all("day-1" in i.quoted and "day-1-copy" in i.quoted for i in raised)


# ------------------------------------------------------------------ 2. identical copies

def test_identical_copies_are_both_shown_as_copies_of_one_run_each_with_its_own_reading(
        tmp_path, examined):
    folder = _folder(tmp_path, "day-1", "day-1-copy")
    store, loaded = _load(folder, tmp_path)
    by_name = {r.name: r.run for r in loaded.runs}
    examined(2, "identical run folders")
    a, b = by_name["day-1"], by_name["day-1-copy"]
    assert a is not None and b is not None and a.key != b.key
    assert sorted(r.key for r in store.runs()) == sorted((a.key, b.key))
    assert a.check_report and b.check_report, "each folder is checked on its own"
    said = _said(loaded, store)
    assert said == {"day-1": "Records agree", "day-1-copy": "Records agree"}, said
    assert not _incidents(store), "identical copies are not an incident"
    page_a, page_b = _case(a, store), _case(b, store)
    assert ("this folder, day-1 (Records agree), is a copy of the folder day-1-copy "
            "(Records agree)") in page_a, page_a[:800]
    assert ("this folder, day-1-copy (Records agree), is a copy of the folder day-1 "
            "(Records agree)") in page_b, page_b[:800]


def test_a_run_folder_with_no_twin_keeps_its_address(tmp_path, examined):
    from onetrace_console.store import run_key
    folder = _folder(tmp_path, "day-1")
    store, loaded = _load(folder, tmp_path)
    run = loaded.runs[0].run
    examined(1, "run folder")
    assert run.key == run_key(run.run_id, run.chain_head)
    assert "a copy of the folder" not in _case(run, store)


# ------------------------------------------------------------------ 3. --compare and addresses

def test_compare_with_a_twin_compares_the_two_folders_it_names(tmp_path, examined):
    folder = _folder(tmp_path, "day-1", "day-1-twin")
    _edit_output(folder / "day-1-twin")
    store, loaded = _load(folder, tmp_path, compare=("day-1", "day-1-twin"))
    by_name = {r.name: r.run for r in loaded.runs}
    examined(1, "comparison with a twin")
    assert loaded.comparison is not None, loaded.compare_note
    assert (loaded.comparison.run_a, loaded.comparison.run_b) == (by_name["day-1"].key,
                                                                  by_name["day-1-twin"].key)
    from onetrace_console.folder_load import announce
    lines, opened = announce(folder, loaded, store)
    compared = [t for t, _ in lines if t.startswith("compared")]
    assert compared == ["compared day-1 with day-1-twin:"], lines
    hrefs = {t.split()[0]: h for t, h in lines if t.startswith("  ")}
    assert hrefs["day-1"] != hrefs["day-1-twin"], "two folders, one address"


def test_each_twins_address_is_its_folders_own_in_either_load_order(tmp_path, examined):
    """The address names the folder: the same folder gets the same address whether its twin sorts
    before or after it."""
    first = _folder(tmp_path / "one", "day-1", "zz-twin")
    second = _folder(tmp_path / "two", "day-1", "aa-twin")
    _s1, l1 = _load(first, tmp_path / "one")
    _s2, l2 = _load(second, tmp_path / "two")
    examined(2, "load orders")
    k1 = {r.name: r.run.key for r in l1.runs}
    k2 = {r.name: r.run.key for r in l2.runs}
    assert k1["day-1"] == k2["day-1"]
    assert len({k1["day-1"], k1["zz-twin"], k2["aa-twin"]}) == 3
