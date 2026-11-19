"""The Runs page (`runs_page`, `/runs`): one page of runs across pipelines, drawn as asked from the run index.

1. Its filters are terms of the index's query: each adds exactly its term to the search box, and the page lists what
   `/search` answers for the same query.
2. Its columns are the runs list's words, read from the index: a run of each format (0.3 to 0.5) is listed with them.
3. An empty store, an index not written yet and an index written before it held the list each say so.
4. Paged at 50 runs: "Runs 1-50 of N", and its pages are links.
5. A FAIL is never hidden by a default: no filter is on by default, and the page says how many of the runs listed the
   verifier FAILs, with the filter that lists them.
6. Every list and count on it goes through one query function (`runs_page.select`), so a later round can scope it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_format_03 import _tar

HERE = Path(__file__).resolve().parent
FORMATS = {
    "0.3": HERE / "onetrace_runs" / "0.6.1" / "refund-closed",
    "0.4": HERE / "onetrace_runs" / "0.7.1" / "refund-closed",
    "0.5": HERE / "onetrace_runs" / "0.8.0" / "refund-closed",
}
FAILING = HERE / "format_05_usage" / "reject" / "R301-usage-total-below-part"
RAN_AT = "2026-11-12T00:00:00+00:00"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console import run_index
    from onetrace_console.store import Store

    folder = shared_demo["folder"]
    index = run_index.read(folder / "store")
    assert index is not None, "the build wrote no index"
    return Store(folder / "store" / "store"), index


def _text(html: str) -> str:
    html = re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _keys(page: str) -> list[str]:
    return re.findall(r'<tr data-run="[^"]*" data-key="([0-9a-f]{64})"', page)


def _box(page: str) -> str:
    m = re.search(r'<input type="search" name="q" value="([^"]*)"', page)
    assert m, "the page has no search box"
    import html

    return html.unescape(m.group(1))


def _store(tmp_path, folders: dict[str, Path]):
    from onetrace_console import run_index
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store

    store = Store(tmp_path / "store")
    keys = {n: run_and_record(accept(_tar(f), store).run, store, ran_at=RAN_AT).key for n, f in folders.items()}
    return store, keys, run_index.build(store)


# ----------------------------------------------------------------------------------------- 1. filters


FILTERS = [
    ({"pipeline": "P1"}, "pipeline:P1"),
    ({"agree": "yes"}, "agree:yes"),
    ({"verdict": "FAIL"}, "verdict:FAIL"),
    ({"after": "2026-01-01"}, "after:2026-01-01"),
    ({"before": "2030-01-01"}, "before:2030-01-01"),
]


@pytest.mark.parametrize(("given", "term"), FILTERS, ids=[t for _, t in FILTERS])
def test_each_filter_adds_exactly_its_term_and_lists_what_search_answers(demo, given, term, examined):
    from onetrace_console import run_index, runs_page

    _store_, index = demo
    page = runs_page.body(index, {**given, "page": "all"}, public=True)
    want = [r.run["key"] for r in run_index.query(index, term)]
    examined(len(want) or 1, f"runs {term} lists")
    assert _box(page) == term
    assert sorted(_keys(page)) == sorted(want)


def test_the_word_filter_lists_each_word_the_index_holds(demo, examined):
    from onetrace_console import run_index, runs_page

    _store_, index = demo
    words = sorted({r["list"]["word"] for r in index["runs"] if r["list"]["word"]})
    examined(len(words), "verdict words")
    assert words, "the demo holds no run with a verdict against its reference"
    for w in words:
        page = runs_page.body(index, {"word": w, "page": "all"}, public=True)
        assert _box(page) == f"word:{w}"
        assert sorted(_keys(page)) == sorted(r.run["key"] for r in run_index.query(index, f"word:{w}"))


def test_filters_and_the_box_combine_and_a_filter_s_term_in_the_box_is_not_doubled(demo, examined):
    from onetrace_console import runs_page

    _store_, index = demo
    page = runs_page.body(index, {"pipeline": "P1", "q": "pipeline:P2 benchmark:yes"}, public=True)
    examined(1, "a filter and the box together")
    assert _box(page) == "benchmark:yes pipeline:P1"


def test_a_query_the_grammar_does_not_hold_is_refused_in_words_and_lists_nothing(demo, examined):
    from onetrace_console import runs_page

    _store_, index = demo
    page = runs_page.body(index, {"q": "agree:maybe"}, public=True)
    examined(1, "a refused query")
    assert 'data-runs="refused"' in page and "agree takes" in _text(page) and not _keys(page)


# ----------------------------------------------------------------------------------------- 2. columns


def test_a_run_of_each_format_is_listed_with_the_runs_list_s_words(tmp_path, examined):
    from onetrace_console import closing, runs_page
    from onetrace_console.pages import run_answers

    store, keys, index = _store(tmp_path, FORMATS)
    page = runs_page.body(index, {}, public=False)
    examined(len(keys), "runs, one per format")
    assert sorted(_keys(page)) == sorted(keys.values())
    for fmt, key in keys.items():
        run = store.get_run(key)
        row = re.search(rf'<tr data-run="[^"]*" data-key="{key}">.*?</tr>', page, re.S).group(0)
        assert f'data-state="{run_answers(run, store)["records-agree"]}"' in row, fmt
        assert f'data-ending="{closing.state(run.ending)}"' in row, fmt
        more = re.search(rf'<tr [^>]*data-more-of="{key}">.*?</tr>', page, re.S).group(0)
        assert "How far it got" in more and "Received by this console" in more, fmt
        assert "Signed by a known recorder" in more and "Ran as approved" in more, fmt


def test_the_columns_and_more_hold_the_words_the_runs_list_shows_for_the_same_run(demo, examined):
    from onetrace_console import runs_page

    store, index = demo
    page = runs_page.body(index, {"page": "all"}, public=True)
    listed = (Path(store.root).parent / "pages" / "executions-all.html").read_text(encoding="utf-8")
    runs = store.runs()
    examined(len(runs), "runs on both lists")
    assert sorted(_keys(page)) == sorted(r.key for r in runs)
    for run in runs:
        theirs = re.search(rf'<tr data-run="[^"]*" data-key="{run.key}">.*?</tr>', listed, re.S).group(0)
        mine = re.search(rf'<tr data-run="[^"]*" data-key="{run.key}">.*?</tr>', page, re.S).group(0)
        more = re.search(rf'<tr [^>]*data-more-of="{run.key}">.*?</tr>', page, re.S).group(0)
        for answer in ("records-agree",):
            state = re.search(rf'data-answer="{answer}"><span [^>]*data-state="([^"]+)"', theirs).group(1)
            assert f'data-state="{state}"' in mine, run.run_id
        for answer in ("signed", "anchored", "approved"):
            state = re.search(rf'data-answer="{answer}"><span [^>]*data-state="([^"]+)"', theirs).group(1)
            assert re.search(rf'data-answer="{answer}"><span [^>]*data-state="{state}"', more), (run.run_id, answer)
        ending = re.search(r'data-ending="([^"]+)"', theirs).group(1)
        assert f'data-ending="{ending}"' in mine, run.run_id
        row = re.search(rf'<tr class="verdict-row" data-verdict-of="{run.key}">.*?</tr>', listed, re.S)
        word = re.search(r'data-verdict-word="([^"]+)"', row.group(0)) if row else None
        assert (f'data-verdict-word="{word.group(1)}"' in mine) if word else "data-verdict-word=" not in mine


def test_started_and_took_are_the_record_s_times(tmp_path, examined):
    from onetrace_console import runs_page

    store, keys, index = _store(tmp_path, {"0.5": FORMATS["0.5"]})
    page = runs_page.body(index, {}, public=False)
    entry = index["runs"][0]["list"]
    started, ended = entry["ran"].split(" → ")
    examined(1, "a run's start and duration")
    assert f'datetime="{started.strip()}"' in page
    from onetrace_console.runs_page import took

    assert took(entry["ran"]) and f"took {took(entry['ran'])}" in _text(page)


# ------------------------------------------------------------------------------- 3. empty, no index


def test_an_empty_store_says_no_run_is_held(tmp_path, examined):
    from onetrace_console import run_index, runs_page
    from onetrace_console.store import Store

    page = runs_page.body(run_index.build(Store(tmp_path / "store")), {}, public=False)
    examined(1, "an empty store")
    assert runs_page.EMPTY in _text(page) and "<table" not in page


def test_no_index_and_an_earlier_index_each_say_so(demo, examined):
    from onetrace_console import run_index, runs_page

    _store_, index = demo
    none = runs_page.body(None, {}, public=False)
    earlier = runs_page.body({k: v for k, v in index.items() if k != run_index.LIST}, {}, public=True)
    examined(2, "pages without an index that holds the list")
    assert 'data-runs="no-index"' in none and not _keys(none)
    assert 'data-runs="not-listed"' in earlier and not _keys(earlier)


# ------------------------------------------------------------------------------------------ 4. paging


def _many(index: dict, n: int) -> dict:
    import copy

    one = index["runs"][0]
    runs = []
    for i in range(n):
        r = copy.deepcopy(one)
        r["key"], r["run_id"], r["order"] = f"{i:064x}", f"run-{i:03d}", i
        runs.append(r)
    return {**index, "runs": runs, "comparisons": []}


def test_paged_at_fifty_with_links_to_each_page(demo, examined):
    from onetrace_console import runs_page

    _store_, index = demo
    many = _many(index, 120)
    first = runs_page.body(many, {}, public=True)
    third = runs_page.body(many, {"page": "3"}, public=True)
    examined(120, "runs across three pages")
    assert len(_keys(first)) == 50 and "Runs 1–50 of 120" in _text(first)
    assert len(_keys(third)) == 20 and "Runs 101–120 of 120" in _text(third)
    assert 'href="runs?page=2"' in first and 'href="runs?page=3"' in first
    assert _keys(first)[0] == f"{119:064x}", "newest first"
    beyond = runs_page.body(many, {"page": "9"}, public=True)
    assert not _keys(beyond) and 'data-runs="no-page"' in beyond


def test_a_page_link_keeps_the_filters(demo, examined):
    from onetrace_console import runs_page

    _store_, index = demo
    page = runs_page.body(_many(index, 60), {"agree": index["runs"][0]["list"]["records-agree"]}, public=True)
    examined(1, "a filtered page's links")
    assert re.search(r'href="runs\?[^"]*agree=[a-z-]+[^"]*page=2"', page.replace("&amp;", "&"))


# ------------------------------------------------------------------------------- 5. FAIL never hidden


def test_a_run_the_verifier_fails_is_listed_by_default_and_counted(tmp_path, examined):
    from onetrace_console import runs_page

    store, keys, index = _store(tmp_path, {"pass": FORMATS["0.5"], "fail": FAILING})
    page = runs_page.body(index, {}, public=False)
    examined(2, "a passing and a failing run")
    assert sorted(_keys(page)) == sorted(keys.values())
    said = re.search(r'<p data-runs="fails">.*?</p>', page, re.S)
    assert said and "1 of these 2 runs" in _text(said.group(0)) and "verdict=FAIL" in said.group(0)


def test_the_fail_line_counts_beyond_the_page_shown(demo, examined):
    from onetrace_console import runs_page

    _store_, index = demo
    many = _many(index, 60)
    for r in many["runs"][:5]:
        r["verdict"] = "FAIL"
    page = runs_page.body(many, {}, public=True)
    examined(60, "runs, five failing on page 2")
    assert "5 of these 60 runs" in _text(re.search(r'<p data-runs="fails">.*?</p>', page, re.S).group(0))


# --------------------------------------------------------------------------------- 6. one query function


def test_every_list_and_count_goes_through_select(demo, monkeypatch, examined):
    """A scope given to `select` (as item 4's teams will) reaches every run listed, every count and every pipeline
    offered, and nothing on the page names a run left out."""
    from onetrace_console import runs_page

    _store_, index = demo
    real = runs_page.select
    keep = {r["key"] for r in index["runs"] if r["pipeline_label"] == "P1"}
    monkeypatch.setattr(runs_page, "select", lambda idx, q="": [r for r in real(idx, q) if r["key"] in keep])
    page = runs_page.body(index, {"page": "all"}, public=True)
    examined(len(index["runs"]), "runs, a scope of one pipeline")
    assert set(_keys(page)) == keep
    assert f"of {len(keep)}" in _text(page)
    offered = re.findall(r'<option value="(P[0-9]+)"', page)
    assert offered == ["P1"]
    for r in index["runs"]:
        if r["key"] not in keep:
            assert r["key"] not in page and r["run_id"] not in page


def test_the_page_reads_the_index_alone(examined):
    source = (Path(__file__).resolve().parent.parent / "src" / "onetrace_console" / "runs_page.py").read_text(
        encoding="utf-8"
    )
    examined(1, "the page's source")
    assert "store" not in re.sub(r'""".*?"""|#.*', "", source, flags=re.S)
