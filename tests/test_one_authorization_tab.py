"""A run's page has one Authorization tab: among its views, with the count of its gated steps where it has any.

On a run with a gated step the page read "Authorization · 1 gated step" in the run's tabs and "Authorization" again in
its views' tabs, two tabs to one page. The count is now on the views' tab, and the run's tabs no longer repeat it.
Read on the public demo as built: p8-49 (one gated step) and p1-01 (none), on each of their pages that carries tabs.
"""

from __future__ import annotations

import re

from tests.test_authorization_everywhere import _run_folder

TAB_ROWS = re.compile(r'<nav (?:class="tabs"|data-section="views")[^>]*>(.*?)</nav>', re.S)


def _tabs(page: str) -> list[str]:
    return [
        re.sub(r"<[^>]+>", "", a)
        for row in TAB_ROWS.findall(page)
        for a in re.findall(r'<a href="authorization\.html"[^>]*>(.*?)</a>', row, re.S)
    ]


def test_each_page_of_a_run_has_one_authorization_tab_with_its_count_where_gated(shared_demo, examined):
    seen = 0
    for run_id, label in (
        ("p8-49-invoice-paid-on-deny", "Authorization · 1 gated step"),
        ("p1-01-baseline-set1", "Authorization"),
    ):
        folder = _run_folder(shared_demo, run_id)
        for name in ("case.html", "proof.html", "authorization.html"):
            page = (folder / name).read_text(encoding="utf-8")
            assert _tabs(page) == [label], (run_id, name, _tabs(page))
            seen += 1
    examined(seen, "pages")
