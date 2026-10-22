"""A step page's "This step in the other runs": the same step as each other run of its pipeline
recorded it -- the outcome, the settings, the instrument and the outputs.

1. Every step page of the public demo has the section, one row per other run of its pipeline,
   newest first; a row that recorded the step links to that run's page for the same step.
2. "Same as this run" marks a value by exact equality with this page's own receipt: settings,
   instrument and each output. Inputs are never compared -- an input that is an earlier step's
   receipt holds each run's own receipt -- so a row reads the same whatever its inputs.
3. A run that did not record the step says so; a run the store is missing part of says that,
   and is not read.
4. Past OTHER_RUNS_SHOWN other runs, the newest are shown and the page says how many there are.
5. A hostile setting, value or output name is escaped: markup is text, and control and
   bidirectional characters are not drawn raw.

Each check has its sabotage.
"""
from __future__ import annotations

import copy
import re
from html import unescape

import pytest


@pytest.fixture(scope="module")
def demo(shared_demo):
    """The public demo, built once."""
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_demo["folder"]
    return Store(folder / "store" / "store"), folder / "store" / "pages"


def _section(page: str) -> str:
    m = re.search(r'<section data-section="other-runs">.*?</section>', page, re.S)
    return m.group(0) if m else ""


def _rows(section: str) -> list[tuple[str, str, str]]:
    """(run key, outcome, the row's HTML) for each row, in order."""
    return re.findall(r'<tr data-run="([0-9a-f]+)" data-outcome="([^"]*)">(.*?)</tr>', section, re.S)


def section_problems(store, pages) -> tuple[int, list[str]]:
    from onetrace_console.overview import pipelines
    from onetrace_console.stage_pages import OTHER_RUNS_SHOWN
    out, seen = [], 0
    for p in pipelines(store):
        for run in p.runs:
            want = [r.key for r in reversed(p.runs) if r.key != run.key][:OTHER_RUNS_SHOWN]
            for page_path in sorted((pages / "runs" / run.key).glob("stage-*.html")):
                seen += 1
                page = page_path.read_text(encoding="utf-8")
                stage = re.search(r"<h1>.*?</h1>", page, re.S).group(0)
                rows = _rows(_section(page))
                if [k for k, _o, _h in rows] != want:
                    out.append(f"{run.key[:12]}/{page_path.name}: rows {len(rows)}, not the pipeline's other runs newest first")
                for key, outcome, row in rows:
                    link = re.match(r'<td[^>]*><a href="\.\./([0-9a-f]+)/(stage-\d+\.html)">', row)
                    if outcome in ("no-receipt", "not-read"):
                        if link:
                            out.append(f"{run.key[:12]}/{page_path.name}: {key[:12]} links with no receipt")
                        continue
                    if not link or link.group(1) != key:
                        out.append(f"{run.key[:12]}/{page_path.name}: {key[:12]} has no link to its step")
                        continue
                    target = pages / "runs" / key / link.group(2)
                    if not target.is_file() or re.search(r"<h1>.*?</h1>", target.read_text(encoding="utf-8"),
                                                         re.S).group(0) != stage:
                        out.append(f"{run.key[:12]}/{page_path.name}: {key[:12]}'s link is not the same step")
    return seen, out


def test_every_step_page_shows_the_step_in_its_pipeline_s_other_runs(demo, examined):
    seen, problems = section_problems(*demo)
    examined(seen, "step pages, each with the step in the other runs")
    assert seen and problems == []


def test_sabotage_a_row_left_out_is_named(demo, tmp_path, examined):
    import shutil
    store, pages = demo
    copied = tmp_path / "pages"
    shutil.copytree(pages, copied)
    page = next(p for p in sorted(copied.rglob("stage-*.html")) if _rows(_section(p.read_text(encoding="utf-8"))))
    text = page.read_text(encoding="utf-8")
    first = re.search(r'<tr data-run="[0-9a-f]+" data-outcome="[^"]*">.*?</tr>', text, re.S).group(0)
    page.write_text(text.replace(first, "", 1), encoding="utf-8")
    examined(1, "planted page")
    assert any("not the pipeline's other runs" in p for p in section_problems(store, copied)[1])


def test_the_demo_shows_each_kind_of_outcome_it_holds(demo, examined):
    """The failed answer of the demo's run 20, the retried lookup of its P3 run, and its declined
    P4 run, which has no receipt for `send`, are rows."""
    _store, pages = demo
    outcomes = {o for p in pages.rglob("stage-*.html")
                for _k, o, _h in _rows(_section(p.read_text(encoding="utf-8")))}
    examined(len(outcomes), "kinds of outcome shown")
    assert {"ok", "error", "refused", "no-receipt"} <= outcomes, outcomes
    attempts = [h for p in pages.rglob("stage-*.html")
                for _k, _o, h in _rows(_section(p.read_text(encoding="utf-8"))) if "the last of 2 attempts" in h]
    assert attempts, "a retried step does not say its row is the last attempt"


# -- the row itself, from receipts written here ------------------------------------------------

D = "sha256:" + "ab" * 32
RECEIPT = {
    "stage": {"index": "2", "name": "split"},
    "outcome": {"class": "ok"},
    "assertions": {"constants": {"chunk_size": "512", "overlap": "64"}},
    "instrument": {"id": "char-splitter", "version": "1.0.0", "config_digest": "sha256:" + "cd" * 32},
    "inputs": [{"name": "receipt:load_docs", "digest": "sha256:" + "11" * 32},
               {"name": "documents.json", "digest": "sha256:" + "22" * 32}],
    "outputs": [{"name": "chunks.json", "digest": D}],
}


def _row(demo, other_receipt, mine=RECEIPT, monkeypatch=None):
    from onetrace_console.stage_pages import _other_row, _recorded
    store, _pages = demo
    run = next(iter(store.runs()))
    return _other_row(store, run, [{"index": "2", "file": "receipts/02-split.json", "receipt": other_receipt}],
                      "split", _recorded(mine))


def marks(row: str) -> int:
    return row.count('data-same="this-run"')


def test_each_value_equal_to_this_run_s_is_marked(demo, examined):
    examined(3, "values compared: settings, instrument, output")
    assert marks(_row(demo, RECEIPT)) == 3
    changed = copy.deepcopy(RECEIPT)
    changed["assertions"]["constants"]["chunk_size"] = "1024"
    assert marks(_row(demo, changed)) == 2
    changed["outputs"][0]["digest"] = "sha256:" + "ef" * 32
    assert marks(_row(demo, changed)) == 1


def test_inputs_are_never_compared(demo, examined):
    other = copy.deepcopy(RECEIPT)
    other["inputs"][0]["digest"] = "sha256:" + "99" * 32
    examined(1, "a row whose receipt input differs")
    assert _row(demo, other) == _row(demo, RECEIPT)


def test_sabotage_a_row_that_compares_inputs_is_named(demo, monkeypatch, examined):
    from onetrace_console import stage_pages
    real = stage_pages._recorded

    def with_inputs(receipt):
        settings, inst, outputs = real(receipt)
        return settings, inst, {**outputs, **{i["name"]: i["digest"] for i in receipt.get("inputs") or []}}
    monkeypatch.setattr(stage_pages, "_recorded", with_inputs)
    other = copy.deepcopy(RECEIPT)
    other["inputs"][0]["digest"] = "sha256:" + "99" * 32
    examined(1, "planted comparison of inputs")
    assert _row(demo, other) != _row(demo, RECEIPT)


def test_a_run_without_the_step_or_missing_part_of_it_says_so(demo, examined):
    from onetrace_console.stage_pages import NO_RECEIPT, NOT_READ, _other_row, _recorded
    store, _pages = demo
    run = next(iter(store.runs()))
    examined(2, "rows")
    assert unescape(NO_RECEIPT) in unescape(_other_row(store, run, [], "split", _recorded(RECEIPT)))
    assert unescape(NOT_READ) in unescape(_other_row(store, run, None, "split", _recorded(RECEIPT)))


def test_past_the_cap_the_newest_are_shown_and_counted(demo, monkeypatch, examined):
    from onetrace_console import stage_pages
    from onetrace_console.overview import pipelines
    store, _pages = demo
    big = max(pipelines(store), key=lambda p: len(p.runs))
    monkeypatch.setattr(stage_pages, "OTHER_RUNS_SHOWN", 3)
    label, others, total = stage_pages._other_runs(big.runs[0], store)
    examined(len(others), "rows past the cap")
    assert [r.key for r, _s in others] == [r.key for r in reversed(big.runs[1:])][:3]
    assert total == len(big.runs) - 1 > 3
    section = stage_pages._in_other_runs(store, "split", RECEIPT, label, others, total)
    assert f"The newest 3 of {total} other runs in {label} are shown." in unescape(section)


def test_a_hostile_setting_value_and_output_name_stay_escaped(demo, examined):
    rlo, bell = "\u202e", "\x07"
    other = copy.deepcopy(RECEIPT)
    other["assertions"]["constants"] = {f"<b>k{rlo}</b>": f"<i>v{bell}</i>"}
    other["outputs"] = [{"name": "<script>x</script>", "digest": D}]
    other["instrument"]["id"] = "<u>tool</u>"
    row = _row(demo, other)
    examined(4, "hostile parts")
    assert not re.search(r"<(b|i|script|u)>", row), row
    assert "&lt;b&gt;k" in row and "&lt;script&gt;x" in row and "&lt;u&gt;tool" in row
    assert rlo not in row and bell not in row
