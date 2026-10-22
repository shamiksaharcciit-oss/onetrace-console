"""A pipeline's drift page: `onetrace drift` over its stored runs, shown as the report gives it.

The store here holds one pipeline's four runs, delivered in this order: a baseline; a run whose
stage `b` writes something else; a run whose stage `b` records 1.2 seconds more; and a run with
one receipt byte changed after it closed (the verifier refuses it). One comparison, run 1 against
run 2, is held, so a cell links to its page; every other cell links to the pair's choose page.

The expected verdicts are not the console's: each test runs the same command itself, over the same
runs laid out the same way, and reads its own `drift.json`. The page must equal that report cell for
cell, and its exit the command's.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

import pytest

GENERATED_AT = "2026-10-04T12:00:00+00:00"
RAN_AT = "2026-09-26T12:00:00+02:00"


#: How much longer the third run's stage `b` takes than the others', in its recorded times.
SLOWER_MS = 1200


class _Clock:
    """The times the runs record: each reading one millisecond after the last, and a stage's wait
    added to them, not slept. With the machine's own clock, a baseline stage `b` that a loaded
    machine held for over 200 ms left the third run's less than `onetrace drift`'s 1000 ms
    slower, and the report listed no slower line."""

    def __init__(self) -> None:
        self.t = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)

    def now(self) -> str:
        self.t += timedelta(milliseconds=1)
        return self.t.isoformat(timespec="milliseconds")

    def wait(self, ms: int) -> None:
        self.t += timedelta(milliseconds=ms)


def _make(root: Path) -> list[Path]:
    from onetrace import emit
    from onetrace.emit import Instrument, Recorder
    tool = Instrument("tool", "tool", "1.0.0", {"x": "1"})
    clock = _Clock()
    out = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(emit, "_now", clock.now)
        for i, (b_value, b_wait) in enumerate((("1", 0), ("2", 0), ("1", SLOWER_MS), ("1", 0)), start=1):
            rec = Recorder(str(root / f"r{i}"), run_id=f"drift-{i}", declared_stages=["a", "b", "c"],
                           manifest=Path(__file__), policy="fail-closed", topology=True,
                           anchor_reason="a test record")

            def body(stage, value="1", wait=0, reads=()):
                def f(ctx):
                    for r in reads:
                        ctx.read_receipt(r)
                    if wait:
                        clock.wait(wait)
                    return ctx.write_json(f"{stage}.json", {stage: value})
                return f
            rec.run_node("a", "1", tool, body("a"))
            rec.run_node("b", "1", tool, body("b", b_value, b_wait, ["a"]))
            rec.run_node("c", "1", tool, body("c", "1", 0, ["b"]))
            rec.close()
            out.append(root / f"r{i}")
    #: The fourth: one byte of its first receipt changed after the run closed.
    first = next((out[3] / "receipts").glob("01-*.json"))
    raw = first.read_bytes()
    assert raw.count(b'"1.0.0"') == 1
    first.write_bytes(raw.replace(b'"1.0.0"', b'"1.0.1"'))
    return out


@pytest.fixture(scope="module")
def drift_store(tmp_path_factory):
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.overview import pipelines
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    from tests.test_compare import _deliver
    _require_installed()
    root = tmp_path_factory.mktemp("drift")
    store = Store(root / "store")
    runs = [run_and_record(_deliver(f, store, outputs=True), store, ran_at=RAN_AT)
            for f in _make(root / "made")]
    compare(runs[0], runs[1], store)
    (pipeline,) = pipelines(store)
    assert [r.key for r in pipeline.runs] == [r.key for r in runs], "received order"
    return store, pipeline, root


def _page(drift_store, against: str = "first") -> str:
    from onetrace_console.drift import render_drift
    store, pipeline, _root = drift_store
    return render_drift(pipeline, store, generated_at=GENERATED_AT, against=against)


def own_report(drift_store, against: str, tmp: Path) -> tuple[dict, str, int]:
    """The command run here, independently: its drift.json, its drift.txt and its exit."""
    from onetrace_console.checks import materialise
    store, pipeline, _root = drift_store
    tmp.mkdir()
    names = [f"run-{i}" for i in range(1, len(pipeline.runs) + 1)]
    for run, name in zip(pipeline.runs, names):
        materialise(run, store, tmp / name)
    proc = subprocess.run([sys.executable, "-m", "onetrace", "drift", *names, "--against", against,
                           "--durations", "--quiet", "--out", "out"], cwd=tmp, capture_output=True)
    return (json.loads((tmp / "out" / "drift.json").read_text(encoding="utf-8")),
            (tmp / "out" / "drift.txt").read_text(encoding="utf-8"), proc.returncode)


def _text(fragment: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def cell_problems(page: str, report: dict) -> list[str]:
    """Each run's line and each node's cell on the page, against the report's own, cell for cell."""
    out = []
    by_cand = {c["candidate"]: c for c in report["comparisons"]}
    for r in report["runs"]:
        row = re.search(rf'<tr data-run="{r["index"]}">(.*?)</tr>', page, re.S)
        if row is None:
            out.append(f"run {r['index']}: no line")
            continue
        said = _text(re.search(r"<td\b[^>]*\bdata-line\b[^>]*>(.*?)</td>", row.group(1), re.S).group(1))
        c = by_cand.get(r["index"])
        want = "the baseline" if c is None else f"against {c['baseline']}: {c['envelope']}"
        if not said.startswith(want):
            out.append(f"run {r['index']}: {said!r}, not {want!r}")
        if c is not None and c["reason"] and c["reason"] not in said:
            out.append(f"run {r['index']}: the verifier's words {c['reason']!r} are not on its line")
        if c is not None and c["first_difference"] and ", ".join(c["first_difference"]) not in said:
            out.append(f"run {r['index']}: its first difference is not named")
    comps = report["comparisons"]
    for n in report["nodes"]:
        row = re.search(rf'<tr data-node="{re.escape(n["node"])}">(.*?)</tr>', page, re.S)
        if row is None:
            out.append(f"node {n['node']}: no row")
            continue
        cells = re.findall(r'<li data-cell="([^"]*)">.*?<span data-verdict>(.*?)</span></li>', row.group(1), re.S)
        if [c for c, _ in cells] != [c["candidate"] for c in comps]:
            out.append(f"node {n['node']}: columns {[c for c, _ in cells]}")
            continue
        for (cand, cell), verdict in zip(cells, n["verdicts"]):
            want = "-" if verdict is None else verdict
            if _text(cell) != want:
                out.append(f"node {n['node']}, run {cand}: {_text(cell)!r}, not {want!r}")
    return out


def _exit(page: str) -> str | None:
    found = re.search(r"<span data-exit>([^<]*)</span>", page)
    return found.group(1) if found else None


@pytest.mark.parametrize("against", ["first", "previous"])
def test_the_page_is_the_command_s_report_cell_for_cell(drift_store, tmp_path, against, examined):
    report, _txt, code = own_report(drift_store, against, tmp_path / "own")
    page = _page(drift_store, against)
    examined(len(report["nodes"]) * len(report["comparisons"]) + len(report["runs"]), "cells and lines")
    assert cell_problems(page, report) == []
    assert _exit(page) == str(code) == report["exit"]


def test_a_refused_run_is_named_on_its_line_with_the_verifier_s_words(drift_store, tmp_path, examined):
    report, _txt, _code = own_report(drift_store, "first", tmp_path / "own")
    refused = [c for c in report["comparisons"] if c["envelope"] == "refused"]
    examined(len(refused), "refused runs")
    assert [c["candidate"] for c in refused] == ["4"] and refused[0]["reason"] == "does not verify: run-4"
    line = re.search(r'<tr data-run="4">(.*?)</tr>', _page(drift_store), re.S).group(1)
    assert "refused" in _text(line) and "does not verify: run-4" in _text(line)


def test_no_path_of_this_machine_is_on_the_page(drift_store, examined):
    store, _pipeline, root = drift_store
    examined(2, "drift pages")
    for against in ("first", "previous"):
        page = _page(drift_store, against)
        assert str(root) not in page and str(store.root) not in page
        assert str(Path(sys.executable).parent) not in page


def test_the_toggle_links_the_two_reports(drift_store, examined):
    from onetrace_console.drift import page_href
    _store, pipeline, _root = drift_store
    first, previous = _page(drift_store, "first"), _page(drift_store, "previous")
    examined(2, "drift pages")
    toggle = re.compile(r'<p data-section="toggle">(.*?)</p>', re.S)
    for page, here, there in ((first, "first", "previous"), (previous, "previous", "first")):
        t = toggle.search(page).group(1)
        assert f'href="{page_href(pipeline.label, there)}"' in t
        assert re.search(rf'href="{re.escape(page_href(pipeline.label, here))}" aria-current="page"', t)
    assert "--against first" in first and "--against previous" in previous


def slower_problems(page: str, txt: str, report: dict) -> list[str]:
    """The command's own slower lines, each on the page apart from the verdicts, and as many as the
    report lists; none inside a verdict table."""
    lines = [ln for ln in txt.splitlines() if ln.startswith("slower: ")]
    out = []
    if len(lines) != len(report["durations"]["slower"]):
        out.append(f"{len(lines)} slower lines, the report lists {len(report['durations']['slower'])}")
    section = re.search(r'<section data-section="drift-slower">(.*?)</section>', page, re.S)
    shown = [_text(m) for m in re.findall(r"<p data-slower[^>]*>(.*?)</p>", section.group(1), re.S)] if section else []
    if shown != lines:
        out.append(f"the page shows {shown}, the command wrote {lines}")
    for table in re.findall(r"<table.*?</table>", page, re.S):
        if "slower" in table:
            out.append("a slower line inside a verdict table")
    return out


def test_each_verdict_names_its_own_pair(drift_store, examined):
    """However many runs, a node's verdicts wrap in its row, each saying which pair it is: on a
    phone the row stacks under its two headers, and at desktop width nothing scrolls sideways."""
    page = _page(drift_store)
    examined(1, "drift page")
    row = re.search(r'<tr data-node="b#1">(.*?)</tr>', page, re.S).group(1)
    items = re.findall(r'<li data-cell="([^"]*)"><span data-pair>([^<]*)</span>', row)
    assert items and all(unescape(pair).startswith(f"{cand} vs ") for cand, pair in items), items
    assert re.findall(r'<td data-label="([^"]*)"', row) == ["Node", "Its verdict in each comparison"]


def test_the_slower_lines_are_the_command_s_and_apart_from_the_verdicts(drift_store, tmp_path, examined):
    report, txt, _code = own_report(drift_store, "first", tmp_path / "own")
    examined(1, "drift page")
    (b,) = [r["runs"] for r in report["durations"]["rows"] if r["node"] == "b#1"]
    assert int(b[2]) - int(b[0]) == SLOWER_MS, f"stage b's recorded times, run by run: {b}"
    assert report["durations"]["slower"], "the third run's stage b is slower than the baseline's"
    assert slower_problems(_page(drift_store), txt, report) == []


def test_each_cell_links_to_its_pair_s_comparison(drift_store, examined):
    from onetrace_console.choose_pages import b_anchor, held_comparisons, pair_href
    store, pipeline, _root = drift_store
    page = _page(drift_store)
    held = held_comparisons(store)
    runs = pipeline.runs
    row = re.search(r'<tr data-node="b#1">(.*?)</tr>', page, re.S).group(1)
    cells = dict(re.findall(r'<li data-cell="([^"]*)">(.*?)</li>', row, re.S))
    examined(len(cells), "cells")
    for cand, cell in cells.items():
        a, b = runs[0], runs[int(cand) - 1]
        found = held.get((a.key, b.key))
        want = f"diff/{found.key}.html" if found else f"{pair_href(pipeline.label, a.key)}#{b_anchor(b.key)}"
        assert f'href="{want}"' in cell, (cand, cell)
    assert held.get((runs[0].key, runs[1].key)) is not None and 'href="diff/' in cells["2"]


def test_the_pipeline_page_links_to_its_drift_page(drift_store, examined):
    from onetrace_console.drift import page_href
    from onetrace_console.pipeline_pages import render_pipeline
    store, pipeline, _root = drift_store
    examined(1, "pipeline page")
    page = render_pipeline(pipeline, store, generated_at=GENERATED_AT)
    assert f'href="{page_href(pipeline.label)}"' in page and 'data-link="drift"' in page


def test_the_same_runs_read_the_kept_report(drift_store, monkeypatch, examined):
    """Kept by the runs and the SDK's build: drawn again, the command is not run again."""
    from onetrace_console import drift
    _page(drift_store)
    examined(1, "drift page drawn twice")
    monkeypatch.setattr(drift, "run_drift", lambda *a, **k: pytest.fail("the command ran again"))
    _page(drift_store)


def test_a_public_console_never_runs_the_command(drift_store, monkeypatch, examined):
    """With no kept report, a public console says it holds none: it runs nothing."""
    from onetrace_console import drift
    from onetrace_console.frame import rendering_public  # noqa: F401  (the switch read below)
    store, pipeline, _root = drift_store
    monkeypatch.setattr(drift, "run_drift", lambda *a, **k: pytest.fail("a public console ran the command"))
    monkeypatch.setattr(drift, "_public", lambda: True)
    monkeypatch.setattr(store, "get_drift", lambda key: None)
    examined(1, "public drift page")
    page = drift.render_drift(pipeline, store, generated_at=GENERATED_AT)
    assert drift.NO_REPORT in unescape(page)


def test_the_drift_pages_are_pages_a_reader_may_open(examined):
    from onetrace_console import roles
    examined(3, "paths")
    for rel in ("drift-p1.html", "drift-p12-previous.html"):
        assert roles.required_role("GET", "/" + rel, rel_for_get=rel) == roles.VIEWER
    with pytest.raises(roles.NoRouteTableEntry):
        roles.required_role("GET", "/drift-p1-x.html", rel_for_get="drift-p1-x.html")


# ------------------------------------------------------------------ the sabotage

def test_sabotage_a_cell_changed_on_the_page_is_named(drift_store, tmp_path, examined):
    report, _txt, _code = own_report(drift_store, "first", tmp_path / "own")
    page = _page(drift_store)
    examined(3, "planted pages")
    row = re.search(r'<tr data-node="b#1">.*?</tr>', page, re.S).group(0)
    planted = page.replace(row, row.replace(">FIRST DIFFERENCE<", ">same<", 1), 1)
    assert planted != page and cell_problems(planted, report) != []
    line = re.search(r'<tr data-run="4">.*?</tr>', page, re.S).group(0)
    assert cell_problems(page.replace(line, line.replace("refused", "identical", 1), 1), report) != []
    assert _exit(page.replace("<span data-exit>", "<span data-exit>9", 1)) != report["exit"]


def test_sabotage_a_slower_line_left_out_or_in_a_table_is_named(drift_store, tmp_path, examined):
    report, txt, _code = own_report(drift_store, "first", tmp_path / "own")
    page = _page(drift_store)
    examined(2, "planted pages")
    gone = re.sub(r"<p data-slower[^>]*>.*?</p>", "", page, count=1, flags=re.S)
    assert slower_problems(gone, txt, report) != []
    inside = page.replace("</table>", "<tr><td>slower</td></tr></table>", 1)
    assert slower_problems(inside, txt, report) != []
