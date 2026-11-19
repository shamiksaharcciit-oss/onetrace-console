"""From the Runs page to a pair and to the first run to leave: with one pipeline chosen.

- **The bisect line.** With one pipeline chosen, a line above the table asks for a time and posts the first-run-to-leave
  page's own `GET` form (`/bisect?p=&after=`); each run's start links into it, as on that page. With none chosen, it
  says to choose a pipeline. A static export draws neither.
- **The pair picker.** With one pipeline chosen, the pipeline page's picker is drawn under the filters, posting
  `POST /compare` as it does: on a public console the visitor's picker, two run ids; on a local one the local picker,
  two run keys and the session's token. The pairs already compared are listed first, each opening at once. A static
  export draws none. Its runs are read from the index, as the rest of the page is.
"""

from __future__ import annotations

import re
from html import unescape

import pytest


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console import run_index

    folder = shared_demo["folder"]
    index = run_index.read(folder / "store")
    assert index is not None
    return index, folder / "store" / "pages"


def _of(index: dict, label: str) -> list[dict]:
    return sorted((r for r in index["runs"] if r.get("pipeline_label") == label), key=lambda r: r["order"])


def _held(index: dict, label: str) -> list[dict]:
    keys = {r["key"] for r in _of(index, label)}
    return [c for c in index["comparisons"] if c["a"] in keys and c["b"] in keys]


def test_the_bisect_line_is_drawn_with_one_pipeline_chosen_and_posts_the_existing_form(demo, examined):
    from onetrace_console import bisect_page, runs_page

    index, _pages = demo
    labels = sorted({r["pipeline_label"] for r in index["runs"] if r.get("pipeline_label")})
    examined(len(labels), "pipelines")
    for label in labels:
        page = runs_page.body(index, {"pipeline": label}, public=True)
        form = re.search(r'<form method="get" action="bisect" data-bisect-window>.*?</form>', page, re.S)
        assert form, label
        assert f'<input type="hidden" name="p" value="{label}">' in form.group(0)
        assert 'name="after"' in form.group(0) and bisect_page.WINDOW_BUTTON in form.group(0)
        assert page.index("data-bisect-window") < page.index('data-section="runs-page"'), "not above the table"
    page = runs_page.body(index, {}, public=True)
    assert "data-bisect-window" not in page and runs_page.BISECT_NONE in unescape(page)


def test_each_run_s_start_links_into_it_with_one_pipeline_chosen(demo, examined):
    from onetrace_console import bisect_page, runs_page

    index, _pages = demo
    page = runs_page.body(index, {"pipeline": "P1", "page": "all"}, public=True)
    runs = _of(index, "P1")
    examined(len(runs), "runs' starts")
    for r in runs:
        start = r["list"]["ran"].partition(" → ")[0].strip()
        if not start:
            continue
        row = re.search(rf'<tr data-run="[^"]*" data-key="{r["key"]}">.*?</tr>', page, re.S).group(0)
        assert f'<a href="{bisect_page.ask_href("P1", start)}">' in row, r["run_id"]
    assert 'href="bisect?' not in runs_page.body(index, {"page": "all"}, public=True)


def test_the_public_picker_is_under_the_filters_its_held_pairs_first(demo, examined):
    from onetrace_console import runs_page, visitor_compare

    index, pages = demo
    seen = 0
    for label in sorted({r["pipeline_label"] for r in index["runs"] if r.get("pipeline_label")}):
        runs = _of(index, label)
        page = runs_page.body(index, {"pipeline": label}, public=True)
        if len(runs) < 2:
            assert "data-visitor-compare" not in page, label
            continue
        seen += 1
        section = re.search(r'<section id="visitor-compare".*?</section>', page, re.S).group(0)
        assert page.index('data-runs="filters"') < page.index('id="visitor-compare"') < page.index('data-runs="count"')
        form = re.search(r'<form method="post" action="/compare" data-visitor-compare>.*?</form>', section, re.S)
        assert form, label
        for name in ("a", "b"):
            sel = re.search(rf'<select name="{name}">(.*?)</select>', form.group(0), re.S).group(1)
            assert [unescape(v) for v in re.findall(r'<option value="([^"]*)"', sel)] == [r["run_id"] for r in runs]
        assert visitor_compare.PICKER_BUTTON in form.group(0)
        held = _held(index, label)
        links = re.findall(r'<li data-held-pair><a href="(diff/[0-9a-f]{64}\.html)">', section)
        assert links == [f"diff/{c['key']}.html" for c in held], label
        for link in links:
            assert (pages / link).is_file(), link
        if held:
            assert section.index("data-held-pair") < section.index("<form"), "the held pairs are not first"
            assert runs_page.OPENS_AT_ONCE in unescape(section)
    examined(seen, "pipelines with a picker")
    assert seen >= 3


def test_the_local_picker_posts_keys_and_the_session_s_token(demo, examined):
    from onetrace_console import runs_page
    from onetrace_console.frame import CSRF_SLOT

    index, _pages = demo
    runs = _of(index, "P1")
    page = runs_page.body(index, {"pipeline": "P1"}, public=False)
    examined(len(runs), "runs offered")
    form = re.search(r'<form method="post" action="/compare" data-local-compare>.*?</form>', page, re.S).group(0)
    assert CSRF_SLOT in form
    sel = re.search(r'<select name="a" required>(.*?)</select>', form, re.S).group(1)
    assert re.findall(r'<option value="([0-9a-f]{64})"', sel) == [r["key"] for r in runs]
    assert "data-visitor-compare" not in page


def test_a_pair_asked_for_is_chosen_in_the_picker(demo, examined):
    from onetrace_console import runs_page

    index, _pages = demo
    runs = _of(index, "P1")
    a, b = runs[-1]["run_id"], runs[0]["run_id"]
    page = runs_page.body(index, {"pipeline": "P1", "a": a, "b": b}, public=True)
    examined(2, "runs chosen")
    for name, want in (("a", a), ("b", b)):
        sel = re.search(rf'<select name="{name}">(.*?)</select>', page, re.S).group(1)
        assert re.findall(r'<option value="([^"]*)" selected>', sel) == [want], name


def test_no_pipeline_chosen_or_an_export_draws_no_picker_and_no_form(demo, examined):
    from onetrace_console import runs_page

    index, _pages = demo
    examined(3, "pages")
    assert "/compare" not in runs_page.body(index, {}, public=True)
    exported = runs_page.body(index, {"pipeline": "P1"}, public=False, exported=True)
    assert "<form" not in exported and "<select" not in exported and "/compare" not in exported
    assert "data-bisect-window" not in exported and runs_page.BISECT_NONE not in unescape(exported)
