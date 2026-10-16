"""The dropped-upload 500, reproduced first.

Observed in the console's full suite (775ce4b, run 1): a client gave up on `POST /v1/runs` after its
10 s timeout; the server finished the ingest. Its request read `self.store` -- a class attribute
every test's server shares -- once in `accept()` and again in `run_and_record()`: between the two
the next test's server fixture had swapped `Handler.store`, so the run's objects went to one store
and its record to another. That store's own delivery of the same run then found the record "already
held" and stored nothing (ingest: "a second delivery ... is not stored again"), so the run's
`MANIFEST.json` was never there: its pages failed to draw, and `/compare` raised `StoreError` as a
500.

The expected behaviour: "complete or nothing" -- a run's record is written only once every object
it names is stored; a held run missing an object, delivered again, is refused with 409 and never
repaired; and the store refuses a record whose objects it does not hold, each request keeps one
store, and compare and every page say what is missing, never a 500.
"""
from __future__ import annotations

import json

import pytest

from tests.test_compare import RUN_C, RUN_C_POPPLER24, _require_exam
from tests.test_checks import _require_installed
from tests.test_serve import _post, _real_delivery


#: On the 0.2.0 branch a new preview-format delivery is refused; these tests
#: deliver the exam's preview-format run, so they store it the way the console stores a run it holds
#: (`preview_stored_directly`). Added when the fix was merged into wo-c18-020.
pytestmark = pytest.mark.usefixtures("preview_stored_directly")


def _missing(store, run) -> list[str]:
    return [path for path, key in run.listing if not store.has(key)]


def test_a_record_is_never_written_where_its_objects_are_not(tmp_path):
    """The harness's interleaving, made deterministic: accepted into one store, recorded into
    another. Expected: no run in the second store without its objects."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    _require_installed()
    _require_exam()
    first, second = Store(tmp_path / "first"), Store(tmp_path / "second")
    accepted = accept(_real_delivery(RUN_C), first)
    try:
        run_and_record(accepted.run, second)
    except Exception:  # noqa: BLE001 - refusing to write it is an acceptable outcome
        pass
    held = [r for r in second.runs() if r.key == accepted.run.key]
    assert not held or not _missing(second, held[0]), (
        "a run record is held without its objects: " + ", ".join(_missing(second, held[0])))


def test_compare_of_a_run_whose_object_is_missing_is_never_a_500(server):
    """Whatever left a stored run without one of its objects, comparing it is said, not a 500."""
    from onetrace_console.store import Store
    _require_installed()
    _require_exam()
    base, root = server
    keys = []
    for folder in (RUN_C, RUN_C_POPPLER24):
        status, body = _post(base, "/v1/runs", _real_delivery(folder))
        assert status == 200, body[:300]
        keys.append(json.loads(body)["run_key"])
    store = Store(root / "store")
    run = store.get_run(keys[0])
    (manifest_key,) = [k for p, k in run.listing if p == "MANIFEST.json"]
    store._object_path(manifest_key).unlink()
    #: The run's record for download says the same, as a 409.
    from urllib.error import HTTPError
    from urllib.request import urlopen
    try:
        urlopen(f"{base}/runs/{keys[0]}/record.tar", timeout=30)
        raise AssertionError("the record of a run missing an object was served")
    except HTTPError as e:
        assert e.code == 409 and e.read().decode("utf-8") == (
            "couldn't check: the stored record is missing MANIFEST.json\n")
    status, body = _post(base, f"/compare?a={keys[0]}&b={keys[1]}")
    assert status != 500, body[:300]
    #: Compare refuses the pair in the fixed words.
    assert status == 409, (status, body[:300])
    assert "couldn't check: the stored record is missing MANIFEST.json" in body.decode("utf-8")


MISSING_409 = ("Not stored: this run is already held, but the console is missing {objects} for "
               "it. A held record is never repaired. Remove the held run, then deliver it again.")


def test_the_store_refuses_a_record_whose_objects_it_does_not_hold(tmp_path):
    """A refusal inside the store; no record is written."""
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store, StoreError
    _require_installed()
    _require_exam()
    first, second = Store(tmp_path / "first"), Store(tmp_path / "second")
    run = accept(_real_delivery(RUN_C), first).run
    with pytest.raises(StoreError, match="MANIFEST.json"):
        second.put_run(run)
    assert second.runs() == () and not list((second.root / "runs").glob("*.json"))
    #: Where every object is held, the record is written as before.
    first.put_run(run)
    assert first.get_run(run.key) == run


def test_a_held_run_missing_an_object_delivered_again_is_refused_409_and_not_repaired(tmp_path):
    """Refused with 409 and never repaired: nothing is stored."""
    from onetrace_console.ingest import Rejection, accept
    from onetrace_console.store import Store
    _require_installed()
    _require_exam()
    store = Store(tmp_path / "store")
    delivery = _real_delivery(RUN_C)
    run = accept(delivery, store).run
    (key,) = [k for p, k in run.listing if p == "MANIFEST.json"]
    store._object_path(key).unlink()
    again = accept(delivery, store)
    assert isinstance(again, Rejection) and again.status == 409, again
    assert again.body == MISSING_409.format(objects="MANIFEST.json") + "\n", again.body
    assert not store.has(key), "a held record is never repaired"


def test_each_request_keeps_the_store_it_started_with(server, monkeypatch):
    """The store the console holds is swapped while an ingest is under way -- as the
    next test's server did to a request whose client had gone. The request finishes in the store
    it started in: its record and every object together, and nothing in the other store."""
    from onetrace_console import ingest
    from onetrace_console.serve import Handler
    from onetrace_console.store import Store
    _require_installed()
    _require_exam()
    base, root = server
    started, other = Handler.store, Store(root / "other")
    original = ingest.accept

    def swapped_meanwhile(body, store, **kw):
        #: Between accept() and run_and_record(), where the suite's interleaving fell.
        accepted = original(body, store, **kw)
        Handler.store = other
        return accepted
    monkeypatch.setattr(ingest, "accept", swapped_meanwhile)
    try:
        status, body = _post(base, "/v1/runs", _real_delivery(RUN_C))
    finally:
        Handler.store = started
    assert status == 200, body[:300]
    run = started.get_run(json.loads(body)["run_key"])
    assert run is not None and not _missing(started, run)
    assert other.runs() == ()


def test_a_run_missing_an_object_reads_couldnt_check_on_its_pages_and_in_the_counts(tmp_path):
    """The fixed line, in the shape of the "couldn't check" lines -- never holds or
    contradicts: the run's own pages, and every count and list that reads it."""
    from onetrace_console.checks import COULD_NOT_CHECK, run_and_record
    from onetrace_console.home import tallies
    from onetrace_console.ingest import accept
    from onetrace_console.pages import CASE, render_execution
    from onetrace_console.store import Store
    _require_installed()
    _require_exam()
    from tests.test_reference_demo import RUNS, _delivery
    store = Store(tmp_path / "store")
    #: A run with a verdict of its own under 0.2.0: the reference demo's day 1 (the exam's
    #: preview-format run reads NOT VERIFIED there). Changed at the merge.
    run = run_and_record(accept(_delivery(RUNS / "day-1"), store).run, store)
    assert run.check_verdict != COULD_NOT_CHECK, "the premise: a run with a verdict of its own"
    (key,) = [k for p, k in run.listing if p == "MANIFEST.json"]
    store._object_path(key).unlink()
    words = "couldn't check: the stored record is missing MANIFEST.json"
    held = store.get_run(run.key)
    assert (held.check_verdict, held.check_note) == (COULD_NOT_CHECK, words)
    case = render_execution(held, store, generated_at="2026-10-07T00:00:00+00:00").pages[CASE]
    assert words in case.replace("&#x27;", "'") and 'data-state="couldnt-check"' in case
    t = {x.slug: x for x in tallies(store)}
    assert [r.key for r in t["could-not-check"].runs] == [run.key]
    assert words in t["could-not-check"].reasons
    assert not t["records-agree"].runs and not t["contradicts"].runs and not t["not-checked"].runs


def test_a_raw_run_missing_an_object_renders_could_not_check_not_its_stored_verdict(tmp_path):
    """render_execution() given a raw StoredRun -- built from the record's JSON,
    not through the store, so still carrying its stored verdict -- whose object is missing returns
    could not check, never the stale verdict beside pages that say could not check."""
    from onetrace_console.checks import COULD_NOT_CHECK, run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store, StoredRun
    from tests.test_reference_demo import RUNS, _delivery
    _require_installed()
    store = Store(tmp_path / "store")
    run = run_and_record(accept(_delivery(RUNS / "day-1"), store).run, store)
    (key,) = [k for p, k in run.listing if p == "MANIFEST.json"]
    store._object_path(key).unlink()
    raw = StoredRun.from_json(store._run_path(run.key).read_text(encoding="utf-8"))
    assert raw.check_verdict != COULD_NOT_CHECK, "the premise: the raw record keeps its own verdict"
    rendered = render_execution(raw, store, generated_at="2026-10-07T00:00:00+00:00")
    assert rendered.verdict == COULD_NOT_CHECK
