"""Step expectations (onetrace 0.7, its manual's 16.22): each step's declared expectations, one row each
as onetrace-verify reads it -- PASS; FAIL naming the value and the rule; NOT-RUN with its reason -- with
the manual's own words beside them, and how many held on a line of their own, apart from the
comparison's verdicts.

The runs are `tests/onetrace_runs/0.7.1/expect/` (`tools/make_expectation_runs.py`): `calibrate-holds`,
whose step declares five expectations (four hold, one is not run), and `calibrate-fails`, whose step
declares those and two that fail.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

from tests.test_format_04 import _pages

EXPECT = Path(__file__).resolve().parent / "onetrace_runs" / "0.7.1" / "expect"
NON_CLAIM = "An expectation that holds shows the declared rule held, not that the output was right."


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed
    _require_installed()


def _text(block: str) -> str:
    inline = re.sub(r"</?(?:span|code|strong|a)\b[^>]*>", "", block)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", inline))).strip()


def _section(pages: dict) -> str:
    found = [m.group(0) for p in ("case.html", "proof.html")
             for m in [re.search(r'<section data-section="expectations".*?</section>', pages[p], re.S)] if m]
    return found[0] if found else ""


def _declared(name: str) -> list[dict]:
    m = json.loads((EXPECT / name / "MANIFEST.json").read_text(encoding="utf-8"))
    out = []
    for e in m["chain"]:
        r = json.loads((EXPECT / name / e["file"]).read_text(encoding="utf-8"))
        out += [dict(x, step=r["stage"]["name"]) for x in r.get("expectations") or []]
    return out


def _rows(run, store) -> list[dict]:
    report = json.loads(store.get(run.check_report))
    doc = json.loads(report["rows_json"]["stdout"])
    return [r for r in doc["rows"] if r["name"].startswith("expect ")]


def _drawn(name: str, tmp_path):
    from onetrace_console.store import Store
    store = Store(tmp_path / name)
    run, pages = _pages(EXPECT / name, store)
    return run, pages, store


@pytest.mark.parametrize("name, held, of", [("calibrate-holds", 4, 5), ("calibrate-fails", 4, 7)])
def test_each_declared_expectation_has_its_row_in_the_verifier_s_words(name, held, of, tmp_path, examined):
    run, pages, store = _drawn(name, tmp_path)
    declared, rows = _declared(name), _rows(run, store)
    examined(len(declared), f"expectations {name} declares")
    assert len(declared) == len(rows) == of
    section = _section(pages)
    assert section, "no expectations section"
    text = _text(section)
    for r in rows:
        assert f'{r["result"]} {r["name"]} — {r["detail"]}' in text, (r, text)
    for d in declared:
        assert f'expect {d["step"]}.{d["name"]}' in text, d


@pytest.mark.parametrize("name, held, of", [("calibrate-holds", 4, 5), ("calibrate-fails", 4, 7)])
def test_the_count_of_those_that_held_is_a_line_of_its_own_and_the_non_claim_is_beside_them(name, held, of,
                                                                                             tmp_path, examined):
    _run, pages, _store = _drawn(name, tmp_path)
    section = _section(pages)
    examined(1, f"{name}'s count")
    (count,) = re.findall(r'<p data-expectations="count">(.*?)</p>', section, re.S)
    assert _text(count) == f"{held} of {of} expectations held.", count
    assert NON_CLAIM in _text(section)


def test_a_fail_names_the_value_and_the_rule_and_a_not_run_its_reason(tmp_path, examined):
    run, pages, store = _drawn("calibrate-fails", tmp_path)
    text = _text(_section(pages))
    examined(3, "rows read")
    assert "FAIL expect calibrate.under-400 — 430.5 is outside [, 400]" in text
    assert "FAIL expect calibrate.serial — /serial is absent from return.json" in text
    assert "NOT-RUN expect calibrate.note-is-a-number — 'steady' is not a decimal" in text


def test_a_run_with_no_expectations_has_no_section(tmp_path, examined):
    from onetrace_console.store import Store
    _run, pages = _pages(EXPECT.parent / "refund-closed", Store(tmp_path / "s"))
    examined(1, "a run declaring no expectations")
    assert _section(pages) == ""


def test_a_declared_expectation_the_check_gives_no_row_for_reads_not_run(examined):
    """An expectation a receipt declares and the check holds no row for (an earlier verifier, say) still
    has its row: NOT-RUN, saying the check holds none."""
    from onetrace_console import expectations
    declared = [{"step": "calibrate", "name": "in-range", "kind": "range"},
                {"step": "calibrate", "name": "extra", "kind": "member"}]
    rows = [{"name": "expect calibrate.in-range", "result": "PASS", "detail": "1 within [0, 2]"}]
    examined(2, "declared expectations")
    got = expectations.with_rows(declared, rows)
    assert [(r["name"], r["result"]) for r in got] == [("expect calibrate.in-range", "PASS"),
                                                       ("expect calibrate.extra", "NOT-RUN")]
    assert got[1]["detail"] == expectations.NO_ROW


def test_sabotage_a_count_that_takes_not_run_as_held_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import expectations
    monkeypatch.setattr(expectations, "HELD", ("PASS", "NOT-RUN"))
    examined(1, "a count read with NOT-RUN as held")
    with pytest.raises(AssertionError):
        test_the_count_of_those_that_held_is_a_line_of_its_own_and_the_non_claim_is_beside_them(
            "calibrate-holds", 4, 5, tmp_path, lambda *a: None)
