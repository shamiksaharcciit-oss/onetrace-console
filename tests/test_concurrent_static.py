"""Static files answer 200 under concurrent requests, and the access log keeps one chain.

Every response leaves through `_respond`, which appends to the access log first and answers 500
where it cannot. The log's append composes an entry from its chain head, writes it, then rewrites
HEAD.json by a replace. Two requests at once, as a page's fonts after a reload are, appended at the
same time: off Windows the chain was broken (two entries naming the same `prev`); on Windows a
replace onto a file another replace is writing is refused, and a font answered 500 among 200s.

Off Windows, Windows' refusal is modelled: a replace onto a target another replace is still
writing raises PermissionError, as Windows' does. The Windows probe runs this file for real.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request

import pytest

FONT = "/static/fonts/IBMPlexSans-Regular-Latin1.woff2"


def _windows_like_replace(real):
    """os.replace as Windows answers two at once onto one target: the second is refused."""
    busy, guard = set(), threading.Lock()

    def replace(src, dst):
        key = os.fspath(dst)
        with guard:
            if key in busy:
                raise PermissionError(13, "Access is denied", key)
            busy.add(key)
        try:
            time.sleep(0.003)
            real(src, dst)
        finally:
            with guard:
                busy.discard(key)
    return replace


def _concurrently(n: int, f) -> list:
    out, start = [None] * n, threading.Barrier(n)

    def one(i):
        start.wait()
        out[i] = f(i)
    threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def test_concurrent_appends_keep_one_chain(tmp_path, monkeypatch, examined):
    from onetrace_console import store as store_module
    from onetrace_console.access_log import AccessLog
    log = AccessLog(tmp_path / "log", max_segment_bytes=10_000_000)
    monkeypatch.setattr(store_module.os, "replace", _windows_like_replace(os.replace))
    errors = []

    def append(i):
        for _ in range(10):
            try:
                log.append(principal="anonymous", method="GET", path=FONT, status=200)
            except BaseException as e:  # noqa: BLE001 - counted
                errors.append(type(e).__name__)
    _concurrently(8, append)
    examined(80, "appends")
    assert errors == []
    assert log.verify_chain() == (True, "")
    assert len(log.read_all_entries()) == 80


def test_concurrent_requests_for_one_font_all_answer_200(server, monkeypatch, examined):
    from onetrace_console import store as store_module
    base, _ = server
    monkeypatch.setattr(store_module.os, "replace", _windows_like_replace(os.replace))

    def get(i):
        try:
            with urllib.request.urlopen(f"{base}{FONT}", timeout=30) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    got = _concurrently(16, get)
    examined(16, "concurrent font requests")
    assert got == [200] * 16


def test_sabotage_the_append_unlocked_is_named(tmp_path, monkeypatch, examined):
    """The append without its lock: the modelled refusal reaches it, and the chain breaks."""
    import contextlib

    from onetrace_console import access_log
    from onetrace_console import store as store_module
    monkeypatch.setattr(store_module.os, "replace", _windows_like_replace(os.replace))
    monkeypatch.setattr(access_log, "_APPEND_LOCK", contextlib.nullcontext())
    log = access_log.AccessLog(tmp_path / "log", max_segment_bytes=10_000_000)
    errors = []

    def append(i):
        for _ in range(10):
            try:
                log.append(principal="anonymous", method="GET", path=FONT, status=200)
            except BaseException as e:  # noqa: BLE001 - counted
                errors.append(type(e).__name__)
    _concurrently(8, append)
    examined(1, "unlocked appends")
    assert errors or log.verify_chain()[0] is False


def test_the_start_up_line_names_the_store_s_own_folder(examined):
    """The line names the folder the store is in, as the explanations' paths use it: the store
    root's `store`, where `x/` and every record are."""
    from onetrace_console.serve import startup_line
    examined(1, "start-up line")
    line = startup_line("http://127.0.0.1:8080", "/srv/demo/store")
    assert line == f"onetrace-console serving on http://127.0.0.1:8080 (store: {os.path.join('/srv/demo/store', 'store')})"
