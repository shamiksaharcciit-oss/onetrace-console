"""The comparison's "At the first difference: the model's rows and choices", read at a glance (`token_levels`).

- **L3, a strip of token positions** under the sentences: one cell per position, each saying in words whether the row
  and the chosen token are the same, the row changed with the same token, or the chosen token changed; the chosen
  token's id on each side where ids are shown; the first row change and the first choice change marked.
- **L2, a side-by-side table** at the first token whose choice differs, rank 1 to k: each side's candidate, with its
  logprob where the record holds one; the chosen token marked on each side, and a token missing from the other side's
  top k marked. With more differing positions, the first three, and the rest behind "Show all N differing positions",
  in place.
- **The capture settings** fold into one line where all are identical ("Capture settings: N recorded, all
  identical"); where any differ, those rows are shown open and marked, the rest folded.
- **Each cell gives the value only**, never its label again; a field not recorded reads "not recorded".
- **L2's capture level** says "capture level (L3 includes L2)" where it is L3.
- **One short line of caveats under each part**; the rest under "What this does not show".

Read on the token-level tests' own example runs (`tests/token_level_runs.py`, constructed; no model is called).
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess

import pytest

from tests.test_token_levels_l2 import local  # noqa: F401 - the fixture, requested by name
from tests.test_token_levels_l3 import IDS, _section, _side, built  # noqa: F401 - the fixture, requested by name

BROWSER_PYTHON = os.environ.get("ONETRACE_BROWSER_PYTHON", "")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _cells(page: str) -> list[dict]:
    strip = re.search(r"<ol [^>]*data-l3-strip[^>]*>(.*?)</ol>", page, re.S)
    assert strip, "no strip"
    return [
        {"state": m.group(1), "first": m.group(2) or "", "text": _text(m.group(3))}
        for m in re.finditer(
            r'<li data-state="([a-z]+)"(?: data-first="([a-z ]+)")?[^>]*>(.*?)</li>', strip.group(1), re.S
        )
    ]


def test_the_strip_says_each_position_and_marks_the_first_row_and_choice_changes(built, examined):  # noqa: F811
    cells = _cells(_section(built["row-first"]))
    examined(len(cells), "positions")
    assert [c["state"] for c in cells] == ["same", "same", "row", "row", "token", "token"]
    assert cells[2]["first"] == "row" and "first row change" in cells[2]["text"]
    assert cells[4]["first"] == "choice" and "first choice change" in cells[4]["text"]
    #: In words, not by colour alone: each state names itself.
    assert "row changed" in cells[3]["text"] and "choice changed" in cells[5]["text"] and "same" in cells[0]["text"]
    #: The chosen token's id on each side, baseline then candidate.
    assert "15" in cells[4]["text"] and "40" in cells[4]["text"]
    #: The sentence summary stays above the strip.
    section = _section(built["row-first"])
    assert section.index("The logits row changed at token 2") < section.index("data-l3-strip")


def test_a_pair_the_same_at_every_token_marks_no_change(built, examined):  # noqa: F811
    cells = _cells(_section(built["same"]))
    examined(len(cells), "positions")
    assert {c["state"] for c in cells} == {"same"} and not any(c["first"] for c in cells)


def _table(page: str, at: int) -> list[list[str]]:
    t = re.search(rf'<table [^>]*data-l2-at="{at}"[^>]*>.*?<tbody>(.*?)</tbody>', page, re.S)
    assert t, f"no L2 table at token {at}"
    return [
        [_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t.group(1), re.S)
    ]


def test_the_l2_table_gives_each_rank_side_by_side_marking_the_chosen_and_the_missing(local, examined):  # noqa: F811
    rows = _table(local["rank-2"], 2)
    examined(len(rows), "ranks")
    assert [r[0] for r in rows] == ["1", "2", "3", "4"]
    assert "13" in rows[0][1] and "chosen" in rows[0][1] and "9001" in rows[0][2] and "chosen" in rows[0][2]
    assert "not in" not in " ".join(r[1] + r[2] for r in rows)
    outside = _table(local["outside"], 2)
    assert "77" in outside[0][2] and "not in the baseline's top 4" in outside[0][2]
    assert "13" in outside[0][1] and "not in the candidate's top 4" in outside[0][1]


def test_the_l2_table_gives_the_logprob_where_the_record_holds_one(local, examined):  # noqa: F811
    with_lp = _table(local["hosted"], 2)
    without = _table(local["rank-2"], 2)
    examined(2, "tables")
    assert len(with_lp[0]) == 5 and "-0.10" in with_lp[0][2], with_lp
    assert len(without[0]) == 3, without


def test_the_settings_fold_when_identical_and_open_where_one_differs(examined):
    from onetrace_console import token_levels as tl

    same = tl.pair_block("model_call.json", _side(), _side(), (True, True), public=False)
    ra, da = _side()
    rb, db = _side()
    ra = {**ra, "batch.batch_invariant": {"status": "observed", "value": "on", "source": "x"}}
    rb = {**rb, "batch.batch_invariant": {"status": "observed", "value": "off", "source": "x"}}
    differ = tl.pair_block("model_call.json", (ra, da), (rb, db), (True, True), public=False)
    examined(2, "pairs")
    folded = re.search(r'<details data-settings="identical"><summary>(.*?)</summary>', same)
    assert folded and _text(folded.group(1)).startswith("Capture settings:") and "all identical" in folded.group(1)
    opened = re.search(r'<table [^>]*data-settings="differ"[^>]*>(.*?)</table>', differ, re.S)
    assert opened and "batch-invariant mode" in _text(opened.group(1)) and 'data-differs="yes"' in opened.group(1)
    assert '<details data-settings="identical">' in differ


def test_a_cell_gives_the_value_only_and_not_recorded_where_absent(built, examined):  # noqa: F811
    section = "".join(re.findall(r'<table [^>]*data-settings="[a-z]+".*?</table>', _section(built["row-first"]), re.S))
    rows = re.findall(
        r"<tr[^>]*><th scope=\"row\">(.*?)</th><td[^>]*>(.*?)</td><td[^>]*>(.*?)</td></tr>", section, re.S
    )
    examined(len(rows), "settings rows")
    assert rows
    for label, a, b in rows:
        assert _text(label) not in _text(a) and _text(label) not in _text(b), (label, a, b)
    from onetrace_console import token_levels as tl

    assert tl.shown_value({}, "steps.k_requested") == "not recorded"


def test_l2_s_capture_level_says_l3_includes_l2(examined):
    from onetrace_console import token_levels as tl

    examined(1, "label")
    assert tl.level_words("L3", l2=True) == "capture level (L3 includes L2)"
    assert tl.level_words("L2", l2=True) == "capture level"


def test_one_line_of_caveats_under_each_part_and_the_rest_folded(built, examined):  # noqa: F811
    section = _section(built["row-first"])
    examined(1, "section")
    shown = re.findall(r'<p class="caveat" data-caveat="(L[23])">(.*?)</p>', section, re.S)
    assert [p for p, _ in shown] == ["L3", "L2"] or [p for p, _ in shown] == ["L3"], shown
    folded = re.findall(r"<details data-caveats=\"L[23]\"><summary>What this does not show</summary>", section)
    assert len(folded) == len(shown)


def test_more_than_three_differing_positions_show_three_and_the_rest_in_place(examined):
    from onetrace_console import token_levels as tl

    ids_a = [str(10 + i) for i in range(8)]
    ids_b = [str(50 + i) for i in range(8)]
    top_a = [[t, "9001"] for t in ids_a]
    top_b = [[t, "9001"] for t in ids_b]
    rec = {
        "steps.level": {"status": "observed", "value": "L2", "source": "x"},
        "steps.k_requested": {"status": "observed", "value": "2", "source": "x"},
    }
    block = tl.pair_block(
        "model_call.json",
        (rec, {"level": "L2", "token_ids": ids_a, "top_k_ids": top_a}),
        (rec, {"level": "L2", "token_ids": ids_b, "top_k_ids": top_b}),
        (True, True),
        public=False,
    )
    examined(1, "pair")
    shown = re.findall(r'data-l2-at="(\d+)"', block.split("<details data-l2-all>")[0])
    assert shown == ["0", "1", "2"], shown
    rest = re.search(r"<details data-l2-all><summary>(.*?)</summary>(.*?)</details>", block, re.S)
    assert rest and _text(rest.group(1)) == "Show all 8 differing positions"
    assert re.findall(r'data-l2-at="(\d+)"', rest.group(2)) == [str(i) for i in range(3, 8)]


BOX_SCRIPT = r"""
import json, sys
from playwright.sync_api import sync_playwright
html = open(sys.argv[1], encoding="utf-8").read()
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (1440, 375):
        page = b.new_page(viewport={"width": width, "height": 900})
        page.set_content(html)
        page.evaluate("document.querySelectorAll('[data-section=token-levels] details').forEach(d => d.open = true)")
        out[str(width)] = page.evaluate('''() => { const s = document.querySelector('[data-section=token-levels]').getBoundingClientRect();
          return [...document.querySelectorAll('[data-section=token-levels] table')].filter(t => {
            const r = t.getBoundingClientRect(); return r.left < s.left - 1 || r.right > s.right + 1 }).map(t => t.outerHTML.slice(0, 80)) }''')
        page.close()
    b.close()
print(json.dumps(out))
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_in_a_browser_every_table_of_the_section_stays_inside_it(tmp_path, examined):
    #: The capture store's pair whose batch-invariant mode differs: its settings shown open, the rest opened too.
    from onetrace_console import frame
    from onetrace_console.demo_store import captures
    from onetrace_console.folder_load import build_public

    folder = tmp_path / "built"
    build_public(folder, builder=captures)
    page = next(
        p.read_text(encoding="utf-8")
        for p in sorted((folder / "store" / "pages" / "diff").glob("*.html"))
        if "batch-off" in p.read_text(encoding="utf-8") and 'data-settings="differ"' in p.read_text(encoding="utf-8")
    )
    page = page.replace(
        '<link rel="stylesheet" href="/static/console.css">', f"<style>{frame.stylesheet().decode()}</style>"
    )
    f = tmp_path / "page.html"
    f.write_text(page, encoding="utf-8")
    script = tmp_path / "box.py"
    script.write_text(BOX_SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), str(f)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    examined(len(got), "widths")
    assert got == {"1440": [], "375": []}, got


def test_the_capture_settings_are_identical_only_in_those_both_records_state(examined):
    """Two L3 captures stating 2 of the 4 L3 settings are identical in those 2, and the line says so; a setting one
    record lacks, or neither states, is not compared, never counted as identical nor as differing."""
    from onetrace_console import token_levels as tl

    def said(ra, rb) -> str:
        block = tl._capture_rows(ra, rb, tl.L3_CAPTURE)
        got = re.search(r"<summary>(.*?)</summary>", block) if "data-settings-said" not in block else None
        return _text(got.group(1)) if got else _text(re.search(r"<p data-settings-said>(.*?)</p>", block).group(1))

    ra, _ = _side()
    rb, _ = _side()
    runner = {**ra, "engine.settings.model_runner": {"status": "observed", "value": "example", "source": "x"}}
    on = {**ra, "batch.batch_invariant": {"status": "observed", "value": "on", "source": "x"}}
    off = {**rb, "batch.batch_invariant": {"status": "observed", "value": "off", "source": "x"}}
    examined(3, "capture settings: 2 on both, one more on one side, one differing")
    assert said(ra, rb) == "Capture settings: 2 recorded by both, all identical; 2 not recorded by both, not compared"
    assert said(runner, rb) == said(ra, rb)
    assert said(on, off) == ("Capture settings: 1 of the 3 recorded by both differ, shown here; the rest folded below.")
