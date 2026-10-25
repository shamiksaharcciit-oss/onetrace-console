"""The Explain panel while a press runs, and after one fails.

A press starts the work and returns at once; the panel reads the work's state and says what is
happening, in plain words and with the time it started: preparing the comparison, sent to the model
and waiting for its reply, checking the reply, verifying the record. One press at a time per
comparison. Each explanation is verified once, again only where its record's chain head changed.
Every failure says so: the command failed, its exit, and its last line of error output, paths of
this machine shortened. Each attempt keeps its step times, shown under its explanation.

Test fixtures only: the model is a fake endpoint on this machine's loopback, an OpenAI-compatible
one that holds its reply until the test lets it go, replying with tests/fixtures/explain/mixed.json's
text. No model is called and nothing leaves this machine; no key is configured or sent.
"""
from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from tests.test_explain_panel import REPLIES, _panel, _text, pair, toml_string  # noqa: F401  (pair: a fixture)


@pytest.fixture
def endpoint():
    """A fake OpenAI-compatible endpoint on loopback: it answers each request with mixed.json's
    reply once `gate` is set."""
    gate = threading.Event()
    reply = (REPLIES / "mixed.json").read_text(encoding="utf-8")

    class Fake(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            gate.wait(120)
            body = json.dumps({"choices": [{"message": {"content": reply}}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/v1", gate
    finally:
        gate.set()
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def held(pair, endpoint):
    """The pair, with the fake endpoint configured as the model (`openai:test-model`)."""
    store, comparison, config = pair
    base, gate = endpoint
    config.write_text(f'[model]\nprovider = "openai"\nname = "test-model"\nbase_url = {toml_string(base)}\n',
                      encoding="utf-8")
    return store, comparison, gate


def _until(f, seconds: float = 120):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        got = f()
        if got:
            return got
        time.sleep(0.05)
    raise AssertionError("not reached in time")


def running_problems(panel: str, step_words: str) -> list[str]:
    """The panel while a press runs: its step in words, and the time it started."""
    line = re.search(r'<p data-explain="running"[^>]*>(.*?)</p>', panel, re.S)
    if line is None:
        return ["no line says the press is running"]
    text = _text(line.group(1))
    out = []
    if step_words not in text:
        out.append(f"the line does not say {step_words!r}: {text!r}")
    if not re.search(r"started \d\d:\d\d:\d\d UTC", text):
        out.append(f"the line gives no start time: {text!r}")
    return out


# ------------------------------------------------------------------ 1 and 2: say it, don't hold the page

def test_a_press_returns_at_once_and_says_what_it_is_waiting_for(held, examined):
    from onetrace_console import explain
    store, comparison, gate = held
    t = time.monotonic()
    explain.start(comparison, store, send=True)
    assert time.monotonic() - t < 5
    seen = []

    def waiting():
        s = explain.state(store, comparison.key)
        if s["running"] and (not seen or seen[-1] != s["step"]):
            seen.append(s["step"])
        return s["running"] and s["step"] == "waiting" and s
    s = _until(waiting)
    examined(1, "press waiting for its reply")
    assert s["words"] == "Sent to openai:test-model and waiting for its reply"
    assert seen[0] == "preparing"
    assert running_problems(explain.panel(comparison, store, public=False), s["words"]) == []
    gate.set()
    explain.wait(comparison.key, 120)
    assert explain.state(store, comparison.key) == {"running": False}
    assert len(explain.explanations(store, comparison.key)) == 1


def test_a_second_press_while_one_runs_is_refused_in_words(held, examined):
    from onetrace_console import explain
    store, comparison, gate = held
    explain.start(comparison, store, send=True)
    examined(1, "second press")
    with pytest.raises(explain.Busy, match=re.escape(explain.BUSY)):
        explain.start(comparison, store, send=True)
    gate.set()
    explain.wait(comparison.key, 120)


def test_sabotage_the_running_line_left_out_is_named(held, monkeypatch, examined):
    from onetrace_console import explain
    store, comparison, gate = held
    monkeypatch.setattr(explain, "_running_line", lambda s: "")
    explain.start(comparison, store, send=True)
    s = _until(lambda: (lambda s: s["running"] and s["step"] == "waiting" and s)(explain.state(store, comparison.key)))
    examined(1, "panel without its running line")
    assert running_problems(explain.panel(comparison, store, public=False), s["words"]) != []
    gate.set()
    explain.wait(comparison.key, 120)


def test_sabotage_a_press_that_holds_the_page_is_named(held, monkeypatch, examined):
    """The work run in the press itself: the press returns only when the reply has come."""
    from onetrace_console import explain
    store, comparison, gate = held
    monkeypatch.setattr(explain, "_spawn", lambda work: work())
    threading.Timer(6, gate.set).start()
    t = time.monotonic()
    explain.start(comparison, store, send=True)
    examined(1, "press run in place")
    assert time.monotonic() - t >= 5


# ------------------------------------------------------------------ 5: step times

def test_each_attempt_keeps_its_step_times_shown_under_its_explanation(held, examined):
    from onetrace_console import explain
    store, comparison, gate = held
    gate.set()
    explain.start(comparison, store, send=True)
    explain.wait(comparison.key, 120)
    a = explain.attempts(store, comparison.key)[-1]
    examined(4, "step times")
    assert sorted(a["steps"]) == ["model", "post_check", "preparing", "verifying"]
    assert all(re.fullmatch(r"\d+\.\d", v) for v in a["steps"].values()), a["steps"]
    panel = _text(explain.panel(comparison, store, public=False))
    assert re.search(r"Preparing \d+\.\d s · the model's reply \d+\.\d s · the post-check \d+\.\d s · "
                     r"verifying \d+\.\d s", panel), panel


# ------------------------------------------------------------------ 3: verified once

def test_each_explanation_is_verified_once_and_again_only_where_its_record_changed(held, monkeypatch, examined):
    from onetrace_console import explain
    store, comparison, gate = held
    gate.set()
    starts = []
    real = explain._record_verifies
    monkeypatch.setattr(explain, "_record_verifies", lambda folder: starts.append(folder.name) or real(folder))
    for _ in range(2):
        explain.start(comparison, store, send=True)
        explain.wait(comparison.key, 120)
    first, second = sorted(e["record"] for e in explain.explanations(store, comparison.key))
    examined(2, "presses")
    assert starts == [first, second]
    explain.panel(comparison, store, public=False)
    assert starts == [first, second]
    man = explain.folder_of(store, comparison.key) / explain.REPORT / "explain" / first / "MANIFEST.json"
    m = json.loads(man.read_text(encoding="utf-8"))
    m["chain_head"] = "sha256:" + "0" * 64
    man.write_text(json.dumps(m), encoding="utf-8")
    said = explain.verified(store, comparison.key, first)
    assert starts == [first, second, first] and not said.endswith("(exit 0)"), said


def test_sabotage_the_reading_kept_by_name_alone_is_named(held, monkeypatch, examined):
    """The kept reading not keyed by the chain head: a changed record keeps its old reading."""
    from onetrace_console import explain
    store, comparison, gate = held
    gate.set()
    explain.start(comparison, store, send=True)
    explain.wait(comparison.key, 120)
    rec = explain.explanations(store, comparison.key)[0]["record"]
    monkeypatch.setattr(explain, "_chain_head", lambda folder: "the same for every record")
    explain.verified(store, comparison.key, rec)
    man = explain.folder_of(store, comparison.key) / explain.REPORT / "explain" / rec / "MANIFEST.json"
    m = json.loads(man.read_text(encoding="utf-8"))
    m["chain_head"] = "sha256:" + "0" * 64
    man.write_text(json.dumps(m), encoding="utf-8")
    examined(1, "changed record")
    assert explain.verified(store, comparison.key, rec).endswith("(exit 0)")


# ------------------------------------------------------------------ 4: every failure says so

KEY = "d" * 64


def _failed_panel(tmp_path, monkeypatch, attempt: dict) -> str:
    from pathlib import Path

    from onetrace_console import explain
    from onetrace_console.store import Store
    store = Store(tmp_path / "store")
    d = explain.folder_of(store, KEY) / "attempts"
    d.mkdir(parents=True)
    (d / "000001.json").write_text(json.dumps({"n": "1", "kind": "explain", "command": "onetrace-explain r",
                                               "stdout": "", **attempt}), encoding="utf-8")
    (d.parent / explain.REPORT).mkdir()
    monkeypatch.setattr(explain, "command", lambda: Path("onetrace-explain"))
    monkeypatch.setattr(explain, "too_long", lambda store: None)
    return explain.panel(SimpleNamespace(key=KEY), store, public=False)


TRACEBACK = ("Traceback (most recent call last):\n  File \"/home/someone/venv/lib/onetrace_explain/cli.py\", line 9\n"
             "tomllib.TOMLDecodeError: Invalid value (at line 2, column 8) in /home/someone/.config/onetrace/explain.toml\n")


@pytest.mark.parametrize("attempt, want", [
    ({"exit": "1", "stderr": TRACEBACK},
     "The command failed, exit 1: tomllib.TOMLDecodeError: Invalid value (at line 2, column 8) in "
     "…/onetrace/explain.toml"),
    ({"exit": "1", "stderr": "boom at C:\\Users\\someone\\AppData\\onetrace\\explain.toml\r\n"},
     "The command failed, exit 1: boom at …\\onetrace\\explain.toml"),
    ({"exit": "", "stderr": "", "note": "it reached its limit of 300 seconds and was stopped"},
     "The command failed with no exit: it reached its limit of 300 seconds and was stopped."),
    ({"exit": "", "stderr": "", "note": "it could not start: No such file or directory"},
     "The command failed with no exit: it could not start: No such file or directory."),
], ids=["exit 1, a traceback", "exit 1, a Windows path", "a limit reached", "could not start"])
def test_every_failure_says_so_with_its_exit_and_last_line(tmp_path, monkeypatch, attempt, want, examined):
    panel = _text(_failed_panel(tmp_path, monkeypatch, attempt))
    examined(1, "failed press")
    assert want in panel, panel
    assert "Traceback" not in panel and "/home/someone" not in panel and "C:\\Users" not in panel


def test_sabotage_the_failure_line_left_out_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import explain
    monkeypatch.setattr(explain, "_failed_line", lambda a: "")
    panel = _text(_failed_panel(tmp_path, monkeypatch, {"exit": "1", "stderr": TRACEBACK}))
    examined(1, "failed press, its line left out")
    assert "The command failed" not in panel


# ------------------------------------------------------------------ through the console

def test_the_console_answers_a_press_at_once_and_reports_its_state(held, server, monkeypatch, examined):
    """POST /explain answers 202 at once; GET /explain/state reports the press; a second press
    while it runs answers 409 with BUSY."""
    import urllib.error
    import urllib.request

    from onetrace_console import explain
    from onetrace_console.serve import Handler
    store, comparison, gate = held
    base, _ = server
    monkeypatch.setattr(Handler, "store", store)

    def post():
        req = urllib.request.Request(f"{base}/explain?c={comparison.key}&send=yes", method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def now():
        with urllib.request.urlopen(f"{base}/explain/state?c={comparison.key}", timeout=30) as r:
            return json.loads(r.read())
    t = time.monotonic()
    status, body = post()
    examined(3, "requests")
    assert status == 202 and body["started"] and time.monotonic() - t < 5, body
    assert now()["running"] is True
    assert post() == (409, {"error": explain.BUSY})
    gate.set()
    explain.wait(comparison.key, 120)
    assert now() == {"running": False}


def test_a_press_that_reaches_its_limit_is_stopped_and_says_so(held, monkeypatch, examined):
    from onetrace_console import explain
    store, comparison, gate = held
    monkeypatch.setattr(explain, "TIMEOUT", 3)
    explain.start(comparison, store, send=True)
    assert explain.wait(comparison.key, 60)
    a = explain.attempts(store, comparison.key)[-1]
    examined(1, "press at its limit")
    assert (a["exit"], a["note"]) == ("", explain.LIMIT_REACHED.format(n=3))
    assert explain.FAILED_NO_EXIT.format(why=explain.LIMIT_REACHED.format(n=3)) in _text(
        explain.panel(comparison, store, public=False))
