"""The follow-up batch, after the merges and B5.

SF4   Three cases reachable only by editing the store's own files: a re-delivery over a run record
      that cannot be read answered 500; a stored path or key was followed outside the store; an
      absurd segment number in the access log's HEAD.json broke every request.
SF2   A run whose chain spells `./receipts/…` had its recorded digests read as unreadable, so it
      was left out of the change markers and same-change matching (`overview.py:189` compared the
      chain's name as written).
SF3   "Delivered" counts only files the chain names that are receipts, not `notes.txt`.
Paths The Diff page's SDK text printed the server's temporary folders.
Record A page that shortens a run's words offers the whole value for download as the run's own
      record: `runs/<key>/record.tar`, the delivery as it arrived, byte for byte.
"""
from __future__ import annotations

import json
import re
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from onetrace_console.ingest import Rejection, accept, bundle
from onetrace_console.render import HOME, render_all
from tests.conftest import make_tar, server  # noqa: F401  (fixture)
from tests.test_pages import GENERATED_AT, checked  # noqa: F401  (fixture)
from tests.test_review_fixes import _refused_in_words, _serve_with
from tests.test_unreadable import _renamed, _resummed, _stored, _text


# ---------------------------------------------------------------------------------- SF4

def test_a_re_delivery_over_a_record_that_cannot_be_read_is_said_not_a_500(server, files):
    from onetrace_console.serve import Handler
    from tests.test_serve import _post
    base, _root = server
    run = _stored(files, Handler.store)
    path = Handler.store.root / "runs" / f"{run.key}.json"
    path.write_text("{not json", encoding="utf-8")
    status, body = _post(base, "/v1/runs", make_tar(files))
    assert status == 409, body[:300]
    answer = json.loads(body)
    assert any("cannot be read" in r and f"{run.key}.json" in r for r in answer["rows"]), answer
    assert "Traceback" not in body.decode("utf-8")


@pytest.mark.parametrize("change", [
    lambda d: d.update(key="..\\..\\..\\escaped_key"),
    lambda d: d.update(key="ab" * 31),
    lambda d: d.update(listing=[["../../escaped.txt", "ab" * 32]]),
    lambda d: d.update(listing=[["C:/escaped.txt", "ab" * 32]]),
    lambda d: d.update(listing=[["receipts\\x.json", "ab" * 32]]),
    lambda d: d.update(listing=[["MANIFEST.json", "../../escaped"]]),
], ids=["key-a-path", "key-short", "listing-dotdot", "listing-drive", "listing-backslash",
        "listing-object-key"])
def test_a_stored_record_naming_a_place_outside_the_store_is_unreadable(checked, store,  # noqa: F811
                                                                        tmp_path, change):
    """The reviewer's probe_store_types2.py: such a record wrote a file outside the store root at
    check time, and pages outside the pages folder at start-up. It is left out and named."""
    from onetrace_console.serve import _render_startup_pages
    path = store.root / "runs" / f"{checked.key}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert store.runs() == ()
    assert any(path.name in u for u in store.unreadable_runs), store.unreadable_runs
    root = tmp_path / "root"
    root.mkdir()
    before = set(Path(tempfile.gettempdir()).glob("escaped*")) | set(tmp_path.glob("escaped*"))
    _render_startup_pages(store, root)
    after = set(Path(tempfile.gettempdir()).glob("escaped*")) | set(tmp_path.glob("escaped*"))
    assert after == before, after - before


def test_a_run_is_never_laid_out_outside_its_folder(checked, store, tmp_path):  # noqa: F811
    """The same, below the record's own check: a run built in memory with such a path."""
    from onetrace_console.checks import materialise
    from onetrace_console.store import StoreError
    run = replace(checked, listing=checked.listing + (("../escaped.txt", checked.listing[0][1]),))
    with pytest.raises(StoreError, match="outside"):
        materialise(run, store, tmp_path / "deep" / "run")
    assert not (tmp_path / "deep" / "escaped.txt").exists()


@pytest.mark.parametrize("head", [
    json.dumps({"segment": 10 ** 400, "segment_size": 0, "chain_head": None}),
    json.dumps({"segment": 1_000_000, "segment_size": 0, "chain_head": None}),
    json.dumps({"segment": 1, "segment_size": 10 ** 400, "chain_head": None}),
], ids=["segment-10e400", "segment-past-its-digits", "segment-size-10e400"])
def test_an_access_log_head_with_an_absurd_number_is_refused_in_words(tmp_path, monkeypatch,
                                                                      capsys, head):
    root = tmp_path / "data"
    (root / "access_log").mkdir(parents=True)
    (root / "access_log" / "HEAD.json").write_text(head, encoding="utf-8")
    assert _serve_with(tmp_path, monkeypatch, {
        "store_root": root.as_posix(), "sign_in": {"enabled": False}}) == 1
    assert "HEAD.json" in _refused_in_words(capsys, "cannot use store_root")


# ---------------------------------------------------------------------- SF2, overview:189

def _chain_spelled(files, spell) -> dict[str, bytes]:
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    for entry in manifest["chain"]:
        entry["file"] = spell(entry["file"])
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    return _resummed(out)


def test_a_chain_spelled_another_way_has_its_digests_read(files, store):
    from onetrace_console.overview import recorded_digests
    run = _stored(_chain_spelled(files, lambda f: "./" + f), store)
    assert run.check_verdict == "holds", run.check_verdict
    digests = recorded_digests(run, store)
    assert digests, "the receipts of a run whose chain spells ./receipts/... were read as none"
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    assert "could not be read, so no change is marked" not in _text(home)


# ---------------------------------------------------------------------------------- SF3

def test_delivered_counts_only_the_receipts_the_chain_names(files, store):
    """A chain naming `notes.txt` and `SHA256SUMS` beside one real receipt read "3 of 3
    delivered" under "Receipts delivered"."""
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    first = manifest["chain"][0]
    manifest["chain"] = [first, dict(first, file="notes.txt"), dict(first, file="SHA256SUMS"),
                         dict(first, file="extra.json")]
    for entry in json.loads(files["MANIFEST.json"].decode("utf-8"))["chain"][1:]:
        del out[entry["file"]]
    out["notes.txt"] = b"a note\n"
    #: JSON, and not a receipt: no receipt format.
    out["extra.json"] = json.dumps({"note": "not a receipt"}).encode("utf-8")
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    accepted = accept(make_tar(_resummed(out)), store)
    assert accepted.run.recorded_count == 1, "as ingest stores it"
    from onetrace_console.checks import run_and_record
    assert run_and_record(accepted.run, store).recorded_count == 1, "as the check derives it"


# ------------------------------------------------------------------------ the temp paths

def test_the_diff_page_prints_no_path_of_this_host(tmp_path, store):
    """The SDK's own text names the folders it was given. The console gives them relative to the
    folder it runs the SDK from, so a page prints no path of this host."""
    from onetrace_console.compare import compare
    from onetrace_console.render import render_diff
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_diff_sdk_text_layer import _forged_pair
    a, b = _forged_pair(tmp_path)
    page = render_diff(compare(_stored(a, store), _stored(b, store), store,
                               ran_at=FIXED_RAN_AT), store, generated_at=GENERATED_AT)
    temp = str(Path(tempfile.gettempdir()).resolve())
    for shown in (temp, temp.replace("\\", "\\\\"), "onetrace-compare-"):
        assert shown not in page, shown
    from html import unescape
    assert "baseline   a  " in unescape(page) and "candidate  b  " in unescape(page)


def test_any_folder_of_this_hosts_temp_folder_is_left_out_of_the_sdk_text(tmp_path, store):
    """Beyond the pair's own folders, which the SDK's report names: any path under this host's
    temp folder the SDK's words carry, shown in whatever form the layer takes."""
    from dataclasses import replace as swap

    from onetrace_console.compare import DIFF, compare, report_text
    from onetrace_console.render import render_diff
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_diff_sdk_text_layer import _forged_pair
    a, b = _forged_pair(tmp_path)
    comparison = compare(_stored(a, store), _stored(b, store), store, ran_at=FIXED_RAN_AT)
    run = comparison.verb(DIFF)
    elsewhere = str(Path(tempfile.gettempdir()) / "onetrace-verify-x1" / "MANIFEST.json")
    text = report_text(comparison, DIFF, store) + f"note: read {elsewhere}\n"
    key = store.put(text.encode("utf-8"))
    swapped = swap(run, reports=tuple((n, key if n == f"{DIFF}.txt" else k)
                                      for n, k in run.reports))
    page = render_diff(swap(comparison, verbs=tuple(swapped if v is run else v
                                                    for v in comparison.verbs)),
                       store, generated_at=GENERATED_AT)
    temp = str(Path(tempfile.gettempdir()))
    assert temp not in page and "onetrace-verify-x1" not in page
    assert "a temporary folder of this host" in page


# ---------------------------------------------------------------------- the record, whole

def test_a_runs_own_record_is_offered_for_download_byte_for_byte(server, files):
    from onetrace_console.serve import Handler
    from tests.test_serve import _get
    base, _root = server
    run = _stored(files, Handler.store)
    status, body = _get(base, f"/runs/{run.key}/record.tar")
    assert status == 200 and body == bundle(run, Handler.store)
    assert _get(base, f"/runs/{'ab' * 32}/record.tar")[0] == 404
    assert _get(base, "/runs/..%2f/record.tar")[0] == 400


def test_the_record_needs_a_viewer_when_sign_in_is_on():
    from onetrace_console.roles import VIEWER, required_role
    assert required_role("GET", f"/runs/{'ab' * 32}/record.tar") == VIEWER
    from onetrace_console.roles import NoRouteTableEntry
    with pytest.raises(NoRouteTableEntry):
        required_role("GET", "/runs/not-a-key/record.tar")


# ------------------------------------------------------------------- the key-order cost

def test_the_key_order_restore_is_not_quadratic_in_the_report():
    """Measured first: 1,000 ladder rows (a 181 KB text) took 4.3 s and 5,000 took 156 s,
    each key of each object searched for through the whole text. Each distinct key is now looked
    up once. 2,000 rows took about 17 s before; the bound is loose, for a loaded machine."""
    import time

    from onetrace_console.render import _ordered_as
    row = {"index": "1", "stage": "s", "verdict": "same", "baseline": {"outputs": []},
           "candidate": {"outputs": []}, "reason": None}
    rep = {"ladder": [dict(row, index=str(i), stage=f"stage-{i}") for i in range(2_000)],
           "annotations": [{"index": str(i), "stage": f"stage-{i}",
                            "differs": {f"k{i}": ["a", "b"], f"c{i}": ["c", "d"]}}
                           for i in range(2_000)]}
    class Counted(str):
        """The stored text, counting its searches: the cost is in them, and a count is exact
        where a clock on a loaded machine is not."""
        searches = 0

        def find(self, *a, **k):
            Counted.searches += 1
            return super().find(*a, **k)

    stored = Counted("\n".join(f"stage-{i}  c{i}  k{i}" for i in range(2_000)) * 3)
    started = time.perf_counter()
    ordered = _ordered_as(rep, stored)
    distinct = {"ladder", "annotations", "index", "stage", "verdict", "baseline", "candidate",
                "reason", "outputs", "differs"} | {f"{p}{i}" for p in "kc" for i in range(2_000)}
    assert Counted.searches == len(distinct), f"{Counted.searches} searches, {len(distinct)} keys"
    assert time.perf_counter() - started < 5
    assert list(ordered["annotations"][7]["differs"]) == ["c7", "k7"], "ordered as the text"
