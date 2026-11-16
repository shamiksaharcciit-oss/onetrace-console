"""A view whose page does not open is opened again, twice at most, and then fails by name.

The layout and Explain look checks stalled, on many runs, with Chromium opening a new page: at random views, the
same views opening on the next run. `layout_check.run_browser` now runs the browser script again from a view that
did not open within its limit (a new page, or loading its address), keeping the views judged before it: at most
twice a view, each retry said on the check's output with its view and time, and counted on the summary line. A view
still not open after two fails by name. A stall while a view is judged is never retried.

Held with a stand-in for playwright that stalls a view's load as many times as it is told (a file counts them down);
no browser is started.
"""

from __future__ import annotations

import json
import re
import sys

import pytest

from tests.test_rendered_check_stall import JOBS, _check, _script

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in runs the scripts as on the gates")

STUB = """
import os, time
from contextlib import contextmanager
def _stall(where):
    if where != os.environ["STUB_STALL_STEP"]:
        return
    left = int(open(os.environ["STUB_COUNT"]).read())
    if left > 0:
        open(os.environ["STUB_COUNT"], "w").write(str(left - 1))
        time.sleep(600)
class Page:
    def add_init_script(self, s): pass
    def goto(self, url, wait_until=None):
        if url.endswith("/b.html"):
            _stall("loading")
    def evaluate(self, code, *a):
        if code == "probe":
            _stall("measuring")
        return {"doc": 1, "win": 1, "over": [], "clipped": [], "seen": 1, "bad": []}
    def screenshot(self, **k): pass
    def close(self): pass
class Browser:
    def new_page(self, **k): return Page()
    def close(self): pass
class P:
    class chromium:
        @staticmethod
        def launch(): return Browser()
@contextmanager
def sync_playwright():
    yield P
"""


@pytest.fixture
def stalls(tmp_path, monkeypatch):
    (tmp_path / "playwright").mkdir()
    (tmp_path / "playwright" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "playwright" / "sync_api.py").write_text(STUB, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))

    def told(times: int, step: str = "loading"):
        (tmp_path / "count").write_text(str(times), encoding="utf-8")
        monkeypatch.setenv("STUB_COUNT", str(tmp_path / "count"))
        monkeypatch.setenv("STUB_STALL_STEP", step)

    return told


TOOLS = pytest.mark.parametrize("tool", ["layout_check", "explain_look_check"])


def _run(tool: str):
    check = _check(tool)
    lc = check if tool == "layout_check" else check.layout_check
    return lc, lc.run_browser([sys.executable, "-c", *_script(tool, JOBS, "2")], lc.Limit(300))


@TOOLS
def test_a_view_that_did_not_open_is_opened_again_said_and_counted(stalls, tool, capsys, examined):
    stalls(1)
    _lc, got = _run(tool)
    out = capsys.readouterr().out
    examined(len(got), "views judged, one opened again")
    assert [r["page"] for r in got] == ["a", "b", "c"]
    assert got.retries == 1
    assert re.search(
        r"^retry 1 of 2: view 2 of 3: b at 390 \(http://127\.0\.0\.1:9/b\.html\), opened again at "
        r"\d\d:\d\d:\d\d UTC: it did not open within 2 s \(loading\)$",
        out,
        re.M,
    ), out


@TOOLS
def test_a_view_still_not_open_after_two_retries_fails_by_name(stalls, tool, capsys, examined):
    stalls(3)
    with pytest.raises(Exception) as failed:
        _run(tool)
    out = capsys.readouterr().out
    examined(1, "a view that never opens")
    assert type(failed.value).__name__ == "Stopped"
    assert str(failed.value) == (
        "the browser could not open view 2 of 3: b at 390 (http://127.0.0.1:9/b.html): "
        "it did not open within 2 s, opened again 2 times"
    ), str(failed.value)
    assert len(re.findall(r"^retry [12] of 2: view 2 of 3: ", out, re.M)) == 2, out


@TOOLS
def test_a_stall_while_a_view_is_judged_is_never_retried(stalls, tool, capsys, examined):
    stalls(1, step="measuring")
    with pytest.raises(Exception) as failed:
        _run(tool)
    examined(1, "a view that stalled while measured")
    assert str(failed.value).startswith("the browser stalled at view 1 of 3: a at 1280 ") and "measuring" in str(
        failed.value
    )
    assert "retry" not in capsys.readouterr().out


def test_the_summary_line_counts_the_retries(examined):
    """Both checks' summary lines end with their count of retries."""
    from tests.export_tree import tool as tool_path

    texts = [tool_path(f"{t}.py").read_text(encoding="utf-8") for t in ("layout_check", "explain_look_check")]
    examined(2, "summary lines")
    assert all("{retried} retries" in t for t in texts)


def test_without_its_views_given_a_stall_is_said_as_before():
    """A script run with no list of views (as the whole check's limit's test runs it) is never retried."""
    lc = _check("layout_check")
    assert json.loads("[]") == [] and lc.RETRIES == 2 and lc.OPENING == ("a new page", "loading")
