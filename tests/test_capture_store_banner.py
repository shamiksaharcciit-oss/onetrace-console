"""The capture store's banner says what the capture store holds, from its own runs; the demo's says the demo's.

The banner's sentence on the runs was the demo's on every public page, the capture store's too ("Its runs come from
11 small example pipelines"), though the capture store holds its own few runs. Built as its image builds it, and
served, each of its pages carries its own line, its counts read from its builder; the demo's pages keep theirs.
"""

from __future__ import annotations

from tests.test_capture_store import built  # noqa: F401 - the fixture, requested by name
from tests.test_capture_store_search import served_captures  # noqa: F401 - the fixture, requested by name
from tests.test_search_engines import _get


def _lines():
    from onetrace_console.demo_store import captures, pipeline_names
    from onetrace_console.public import BANNER_RUNS, CAPTURES_RUNS, count_word

    specs = captures.runs()
    own = CAPTURES_RUNS.format(
        runs=count_word(len(specs)), count=count_word(len(dict.fromkeys(s.pipeline for s in specs)))
    )
    return own, BANNER_RUNS.format(count=count_word(len(pipeline_names())))


def test_every_built_capture_store_page_says_what_it_holds(built, examined):  # noqa: F811
    own, demo = _lines()
    pages = {rel: p for rel, p in built["pages"].items() if 'data-frame="banner"' in p}
    examined(len(pages), "pages with the banner")
    assert pages, "no page carries the banner"
    assert [rel for rel, p in pages.items() if own not in p or demo in p] == []


def test_a_page_the_capture_store_draws_as_it_serves_says_it_too(served_captures, examined):  # noqa: F811
    base, _built = served_captures
    own, demo = _lines()
    examined(1, "served page")
    _s, _k, page = _get(base, "/runs")
    assert own in page and demo not in page


def test_the_demo_s_banner_keeps_its_own_line(shared_demo, examined):
    #: Read on the pages that carry their banner as built (a sealed page's frame is filled before its seal).
    own, demo = _lines()
    pages = [p.read_text(encoding="utf-8") for p in (shared_demo["folder"] / "store" / "pages").rglob("*.html")]
    pages = [p for p in pages if 'data-frame="banner"' in p]
    examined(len(pages), "pages with the banner")
    assert pages and all(demo in p and own not in p for p in pages)
