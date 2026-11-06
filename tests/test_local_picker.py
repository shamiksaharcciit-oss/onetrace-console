"""Console 0.6.1 item 4: two dropdowns to choose a pair on a local console's pipeline page.

The picker posts `POST /compare` with the two run keys and the session's CSRF token (filled into the
drawn page as it is served), through the same guards as the Compare buttons, and opens the comparison
it answers with; no GET makes a comparison. Both lists are in arrival order, each run by its name and
time. The same run twice is refused as today. The two-step pages stay, and are the only way for a
pipeline over `LIST_CAP`. A public console keeps its own picker, and a static export has none.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

import pytest

from tests.http_limits import limit
from tests.test_choose_two_runs import HOSTILE, _pages, three  # noqa: F401  (three: a fixture)
from tests.test_home_and_diff import diverging  # noqa: F401  (three's fixture)

PICKER = re.compile(r'<section id="local-compare" data-section="local-compare".*?</section>', re.S)


def _pipeline_page(pages: dict[str, str]) -> str:
    """The pipeline's own page (its "all" filter): the other filters draw the same picker."""
    from onetrace_console.pipeline_pages import page_href
    (label,) = {re.search(r"<title>Pipeline · (.*?)</title>", p).group(1) for p in pages.values()
                if 'data-section="first-differences"' in p}
    return pages[page_href(unescape(label), "all")]


def test_the_picker_lists_the_runs_in_arrival_order_by_name_and_time(three):
    from onetrace_console.frame import CSRF_SLOT
    from onetrace_console.overview import pipelines
    from onetrace_console.store import arrival_order
    comparison, store, hostile = three
    page = _pipeline_page(_pages(store))
    (picker,) = PICKER.findall(page)
    assert '<form method="post" action="/compare" data-local-compare>' + CSRF_SLOT in picker
    (p,) = pipelines(store)
    runs = arrival_order(p.runs, newest_first=False)
    for name in ("a", "b"):
        (select,) = re.findall(rf'<select name="{name}" required>(.*?)</select>', picker, re.S)
        options = re.findall(r'<option value="([0-9a-f]{64})"[^>]*>(.*?)</option>', select)
        assert [k for k, _ in options] == [r.key for r in runs]
        for (_, words), r in zip(options, runs):
            assert unescape(words) == f"{r.run_id} · {str(r.received_at).replace('T', ' ')}"
    assert "<script" not in picker and HOSTILE not in picker
    #: The two-step pages stay.
    assert 'data-link="compare">Compare two runs</a>' in page


def test_a_public_console_keeps_its_own_picker_and_a_static_export_has_none(three):
    from onetrace_console.explain import no_presses
    comparison, store, _ = three
    assert not PICKER.findall(_pipeline_page(_pages(store, public=True)))
    with no_presses():
        assert not PICKER.findall(_pipeline_page(_pages(store)))


def test_over_the_list_cap_only_the_two_step_pages_stay(three, monkeypatch):
    from onetrace_console.viewer import model
    comparison, store, _ = three
    monkeypatch.setattr(model, "LIST_CAP", 2)
    page = _pipeline_page(_pages(store))
    assert not PICKER.findall(page) and 'data-link="compare">Compare two runs</a>' in page


def test_the_csrf_slot_is_filled_as_the_page_is_served():
    from onetrace_console.frame import CSRF_SLOT, fill_csrf
    page = f"<form>{CSRF_SLOT}</form>".encode()
    assert fill_csrf(page, None) == page
    assert fill_csrf(page, 'tok"en') == b'<form><input type="hidden" name="csrf_token" value="tok&quot;en" data-csrf-slot></form>'


# ------------------------------------------------------------------ over HTTP

def _post_form(base: str, fields: dict) -> tuple[int, dict, bytes]:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    req = urllib.request.Request(base + "/compare", data=urllib.parse.urlencode(fields).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=limit(60)) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _two_runs(base):
    from tests.test_serve import _post
    from tests.test_serve import _real_delivery
    exam = Path(__file__).resolve().parent.parent / ".sdk-fixtures" / "exam" / "fixtures" / "ingest-r1"
    run_c, run_c_poppler24 = exam / "run_C", exam / "run_C_poppler24"
    if not (run_c.is_dir() and run_c_poppler24.is_dir()):
        pytest.fail(f"the SDK's exam fixtures are not there under {exam}\n    python tools/fetch_sdk_fixtures.py")
    keys = []
    for d in (run_c, run_c_poppler24):
        status, body = _post(base, "/v1/runs", _real_delivery(d))
        assert status == 200, body
        keys.append(json.loads(body)["run_key"])
    return keys


@pytest.mark.usefixtures("preview_stored_directly")
def test_the_form_posts_compare_and_opens_the_comparison(server):
    from onetrace_console.serve import SAME_RUN
    from onetrace_console.store import Store
    from tests.test_serve import _get
    base, store_root = server
    a, b = _two_runs(base)
    drawn = [p.read_text(encoding="utf-8") for p in sorted((store_root / "pages").glob("pipeline-*.html"))]
    page = next(p for p in drawn if "data-local-compare" in p)
    assert f'<option value="{a}"' in page and f'<option value="{b}"' in page
    #: No GET makes a comparison.
    assert _get(base, f"/compare?a={a}&b={b}")[0] in (400, 404)
    assert not list(Store(store_root / "store").comparisons())
    status, headers, _ = _post_form(base, {"a": b, "b": b})
    assert status == 400 and not list(Store(store_root / "store").comparisons())
    assert SAME_RUN.split(":")[0] in unescape(_post_form(base, {"a": b, "b": b})[2].decode())
    status, headers, _ = _post_form(base, {"a": a, "b": b})
    assert status == 303 and re.fullmatch(r"/diff/[^/]+\.html", headers["Location"]), headers
    assert _get(base, headers["Location"])[0] == 200
    (c,) = Store(store_root / "store").comparisons()
    assert (c.run_a, c.run_b) == (a, b)
    #: The Compare buttons' own request is answered as before: JSON.
    from tests.test_serve import _post
    status, body = _post(base, f"/compare?a={a}&b={b}")
    assert status == 200 and json.loads(body)["pages"]["diff"]


def test_an_unknown_run_is_refused_on_a_page_never_500(server):
    base, _root = server
    status, _, body = _post_form(base, {"a": "nope", "b": "alsonope"})
    assert status == 400 and b"unknown or malformed run key" in body and b"<html" in body.lower()
