"""Board 7, where the change started.

Every value from the comparison's own trace run, `onetrace diff A B --text --json --runs-root
RUNS_ROOT`, made only where the stored `--no-follow` text diff names a changed corpus link, over a
runs root laid out from the store: every run it holds whole, whatever its own check said.

The pairs here are the SDK's own warranty fixture (`tests/fixtures/warranty/`, from the hash-checked
development sdist, `tools/fetch_sdk_fixtures.py`), stored as the console stores any delivery.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import replace
from html import unescape
from pathlib import Path

import pytest

from onetrace_console.board7 import (LIMIT, SHOWN_COMMAND, TRACE, read_traces, render_board7,
                                     runs_root)
from onetrace_console.compare import TEXT_DIFF, compare
from onetrace_console.render import render_diff
from onetrace_console.textdiff_view import TextDiffUnreadable
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_pages import GENERATED_AT
from tools.fetch_sdk_fixtures import WARRANTY, check as fixtures_ready
#: The SDK run as the console runs it (compare.py): UTF-8 forced on the child's output, so the bytes
#: compared are the console's, on a machine whose default encoding is not UTF-8 too.
from onetrace_console.child import utf8_env  # noqa: E402

RUNS = WARRANTY / "runs"
SECTION = '<section data-section="where-started">'


def _require_warranty():
    _require_installed()
    if not fixtures_ready():
        pytest.fail("the SDK's fixtures are not there or do not match:\n"
                    "    python tools/fetch_sdk_fixtures.py")


def _store_run(store, folder: Path, *, check: bool = True):
    """A run delivered whole (artifacts/ included), as ingest takes it, then its own check run."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from tests.conftest import make_tar
    from tests.test_diff_sdk_text_layer import _files
    got = accept(make_tar(_files(folder)), store)
    assert got.run is not None, getattr(got, "body", got)
    return run_and_record(got.run, store, ran_at=FIXED_RAN_AT) if check else got.run


def _changed(tmp_path: Path, name: str, change) -> Path:
    """A copy of a warranty run, changed by `change(folder)`."""
    folder = tmp_path / "changed" / name
    shutil.copytree(RUNS / name, folder)
    change(folder)
    return folder


def _pair(store, tmp_path, *, ingest=("ingest-v1", "ingest-v2"), work="work"):
    """The query pair compared, with whichever ingest runs `ingest` names (or folders) stored."""
    for run in ingest:
        _store_run(store, run if isinstance(run, Path) else RUNS / run)
    a, b = _store_run(store, RUNS / "query-v1"), _store_run(store, RUNS / "query-v2")
    return compare(a, b, store, ran_at=FIXED_RAN_AT, work_root=tmp_path / work)


def _board(page: str) -> str:
    assert page.count(SECTION) == 1, "board 7 is not on the page once"
    return page[page.index(SECTION):].split("</section>\n", 1)[0]


def _trace_doc(comparison, store) -> dict:
    return read_traces(store.get(comparison.verb(TRACE).stdout_key), followed=True)


@pytest.fixture
def golden(store, tmp_path):
    _require_warranty()
    comparison = _pair(store, tmp_path)
    return comparison, store, render_diff(comparison, store, generated_at=GENERATED_AT)


# ------------------------------------------------------------- the golden: load, twelve -> six

def test_the_golden_fixture_renders_the_warranty_trace(golden, examined):
    comparison, store, page = golden
    doc = _trace_doc(comparison, store)
    board = _board(page)
    text = unescape(board)
    (entry,) = doc["corpus_traces"]
    examined(len(entry["nodes"]), "traced ingest nodes")
    assert entry["status"] == "traced" and entry["node"] == "retrieve"
    #: Point 1: the SDK's first lines, for the query runs and for the trace, word for word.
    assert doc["first_line"] in text
    assert "traced into the linked ingest runs: ingest-v1 -> ingest-v2" in text
    assert ("started at: load — 1 of 3 documents changed (help-centre/warranty.md); "
            "settings unchanged") in text
    #: Point 3: the chain, in the SDK's order, the first difference marked, the one count it gives.
    chain = re.search(r'data-section="where-started-chain">(.*?)</section>', board, re.S).group(1)
    assert re.findall(r'<li data-node="([^"]+)" data-verdict="([^"]+)"', chain) == [
        ("load", "FIRST DIFFERENCE"), ("split", "downstream"), ("index", "downstream")]
    assert chain.count('data-first-difference="true"') == 1
    assert '<p data-documents>1 of 3 documents changed</p>' in chain
    #: Point 4: twelve -> six at load, ingest rows first, then the query rows, each verified.
    table = re.search(r'data-section="where-started-text">(.*?)</section>', board, re.S).group(1)
    stages = re.findall(r"<td><code>([^<]+)</code></td><td><code>[^<]*</code></td>", table)
    assert stages == ["load", "split", "index", "retrieve", "prompt", "answer"]
    load = table.split("<tr data-output")[1]
    assert '<mark class="del">twelve</mark>' in load and '<mark class="ins">six</mark>' in load
    assert table.count('data-badge="verified"') == table.count("<tr data-output") == 6
    #: Point 6, and the command a reader types: the SDK's own, over the two run folders.
    from onetrace_console.render import typed_command
    assert LIMIT in text
    assert typed_command(comparison, store, "diff", text=True) in text
    assert "RUN_A" not in text


def test_the_trace_is_its_own_run_its_json_the_sdks_bytes_and_the_text_diff_unchanged(golden,
                                                                                        tmp_path):
    comparison, store, _ = golden
    run = comparison.verb(TRACE)
    assert run.shown_command == SHOWN_COMMAND and "--no-follow" not in run.command
    assert "--out" in run.command and "--runs-root" in run.command
    #: The recorded command, by hand over the same folders, prints the same bytes.
    argv = list(run.command)
    argv[argv.index("--out") + 1] = str(tmp_path / "by-hand")
    assert subprocess.run(argv, capture_output=True, env=utf8_env()).stdout == store.get(run.stdout_key)
    #: The text diff's own run is still `--no-follow`, its trace "not followed".
    plain = comparison.verb(TEXT_DIFF)
    assert "--no-follow" in plain.command
    no_follow = json.loads(store.get(plain.stdout_key))
    assert [t["status"] for t in no_follow["corpus_traces"]] == ["not followed"]


def test_every_recorded_cause_is_one_row_as_the_sdk_lists_it(golden, examined):
    comparison, store, page = golden
    doc = _trace_doc(comparison, store)
    causes = next(n for n in doc["nodes"] if n["node"] == "retrieve")["causes"]
    board = _board(page)
    section = re.search(r'data-section="where-started-causes">(.*?)</section>', board, re.S).group(1)
    rows = re.findall(r'<tr data-cause="([^"]+)"><td>([^<]+)</td>.*?<td data-status="[^"]+">([^<]+)'
                      r"</td></tr>", section)
    examined(len(causes), "causes the SDK listed")
    assert rows == [(c["name"], c["kind"], c["status"]) for c in causes]
    assert ("corpus link", "changed") in {(c["kind"], c["status"]) for c in causes}


# ----------------------------------------------------------------- only where a link changed

def test_no_trace_run_and_no_board_where_no_corpus_link_changed(store, tmp_path, examined):
    """The ingest pair itself: its first difference (load) records no corpus link."""
    _require_warranty()
    a, b = _store_run(store, RUNS / "ingest-v1"), _store_run(store, RUNS / "ingest-v2")
    comparison = compare(a, b, store, ran_at=FIXED_RAN_AT)
    examined(len(comparison.verbs), "runs the comparison made")
    assert comparison.verb(TEXT_DIFF) is not None and comparison.verb(TRACE) is None
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    assert "Where the change started" not in page and LIMIT not in page


def test_a_comparison_stored_without_its_trace_is_made_again(golden):
    comparison, store, _ = golden
    store.put_comparison(replace(comparison, verbs=tuple(v for v in comparison.verbs
                                                         if v.verb != TRACE)))
    again = compare(store.get_run(comparison.run_a), store.get_run(comparison.run_b), store,
                    ran_at=FIXED_RAN_AT)
    assert again.verb(TRACE) is not None


def test_without_its_trace_run_the_page_has_no_board(golden):
    """c171976's rule: absent unless the comparison holds the trace a changed link made."""
    comparison, store, _ = golden
    older = replace(comparison, verbs=tuple(v for v in comparison.verbs if v.verb != TRACE))
    assert "Where the change started" not in render_diff(older, store, generated_at=GENERATED_AT)


# ------------------------------------------------------------- the runs root, and the reasons

def _reason(comparison, store) -> str:
    (entry,) = _trace_doc(comparison, store)["corpus_traces"]
    assert entry["status"] == "could not check"
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    board = unescape(_board(page))
    assert entry["reason"] in board, "the SDK's reason is not on the board word for word"
    assert LIMIT in board
    return entry["reason"]


def test_a_linked_run_the_store_does_not_hold_reads_not_found(store, tmp_path):
    _require_warranty()
    comparison = _pair(store, tmp_path, ingest=())
    reason = _reason(comparison, store)
    assert reason.startswith("linked ingest run not found: sha256:") and reason.endswith(
        "; pass --runs-root")


def test_a_linked_run_whose_own_check_failed_reads_did_not_verify_not_not_found(store, tmp_path):
    """Every run the store holds whole is laid out, whatever its own check said."""
    _require_warranty()
    tampered = _changed(tmp_path, "ingest-v2", lambda f: (f / "artifacts" / "01-load" / "return.json")
                        .write_bytes((f / "artifacts" / "01-load" / "return.json").read_bytes()
                                     .replace(b"six", b"ten")))
    comparison = _pair(store, tmp_path, ingest=("ingest-v1", tampered))
    held = [r for r in store.runs() if r.run_id == "ingest-v2"]
    assert held and held[0].check_verdict == "contradicts", "the stored run's own check passed"
    reason = _reason(comparison, store)
    assert reason == f"linked ingest run did not verify: {held[0].key}"
    #: A tampered ingest artifact: its text is never shown.
    assert "ten months" not in render_diff(comparison, store, generated_at=GENERATED_AT)


def test_a_linked_run_the_store_does_not_hold_whole_is_left_out_and_reads_not_found(store, tmp_path):
    _require_warranty()
    for name in ("ingest-v1", "ingest-v2"):
        _store_run(store, RUNS / name)
    v2 = next(r for r in store.runs() if r.run_id == "ingest-v2")
    #: One of its objects gone from the store: not held whole.
    store._object_path(v2.listing[-1][1]).unlink()
    root = tmp_path / "root"
    laid = runs_root(store, {v2.chain_head}, root)
    assert laid == [] and not any(root.iterdir()), "a run not held whole was laid out, or part of it"
    a, b = _store_run(store, RUNS / "query-v1"), _store_run(store, RUNS / "query-v2")
    comparison = compare(a, b, store, ran_at=FIXED_RAN_AT, work_root=tmp_path / "work")
    assert _reason(comparison, store).startswith("linked ingest run not found: ")


def test_linked_runs_that_are_not_comparable_read_the_sdks_reason(store, tmp_path):
    def linear(folder):
        manifest = json.loads((folder / "MANIFEST.json").read_text())
        manifest.pop("edges")
        (folder / "MANIFEST.json").write_text(json.dumps(manifest))
    comparison = _pair(store, tmp_path, ingest=("ingest-v1", _changed(tmp_path, "ingest-v2", linear)))
    assert _reason(comparison, store) == ("the linked ingest runs are not comparable: one run "
                                          "records a topology and the other does not")


@pytest.mark.parametrize("reason", [
    "the baseline records no corpus link at retrieve",
    "the candidate records no corpus link at retrieve",
    "the linked ingest runs could not be compared: could not check load",
])
def test_the_other_reasons_render_word_for_word(golden, reason, examined):
    """The reasons the warranty pair can't be made to give, in the shape the SDK writes them."""
    comparison, store, _ = golden
    doc = copy.deepcopy(_trace_doc(comparison, store))
    entry = doc["corpus_traces"][0]
    for key in ("heading", "first_line", "documents", "second_hop", "envelope", "nodes"):
        entry.pop(key)
    entry["status"], entry["reason"] = "could not check", reason
    if "no corpus link" in reason:
        side = reason.split()[1]
        entry[side] = {"chain_head": None, "run_id": None, "path": None, "verified": None}
    doc = read_traces(json.dumps(doc), followed=True)
    html = render_board7(doc, "q")
    examined(1, "reason drawn")
    assert f"<p data-trace-reason>{reason}</p>" in html
    assert "<mark" not in html and 'data-badge="verified"' not in html


def test_runs_the_trace_cannot_reach_change_nothing(store, tmp_path):
    """Only runs whose manifest names a chain head the trace looks for are laid out; the SDK's
    finder takes nothing else, so laying out every held run gives the same document."""
    _require_warranty()
    comparison = _pair(store, tmp_path)
    keys = runs_root(store, {r.chain_head for r in store.runs()}, tmp_path / "every")
    assert len(keys) == 4
    run = comparison.verb(TRACE)
    argv = list(run.command)
    argv[argv.index("--runs-root") + 1] = str(tmp_path / "every")
    argv[argv.index("--out") + 1] = str(tmp_path / "out-every")
    every = subprocess.run(argv, capture_output=True, env=utf8_env()).stdout
    assert json.loads(every) == json.loads(store.get(run.stdout_key))


# ------------------------------------------------------------------ never unverified text

def test_ingest_outputs_the_sdk_did_not_verify_show_its_reason_never_text(store, tmp_path):
    _require_warranty()
    bare = _changed(tmp_path, "ingest-v2", lambda f: shutil.rmtree(f / "artifacts"))
    comparison = _pair(store, tmp_path, ingest=("ingest-v1", bare))
    (entry,) = _trace_doc(comparison, store)["corpus_traces"]
    board = _board(render_diff(comparison, store, generated_at=GENERATED_AT))
    ingest = [r for r in board.split("<tr data-output")[1:] if "ingest-v1 → ingest-v2" in r]
    assert len(ingest) == 3
    for row in ingest:
        assert 'data-verified="false"' in row and "<mark" not in row
        assert "not shown: return.json is missing" in unescape(row)
    assert "six months" not in "".join(ingest)


def test_an_ingest_output_not_marked_verified_is_never_drawn_even_handed_lines(golden):
    comparison, store, _ = golden
    doc = copy.deepcopy(_trace_doc(comparison, store))
    out = doc["corpus_traces"][0]["nodes"][0]["outputs"][0]
    out["verified"], out["reason"] = False, "not shown: return.json does not match its receipt"
    html = render_board7(doc, "q")       # past the reader, which refuses it: the renderer's guard
    row = html.split("<tr data-output")[1]
    assert "twelve" not in row and "six" not in row and "verified" not in row.replace(
        'data-verified="false"', "")
    assert "not shown: return.json does not match its receipt" in unescape(row)


def test_no_count_is_drawn_that_the_json_does_not_hold(golden):
    comparison, store, _ = golden
    doc = copy.deepcopy(_trace_doc(comparison, store))
    doc["corpus_traces"][0]["documents"] = None
    html = render_board7(read_traces(json.dumps(doc), followed=True), "q")
    assert "<p data-documents>" not in html


# ------------------------------------------------------------------------ read strictly

def _refused(doc: dict, match: str) -> None:
    with pytest.raises(TextDiffUnreadable, match=match):
        read_traces(json.dumps(doc), followed=True)


def test_the_trace_is_read_strictly(golden):
    comparison, store, _ = golden
    doc = _trace_doc(comparison, store)
    for change, match in [
        (lambda e: e.update(colour="red"), "not been taught"),
        (lambda e: e.update(status="guessed"), "status"),
        (lambda e: e["candidate"].update(verified=None), "not found and verified"),
        (lambda e: e["candidate"].update(verified=False), "did not verify and still names its run"),
        (lambda e: e.update(reason="x"), "not been taught"),
        (lambda e: e["documents"].update(total=3), "decimal"),
        (lambda e: e.update(envelope="refused"), "envelope"),
        (lambda e: e["baseline"].update(chain_head="sha256:00"), "digest"),
    ]:
        bad = copy.deepcopy(doc)
        change(bad["corpus_traces"][0])
        _refused(bad, match)
    not_followed = copy.deepcopy(doc)
    not_followed["corpus_traces"][0] = {"node": "retrieve", "status": "not followed", "also_at": [],
                                        "baseline": {"chain_head": None},
                                        "candidate": {"chain_head": None}}
    _refused(not_followed, "not followed in a run made to follow it")


def test_an_unreadable_trace_says_so_and_keeps_the_limit_line(golden):
    comparison, store, _ = golden
    run = comparison.verb(TRACE)
    broken = replace(comparison, verbs=tuple(
        replace(v, stdout_key=store.put(b'{"format": "x"}')) if v.verb == TRACE else v
        for v in comparison.verbs))
    board = unescape(_board(render_diff(broken, store, generated_at=GENERATED_AT)))
    assert "This console can't read this text diff: " in board and LIMIT in board
    from onetrace_console.render import typed_command
    assert typed_command(comparison, store, "diff", text=True) in board


# ------------------------------------------------------------------------- visible text

#: Board 7's new lines on the golden pair's Diff page, each declared (WO-B7 §3): what the page gains
#: when the comparison holds its trace run. Nothing on the page is gone or reworded. Normalised as
#: tools/visible_text.py normalises (digests to <hex>).
_ITEM11 = "board 7's heading, sections and fixed words"
_SDK = "the SDK's own words from the trace run's JSON"
_ROW = "a changed-text row, the SDK's text as it gave it"
BOARD7_NEW = {
    "Where the change started": _ITEM11,
    "Every recorded cause checked": _ITEM11,
    "The ingest chain": _ITEM11,
    "Changed text, from the source document to the answer": _ITEM11,
    LIMIT: "the limit line, always shown",
    #: The command as a reader types it, over the golden pair's two run folders.
    'Command: onetrace diff runs/query-v1 runs/query-v2 --text': "the trace's command, as a reader types it",
    "first difference: retrieve — output text changed; settings unchanged; corpus link changed; "
    "input help_centre changed": _SDK,
    "traced into the linked ingest runs: ingest-v1 -> ingest-v2": _SDK,
    "started at: load — 1 of 3 documents changed (help-centre/warranty.md); settings unchanged": _SDK,
    "retrieve": _SDK,
    "load · FIRST DIFFERENCE": _SDK,
    "split · downstream": _SDK,
    "index · downstream": _SDK,
    "1 of 3 documents changed": "the one count the SDK gives, documents changed",
}


def test_board7_s_new_lines_are_each_declared_and_nothing_else_changes(golden, examined):
    from tools.visible_text import blocks
    comparison, store, page = golden
    older = replace(comparison, verbs=tuple(v for v in comparison.verbs if v.verb != TRACE))
    before = Counter(blocks(render_diff(older, store, generated_at=GENERATED_AT)))
    after = Counter(blocks(page))
    gone, new = before - after, after - before
    examined(sum(new.values()), "new text blocks")
    assert not gone, f"gone from the page: {sorted(gone)}"
    #: Everything new is board 7's; its tables' cells are the JSON's values, row by row (the tests
    #: above hold them to the SDK's), and every other line is declared.
    board = _board(page) + "</section>"
    assert new == Counter(blocks(board))
    lines = Counter(blocks(re.sub(r"<table>.*?</table>", "", board, flags=re.S)))
    assert set(lines) == set(BOARD7_NEW), (sorted(set(lines) - set(BOARD7_NEW)),
                                           sorted(set(BOARD7_NEW) - set(lines)))
    assert sum(new.values()) > sum(lines.values()), "no table drawn"
