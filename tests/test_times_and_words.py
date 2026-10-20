"""What a time means, what "Same" means, and the runs page's words.

1. "Received" is the time this console took a run in, and says so; the run's own time, from its
    record, stands beside it where the record has one. Checked with the reference demo's
    committed runs, recorded on a declared clock days before they are taken in.
2. When a stage reads "Same" but its recorded inputs differ, the comparison page says so in
    plain words, on the changes table and on the graph: the verdict compares outputs.
3. The console's runs lists say what they are, and their time column says "When it ran".

Each check has its sabotage.
"""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "examples" / "reference-demo" / "runs"


def _console(tmp_path, runs: Path, compare=None):
    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.serve import _render_startup_pages
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    store = Store(tmp_path / "store" / "store")
    loaded = load_folder(runs, store, Config(), compare=compare)
    _render_startup_pages(store, tmp_path / "store", Config())
    return store, tmp_path / "store" / "pages", loaded


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


# ------------------------------------------------------------------ the two times

def recent_problems(home: str, runs) -> list[str]:
    from onetrace_console.words import short_time
    from onetrace_console.overview import ran_at
    head = re.search(r'<section data-section="recent-runs">.*?<thead>(.*?)</thead>', home, re.S).group(1)
    out = []
    if not ("<th>Ran</th><th>Received by this console</th>" in head):
        out.append("the columns don't say which time is which")
    for run in runs:
        row = re.search(rf'<tr data-recent="{run.key}">(.*?)</tr>', home, re.S)
        if row is None:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row.group(1), re.S)
        if _text(cells[-2]) != short_time(ran_at(run)) or _text(cells[-1]) != short_time(run.received_at):
            out.append(f"{run.run_id}: ran {_text(cells[-2])!r}, received {_text(cells[-1])!r}")
    return out


def test_received_says_it_is_this_consoles_and_the_runs_own_time_stands_beside_it(tmp_path, examined):
    import shutil
    shutil.copytree(EXAMPLE, tmp_path / "runs")
    store, pages, _ = _console(tmp_path, tmp_path / "runs")
    home = (pages / "home.html").read_text(encoding="utf-8")
    runs = store.runs()
    examined(len(runs), "runs in Recent runs")
    assert recent_problems(home, runs) == []
    from onetrace_console.overview import ran_at
    assert {ran_at(r)[:10] for r in runs} == {"2026-09-28", "2026-09-29"}, "the record's own clock"
    assert all(r.received_at[:10] != "2026-09-28" for r in runs), "taken in today, not on the record's day"
    assert "Latest received by this console" in _text(home)


def test_sabotage_the_received_time_shown_as_when_it_ran_is_named(tmp_path, examined):
    import shutil
    shutil.copytree(EXAMPLE, tmp_path / "runs")
    store, pages, _ = _console(tmp_path, tmp_path / "runs")
    home = (pages / "home.html").read_text(encoding="utf-8")
    from onetrace_console.words import time_html
    run = store.runs()[0]
    row = re.search(rf'<tr data-recent="{run.key}">(.*?)</tr>', home, re.S)
    cells = re.findall(r"<td[^>]*>.*?</td>", row.group(1), re.S)
    ran_cell = cells[-2]
    planted_row = row.group(0).replace(ran_cell, f'<td class="value">{time_html(run.received_at)}</td>', 1)
    planted = home.replace(row.group(0), planted_row, 1)
    assert planted != home
    examined(1, "planted page")
    assert any(p.startswith(run.run_id) for p in recent_problems(planted, [run]))


def test_a_record_with_no_time_gives_none_never_the_received_time(examined):
    from types import SimpleNamespace
    from onetrace_console.overview import ran_at
    cases = [(None, ""), ("{}", ""), ("not json", ""), ('{"case_ran": 7}', ""),
             ('{"case_ran": "2026-09-28T10:00:00Z \u2192 2026-09-28T10:00:05Z"}', "2026-09-28T10:00:00Z")]
    examined(len(cases), "list rows")
    for row, want in cases:
        run = SimpleNamespace(list_row=row, received_at="2026-10-11T04:00:28+00:00")
        assert ran_at(run) == want, row


# ------------------------------------------------------------------ same outputs, different inputs

def _intake_pair(root: Path, questions: tuple[str, str]) -> Path:
    from onetrace.emit import Instrument, Recorder
    runs = root / "runs"
    for name, q in zip("ab", questions):
        out = runs / name
        out.mkdir(parents=True)
        (out / "q.json").write_text(json.dumps({"question": q}), encoding="utf-8")
        rec = Recorder(str(out), run_id=f"pair-{name}", declared_stages=["intake", "answer"],
                       manifest=Path(__file__), policy="fail-closed", anchor_reason="a test record")

        def intake(ctx, out=out):
            ctx.read_external(out / "q.json", "application/json", name="question",
                              trust_class="operator-authored")
        rec.run_node("intake", None, Instrument("asker", "reader", "1.0.0", {"k": "v"}), intake)
        rec.run_node("answer", None, Instrument("answerer", "tool", "1.0.0", {"k": "v"}),
                     lambda ctx, q=q: (ctx.read_receipt("intake"),
                                       ctx.write("a.txt", q.encode("utf-8"), "text/plain"))[1])
        rec.close()
    return runs


def _intake_cell(diff: str) -> str:
    table = re.search(r'<table data-section="changes" data-verb="diff".*?</table>', diff, re.S).group(0)
    row = next(r for r in re.findall(r"<tr data-verdict[^>]*>(.*?)</tr>", table, re.S) if ">intake<" in r)
    return re.search(r"<td[^>]*\bdata-result[^>]*>(.*?)</td>", row, re.S).group(1)


def test_a_same_stage_whose_inputs_differ_says_so(tmp_path, examined):
    runs = _intake_pair(tmp_path, ("What is the refund window?", "How long does shipping take?"))
    store, pages, loaded = _console(tmp_path, runs, compare=("a", "b"))
    #: The comparison's two views: the stage table is on "Proof", the graph on "What changed".
    diff = ((pages / "diff" / f"{loaded.comparison.key}-proof.html").read_text(encoding="utf-8")
            + (pages / "diff" / f"{loaded.comparison.key}.html").read_text(encoding="utf-8"))
    cell = _text(_intake_cell(diff))
    examined(1, "comparison page")
    assert cell.startswith("Same · its inputs differ (question); the verdict compares outputs, "
                           "and this stage records none"), cell
    assert "inputs differ" in _text(re.search(r'<svg class="graph".*?</svg>', diff, re.S).group(0))


def test_sabotage_the_same_inputs_say_nothing(tmp_path, examined):
    runs = _intake_pair(tmp_path, ("What is the refund window?", "What is the refund window?"))
    store, pages, loaded = _console(tmp_path, runs, compare=("a", "b"))
    #: The stage table is on the comparison's "Proof" view.
    diff = (pages / "diff" / f"{loaded.comparison.key}-proof.html").read_text(encoding="utf-8")
    examined(1, "comparison page")
    assert _text(_intake_cell(diff)) == "Same" and 'data-inputs-differ' not in diff


# ------------------------------------------------------------------ the runs lists' words

def list_problems(page: str, filtered: bool) -> list[str]:
    from onetrace_console.pages import LIST_RAN, LIST_TITLE_ALL, LIST_TITLE_FILTERED
    title = LIST_TITLE_FILTERED if filtered else LIST_TITLE_ALL
    out = []
    if f"<h1>{title}</h1>" not in page or f"<title>{title}</title>" not in page:
        out.append("title")
    if f"<th>{LIST_RAN}</th>" not in page or "<th>ran</th>" in page:
        out.append("time column")
    if "The runs this page was given" in page:
        out.append("old title")
    return out


def _lists(tmp_path, examined):
    import shutil
    shutil.copytree(EXAMPLE, tmp_path / "runs")
    _store, pages, _ = _console(tmp_path, tmp_path / "runs")
    examined(2, "lists")
    return ((pages / "executions-all.html").read_text(encoding="utf-8"),
            (pages / "executions-records-agree.html").read_text(encoding="utf-8"))


def test_the_runs_lists_say_what_they_are_and_when_it_ran(tmp_path, examined):
    every, some = _lists(tmp_path, examined)
    assert list_problems(every, filtered=False) == []
    assert list_problems(some, filtered=True) == []


def test_sabotage_the_old_words_are_named(tmp_path, examined):
    from onetrace_console.pages import LIST_RAN, LIST_TITLE_ALL
    every, _some = _lists(tmp_path, examined)
    old_title = every.replace(LIST_TITLE_ALL, "The runs this page was given")
    old_column = every.replace(f"<th>{LIST_RAN}</th>", "<th>ran</th>")
    assert old_title != every and old_column != every
    assert "title" in list_problems(old_title, filtered=False)
    assert list_problems(old_column, filtered=False) == ["time column"]
