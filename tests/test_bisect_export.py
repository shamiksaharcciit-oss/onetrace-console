"""A static export's first-run-to-leave page: its "Find the first run to leave after:" control is shown
disabled, with one line, "Needs a running console.", since the form is a GET to a console that isn't
there. No dead control: no form, nothing to submit. The page the console serves keeps its live form."""
from __future__ import annotations

import re
from html import unescape

from tests.test_bisect_page import CHANGED, SAME, _page, _series

NEEDS = "Needs a running console."


def _exported(tmp_path) -> str:
    from onetrace_console.export_static import export
    store, runs = _series(tmp_path / "made", [SAME, SAME, CHANGED, SAME], arrival=[1, 2, 3, 4])
    out = tmp_path / "export"
    export(tmp_path / "made", [r.key for r in runs.values()], out)
    (page,) = [p for p in out.glob("bisect-p*.html")]
    return page.read_text(encoding="utf-8")


def test_the_exported_page_shows_the_control_disabled_with_its_one_line(tmp_path, examined):
    page = _exported(tmp_path)
    examined(1, "exported page")
    assert 'data-bisect-window' in page
    assert not re.search(r"<form\b[^>]*data-bisect-window", page), "a form on the exported page"
    control = re.search(r"<p data-bisect-window data-needs-console>(.*?)</p>", page, re.S)
    assert control, page[:2000]
    assert re.search(r'<input type="text" name="after" value="" maxlength="64" disabled>', control.group(1))
    assert '<button type="button" disabled>Find</button>' in control.group(1)
    assert "Find the first run to leave after:" in unescape(control.group(1))
    assert f'<p data-needs-console>{NEEDS}</p>' in page and page.count(NEEDS) == 1


def test_the_served_page_keeps_its_live_form(tmp_path, examined):
    store, _ = _series(tmp_path / "made", [SAME, SAME, CHANGED, SAME], arrival=[1, 2, 3, 4])
    page = _page(store)
    examined(1, "served page")
    assert re.search(r'<form method="get" action="bisect" data-bisect-window>', page) and NEEDS not in page
