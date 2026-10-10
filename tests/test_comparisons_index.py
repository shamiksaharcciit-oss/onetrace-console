"""The Comparisons index (approved by the maintainer): every stored comparison, newest
first, each linking to its compare page.

What it holds:
- the rows are exactly the stored comparisons the console can read -- none dropped, none added;
- newest first by the record's own `ran_at`, read as a time (offsets included, never as text);
  comparisons sharing a `ran_at` are ordered by key, ascending; a `ran_at` that is not a time
  is listed after every one that is, by key, and shown as written;
- each row links to `diff/<key>.html`, and every link answers 200 over HTTP;
- a comparison record the console cannot read is named on the page, never dropped silently
  (as the Overview names it);
- an empty store says that nothing has been compared;
- it is a viewer page in the role table, and "Comparisons" sits after Runs in the navigation.
"""
from __future__ import annotations

import dataclasses
import re

import pytest

from onetrace_console.render import COMPARISONS, render_comparisons
from onetrace_console.store import Store

GENERATED_AT = "2026-10-01T12:00:00+02:00"
ROW = re.compile(r'<tr data-key="([^"]+)">.*?<a href="([^"]+)">', re.S)


@pytest.fixture
def compared(tmp_path):
    """A store holding two runs and one real comparison of them."""
    from onetrace_console.compare import compare
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_diff_sdk_text_layer import _forged_pair
    from tests.test_unreadable import _stored
    store = Store(tmp_path / "store")
    (tmp_path / "pair").mkdir()
    a, b = _forged_pair(tmp_path / "pair")
    comparison = compare(_stored(a, store), _stored(b, store), store, ran_at=FIXED_RAN_AT)
    return store, comparison


def _variant(store: Store, base, key: str, ran_at: str):
    c = dataclasses.replace(base, key=key, ran_at=ran_at)
    store.put_comparison(c)
    return c


def _rows(page: str) -> list[tuple[str, str]]:
    return ROW.findall(page)


def test_the_rows_are_exactly_the_readable_stored_comparisons(compared, examined):
    store, base = compared
    for i in range(3):
        _variant(store, base, f"{i:064x}", f"2026-09-2{i}T10:00:00+00:00")
    stored = {c.key for c in store.comparisons()}
    rows = _rows(render_comparisons(store, generated_at=GENERATED_AT))
    examined(len(stored), "stored comparisons")
    assert len(rows) == len(stored) == 4
    assert {key for key, _ in rows} == stored


def test_newest_first_by_the_time_and_ties_by_key(compared, examined):
    store, base = compared                      # base ran at 2026-09-26T12:00:00+02:00
    _variant(store, base, "b" * 64, "2026-09-26T11:30:00+00:00")   # 13:30+02: the newest
    _variant(store, base, "d" * 64, "2026-09-26T11:30:00+00:00")   # the same moment...
    _variant(store, base, "c" * 64, "2026-09-26T13:30:00+02:00")   # ...written another way
    _variant(store, base, "a" * 64, "2026-09-25T09:00:00+00:00")   # the oldest
    _variant(store, base, "0" * 64, "not a time")                   # last, shown as written
    page = render_comparisons(store, generated_at=GENERATED_AT)
    order = [key for key, _ in _rows(page)]
    examined(len(order), "rows")
    assert order == ["b" * 64, "c" * 64, "d" * 64, base.key, "a" * 64, "0" * 64]
    assert "not a time" in page


def test_each_row_links_its_compare_page(compared, examined):
    store, base = compared
    rows = _rows(render_comparisons(store, generated_at=GENERATED_AT))
    examined(len(rows), "rows")
    assert rows == [(base.key, f"diff/{base.key}.html")]


def test_an_unreadable_comparison_is_named_not_dropped(compared, examined):
    store, base = compared
    (store.root / "comparisons" / f"{'e' * 64}.json").write_bytes(b"{not json")
    page = render_comparisons(store, generated_at=GENERATED_AT)
    examined(1, "unreadable record")
    named = re.search(r'<p data-section="unreadable-comparisons">(.*?)</p>', page, re.S)
    assert named and f"{'e' * 64}.json" in named.group(1)
    assert [key for key, _ in _rows(page)] == [base.key]


def test_an_empty_store_says_nothing_has_been_compared(tmp_path, examined):
    page = render_comparisons(Store(tmp_path / "store"), generated_at=GENERATED_AT)
    examined(1, "page")
    assert _rows(page) == []
    assert "Nothing has been compared yet." in page


def test_it_is_rendered_with_every_page(compared, examined):
    from onetrace_console.render import render_all
    store, _ = compared
    examined(1, "render")
    assert COMPARISONS in render_all(store, generated_at=GENERATED_AT)


def test_it_is_a_viewer_page_in_the_role_table(examined):
    from onetrace_console import roles
    examined(1, "route")
    assert roles.required_role("GET", f"/{COMPARISONS}", rel_for_get=COMPARISONS) == roles.VIEWER


def test_every_link_answers_200_and_the_page_is_framed(compared, server, examined):
    from onetrace_console.serve import Handler, _render_startup_pages
    from tests.test_signin_flow import _get
    from tests.test_frame import _items
    store, base = compared
    _variant(store, base, "f" * 64, "2026-09-27T08:00:00+00:00")
    base_url, store_root = server
    old, Handler.store = Handler.store, store
    try:
        _render_startup_pages(store, store_root, Handler.config)
        status, page, _, _ = _get(base_url, f"/{COMPARISONS}")
        assert status == 200
        rows = _rows(page.decode("utf-8"))
        examined(len(rows), "links followed")
        assert len(rows) == 2
        for _, href in rows:
            assert _get(base_url, f"/{href}")[0] == 200, href
        labels = [label for label, _, _ in _items(page)]
        assert labels[:3] == ["Overview", "Runs", "Comparisons"]
        assert [label for label, _, cur in _items(page) if cur] == ["Comparisons"]
    finally:
        Handler.store = old
