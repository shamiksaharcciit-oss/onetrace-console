"""A page view that stalls in the browser is named: which view, its page and width, and the step it waited on.

`tools/layout_check.py` and `tools/explain_look_check.py` each hand their page views to one browser script.
When the browser stopped between two views, the check said only that it had waited on "python (the browser's
script)" until its whole limit, with nothing on which view. The script now says, on its error output, each
view's step as it starts it, and stops when one view takes longer than `--view-timeout` seconds. The check
reads that line and puts it on its summary line, whether the view's own limit or the whole check's came first.

Held with a stand-in for playwright that never opens the second view's page, and stand-ins for the
browser's Python (POSIX shell scripts, so these run where there is one). No browser is started.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stand-ins are POSIX shell scripts")

JOBS = [["http://127.0.0.1:9/a.html", "a", 1280, ""], ["http://127.0.0.1:9/b.html", "b", 390, ""],
        ["http://127.0.0.1:9/c.html", "c", 1280, ""]]

STUB = '''
import os, time
from contextlib import contextmanager
opened = 0
class Page:
    def add_init_script(self, s): pass
    def goto(self, url, wait_until=None): pass
    def evaluate(self, code, *a): return {"doc": 1, "win": 1, "over": [], "clipped": [], "seen": 1, "bad": []}
    def screenshot(self, **k): pass
    def close(self): pass
class Browser:
    def new_page(self, **k):
        global opened
        opened += 1
        if opened == int(os.environ["STUB_STALL_AT"]):
            time.sleep(600)
        return Page()
    def close(self): pass
class P:
    class chromium:
        @staticmethod
        def launch(): return Browser()
@contextmanager
def sync_playwright():
    yield P
'''


def _check(tool: str = "explain_look_check"):
    spec = importlib.util.spec_from_file_location(tool, REPO / "tools" / f"{tool}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _script(tool: str, jobs: list, view_limit: str) -> list[str]:
    """The tool's browser script and its arguments, as the tool runs it."""
    check = _check(tool)
    if tool == "layout_check":
        return [check.BROWSER, json.dumps([j[:3] for j in jobs]), "probe", "", "[]", "light", view_limit]
    return [check.BROWSER, json.dumps(jobs), "probe", "contrast", "", "[]", "light", view_limit]


TOOLS = pytest.mark.parametrize("tool", ["layout_check", "explain_look_check"])


@pytest.fixture
def stub(tmp_path) -> Path:
    (tmp_path / "playwright").mkdir()
    (tmp_path / "playwright" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "playwright" / "sync_api.py").write_text(STUB, encoding="utf-8")
    return tmp_path


@TOOLS
def test_the_browser_script_stops_on_a_view_past_its_limit_and_names_it(stub, tool, examined):
    start = time.monotonic()
    done = subprocess.run([sys.executable, "-c", *_script(tool, JOBS, "3")], capture_output=True, text=True, timeout=120,
                          env={"PYTHONPATH": str(stub), "STUB_STALL_AT": "2", "PATH": "/usr/bin:/bin"})
    took = time.monotonic() - start
    examined(1, f"{tool}'s browser script, with a stand-in playwright that stalls the second view")
    assert done.returncode == 3, (done.returncode, done.stderr[-1500:])
    assert "stalled: view 2 of 3: b at 390 (http://127.0.0.1:9/b.html), waiting on a new page, for 3 s" in done.stderr, (
        done.stderr[-1500:])
    assert took < 60, took


@TOOLS
def test_with_no_stall_the_script_says_each_view_and_gives_every_result(stub, tool, examined):
    done = subprocess.run([sys.executable, "-c", *_script(tool, JOBS, "30")], capture_output=True, text=True, timeout=120,
                          env={"PYTHONPATH": str(stub), "STUB_STALL_AT": "0", "PATH": "/usr/bin:/bin"})
    examined(1, f"{tool}'s browser script, with a stand-in playwright that never stalls")
    assert done.returncode == 0, done.stderr[-1500:]
    assert [r["page"] for r in json.loads(done.stdout)] == ["a", "b", "c"]
    assert "view 3 of 3: c at 1280 (http://127.0.0.1:9/c.html): closing" in done.stderr


def _stand_in(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "browser-python"
    p.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    p.chmod(0o755)
    return p


def test_the_checks_summary_line_names_the_stalled_view(tmp_path, examined):
    check = _check()
    check.LIMIT = check.layout_check.Limit(60)
    py = _stand_in(tmp_path, "echo 'view 2 of 3: b at 390 (http://127.0.0.1:9/b.html): a new page' >&2\n"
                             "echo 'stalled: view 2 of 3: b at 390 (http://127.0.0.1:9/b.html), waiting on a new page, "
                             "for 3 s' >&2\nexit 3\n")
    with pytest.raises(check.layout_check.Stopped) as got:
        check._browser(str(py), JOBS, None, "light", 3)
    examined(1, "the check, given a browser script that stalled on its second view")
    assert str(got.value) == ("the browser stalled at view 2 of 3: b at 390 (http://127.0.0.1:9/b.html), "
                              "waiting on a new page, for 3 s"), str(got.value)


@TOOLS
def test_at_the_whole_checks_limit_the_summary_line_names_the_view_it_waited_on(tmp_path, capsys, tool, examined):
    check = _check(tool)
    lc = check if tool == "layout_check" else check.layout_check
    limit = lc.Limit(3)
    check.LIMIT = limit
    py = _stand_in(tmp_path, "echo 'view 1 of 3: a at 1280 (http://127.0.0.1:9/a.html): loading' >&2\nexec sleep 600\n")
    name = tool.replace("_", " ")
    start = time.monotonic()
    code = lc.guarded(name, "light", limit, lambda: lc.run_browser([str(py)], limit))
    examined(1, "the check, at its own limit, with a browser script that is loading its first view")
    assert code == 2
    assert time.monotonic() - start < 60
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last == (f"{name} (light): no page views judged, FAILED: stopped at its limit of 3 s, "
                    "waiting on the browser at view 1 of 3: a at 1280 (http://127.0.0.1:9/a.html), loading"), last
