"""Compare on the graph (board 6), on the compare page of two graph-shaped runs.

One graph over the union of both runs' nodes, matched by node id, in the SDK's own order (the
rows of its `diff` report, which `topology.order` wrote); its links the union of both runs'
recorded `edges`. Each node carries the SDK's verdict in this page's words and the SDK's own
annotations ("present in B only", ...); every first difference is marked. Its table is the
page's changes table, one row per node, each node linking to its row.

The runs are the SDK exam's dag-r37 P, Q and R, compared by the real SDK: P against R has two
first differences; P against Q has a node in each run only. A comparison of two linear runs is
drawn as it always was.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from onetrace_console.compare import compare
from onetrace_console.render import render_diff
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_home_and_diff import GENERATED_AT, _deliver, _require_exam, compared  # noqa: F401

DAG = Path(__file__).resolve().parent.parent / ".sdk-fixtures" / "exam" / "fixtures" / "dag-r37"


@pytest.fixture
def dag_pages(store):
    _require_installed()
    _require_exam()
    runs = {n: _deliver(DAG / f"run_{n}", store) for n in "PQR"}
    pages = {}
    for a, b in (("P", "R"), ("P", "Q")):
        c = compare(runs[a], runs[b], store, ran_at=FIXED_RAN_AT)
        pages[a + b] = render_diff(c, store, generated_at=GENERATED_AT)
    return pages


def _graph(page: str) -> str:
    found = re.search(r'<section data-section="graph">.*?</section>', page, re.S)
    assert found, "no graph on the compare page"
    return found.group(0)


def _boxes(graph: str) -> list[tuple[str, str]]:
    """(href, title) of each linked box, in drawing order; the title with its quoted lines' titles."""
    return [(re.search(r'href="([^"]+)"', attrs).group(1), title)
            for attrs, title in _box_titles(graph) if 'href="' in attrs]


#: A box is drawn as a link (`<a>`) or a group (`<g>`): its own title holds the page's words, and each
#: line it quotes from the report carries its whole text as its own title. Read together, in order.
_BOX = re.compile(r'<(a|g)( [^>]*)?><rect[^>]*/><title>([^<]*)</title>(.*?)</\1>', re.S)
_QUOTED_TITLE = re.compile(r'<text class="state" data-words="report"[^>]*>[^<]*<title>([^<]*)</title>')


def _box_titles(graph: str) -> list[tuple[str, str]]:
    """(the box's opening tag, its title with its quoted lines' titles after it), in drawing order."""
    return [(attrs or "", " · ".join([title, *_QUOTED_TITLE.findall(rest)]))
            for _tag, attrs, title, rest in _BOX.findall(graph)]


def test_two_first_differences_are_both_marked_and_the_links_are_the_recorded_ones(dag_pages):
    graph = _graph(dag_pages["PR"])
    boxes = _boxes(graph)
    assert sorted(t.split(" · ")[0] for _, t in boxes) == ["alpha", "join", "zeta"]
    assert graph.count('data-mark="first"') == 2
    assert graph.count('class="link"') == 2
    titles = {t.split(" · ")[0]: t for _, t in boxes}
    assert "First difference" in titles["zeta"] and "First difference" in titles["alpha"]
    assert "Changed after it" in titles["join"]


def test_the_union_of_both_runs_nodes_and_links_with_the_sdk_s_own_words(dag_pages):
    graph = _graph(dag_pages["PQ"])
    titles = {t.split(" · ")[0]: t for _, t in _boxes(graph)}
    assert set(titles) == {"omega", "zeta", "alpha", "join"}
    assert "present in B only" in titles["omega"] and "present in A only" in titles["zeta"]
    assert "Same" in titles["alpha"]
    assert graph.count('class="link"') == 3, "zeta>join and alpha>join from P, omega>join from Q"


def test_the_order_is_the_sdk_s_and_every_node_links_to_its_row(dag_pages):
    page = dag_pages["PQ"]
    rows = re.findall(r'<tr data-node-row="(\d+)"[^>]*><td><span id="step-(\d+)"></span>[^<]*</td>'
                      r'<td class="mono">([^<]*)</td>', page)
    assert [node for _, _, node in rows] == ["omega", "zeta", "alpha", "join"], "the SDK's order"
    assert all(a == b for a, b, _ in rows)
    for href, title in _boxes(_graph(page)):
        node = title.split(" · ")[0]
        number = next(n for n, _, name in rows if name == node)
        assert href == f"#step-{number}", (node, href)
    #: Sources share one layer and keep the SDK's order top to bottom.
    ys = {t.split(" · ")[0]: int(y) for y, t in re.findall(
        r'<rect class="node" x="12" y="(\d+)"[^>]*/><title>([^<]*)</title>', _graph(page))}
    assert sorted(ys, key=ys.get) == ["omega", "zeta", "alpha"]


def test_the_table_is_the_page_s_own_and_the_graph_does_not_repeat_it(dag_pages):
    page = dag_pages["PR"]
    assert 'data-section="changes"' in page and 'data-section="graph-table"' not in page
    assert "Recorded order" not in _graph(page), "a comparison's order is the SDK's, not a run's"


def test_a_comparison_of_two_linear_runs_is_drawn_as_it_always_was(compared):  # noqa: F811
    comparison, store = compared
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    assert 'data-section="graph"' not in page and 'data-section="changes"' in page


def _ab_label(page: str) -> str:
    found = re.search(r'<p data-section="runs-ab">([^<]*(?:<span[^>]*>[^<]*</span>[^<]*)*)</p>', page)
    assert found, "no A/B label"
    return re.sub(r"<[^>]+>", "", found.group(1))


def test_runs_a_and_b_are_named_once_at_the_top(dag_pages):
    """The SDK's "present in A only / B only" is used as written, and the page says once, at the
    top, which run is A and which is B: in place of the header line, and not again in the graph."""
    page = dag_pages["PQ"]
    label = _ab_label(page)
    assert "A is the baseline" in label and "B is the candidate" in label
    assert page.count('data-section="runs-ab"') == 1, "said more than once"
    assert 'data-section="pair"' not in page, "the header line says it again"
    assert page.index('data-section="runs-ab"') < page.index("<h2>"), "not at the top"
    assert 'data-section="runs-ab"' not in _graph(page), "the graph card says it again"


def test_a_linear_comparison_needs_no_a_and_b(compared):  # noqa: F811
    comparison, store = compared
    assert 'data-section="runs-ab"' not in render_diff(comparison, store,
                                                       generated_at=GENERATED_AT)


def test_what_the_marks_leave_open_is_said_for_every_first_difference(dag_pages):
    """The linear page says why the first differing stage's output differs is not established;
    the graph page marked first differences and said nothing of it (found with item 5's demo).
    Now each frontier node has the sentence, and no other node does."""
    page = dag_pages["PR"]
    section = re.search(r'<section data-section="first-difference"[^>]*>(.*?)</section>', page,
                        re.S)
    assert section, "no caveat on the graph page"
    said = re.findall(r"<p>Why ([^<]*)&#x27;s output differs is not established by this "
                      r"evidence\.</p>", section.group(1))
    marked = [t.split(" · ")[0] for _, t in _boxes(_graph(page)) if "First difference" in t]
    assert said and sorted(said) == sorted(marked), (said, marked)


def test_the_compare_page_s_incidents_are_inside_its_skin_and_first(runs):  # noqa: F811
    """The incidents raised from the pair's runs are spliced in first, as before, and now inside
    the console's page skin (item 12), so they are drawn as the rest of the page is."""
    from dataclasses import replace

    from onetrace_console.checks import COULD_NOT_CHECK
    from tests.test_incidents import UNREADABLE_REASON
    found, store = runs
    #: A checked 0.2.0 run raises no incident of its own, so one of the pair
    #: is stored as its check runner stores an unreadable report: could not check, with its reason.
    store.put_run(replace(store.get_run(found["R"].key), check_verdict=COULD_NOT_CHECK,
                          check_note=UNREADABLE_REASON))
    page = render_diff(compare(found["P"], found["R"], store, ran_at=FIXED_RAN_AT), store,
                       generated_at=GENERATED_AT)
    assert 'data-section="incidents-raised"' in page, "the pair raised no incidents to place"
    assert re.search(r'<main>\s*(<p data-preview[^>]*>.*?</p>\s*)?<div class="cp">\s*'
                     r'<section data-section="incidents-raised">', page, re.S), "not first in the skin"


from tests.test_run_page_marks import runs  # noqa: E402,F401  P, Q and R, checked
