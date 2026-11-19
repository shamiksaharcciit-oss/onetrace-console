"""The ways to another pair, and the busy state said.

- **Investigate's "Compare another pair".** A comparison of two runs of one pipeline links, under its head, to the
  Runs page with that pipeline chosen, at its picker. A static export, which has no picker, takes it out.
- **The busy page's way back.** Over the public console's bounds, "Busy, try again" keeps its `Retry-After`, and links
  back to the pair's picker with both runs still chosen.
- **A waiting press is said.** On a local console every press that waits sets `aria-busy` and puts its words in a
  polite live region beside it (tests/test_busy_state.py drives it in a browser).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.http_limits import limit
from tests.test_export_static import exported, source  # noqa: F401 - the module's fixtures


def test_each_comparison_of_one_pipeline_links_to_its_picker(shared_demo, examined):
    from onetrace_console.store import Store
    from onetrace_console.verdicts import pipeline_of

    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    pages = folder / "store" / "pages"
    seen = 0
    with store.reading():
        for c in store.comparisons():
            html = (pages / "diff" / f"{c.key}.html").read_text(encoding="utf-8")
            pa, pb = (pipeline_of(store.get_run(k), store) for k in (c.run_a, c.run_b))
            link = re.search(r'<p data-investigate="another"><a href="([^"]+)">Compare another pair</a></p>', html)
            if pa is None or pb is None or pa.label != pb.label:
                assert link is None, c.key
                continue
            seen += 1
            assert link, c.key
            href = urlsplit(unescape(link.group(1)))
            assert href.path == "/runs" and parse_qs(href.query) == {"pipeline": [pa.label]}, c.key
            assert href.fragment == "visitor-compare", "a public console's picker"
            #: Under the head and its tabs, above the short answer.
            assert html.index('data-section="views"') < link.start(), c.key
            if 'data-short="headline"' in html:
                assert link.start() < html.index('data-short="headline"'), c.key
    examined(seen, "comparisons linking their picker")
    assert seen >= 10


def test_a_static_export_draws_no_way_to_another_pair(exported, examined):  # noqa: F811 - the fixture
    out = exported[0]
    diffs = list((out / "diff").glob("*.html"))
    examined(len(diffs), "exported comparison pages")
    assert diffs
    assert not any('data-investigate="another"' in p.read_text(encoding="utf-8") for p in diffs)


def test_the_busy_page_links_back_to_the_pair_s_picker_both_runs_chosen(examined):
    from onetrace_console import visitor_compare as vc

    href = vc.back_to_pair("P1", "p1-02-baseline-set2", "p1-09-candidate-set3")
    page = vc.answer_page(vc.BUSY, vc.BUSY_WORDS, back=href, back_words=vc.BACK_TO_PAIR)
    examined(1, "busy page")
    got = urlsplit(href)
    assert got.path == "/runs" and got.fragment == "visitor-compare"
    assert parse_qs(got.query) == {"pipeline": ["P1"], "a": ["p1-02-baseline-set2"], "b": ["p1-09-candidate-set3"]}
    assert f'<a href="{href.replace("&", "&amp;")}">{vc.BACK_TO_PAIR}</a>' in page


@pytest.fixture(scope="module")
def busy_console(shared_cli_demo, tmp_path_factory):
    """A public console over the demo, at most one new comparison a minute."""
    from tests.test_folder_load import _Console
    from tests.test_public_mode import _config

    tmp = tmp_path_factory.mktemp("busy")
    config = _config(tmp, shared_cli_demo["folder"], compare_cache=str(tmp / "compared"), compare_per_minute=1)
    port = json.loads(config.read_text(encoding="utf-8"))["port"]
    c = _Console(tmp, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config)})
    try:
        c.until("onetrace-console serving on")
        yield f"http://127.0.0.1:{port}"
    finally:
        c.stop()


def test_over_the_bound_the_busy_page_links_back_with_both_runs_chosen(busy_console, examined):
    from tests.test_visitor_compare import _form, _post

    base = busy_console
    first = _post(base, _form("p1-02-baseline-set2", "p1-09-candidate-set3"))
    assert first[0] == 303, first[:2]
    status, headers, page = _post(base, _form("p1-01-baseline-set1", "p1-03-baseline-set3"))
    examined(1, "request over the bound")
    assert status == 503 and headers.get("Retry-After") == "60", (status, headers)
    link = re.search(r'<a href="([^"]+)">Back to the picker, both runs still chosen</a>', page)
    assert link, page[-2000:]
    href = unescape(link.group(1))
    with urllib.request.urlopen(base + href.split("#")[0], timeout=limit(60)) as r:
        runs = r.read().decode("utf-8")
    for name, want in (("a", "p1-01-baseline-set1"), ("b", "p1-03-baseline-set3")):
        sel = re.search(rf'<select name="{name}">(.*?)</select>', runs, re.S).group(1)
        assert re.findall(r'<option value="([^"]*)" selected>', sel) == [want], name


def test_the_busy_hook_puts_its_words_in_a_polite_live_region(examined):
    from onetrace_console.busy_script import BUSY_CSS, BUSY_SCRIPT

    examined(1, "the shared hook")
    assert "setAttribute('aria-busy','true')" in BUSY_SCRIPT
    assert "r.setAttribute('role','status')" in BUSY_SCRIPT and "r.setAttribute('aria-live','polite')" in BUSY_SCRIPT
    assert "r.textContent=b.getAttribute('data-busy')" in BUSY_SCRIPT
    assert "[data-busy-said]" in BUSY_SCRIPT, "the region is not taken away when the busy state ends"
    assert re.search(r"\[data-busy-said\]\{position:absolute;width:1px;height:1px", BUSY_CSS)
