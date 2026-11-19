"""Small actions answer in place.

Set up Explain's forms (the model's Save, the key's Replace, "Always stop before sending") each name the section they
update (`data-in-place`); with script, the busy state's script posts with `fetch` and swaps in only that section from
the console's answer, the same drawing as a full page; the page keeps its place, and the section's status line is
announced (`aria-live="polite"`). Without script the form posts as before and the answer opens at the section's
anchor. Mark as benchmark replaces its own section likewise. The browser half runs where ONETRACE_BROWSER_PYTHON names
a Python with Playwright's Chromium.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from html import unescape
from urllib.parse import urlencode

import pytest

from tests.http_limits import limit

BROWSER_PYTHON = os.environ.get("ONETRACE_BROWSER_PYTHON", "")


@pytest.fixture
def setup(server, tmp_path, monkeypatch):
    """A local console whose Explain configuration names a model, so the page's forms are all drawn."""
    config = tmp_path / "explain-config" / "explain.toml"
    config.parent.mkdir()
    config.write_text(
        '[model]\nprovider = "openai"\nname = "m"\nbase_url = "http://127.0.0.1:9/v1"\n', encoding="utf-8"
    )
    monkeypatch.setenv("ONETRACE_EXPLAIN_CONFIG", str(config))
    base, root = server
    return base, root


def _get(url: str) -> str:
    return urllib.request.urlopen(url, timeout=limit(30)).read().decode()


def _post(base: str, form: dict) -> str:
    req = urllib.request.Request(base + "/explain/setup", data=urlencode(form).encode(), method="POST")
    try:
        return urllib.request.urlopen(req, timeout=limit(30)).read().decode()
    except urllib.error.HTTPError as e:
        return e.read().decode()


def section(page: str, sid: str) -> str:
    """The element whose id is `sid`, whole: from its opening tag to the end tag that closes it."""
    m = re.search(rf'<(div|section)\b[^>]*\bid="{re.escape(sid)}"[^>]*>', page)
    assert m, f"no element with id {sid!r}"
    tag, depth, i = m.group(1), 0, m.start()
    for t in re.finditer(rf"<(/?){tag}\b[^>]*>", page[m.start() :]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return page[i : m.start() + t.end()]
    raise AssertionError(f"{sid!r} is not closed")


def in_place_problems(page: str) -> list[str]:
    """Each form that names a section: its action ends at that section's anchor, and the section holds the form."""
    out = []
    for attrs in re.findall(r"<form\b([^>]*)>", page):
        sid = re.search(r'data-in-place="([^"]+)"', attrs)
        if not sid:
            continue
        sid = sid.group(1)
        action = re.search(r'action="([^"]*)"', attrs).group(1)
        if not action.endswith("#" + sid):
            out.append(f"the form for {sid!r} posts to {action!r}, not to its anchor")
        if f"<form{attrs}>" not in section(page, sid):
            out.append(f"the form for {sid!r} is outside its section")
    return out


def test_each_in_place_form_names_its_section_and_opens_at_it(setup, examined):
    base, _root = setup
    page = _get(base + "/explain/setup")
    forms = re.findall(r'data-in-place="([^"]+)"', page)
    examined(len(forms), "forms that update in place")
    assert sorted(set(forms)) == ["always-stop", "setup-form"], forms
    assert in_place_problems(page) == []


def test_sabotage_a_form_posting_to_the_page_top_is_named():
    planted = (
        '<div id="always-stop"><form method="post" action="/explain/setup" data-in-place="always-stop"></form></div>'
    )
    assert in_place_problems(planted) == ["the form for 'always-stop' posts to '/explain/setup', not to its anchor"]


@pytest.mark.parametrize(
    ("form", "sid", "said"),
    [
        ({"action": "always-stop", "always_stop": "yes"}, "always-stop", "Saved: Explain always stops before sending."),
        (
            {"action": "save", "provider": "openai", "name": "m2", "base_url": "http://127.0.0.1:9/v1"},
            "setup-form",
            None,
        ),
    ],
)
def test_a_press_answers_with_its_status_in_its_own_section(setup, form, sid, said, examined):
    base, _root = setup
    page = _post(base, form)
    here = section(page, sid)
    status = re.search(r'<p data-setup="said" data-status role="status" aria-live="polite">(.*?)</p>', here, re.S)
    examined(1, "the answer's section")
    assert status, here[:500]
    if said:
        assert unescape(status.group(1)) == said
    assert 'data-section="setup-said"' not in page, "said at the top as well"


def test_the_section_in_place_is_the_same_section_of_a_full_page(setup, examined):
    """The section the script swaps in is cut from the answer: the answer's section is the page's own section, drawn
    by the same function with the same state."""
    from onetrace_console import explain, explain_setup
    from onetrace_console.serve import Handler

    base, _root = setup
    answer = _post(base, {"action": "always-stop", "always_stop": "yes"})
    drawn = explain_setup.page(Handler.store, said=explain.ALWAYS_STOP_ON, at=explain_setup.STOP_SECTION)
    csrf = re.compile(r'(name="csrf"[^>]*value=")[^"]*"')
    examined(1, "the section, answered and drawn")
    assert csrf.sub(r"\1", section(answer, "always-stop")) == csrf.sub(r"\1", section(drawn, "always-stop"))


def test_mark_as_benchmark_replaces_its_own_section_and_announces_it(examined):
    from onetrace_console.benchmark_script import BENCHMARK_SCRIPT, MARKED, UNMARKED

    examined(1, "the benchmark mark's script")
    assert "replaceWith(n);bind(n)" in BENCHMARK_SCRIPT and "section[data-section=benchmark]" in BENCHMARK_SCRIPT
    assert f"'{MARKED}'" in BENCHMARK_SCRIPT and f"'{UNMARKED}'" in BENCHMARK_SCRIPT
    #: Loaded again only where the section can't be read.
    assert BENCHMARK_SCRIPT.count("location.reload()") == 2


def test_the_benchmark_section_s_status_line_is_announced(shared_demo, examined):
    from onetrace_console.benchmarks import mark_section as benchmark_section
    from onetrace_console.frame import rendering
    from onetrace_console.store import Store

    store = Store(shared_demo["folder"] / "store" / "store")
    with store.reading():
        run = next(iter(store.runs()))
        with rendering(onedoor=False, sign_in=False, public=False):
            drawn = benchmark_section(run, store, public=False)
    examined(1, "a run's Benchmark section")
    #: Apart from the button before it, by a space.
    assert '</button> <span data-benchmark-said data-status role="status" aria-live="polite"></span>' in drawn


BROWSER = r"""
import json, sys
from playwright.sync_api import sync_playwright
base = sys.argv[1]
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1024, "height": 700})
    page.goto(base + "/explain/setup")
    page.evaluate("() => { window.__stay = 1 }")
    page.locator("#always-stop").scroll_into_view_if_needed()
    page.evaluate("() => window.scrollBy(0, -120)")
    before = page.evaluate("() => window.scrollY")
    page.check("#always-stop input[name=always_stop]")
    page.click("#always-stop button[value=always-stop]")
    page.wait_for_function("() => (document.querySelector('#always-stop [data-status]') || {}).textContent")
    out["stayed"] = page.evaluate("() => window.__stay === 1")
    out["scroll moved"] = abs(page.evaluate("() => window.scrollY") - before)
    out["status"] = page.evaluate("() => document.querySelector('#always-stop [data-status]').textContent")
    out["live"] = page.evaluate("() => document.querySelector('#always-stop [data-status]').getAttribute('aria-live')")
    out["focus"] = page.evaluate("() => document.activeElement && document.activeElement.value")
    out["ticked"] = page.evaluate("() => document.querySelector('#always-stop input[name=always_stop]').checked")
    off = b.new_context(java_script_enabled=False).new_page()
    off.goto(base + "/explain/setup")
    off.check("#always-stop input[name=always_stop]")
    off.click("#always-stop button[value=always-stop]")
    off.wait_for_load_state()
    out["script off url"] = off.url
    out["script off status"] = off.locator("#always-stop [data-status]").text_content()
    print(json.dumps(out))
    b.close()
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_in_a_browser_a_save_updates_its_section_in_place_and_without_script_opens_at_it(setup, tmp_path, examined):
    from onetrace_console.explain import ALWAYS_STOP_ON

    base, _root = setup
    script = tmp_path / "in_place.py"
    script.write_text(BROWSER, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), base], capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    examined(len(got), "browser readings")
    assert got["stayed"] is True and got["scroll moved"] <= 2, got
    assert got["status"] == ALWAYS_STOP_ON and got["live"] == "polite" and got["ticked"] is True, got
    assert got["focus"] == "always-stop", got
    assert got["script off url"].endswith("/explain/setup#always-stop"), got
    assert got["script off status"] == ALWAYS_STOP_ON, got
