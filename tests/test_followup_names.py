"""The follow-up batch, part 2.

- A run_id or stage name longer than 256 characters is shown capped on every page, the
  console's own included, with the whole value offered for download as the run's own record
  (`runs/<key>/record.tar`). Keys, links and comparisons use the whole value.
- A later ingest re-read every stored run's large receipts: each run's list row and recorded
  digests are now kept when it is checked, and the lists and Home read them from the record.
- Runs stored before this batch are re-derived at start-up -- rung 3, the receipts delivered,
  the list row, the digests -- from their stored bytes, without running the check again, so none
  reads "not established" for good.
- A lone surrogate in the manifest's identity (run_id, chain_head) is still a 422; anywhere
  else in the record it is stored, and shown escaped.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest

from onetrace_console.pages import ANSWER, AUTHORIZATION, CASE, RUN_PROOF, render_execution
from onetrace_console.render import HOME, render_all
from tests.conftest import make_tar
from tests.test_pages import GENERATED_AT, checked  # noqa: F401  (fixture)
from tests.test_unreadable import _renamed, _resummed, _stored, _text

LONG_ID = "r" * 256 + "IDTAIL" + "x" * 738


def _with_run_id(files, run_id: str) -> dict[str, bytes]:
    out = dict(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["run_id"] = run_id
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    return _resummed(out)


def _outside_verbatim(page: str) -> str:
    return re.sub(r"<pre[^>]*>.*?</pre>", "", page, flags=re.S)


# ------------------------------------------------------------------------------- §5

def test_a_long_run_id_is_capped_on_every_page_with_its_record_offered(files, store):
    from onetrace_console.unreadable import (render_unchecked_run, render_unreadable_run,
                                             unshowable_runs_block)
    from onetrace_console.pages import render_executions
    run = _stored(_with_run_id(files, LONG_ID), store)
    pages = dict(render_all(store, generated_at=GENERATED_AT))
    pages.update({f"run/{k}": v for k, v in
                  render_execution(run, store, generated_at=GENERATED_AT).pages.items()})
    pages["unreadable"] = render_unreadable_run(run, "why", generated_at=GENERATED_AT)
    pages["unchecked"] = render_unchecked_run(run, generated_at=GENERATED_AT)
    listed = render_executions([], store, generated_at=GENERATED_AT, of=1)
    pages["unshowable"] = unshowable_runs_block(listed, [(run, "why", True)])
    link = f'href="/runs/{run.key}/record.tar" download'
    showing = set()
    for name, page in pages.items():
        assert "IDTAIL" not in _outside_verbatim(page), name
        if "r" * 256 in page:
            showing.add(name)
            assert link in page, f"{name} shortens the run_id and offers no record"
    assert {HOME, "executions-all.html", f"run/{ANSWER}", f"run/{CASE}", f"run/{AUTHORIZATION}",
            "unreadable", "unchecked", "unshowable"} <= showing, set(pages) - showing


def test_a_long_declared_stage_name_is_capped_on_home(files, store):
    stage = "s" * 256 + "STAGETAIL" + "y" * 400
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    for entry in manifest["chain"]:
        receipt = json.loads(out[entry["file"]].decode("utf-8"))
        receipt["coverage"]["declared_stages"] = receipt["coverage"]["declared_stages"] + [stage]
        out[entry["file"]] = json.dumps(receipt).encode("utf-8")
    _stored(_resummed(out), store)
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    assert "STAGETAIL" not in home and "s" * 256 in home


def test_the_whole_run_id_is_kept_for_keys_and_the_record(files, store):
    from onetrace_console.ingest import bundle
    from onetrace_console.store import run_key
    run = _stored(_with_run_id(files, LONG_ID), store)
    assert run.run_id == LONG_ID and run.key == run_key(LONG_ID, run.chain_head)
    manifest = dict((p, k) for p, k in run.listing)["MANIFEST.json"]
    assert json.loads(store.get(manifest))["run_id"] == LONG_ID
    assert LONG_ID.encode() in bundle(run, store)


# ----------------------------------------------------------------------------- SF1

def test_a_runs_list_row_and_digests_are_kept_when_it_is_checked(checked):  # noqa: F811
    row = json.loads(checked.list_row)
    assert row["step_count"] == 3 and "case_for" in row
    digests = json.loads(checked.digests)
    assert digests and all(len(d) == 3 for d in digests)


def test_lists_and_home_read_no_receipt_of_a_checked_run(checked, store, monkeypatch):  # noqa: F811
    """Every later render read every stored run's receipts again (the round-4 reviewer's
    probe_after: one upload of three 14 MB receipts made every later ingest take 40 s)."""
    import onetrace_console.checks as checks
    import onetrace_console.viewer.record as record

    def no(*a, **k):
        raise AssertionError("a render read a checked run's record again")
    monkeypatch.setattr(record, "read_record", no)
    monkeypatch.setattr(checks, "materialise", no)
    real_get = store.get
    manifest_key = dict(checked.listing)["MANIFEST.json"]
    receipts = {k for p, k in checked.listing if p.startswith("receipts/")}

    def get(key):
        if key in receipts or key == manifest_key:
            raise AssertionError("a render read a checked run's receipt or manifest again")
        return real_get(key)
    monkeypatch.setattr(store, "get", get)
    from onetrace_console.unreadable import PAGE_FAILED
    pages = render_all(store, generated_at=GENERATED_AT)
    assert f'data-run="{checked.run_id}"' in pages["executions-all.html"]
    assert PAGE_FAILED not in _text(pages[HOME]), "Home was drawn, from the record alone"
    assert "could not be read, so no change is marked" not in _text(pages[HOME])


# ------------------------------------------------------------------ runs stored before

def test_a_run_stored_before_this_batch_is_re_derived_at_start_up(checked, store,  # noqa: F811
                                                                  tmp_path):
    from onetrace_console.serve import _render_startup_pages
    old = replace(checked, nothing_missing="", list_row="", digests="", derived="",
                  recorded_count=7)
    store.put_run(old)
    root = tmp_path / "root"
    root.mkdir()
    _render_startup_pages(store, root)
    again = store.get_run(checked.key)
    assert again.nothing_missing == checked.nothing_missing
    assert again.recorded_count == 3, "the receipts delivered, recounted"
    assert again.list_row and again.digests and again.derived
    assert (again.check_report, again.check_verdict) == (checked.check_report,
                                                         checked.check_verdict), \
        "the check is not run again: its report and verdict are as stored"


# ------------------------------------------------------------------------------- §7

def test_a_lone_surrogate_in_the_run_id_is_still_refused(files, store):
    from onetrace_console.ingest import Rejection, accept
    out = dict(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["run_id"] = "__PLANTED__"
    out["MANIFEST.json"] = json.dumps(manifest).replace('"__PLANTED__"', '"a\\ud800"').encode()
    assert isinstance(accept(make_tar(_resummed(out)), store), Rejection)


def test_a_lone_surrogate_elsewhere_in_the_record_is_stored_and_shown_escaped(files, store):
    """A stage name carrying one made the whole run "can't be shown"; a chain entry's
    stage in the manifest carrying one was refused at ingest."""
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["chain"][1]["stage"] = "__STAGE__"
    rel = manifest["chain"][1]["file"]
    receipt = json.loads(out[rel].decode("utf-8"))
    receipt["stage"]["name"] = "__STAGE__"
    for entry in manifest["chain"]:
        declares = json.loads(out[entry["file"]].decode("utf-8"))
        declares["coverage"]["declared_stages"] = declares["coverage"]["declared_stages"] + [
            "__STAGE__"]
        if entry["file"] == rel:
            receipt["coverage"] = declares["coverage"]
        else:
            out[entry["file"]] = json.dumps(declares).replace(
                '"__STAGE__"', '"al\\ud800pha"').encode()
    out[rel] = json.dumps(receipt).replace('"__STAGE__"', '"al\\ud800pha"').encode()
    out["MANIFEST.json"] = json.dumps(manifest).replace('"__STAGE__"', '"al\\ud800pha"').encode()
    run = _stored(_resummed(out), store)
    from onetrace_console.unreadable import RUN_FAILED, TITLE
    drawn = render_execution(run, store, generated_at=GENERATED_AT).pages
    #: Both views: the case, which names the stage, is on "Proof" for a run whose records don't hold up.
    case = drawn[CASE] + drawn[RUN_PROOF]
    case.encode("utf-8")
    assert TITLE not in _text(case) and RUN_FAILED not in _text(case)
    assert "al\\ud800pha" in case
    render_all(store, generated_at=GENERATED_AT)[HOME].encode("utf-8")
