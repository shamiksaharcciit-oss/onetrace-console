"""Console 0.6.1 item 1: the confirm button shows the download.

Turning neighbours on with a local model fetches its files in a background thread; the POST answers 303
to the setup page at once, and that page says "Fetching <model>: <n> of <m> files checked", refreshing
itself every 2 s (a `<meta>` refresh, no script) until "Neighbours are on". One fetch at a time: a second
press is answered "already fetching" and starts nothing; the confirm button is disabled while one runs.

The model here is a tiny one of two files whose `get` is a function of the test, so a fetch can be held
open at a chosen file.
"""
from __future__ import annotations

import hashlib
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from tests.http_limits import limit
from tests.test_neighbours import needs_extra

DATA = {"onnx/model.onnx": b"weights", "tokenizer.json": b"{}"}


@pytest.fixture
def tiny(monkeypatch):
    """A two-file model, named among the local embedders, and the fetch state cleared before and after."""
    from onetrace_console.neighbours import embedder, fetching
    model = embedder.Model("tiny", "example/tiny", "0" * 40, "mean", "none",
                           {p: hashlib.sha256(d).hexdigest() for p, d in DATA.items()})
    monkeypatch.setattr(embedder, "MODELS", {**embedder.MODELS, "tiny": model})
    fetching._FETCHES.clear()
    yield model
    for f in list(fetching._FETCHES.values()):
        if f.thread is not None:
            f.thread.join(timeout=limit(30))
    fetching._FETCHES.clear()


def _store(tmp_path):
    from onetrace_console.store import Store
    return Store(tmp_path / "store")


class Gate:
    """A `get` that serves the tiny model's files, holding `tokenizer.json` until `open()`."""

    def __init__(self, model, tampered: bool = False):
        self.model, self.tampered = model, tampered
        self.asked: list[str] = []
        self.release = threading.Event()
        self.waiting = threading.Event()

    def __call__(self, url: str) -> bytes:
        path = url.split(f"/resolve/{self.model.revision}/", 1)[1]
        self.asked.append(path)
        if path == "tokenizer.json":
            self.waiting.set()
            assert self.release.wait(limit(30)), "the test never let the fetch go on"
            if self.tampered:
                return b"tampered"
        return DATA[path]


def _wait(cond, what: str):
    import time
    end = time.monotonic() + limit(30)
    while not cond():
        if time.monotonic() > end:
            pytest.fail(f"timed out waiting for {what}")
        time.sleep(0.01)


LOCAL = {"kind": "local", "model": "tiny"}


def _start(store, gate):
    from onetrace_console.neighbours import fetching, settings
    return fetching.start(store, LOCAL, who="a test", confirmed=settings.confirmation(LOCAL), get=gate)


def test_the_page_during_a_fetch_counts_the_files_checked_and_refreshes_itself(tiny, tmp_path):
    from onetrace_console.neighbours import fetching, settings
    from onetrace_console.neighbours.pages import document
    store, gate = _store(tmp_path), Gate(tiny)
    state = _start(store, gate)
    assert gate.waiting.wait(limit(30))
    page = document(store)
    assert "Fetching tiny: 1 of 2 files checked" in page
    assert '<meta http-equiv="refresh" content="2">' in page
    #: No script of its own: the head's theme line is every page's.
    assert "<script" not in page.split("<body", 1)[1]
    #: While it runs, the page offers nothing to press but the way back.
    assert 'action="/neighbours/on"' not in page
    gate.release.set()
    state.thread.join(limit(30))
    assert settings.read(store)["embedder"] == LOCAL
    page = document(store)
    assert "Neighbours are on, with example/tiny at revision" in page
    assert 'http-equiv="refresh"' not in page and "Fetching" not in page
    assert fetching.now(store) is None


def test_a_refused_file_is_named_and_nothing_is_turned_on(tiny, tmp_path):
    from onetrace_console.neighbours import embedder, fetching, settings
    from onetrace_console.neighbours.pages import document
    store, gate = _store(tmp_path), Gate(tiny, tampered=True)
    state = _start(store, gate)
    gate.release.set()
    state.thread.join(limit(30))
    assert settings.read(store) is None
    page = document(store)
    assert re.search(r'data-neighbours="refused" role="alert">Not turned on: tiny: tokenizer\.json as fetched has '
                     r"sha256 [0-9a-f]{64}, not the pinned", page)
    assert 'http-equiv="refresh"' not in page
    assert not (embedder.folder(embedder.models_root(store), tiny) / "tokenizer.json").exists()
    #: The choice is offered again, to try once more.
    assert 'data-section="choose"' in page and not fetching.running(store)


def test_a_wrong_confirmation_refuses_before_anything_is_fetched(tiny, tmp_path):
    from onetrace_console.neighbours import embedder, fetching
    store = _store(tmp_path)
    with pytest.raises(embedder.Refused):
        fetching.start(store, LOCAL, who="a test", confirmed="yes", get=lambda url: pytest.fail("fetched"))
    assert fetching.now(store) is None


def test_a_second_press_while_fetching_starts_nothing_and_the_button_is_disabled(tiny, tmp_path):
    from onetrace_console.neighbours import fetching, settings
    from onetrace_console.neighbours.pages import document
    store, gate = _store(tmp_path), Gate(tiny)
    state = _start(store, gate)
    assert gate.waiting.wait(limit(30))
    with pytest.raises(fetching.AlreadyFetching):
        _start(store, Gate(tiny))
    confirm = document(store, query={"embedder": "tiny"})
    assert re.search(r'<button type="submit" disabled>Confirm and turn on</button>', confirm)
    gate.release.set()
    state.thread.join(limit(30))
    assert gate.asked == ["onnx/model.onnx", "tokenizer.json"]
    assert settings.read(store) is not None


def test_a_restart_mid_fetch_keeps_the_checked_files_and_fetches_the_rest(tiny, tmp_path):
    """A console stopped mid-fetch: one file kept whole, one cut short. The next confirm checks each by its
    sha256, keeps the whole one and fetches only the other."""
    from onetrace_console.neighbours import embedder, fetching, settings
    store = _store(tmp_path)
    where = embedder.folder(embedder.models_root(store), tiny)
    (where / "onnx").mkdir(parents=True)
    (where / "onnx" / "model.onnx").write_bytes(DATA["onnx/model.onnx"])
    (where / "tokenizer.json").write_bytes(b"{")
    fetching._FETCHES.clear()                      # a new process: nothing remembered
    gate = Gate(tiny)
    gate.release.set()
    _start(store, gate).thread.join(limit(30))
    assert gate.asked == ["tokenizer.json"]
    assert settings.read(store) is not None


@needs_extra
def test_over_http_the_post_answers_at_once_and_a_second_press_is_already_fetching(server, tiny, monkeypatch):
    from onetrace_console.neighbours import fetching, settings
    from onetrace_console.neighbours import embedder
    from onetrace_console.serve import Handler
    base, _root = server
    gate = Gate(tiny)
    monkeypatch.setattr(embedder, "_get", gate)
    #: `fetch`'s default `get` is bound at definition: the server's fetch is given the gate this way.
    real = embedder.fetch
    monkeypatch.setattr(embedder, "fetch", lambda root, model, get=None, progress=None:
                        real(root, model, get=gate, progress=progress))

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    body = urllib.parse.urlencode({"embedder": "tiny", "confirmed": settings.confirmation(LOCAL)}).encode()
    with pytest.raises(urllib.error.HTTPError) as got:
        opener.open(urllib.request.Request(base + "/neighbours/on", data=body), timeout=limit(30))
    assert got.value.code == 303 and got.value.headers["Location"] == "/neighbours/setup"
    assert gate.waiting.wait(limit(30))
    page = urllib.request.urlopen(base + "/neighbours/setup", timeout=limit(30)).read().decode()
    assert "Fetching tiny: 1 of 2 files checked" in page and 'http-equiv="refresh" content="2"' in page
    with pytest.raises(urllib.error.HTTPError) as got:
        opener.open(urllib.request.Request(base + "/neighbours/on", data=body), timeout=limit(30))
    assert got.value.code == 409
    assert "Already fetching tiny; nothing new was started." in got.value.read().decode()
    gate.release.set()
    fetching.now(Handler.store).thread.join(limit(30))
    assert settings.read(Handler.store)["embedder"] == LOCAL
    assert gate.asked == ["onnx/model.onnx", "tokenizer.json"]
