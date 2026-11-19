"""Any error a request's handling does not catch is answered, never dropped (`serve.Handler._unhandled`).

- A browser meets the console's framed 500 page, with a short reference; any other client, the 500 line with the same
  kind of reference. No traceback, path on this machine or exception text reaches either.
- The full error goes only to the console's own log, under that reference: the request's method and path, then the
  traceback; a public console writes it as one JSON line.
- A failure after the answer has started sends nothing more: the error is logged, and the connection is closed.

Reached here by a test-only stand-in that raises inside a GET's handling (no route of its own).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request

from tests.http_limits import limit

HTML = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
PLANTED = "a planted failure at /home/someone/secret_path.py"
REF = re.compile(r"under reference ([0-9a-f]{8})")


def _get(base, path, headers=None):
    req = urllib.request.Request(base + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=limit(30)) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read().decode("utf-8")


def _raises(monkeypatch):
    from onetrace_console.serve import Handler

    def fails(self, *a, **k):
        raise RuntimeError(PLANTED)

    #: Every GET passes the local guard first thing after reading who asks; the framed page never calls it.
    monkeypatch.setattr(Handler, "_local_guard", fails)


def _says_nothing_of_the_error(said: str) -> None:
    assert "planted" not in said and "secret_path" not in said and "RuntimeError" not in said
    assert "Traceback" not in said and ".py" not in said and "/home/" not in said


def test_a_get_that_raises_is_the_framed_page_with_a_reference_and_the_log_has_the_rest(
    server, monkeypatch, capfd, examined
):
    base, _root = server
    _raises(monkeypatch)
    examined(2, "answers")
    capfd.readouterr()
    status, ctype, page = _get(base, "/", HTML)
    assert status == 500 and ctype.startswith("text/html"), (status, ctype, page[:300])
    assert '<html lang="en">' in page and "<title>The console could not answer · onetrace</title>" in page
    assert '<a href="/">Go to the Overview</a>' in page
    ref = REF.search(page)
    assert ref, page[:600]
    _says_nothing_of_the_error(page)
    err = capfd.readouterr().err
    #: The log: the reference, the method and path, then the traceback with the exception's own words.
    head = f"error {ref.group(1)}: answering GET /"
    assert head in err, err[-2000:]
    after = err[err.index(head) :]
    assert "Traceback (most recent call last)" in after and f"RuntimeError: {PLANTED}" in after

    status, ctype, line = _get(base, "/")
    assert status == 500 and ctype == "text/plain"
    assert re.fullmatch(
        r"the console could not answer this request; its log names the cause under reference [0-9a-f]{8}\n", line
    )
    _says_nothing_of_the_error(line)


def test_each_answer_has_its_own_reference(server, monkeypatch, examined):
    base, _root = server
    _raises(monkeypatch)
    refs = {REF.search(_get(base, "/")[2]).group(1) for _ in range(3)}
    examined(3, "answers")
    assert len(refs) == 3


def _bare(public: bool, started: bool):
    """A handler with no socket, as far as `_unhandled` reads it."""
    from onetrace_console.serve import Handler

    h = Handler.__new__(Handler)
    h.command, h.path = "GET", "/runs/abc/case.html?token=x"
    h._answer_started = started
    h.close_connection = False

    class Config:
        pass

    config = Config()
    config.public = public
    return h, config


def test_a_public_console_logs_one_json_line_and_an_answer_under_way_gets_nothing_more(monkeypatch, capfd, examined):
    from onetrace_console.serve import Handler

    h, config = _bare(public=True, started=True)
    monkeypatch.setattr(Handler, "config", config, raising=False)
    sent = []
    monkeypatch.setattr(Handler, "_respond", lambda self, *a, **k: sent.append(a))
    examined(1, "logged failure")
    try:
        raise RuntimeError(PLANTED)
    except RuntimeError:
        h._unhandled()
    lines = [ln for ln in capfd.readouterr().err.splitlines() if ln.startswith("{")]
    assert len(lines) == 1, lines
    got = json.loads(lines[0])
    assert got["event"] == "error" and re.fullmatch(r"[0-9a-f]{8}", got["reference"])
    assert got["method"] == "GET" and got["path"] == "/runs/abc/case.html", "the path, never its query"
    assert got["exception"] == "RuntimeError" and PLANTED in got["traceback"]
    #: Its answer had started: nothing more is sent, and the connection is closed.
    assert sent == [] and h.close_connection is True


def test_a_client_that_went_away_is_not_answered_again(examined):
    """A broken pipe or a reset connection is the client gone: it reaches the server's own error handling as before."""
    h, _config = _bare(public=False, started=False)
    examined(2, "kinds")
    for gone in (BrokenPipeError, ConnectionResetError):
        try:
            with h._answering():
                raise gone()
        except gone:
            pass
        else:
            raise AssertionError(f"{gone.__name__} was answered as a server error")
    assert sys.exc_info() == (None, None, None)
