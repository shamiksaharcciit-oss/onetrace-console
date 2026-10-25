"""One reading of the store per request and per build (`Store.reading`).

A page asks the store for every run, and a page holds several such asks; each once read every
run's record again, and checked every object it lists, so one Compare press read the records
hundreds of times over and the public build hundreds of thousands. Now a request, a drawing of
every page, and the public build each read them once, and a write through the store makes the next
read fresh. Held here, each with a sabotage that the check names:

1. within one reading, each run record is read once; a write through the store, or the reading's
   end, makes the next read fresh; another thread's reading is its own;
2. after one Compare press stores what it compared, the pages it draws read each run record once,
   not once per page;
3. the drawing of every page from a store (`_render_startup_pages`) reads each record once;
4. the public build, as the shared demo is built, reads each record a bounded number of times;
5. a run another hand writes after a request read the store is on the next request's pages.
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

from onetrace_console.store import Store, StoredRun
from tests.test_serve import _post, _real_delivery

EXAM = Path(__file__).resolve().parent.parent / ".sdk-fixtures" / "exam" / "fixtures" / "ingest-r1"
#: The uploads are the exam's preview-format ingest-r1 runs, stored directly, as tests/test_serve.py's
#: are (a new preview delivery is refused since 0.2.0).
pytestmark = pytest.mark.usefixtures("preview_stored_directly")


@contextmanager
def counting(monkeypatch):
    """The run records read from disk while it is open: in all, and since the store's last write."""
    seen = {"all": 0, "since_write": 0}
    real_read, real_forget = StoredRun.from_json, Store._forget

    def counted(text):
        seen["all"] += 1
        seen["since_write"] += 1
        return real_read(text)

    def forgot(self):
        seen["since_write"] = 0
        return real_forget(self)
    monkeypatch.setattr(StoredRun, "from_json", staticmethod(counted))
    monkeypatch.setattr(Store, "_forget", forgot)
    try:
        yield seen
    finally:
        monkeypatch.setattr(StoredRun, "from_json", staticmethod(real_read))
        monkeypatch.setattr(Store, "_forget", real_forget)


def no_reading(monkeypatch):
    """The sabotage: a reading that shares nothing, as before it was made."""
    monkeypatch.setattr(Store, "reading", lambda self: nullcontext(self))


def _runs(names):
    folders = [EXAM / n for n in names]
    if not all(f.is_dir() for f in folders):
        pytest.fail(f"the SDK's exam fixtures are not there under {EXAM}\n    python tools/fetch_sdk_fixtures.py")
    return folders


def _ingested(base, names) -> dict[str, str]:
    keys = {}
    for folder in _runs(names):
        status, body = _post(base, "/v1/runs", _real_delivery(folder))
        assert status == 200, body
        keys[folder.name] = json.loads(body)["run_key"]
    return keys


# ------------------------------------------------------------------ 1. the reading

def test_a_reading_reads_each_record_once_and_a_write_or_its_end_reads_afresh(server, monkeypatch, examined):
    from onetrace_console.serve import Handler
    base, _root = server
    _ingested(base, ["run_C", "run_C_poppler24"])
    store = Handler.store
    n = len(store.runs())
    examined(n, "stored runs")
    with counting(monkeypatch) as seen:
        with store.reading():
            first = store.runs()
            assert store.runs() is first and seen["all"] == n
            #: Another thread's reading is its own: it reads the records itself.
            other = []

            def elsewhere():
                with store.reading():
                    other.append(store.runs())
            t = threading.Thread(target=elsewhere)
            t.start()
            t.join()
            assert seen["all"] == 2 * n and other[0] == first and other[0] is not first
            #: A write through the store: the next read is fresh.
            store.put_run(first[0])
            assert store.runs() is not first and seen["all"] == 3 * n
        store.runs()
        assert seen["all"] == 4 * n


# ------------------------------------------------------------------ 2. a Compare press

def press_reads(base, monkeypatch, a, b) -> int:
    """The run records one press read after its last write to the store: what its pages read."""
    with counting(monkeypatch) as seen:
        status, body = _post(base, f"/compare?a={a}&b={b}")
    assert status == 200, body
    return seen["since_write"]


def test_the_pages_one_compare_press_draws_read_each_run_record_once(server, monkeypatch, examined):
    base, _root = server
    keys = _ingested(base, ["run_B", "run_C", "run_C_poppler24"])
    examined(len(keys), "stored runs")
    assert press_reads(base, monkeypatch, keys["run_C"], keys["run_C_poppler24"]) == len(keys)


def test_sabotage_a_press_without_its_reading_is_named(server, monkeypatch, examined):
    base, _root = server
    keys = _ingested(base, ["run_B", "run_C", "run_C_poppler24"])
    no_reading(monkeypatch)
    examined(1, "planted press")
    assert press_reads(base, monkeypatch, keys["run_C"], keys["run_C_poppler24"]) > len(keys)


# ------------------------------------------------------------------ 3. drawing every page

def drawing_reads(server, monkeypatch) -> tuple[int, int]:
    from onetrace_console.serve import Handler, _render_startup_pages
    base, root = server
    keys = _ingested(base, ["run_B", "run_C", "run_C_poppler24"])
    status, body = _post(base, f"/compare?a={keys['run_C']}&b={keys['run_C_poppler24']}")
    assert status == 200, body
    with counting(monkeypatch) as seen:
        _render_startup_pages(Handler.store, root, Handler.config)
    return seen["all"], len(keys)


def test_drawing_every_page_reads_each_record_once(server, monkeypatch, examined):
    reads, n = drawing_reads(server, monkeypatch)
    examined(n, "stored runs")
    assert reads == n


def test_sabotage_a_drawing_without_its_reading_is_named(server, monkeypatch, examined):
    no_reading(monkeypatch)
    reads, n = drawing_reads(server, monkeypatch)
    examined(1, "planted drawing")
    assert reads > n


# ------------------------------------------------------------------ 4. the public build

#: Each run record read at most this many times in the public build. Before one reading per build
#: it was about 4275 times each (205201 reads of 48 records, counted before the change); with it, about 26:
#: each run's delivery is a write, so the read after it is fresh. 50 holds that with room.
BUILD_READS_EACH = 50


def test_the_public_build_reads_each_run_record_a_bounded_number_of_times(shared_demo, examined):
    runs = len(Store(shared_demo["folder"] / "store" / "store").runs())
    examined(runs, "runs in the build")
    assert shared_demo["run_records_read"] <= BUILD_READS_EACH * runs, shared_demo["run_records_read"]


# ------------------------------------------------------------------ 5. another hand's run

def runs_page_keys(root) -> set[str]:
    import re
    page = (root / "pages" / "executions-all.html").read_text(encoding="utf-8")
    return set(re.findall(r'runs/([0-9a-f]{64})/case\.html', page))


def test_a_run_written_after_a_request_read_the_store_is_on_the_next_requests_pages(server, examined):
    """The console's store reads it; then another hand -- another process, a second store over the
    same folder -- stores a run; the next request draws the pages again, and lists it."""
    from onetrace_console.ingest import accept
    from onetrace_console.serve import Handler
    base, root = server
    keys = _ingested(base, ["run_C", "run_C_poppler24"])
    status, body = _post(base, f"/compare?a={keys['run_C']}&b={keys['run_C_poppler24']}")
    assert status == 200, body
    assert set(keys.values()) <= runs_page_keys(root)
    (b_folder,) = _runs(["run_B"])
    accepted = accept(_real_delivery(b_folder), Store(Handler.store.root), limits=Handler.config)
    late = accepted.run.key
    assert late not in runs_page_keys(root)
    #: B against C: a pair the SDK compares, so the press draws the pages again.
    status, body = _post(base, f"/compare?a={late}&b={keys['run_C']}")
    assert status == 200, body
    examined(1, "run written by another hand")
    assert late in runs_page_keys(root), body
