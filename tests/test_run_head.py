"""The run page's head and graph.

The head names the run and its pipeline and -- only where the run is a comparison's candidate --
carries the comparison, naming its baseline. It gives no one-word verdict: the ladder's questions
are separate. Its four first questions are
the page's own ladder rungs, as the ladder states them. Its times are the record's own and this
console's, each named. A straight-line run's graph wraps at four boxes a row and still reads in
the record's order, with no line drawn between boxes (the record holds no links).

Each check has its sabotage.
"""
from __future__ import annotations

import re
import shutil

import pytest
from html import unescape
from pathlib import Path

from tests.test_times_and_words import EXAMPLE, _console, _intake_pair


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _head(page: str) -> str:
    return re.search(r'<section data-section="run-head">.*?</section>', page, re.S).group(0)


def head_problems(page: str, run_id: str, label: str, baseline: str | None) -> list[str]:
    """What the head gets wrong against the page's own ladder and the run's own facts."""
    out = []
    if page.count('<section data-section="run-head">') != 1:
        return ["no single head"]
    head = _head(page)
    h1 = _text(re.search(r'<h1 class="run-title">(.*?)</h1>', head, re.S).group(1))
    if h1 != f"{run_id} · {label}":
        out.append(f"h1 {h1!r}")
    if page.count("<h1") != 1:
        out.append("more than one h1")
    ladder = dict(re.findall(r'<tr data-rung="([^"]+)" data-state="([^"]+)">', page))
    for key, state in re.findall(r'<li data-head-rung="([^"]+)" data-state="([^"]+)">', head):
        if ladder.get(key) != state:
            out.append(f"rung {key}: head {state}, ladder {ladder.get(key)}")
    chips = _text(head)
    from onetrace_console.home import VERDICT_LABELS
    title = _text(re.search(r'<div class="title">(.*?)</div>', head, re.S).group(1))
    if any(word in title for word in VERDICT_LABELS.values()):
        out.append("a one-word verdict beside the title")
    if baseline is None and "vs " in chips:
        out.append("a comparison chip with no comparison")
    if baseline is not None and f"vs {baseline}" not in chips:
        out.append("the comparison's baseline is not named")
    return out


def test_the_head_names_the_run_and_states_the_ladder(tmp_path, examined):
    shutil.copytree(EXAMPLE, tmp_path / "runs")
    store, pages, _ = _console(tmp_path, tmp_path / "runs")
    from onetrace_console.overview import pipelines
    labels = {r.key: p.label for p in pipelines(store) for r in p.runs}
    runs = store.runs()
    examined(len(runs), "run pages")
    for run in runs:
        page = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
        assert head_problems(page, run.run_id, labels[run.key], None) == [], run.run_id
        head = _head(page)
        assert "received by this console" in _text(head) and "ran " in _text(head)


def test_sabotage_a_head_that_disagrees_with_its_ladder_is_named(tmp_path, examined):
    shutil.copytree(EXAMPLE, tmp_path / "runs")
    store, pages, _ = _console(tmp_path, tmp_path / "runs")
    from onetrace_console.overview import pipelines
    run = store.runs()[0]
    label = next(p.label for p in pipelines(store) for r in p.runs if r.key == run.key)
    page = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
    planted = page.replace('<li data-head-rung="records-agree" data-state="yes">',
                           '<li data-head-rung="records-agree" data-state="no">', 1)
    chip = page.replace("</h1>", '</h1><span class="pill bad">Changed vs someone</span>', 1)
    from onetrace_console.home import VERDICT_LABELS
    verdict = page.replace("</h1>", f'</h1><span class="pill ok">{VERDICT_LABELS["holds"]}</span>', 1)
    examined(3, "planted pages")
    assert planted != page and chip != page and verdict != page
    assert "a one-word verdict beside the title" in head_problems(verdict, run.run_id, label, None)
    assert any(p.startswith("rung records-agree") for p in head_problems(planted, run.run_id, label, None))
    assert "a comparison chip with no comparison" in head_problems(chip, run.run_id, label, None)


def test_a_candidate_names_its_baseline_and_its_first_difference(tmp_path, examined):
    runs = _intake_pair(tmp_path, ("What is the refund window?", "How long does shipping take?"))
    store, pages, loaded = _console(tmp_path, runs, compare=("a", "b"))
    b = store.get_run(loaded.comparison.run_b)
    page = (pages / "runs" / b.key / "case.html").read_text(encoding="utf-8")
    examined(1, "candidate's run page")
    from onetrace_console.overview import pipelines
    label = next(p.label for p in pipelines(store) for r in p.runs if r.key == b.key)
    assert head_problems(page, "pair-b", label, "pair-a") == []
    head = _head(page)
    assert "Changed vs pair-a · first difference at answer" in _text(head)
    assert f'href="../../diff/{loaded.comparison.key}.html"' in head
    a = store.get_run(loaded.comparison.run_a)
    base = (pages / "runs" / a.key / "case.html").read_text(encoding="utf-8")
    assert "vs " not in _text(_head(base)), "the baseline's own page has no comparison it is the candidate of"


def _boxes(page: str) -> list[tuple[int, int, str]]:
    svg = re.search(r'<section data-section="graph".*?<svg class="graph".*?</svg>', page, re.S).group(0)
    return [(int(y), int(x), href) for href, x, y in
            re.findall(r'<a href="([^"]+)"><rect class="node" x="(\d+)" y="(\d+)"', svg)]


def graph_problems(page: str, steps: int, reads: int | None = None) -> list[str]:
    """`reads`: how many of the run's stages record reading the stage just before them; exactly
    that many lines are drawn (None: not counted, for a run whose stage names repeat)."""
    boxes = _boxes(page)
    out = []
    if len(boxes) != steps:
        out.append(f"{len(boxes)} boxes for {steps} steps")
    if steps > 4 and len({y for y, _x, _h in boxes}) < 2:
        out.append("one row")
    reading = [int(re.search(r"(\d+)(?:\.html)?$", h).group(1)) for _y, _x, h in sorted(boxes)]
    if reading != sorted(reading):
        out.append("not read in the record's order")
    lines = page.count('<path class="link"')
    if reads is not None and lines != reads:
        out.append(f"{lines} lines drawn for {reads} recorded reads")
    return out


def _reads(run, store) -> int | None:
    """The run's consecutive recorded reads, from its stored receipts; None where a name repeats."""
    from onetrace_console.stage_pages import _steps
    receipts = [s["receipt"] for s in _steps(run, store)]
    names = [r["stage"]["name"] for r in receipts]
    if len(set(names)) != len(names):
        return None
    return sum(f"receipt:{a}" in {i.get("name") for i in r.get("inputs") or []}
               for a, r in zip(names, receipts[1:]))


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """The public demo, built once."""
    from onetrace_console.folder_load import build_public
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("demo") / "demo"
    build_public(folder)
    return Store(folder / "store" / "store"), folder / "store" / "pages"


def _lines(demo):
    store, pages = demo
    out = []
    for run in store.runs():
        page = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
        if 'data-section="graph-linear"' in page:
            out.append((run, page))
    return out


def test_a_long_line_wraps_and_reads_in_the_records_order(demo, examined):
    lines = _lines(demo)
    long = [(r, p) for r, p in lines if len(_boxes(p)) > 4]
    examined(len(long), "straight-line run pages of more than four boxes")
    assert long, "the demo holds straight-line runs longer than a row"
    store, _pages = demo
    for run, page in lines:
        assert graph_problems(page, len(_boxes(page)), _reads(run, store)) == [], run.run_id


def test_sabotage_a_shuffled_linked_or_single_row_graph_is_named(demo, examined):
    run, page = next((r, p) for r, p in _lines(demo) if len(_boxes(p)) > 4)
    boxes = _boxes(page)
    one_row = re.sub(r'(<rect class="node" x="\d+" y=")\d+(")', r"\g<1>12\2", page)
    by_place = sorted(boxes)
    (y1, x1, _), (y2, x2, _) = by_place[0], by_place[1]
    swapped = (page.replace(f'x="{x1}" y="{y1}"', 'x="SWAP" y="SWAP"', 1)
               .replace(f'x="{x2}" y="{y2}"', f'x="{x1}" y="{y1}"', 1)
               .replace('x="SWAP" y="SWAP"', f'x="{x2}" y="{y2}"', 1))
    linked = page.replace("</svg>", '<path class="link" d="M0,0"/></svg>', 1)
    examined(3, "planted pages")
    assert "one row" in graph_problems(one_row, len(boxes))
    assert "not read in the record's order" in graph_problems(swapped, len(boxes))
    reads = _reads(run, demo[0])
    assert reads is not None and graph_problems(page, len(boxes), reads) == []
    assert f"{reads + 1} lines drawn for {reads} recorded reads" in graph_problems(linked, len(boxes), reads)


def test_the_headline_candidate_names_its_baseline_and_split(demo, examined):
    from onetrace_console.demo_store import COMPARISONS
    from onetrace_console.overview import pipelines
    store, pages = demo
    by_id = {r.run_id: r for r in store.runs()}
    base, cand = (by_id[name] for name in COMPARISONS[0])
    page = (pages / "runs" / cand.key / "case.html").read_text(encoding="utf-8")
    label = next(p.label for p in pipelines(store) for r in p.runs if r.key == cand.key)
    examined(1, "headline candidate's run page")
    assert head_problems(page, cand.run_id, label, base.run_id) == []
    assert f"Changed vs {base.run_id} · first difference at split" in _text(_head(page))


def _box_titles(page: str) -> list[str]:
    return [t for _h, t in _boxes_with_titles(page)]


def _boxes_with_titles(page: str) -> list[tuple[str, str]]:
    return [(h, t) for h, t, _drawn in _boxes_drawn(page)]


def _boxes_drawn(page: str) -> list[tuple[str, str, int]]:
    """(link, title, state lines drawn) for each box."""
    svg = re.search(r'<section data-section="graph".*?<svg class="graph".*?</svg>', page, re.S).group(0)
    return [(h, unescape(t), body.count('class="state"')) for h, t, body in
            re.findall(r'<a href="([^"]+)"[^>]*><rect class="node"[^>]*/><title>([^<]*)</title>(.*?)</a>',
                       svg, re.S)]


def node_problems(page: str, receipts: list[dict]) -> list[str]:
    """Each box's lines against the record: its fact (the step's output files, or "N attempts"
    for a stage retried after a failed attempt -- the store's retry rule) and, where no comparison
    marks the page, its chip: the step table's own words for what the check found for that step."""
    from collections import Counter

    from onetrace_console.render import _RESULT_WORDS
    failed, retried = set(), set()
    for r in receipts:
        name = r["stage"]["name"]
        if name in failed:
            retried.add(name)
        if r["outcome"].get("class") == "error":
            failed.add(name)
    count = Counter(r["stage"]["name"] for r in receipts)
    by_name = {r["stage"]["name"]: r for r in receipts}
    checks = {n: " ".join(unescape(re.sub(r"<[^>]+>", " ", c)).split()) for n, c in
              re.findall(r'<tr data-step="(\d+)">(?:<td.*?</td>){2}<td[^>]*>(.*?)</td>', page, re.S)}
    verdicts = set(_RESULT_WORDS.values())
    out = []
    #: A page whose step table this cannot read would check no chip at all: said, never passed.
    if 'data-section="graph-marked-from"' not in page and not checks:
        out.append("no step's check words read from the step table")
    for href, title, drawn in _boxes_drawn(page):
        label, *lines = title.split(" · ")
        if drawn < min(3, len(lines)):
            out.append(f"{label}: {drawn} of its {len(lines)} lines drawn")
        marked = bool(lines) and lines[0] in verdicts
        if marked:
            lines = lines[1:]
        name = label.split(" ×")[0]
        r = by_name.get(name)
        if r is None:
            out.append(f"{label}: no receipt")
            continue
        n = len(r.get("outputs") or [])
        want = (f"{count[name]} attempts" if name in retried
                else f"{n} output file" + ("" if n == 1 else "s"))
        if not lines or lines[0] != want:
            out.append(f"{label}: fact {lines[:1]} for {want!r}")
        step = re.search(r"(\d+)(?:\.html)?$", href).group(1)
        if not marked and checks.get(step) and checks[step] not in lines[1:]:
            out.append(f"{label}: chip {lines[1:2]} for {checks[step]!r}")
    return out


def test_each_node_carries_a_fact_from_the_record_and_its_check(demo, examined):
    from onetrace_console.stage_pages import _steps
    store, pages = demo
    boxes = 0
    for run in store.runs():
        page = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
        receipts = [s["receipt"] for s in _steps(run, store)]
        assert node_problems(page, receipts) == [], run.run_id
        boxes += len(_box_titles(page))
    examined(boxes, "graph boxes")
    retried = next(r for r in store.runs() if r.run_id.endswith("lookup-retried"))
    titles = _box_titles((pages / "runs" / retried.key / "case.html").read_text(encoding="utf-8"))
    assert any(t.startswith("lookup_account ×2 · 2 attempts") for t in titles), titles


def test_sabotage_a_node_fact_the_record_does_not_hold_is_named(demo, examined):
    from onetrace_console.stage_pages import _steps
    store, pages = demo
    run = store.runs()[0]
    page = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
    receipts = [s["receipt"] for s in _steps(run, store)]
    planted = re.sub(r"(<title>[^<]*?)\b1 output file\b", r"\g<1>318 chunks", page, count=1)
    examined(1, "planted page")
    assert planted != page and node_problems(page, receipts) == []
    assert any(": fact ['318 chunks']" in p for p in node_problems(planted, receipts))
    unmarked = next((r, p) for r in store.runs()
                    for p in [(pages / "runs" / r.key / "case.html").read_text(encoding="utf-8")]
                    if 'data-section="graph-marked-from"' not in p)
    page2 = unmarked[1]
    chip = re.sub(r"(<title>[^<]*?)Checked — it holds\.", r"\g<1>Checked — all clear.", page2, count=1)
    examined(1, "planted page")
    assert chip != page2
    assert any(": chip ['Checked — all clear.']" in p for p in node_problems(
        chip, [s["receipt"] for s in _steps(unmarked[0], store)]))
