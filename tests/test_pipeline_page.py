"""A pipeline's page: its stage chain with where its stored comparisons first differ, its runs as
tiles, the filters, and the way to compare two of its runs.

Checked on the demo, as a public console serves it:
1. one page per pipeline, `pipeline-pN.html`, and its two filters, `-agree` and `-attention`;
2. the stage chain is the pipeline's declared stages, each with the number of the pipeline's stored
   comparisons that first differ there, as each comparison's stored report reads
   (`overview.comparison_reading`); none computed for the page;
3. the runs as tiles, oldest first, each with its "Records agree" as its own page reads it
   (`records.state`) and one line: its run page's comparison, as the Overview reads it
   (`overview.vs_baseline`); a run that is only a stored comparison's baseline says that;
4. the filters hold exactly the pipeline's runs whose records agree, and exactly those the
   Overview says need attention -- the same runs as the console's own counts;
5. "Compare two runs" leads to the pipeline's existing choice of two runs; no form, no button,
   no script of its own;
6. a tile's first difference names the stage its run page's own head names.
A pipeline's name from the demo builder is shown on a public demo only.

Each check is a function returning the problems it finds; each has its sabotage.
"""
from __future__ import annotations

import html
import re

import pytest

DEMO: dict = {}


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_demo["folder"]
    pages = folder / "store" / "pages"
    DEMO.update(folder=folder, store=Store(folder / "store" / "store"), pages=pages)
    return DEMO


def _read(rel: str) -> str:
    return (DEMO["pages"] / rel).read_text(encoding="utf-8")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _tiles(page: str) -> list[tuple[str, str, str]]:
    """(run key, state, line) for each tile, in page order."""
    return [(k, s, _text(line)) for k, s, line in re.findall(
        r'<li data-run="([0-9a-f]{64})" data-state="([\w-]+)">.*?<p data-line="vs">(.*?)</p>',
        page, re.S)]


def _stages(page: str, pipeline) -> list[tuple[str, int]]:
    """(stage, count) under each stage, the stage read by its place in the declared list."""
    return [(pipeline.stages[int(i)], int(c)) for i, c in re.findall(
        r'<li data-stage="(\d+)" data-first-differences="(\d+)">', page)]


def pages_problems(store, read) -> list[str]:
    from onetrace_console.overview import pipelines
    from onetrace_console.pipeline_pages import FILTERS, page_href
    out = []
    for p in pipelines(store):
        for f in FILTERS:
            try:
                read(page_href(p.label, f))
            except FileNotFoundError:
                out.append(f"{p.label}: no page {page_href(p.label, f)}")
    return out


def stage_problems(store, read) -> list[str]:
    """Each declared stage once, in order, with the stored comparisons that first differ there."""
    from onetrace_console.overview import comparison_reading, pipelines
    out = []
    for p in pipelines(store):
        keys = {r.key for r in p.runs}
        want = {s: 0 for s in p.stages}
        for c in store.comparisons():
            if c.run_a in keys and c.run_b in keys:
                state, stages, _ = comparison_reading(c, store)
                for s in stages if state == "changed" else ():
                    if s in want:
                        want[s] += 1
        got = _stages(read(f"pipeline-{p.label.lower()}.html"), p)
        if got != list(want.items()):
            out.append(f"{p.label}: stages {got}, the stored comparisons say {list(want.items())}")
    return out


def tile_problems(store, read) -> list[str]:
    from onetrace_console import records
    from onetrace_console.overview import pipelines
    from onetrace_console.pipeline_pages import run_line
    out = []
    for p in pipelines(store):
        got = _tiles(read(f"pipeline-{p.label.lower()}.html"))
        want = [(r.key, records.state(r, store), _text(html.escape(run_line(r, store)))) for r in p.runs]
        if got != want:
            out.append(f"{p.label}: tiles {[(k[:8], s, l) for k, s, l in got]} "
                       f"!= {[(k[:8], s, l) for k, s, l in want]}")
    return out


def filter_problems(store, read) -> list[str]:
    """The filters' runs are the console's own counts' runs, within the pipeline."""
    from onetrace_console.home import tallies
    from onetrace_console.overview import pipelines
    by_slug = {t.slug: t for t in tallies(store)}
    out = []
    for p in pipelines(store):
        keys = [r.key for r in p.runs]
        for f, slug in (("agree", "records-agree"), ("attention", "needs-attention")):
            counted = {r.key for r in by_slug[slug].runs}
            want = [k for k in keys if k in counted]
            got = [k for k, _, _ in _tiles(read(f"pipeline-{p.label.lower()}-{f}.html"))]
            if got != want:
                out.append(f"{p.label} {f}: {len(got)} tiles, the count {slug} holds {len(want)}")
    return out


def compare_problems(store, read) -> list[str]:
    from onetrace_console.choose_pages import choose_href
    from onetrace_console.overview import pipelines
    out = []
    for p in pipelines(store):
        page = read(f"pipeline-{p.label.lower()}.html")
        if f'<a href="{choose_href(p.label)}" data-link="compare">Compare two runs</a>' not in page:
            out.append(f"{p.label}: no link to compare two runs")
        main = page[page.index("<main>"):page.index("</main>")]
        for tag in ("<form", "<button", "<input", "<script"):
            if tag in main:
                out.append(f"{p.label}: a {tag}> on the page")
    return out


def head_problems(store, read) -> list[str]:
    """A tile's first difference is the stage its run page's head names."""
    from onetrace_console.overview import pipelines
    out = []
    for p in pipelines(store):
        for key, _, line in _tiles(read(f"pipeline-{p.label.lower()}.html")):
            m = re.match(r"First difference · stage \S+ · (.+)$", line)
            if not m:
                continue
            case = read(f"runs/{key}/case.html")
            head = re.search(r"first difference at ([^<]+?)<", case)
            if not head or html.unescape(head.group(1)).strip() != m.group(1):
                out.append(f"{p.label} {key[:8]}: tile says {m.group(1)!r}, run page "
                           f"{head.group(1) if head else None!r}")
    return out


CHECKS = (pages_problems, stage_problems, tile_problems, filter_problems, compare_problems,
          head_problems)


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.__name__)
def test_each_pipeline_page_reads_as_the_console_does(demo, check, examined):
    assert check(demo["store"], _read) == []
    examined(1, check.__name__)


def test_the_demo_holds_what_the_checks_need(demo):
    """The checks read something: a first difference, a run only ever a baseline, both filters."""
    from onetrace_console.overview import pipelines
    store = demo["store"]
    lines = [l for p in pipelines(store) for _, _, l in _tiles(_read(f"pipeline-{p.label.lower()}.html"))]
    assert any(l.startswith("First difference") for l in lines), lines
    assert any(l == "Baseline of a stored comparison" for l in lines), lines
    assert sum(c for p in pipelines(store) for _, c in _stages(_read(f"pipeline-{p.label.lower()}.html"), p)) > 0


def test_a_pipeline_without_comparisons_says_so(demo):
    from onetrace_console.overview import comparison_reading, pipelines
    store = demo["store"]
    for p in pipelines(store):
        keys = {r.key for r in p.runs}
        page = _read(f"pipeline-{p.label.lower()}.html")
        held = [c for c in store.comparisons() if c.run_a in keys and c.run_b in keys]
        said = "No comparison stored for this pipeline." in _text(page)
        assert said == (not held), (p.label, len(held))
    del comparison_reading


def test_the_builder_s_name_is_shown_on_a_public_demo_only(demo):
    from onetrace_console.overview import pipelines
    from onetrace_console.pipeline_pages import render_pipeline
    store = demo["store"]
    for p in pipelines(store):
        public = _read(f"pipeline-{p.label.lower()}.html")
        assert re.search(r'<h1>[^<]*<span data-name>', public), p.label
        local = render_pipeline(p, store, generated_at="2026-01-01T00:00:00+00:00")
        assert "data-name" not in local, p.label


# ------------------------------------------------------------------------------- sabotages

def _planted(change):
    """A reader that serves the demo's pages with one changed by `change(rel, text)`."""
    return lambda rel: change(rel, _read(rel))


def test_sabotage_a_missing_filter_page_is_named(demo):
    def read(rel):
        if rel.endswith("-attention.html") and "-p1-" in rel:
            raise FileNotFoundError(rel)
        return _read(rel)
    assert any("no page" in p for p in pages_problems(demo["store"], read))


def test_sabotage_a_count_moved_to_another_stage_is_named(demo):
    def change(rel, text):
        n = re.findall(r'data-first-differences="(\d+)"', text)
        if rel.startswith("pipeline-") and any(int(x) for x in n):
            text = re.sub(r'data-first-differences="(\d+)"', lambda m: 'data-first-differences="0"',
                          text, count=0)
        return text
    assert stage_problems(demo["store"], _planted(change))


def test_sabotage_a_tile_s_state_swapped_is_named(demo):
    def change(rel, text):
        return text.replace('data-state="no"', 'data-state="yes"', 1) if rel == "pipeline-p1.html" else text
    assert any("P1" in p for p in tile_problems(demo["store"], _planted(change)))


def test_sabotage_a_filter_leaking_a_run_is_named(demo):
    def change(rel, text):
        if rel == "pipeline-p1-agree.html":
            whole = _read("pipeline-p1.html")
            return whole
        return text
    assert any("P1 agree" in p for p in filter_problems(demo["store"], _planted(change)))


def test_sabotage_the_compare_link_dropped_or_a_form_added_is_named(demo):
    def drop(rel, text):
        return text.replace('data-link="compare"', 'data-link="gone"')
    def form(rel, text):
        return text.replace("</main>", "<form></form></main>")
    assert compare_problems(demo["store"], _planted(drop))
    assert any("<form" in p for p in compare_problems(demo["store"], _planted(form)))


def test_sabotage_a_tile_naming_another_stage_is_named(demo):
    def change(rel, text):
        return re.sub(r"(First difference · stage \S+ · )([^<]+)", r"\1elsewhere", text) \
            if rel.startswith("pipeline-") else text
    assert head_problems(demo["store"], _planted(change))
