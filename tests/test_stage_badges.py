"""The stage page's anchoring badge states the run's own rung, in the run page's
words; the signing badge keeps its placeholder until the third build.

| Rung | Badge row |
|---|---|
| Yes | "Committed by a known time · Yes · existed by {time} · {source} (the whole run's record)" |
| Couldn't check | "Committed by a known time · Couldn't check · {the verifier's reason}" |
| No, the check failed | "Committed by a known time · No · the check says: {detail}" |
| No anchor row | "Committed by a known time · No · not anchored" |
| No own check | the record-declared rung, as on the run page |

The FAIL is the pinned verifier's own; PASS and NOT-RUN edit that stored report's one anchor row,
text and --json together, read by the viewer row by row (tests/test_step3_receipt_anchor.py).
"""
from __future__ import annotations

import json
import re
from html import unescape


from tests.test_stage_pages import _pages, demo  # noqa: F401
from tests.test_step3_receipt_anchor import (BITCOIN, _anchor_row_as, _read_by_the_viewer,  # noqa: F401
                                             anchored, declared)


def _cells(row: str) -> list[str]:
    return [re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"<td>(.*?)</td>", row, re.S)]


def _badges(run, store) -> set[str]:
    """Each stage page's anchoring badge, as "question · state · evidence"; one per run, so a set."""
    out = set()
    stages = {k: v for k, v in _pages(run, store).items() if k.startswith("stage-")}
    assert stages, "no stage pages"
    for page in stages.values():
        badge = re.search(r'<tr data-badge="2"[^>]*>(.*?)</tr>', page, re.S).group(1)
        out.add(" · ".join(_cells(badge)))
    return out


def test_yes_names_the_whole_runs_record(anchored):
    run, store = anchored
    run = _anchor_row_as(run, store, "PASS", BITCOIN)
    assert _badges(run, store) == {"Committed by a known time · Yes · existed by "
                                   "2024-04-20T00:09:27Z · bitcoin block 840000 (the whole run's record)"}


def test_couldnt_check_gives_the_verifiers_reason_alone(anchored):
    run, store = anchored
    run = _anchor_row_as(run, store, "NOT-RUN", "needs block headers")
    assert _badges(run, store) == {"Committed by a known time · Couldn't check · needs block headers"}


def test_a_failed_check_says_what_the_check_says(anchored):
    run, store = anchored
    _read_by_the_viewer(json.loads(store.get(run.check_report).decode("utf-8")))
    (said,) = _badges(run, store)
    assert said.startswith("Committed by a known time · No · the check says: malformed anchor "
                           "record"), said


def test_no_anchor_row_is_no_not_anchored(demo):  # noqa: F811
    run, store = demo
    assert _badges(run, store) == {"Committed by a known time · No · not anchored"}


def test_a_record_declaring_an_anchor_it_does_not_have_is_no_not_anchored(declared):
    """The record's declaration is not read while an own check exists."""
    run, store = declared
    assert _badges(run, store) == {"Committed by a known time · No · not anchored"}


def test_without_an_own_check_it_is_the_record_declared_rung_as_on_the_run_page(anchored):
    """An own check the page cannot read: the run page's rung is what the record declares, and
    the badge says the same."""
    from dataclasses import replace

    from tests.test_step3_receipt_anchor import _case_rung
    run, store = anchored
    envelope = json.loads(store.get(run.check_report).decode("utf-8"))
    envelope["stdout"] += "forged: a line after the summary\n"
    run = replace(run, check_report=store.put(json.dumps(envelope).encode("utf-8")))
    rung = _case_rung(run, store)
    assert "the check says" not in rung, rung
    assert _badges(run, store) == {f"Committed by a known time · {rung}"}
