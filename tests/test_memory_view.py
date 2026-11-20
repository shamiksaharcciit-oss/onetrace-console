"""A run's memory page: each step's store reads and writes in the run's order, and across runs, "read what <run>
wrote" by an equal digest, with what that lineage does and doesn't show in the store hooks' own words.

P12's runs (example data): the first run finds no note, pays and writes the vendor's note to the agent's memory; the
later runs read it. A run whose record holds no store state has no memory page and no Memory tab.
"""

from __future__ import annotations

import html
import re

import pytest

GENERATED_AT = "2026-11-18T23:45:00+00:00"


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.fixture(scope="module")
def drawn(tmp_path_factory):
    from onetrace_console import demo_store, run_index
    from onetrace_console.checks import run_and_record
    from onetrace_console.demo_store import onedoor_demo
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    from tests.token_level_runs import l3_call, record_run

    folder = tmp_path_factory.mktemp("memory")
    runs, store = folder / "runs", Store(folder / "store")
    runs.mkdir()
    issuer = onedoor_demo.Issuer()
    specs = [s for s in demo_store.runs() if s.pipeline == "p12"]
    for spec in specs:
        demo_store._record(spec, runs / spec.folder, issuer)
    issuer.write_beside(runs)
    stored = [run_and_record(_deliver(runs / s.folder, store, outputs=True), store, ran_at=FIXED_RAN_AT) for s in specs]
    plain = run_and_record(
        _deliver(record_run(folder / "plain", "no-state", l3_call(["1"], ["0" * 64])), store, outputs=True),
        store,
        ran_at=FIXED_RAN_AT,
    )
    index = run_index.build(store)
    with run_index.drawing(index), rendering(onedoor=False, sign_in=False, public=False):
        pages = {r.key: dict(render_execution(r, store, generated_at=GENERATED_AT).pages) for r in (*stored, plain)}
    return pages, stored, plain


def test_the_memory_timeline_lists_each_read_and_write_in_the_run_s_order(drawn, examined):
    pages, stored, _plain = drawn
    page = pages[stored[0].key]["memory.html"]
    examined(1, "the first run's memory page")
    rows = re.findall(r'<tr data-memory="(read|written)"><td[^>]*><a href="(stage-\d+\.html)"', page)
    assert rows == [("read", "stage-2.html"), ("written", "stage-5.html")], rows
    text = _text(page)
    assert "agent-memory.vendor-notes" in text and "found nothing" in text


def test_across_runs_a_later_run_reads_what_the_first_run_wrote(drawn, examined):
    pages, stored, _plain = drawn
    page = pages[stored[3].key]["memory.html"]
    examined(1, "a later run's memory page")
    across = re.search(r'<section data-section="memory-across">.*?</section>', page, re.S).group(0)
    assert f'href="../{stored[0].key}/stage-5.html"' in across
    assert stored[0].run_id in _text(across) and "equal digest" in _text(across)
    #: What lineage by digest does not show, in the store hooks' own words.
    assert "Lineage is equality of recorded digests or versions" in _text(page)


def test_the_run_s_pages_point_at_one_another(drawn, examined):
    pages, stored, _plain = drawn
    own = pages[stored[0].key]
    examined(3, "pages of one run")
    assert 'href="memory.html"' in own["case.html"]
    links = re.search(r'<p data-section="memory-links">.*?</p>', own["memory.html"], re.S).group(0)
    assert 'href="call-3.html"' in links and 'href="authorization.html"' in links
    assert "call-3.html" in own and 'href="case.html"' in own["call-3.html"]


def test_a_run_with_no_store_state_has_no_memory_page_or_tab(drawn, examined):
    pages, _stored, plain = drawn
    examined(1, "a run without store state")
    assert "memory.html" not in pages[plain.key]
    assert 'href="memory.html"' not in pages[plain.key]["case.html"]
