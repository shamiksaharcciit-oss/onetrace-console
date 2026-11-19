"""What a stored `onetrace check` came back with, on the runs it checked and on its own run.

On onetrace 0.8.0's own vectors (`tests/format_04_item8/`): a check's run (A09), which re-ran vector-base's candidate
from `b` and came back as predicted; vector-base (A02), the check's baseline, held; its candidate, not held.

- The baseline's head says "confirmed by a check", the check's run linked, and that neither word is a verdict.
- The check's own head names its verb, its runs (linked where held), its stage, what it predicted and what came back.
- What came back is said in onetrace's words: "confirmed by a check", "not supported by its check", "the check did
  not run: <reason>".
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent / "format_04_item8" / "accept"
RAN_AT = "2026-11-13T00:00:00+00:00"


@pytest.fixture(scope="module")
def held(tmp_path_factory):
    from tests.test_checks import _require_installed

    _require_installed()
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from tests.test_format_03 import _tar

    store = Store(tmp_path_factory.mktemp("checked") / "store")
    runs = {
        n: run_and_record(accept(_tar(HERE / n), store).run, store, ran_at=RAN_AT)
        for n in ("A02-closed-recorder", "A09-check-run", "A10-check-produced-run", "A08-reproduce")
    }
    return store, runs


def _case(run, store) -> str:
    from onetrace_console.pages import CASE, render_execution

    return render_execution(run, store, generated_at=RAN_AT).pages[CASE]


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", html))).strip()


def test_what_came_back_is_said_in_onetrace_s_words(examined):
    from onetrace_console import check_results as cr

    examined(4, "outcomes")
    assert cr.outcome("as predicted") == "confirmed by a check"
    assert cr.outcome("otherwise") == "not supported by its check"
    assert cr.outcome("did not run: the wall-clock limit was reached") == (
        "the check did not run: the wall-clock limit was reached"
    )
    assert cr.outcome("") == ""


def test_the_checked_run_s_head_says_what_came_back_linking_the_check(held, examined):
    from onetrace_console import check_results as cr

    store, runs = held
    case = _case(runs["A02-closed-recorder"], store)
    section = re.search(r'<div class="sub" data-section="checked"[^>]*>.*?</div>', case, re.S)
    examined(1, "checked run")
    assert section, "no Checked line"
    assert f'href="../../runs/{runs["A09-check-run"].key}/case.html"' in section.group(0)
    text = _text(section.group(0))
    assert "confirmed by a check (check vector-check; this run its baseline)" in text, text
    assert cr.NOT_A_VERDICT in text
    for name in ("A08-reproduce", "A10-check-produced-run", "A09-check-run"):
        assert 'data-section="checked"' not in _case(runs[name], store), name


def test_the_check_s_own_head_names_what_it_ran_predicted_and_got(held, examined):
    store, runs = held
    case = _case(runs["A09-check-run"], store)
    section = re.search(r'<div class="sub" data-section="check-run"[^>]*>.*?</div>', case, re.S)
    examined(1, "check's run")
    assert section, "no check's line"
    assert f'href="../../runs/{runs["A02-closed-recorder"].key}/case.html"' in section.group(0)
    text = _text(section.group(0))
    assert text.startswith(
        "A check's run: reproduce, baseline vector-base, candidate 7c7047042342… (not held in this store), from b"
    ), text
    assert "(not held in this store)" in text and "from b" in text, text
    assert "predicted equal to the candidate's; confirmed by a check." in text, text
    for name in ("A02-closed-recorder", "A08-reproduce"):
        assert 'data-section="check-run"' not in _case(runs[name], store), name


@pytest.mark.parametrize(
    ("came_back", "said"),
    [("otherwise", "not supported by its check"), ("did not run: refused", "the check did not run: refused")],
)
def test_each_outcome_is_drawn_on_the_checked_run(held, came_back, said, examined):
    import json
    from dataclasses import replace

    from onetrace_console import check_results as cr

    store, runs = held
    check = runs["A09-check-run"]
    planted = replace(check, rerun=json.dumps({**json.loads(check.rerun), "came_back": came_back}))
    store.put_run(planted)
    try:
        line = cr.checked_line(runs["A02-closed-recorder"], store, "../../")
    finally:
        store.put_run(check)
    examined(1, "planted outcome")
    assert f"{said} (check vector-check" in _text(line), line
