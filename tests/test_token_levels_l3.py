"""L3 at the first difference: where both runs' model calls at the first differing step carry L3 steps files, the
comparison's first-difference view gives the first token position whose logits-row digests differ, the first position
whose chosen token differs, and how many positions before the token difference had a changed digest with the same
token; the capture as recorded beside it; only delivered tokens compared, the surplus shown and never compared; "not
comparable" with why where one run has L3 and the other doesn't or the digest methods differ; "couldn't check" unless
both runs' records verify; and the non-claims. A step without steps files gives a byte-identical page.

The runs are example data, constructed through onetrace 0.7.1's own writer (`tests/token_level_runs.py`).
"""

from __future__ import annotations

import html
import re

import pytest

from tests.token_level_runs import digest, l2_call, l3_call, record_run

GENERATED_AT = "2026-11-09T12:00:00+00:00"
IDS = ["11", "12", "13", "14", "15", "16"]
D = [digest(i) for i in range(6)]


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _section(page: str) -> str:
    m = re.search(r'<section data-section="token-levels".*?</section>', page, re.S)
    return m.group(0) if m else ""


#: Each pair: the baseline's call, the candidate's.
PAIRS = {
    #: The step's answer differs, so the step is the first difference; the two captures agree at every token.
    "same": (l3_call(IDS, D), {**l3_call(IDS, D), "answer": "2"}),
    #: The row changes at token 2; the chosen token at token 4.
    "row-first": (l3_call(IDS, D), l3_call(IDS[:4] + ["40", "41"], D[:2] + [digest(100 + i) for i in range(4)])),
    "row-only": (l3_call(IDS, D), l3_call(IDS, D[:3] + [digest(200 + i) for i in range(3)])),
    "invariant-off": (
        l3_call(IDS, D, batch_invariant="off"),
        l3_call(IDS[:4] + ["40", "41"], D[:2] + [digest(100 + i) for i in range(4)], batch_invariant="off"),
    ),
    "surplus": (l3_call(IDS, D, surplus=3), l3_call(IDS, D, surplus=0)),
    "one-l3": (l3_call(IDS, D), l2_call(IDS, [[t, "9001"] for t in IDS])),
    "unverifiable": (
        l3_call(IDS, D),
        {**l3_call(IDS[:4] + ["40", "41"], D[:2] + [digest(100 + i) for i in range(4)]), "unverifiable": True},
    ),
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.frame import rendering
    from onetrace_console.render import render_diff
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver

    folder = tmp_path_factory.mktemp("token-levels-l3")
    store = Store(folder / "store")
    pages = {}
    for name, (a, b) in PAIRS.items():
        ra = run_and_record(
            _deliver(record_run(folder / name / "a", f"{name}-a", a), store, outputs=True), store, ran_at=FIXED_RAN_AT
        )
        rb = run_and_record(
            _deliver(record_run(folder / name / "b", f"{name}-b", b), store, outputs=True), store, ran_at=FIXED_RAN_AT
        )
        c = compare(ra, rb, store, ran_at=FIXED_RAN_AT)
        with rendering(onedoor=False, sign_in=False, public=False):
            pages[name] = render_diff(c, store, generated_at=GENERATED_AT)
    return pages


def test_equal_digests_and_choices_give_no_position(built, examined):
    said = _text(_section(built["same"]))
    examined(1, "a pair the same at every token")
    assert "The logits rows and the chosen tokens are the same at every delivered token (6)." in said
    assert "changed at token" not in said


def test_a_planted_digest_change_before_a_token_change(built, examined):
    said = _text(_section(built["row-first"]))
    examined(1, "a pair whose row changes before its token")
    assert "The logits row changed at token 2; the chosen token first changed at token 4." in said
    assert "2 positions before token 4 had a changed logits row and the same chosen token." in said


def test_a_row_change_with_no_token_change(built, examined):
    said = _text(_section(built["row-only"]))
    examined(1, "a pair whose row changes and token does not")
    assert (
        "The logits row changed at token 3; the chosen token did not change in the 6 delivered tokens both runs hold."
    ) in said


def test_the_capture_as_recorded_is_beside_it(built, examined):
    section = _section(built["row-first"])
    examined(1, "capture rows")
    said = _text(section)
    for words in ("capture level L3", "digest method sha256-tree-512/v0", "model runner V1", "batch-invariant mode on"):
        assert words in said, words


def test_with_batch_invariant_off_the_non_claim_is_on_the_spot(built, examined):
    off, on = _text(_section(built["invariant-off"])), _text(_section(built["row-first"]))
    examined(2, "pairs, batch-invariant off and on")
    nonclaim = "a changed digest can come from how requests were batched, not from the model"
    assert nonclaim in off and "batch-invariant mode off" in off
    assert nonclaim not in on


def test_the_surplus_is_shown_as_recorded_and_never_compared(built, examined):
    said = _text(_section(built["surplus"]))
    examined(1, "a pair with a surplus on one side")
    assert "The logits rows and the chosen tokens are the same at every delivered token (6)." in said
    assert "digests computed beyond the delivered tokens, counted and never compared: baseline 3, candidate 0" in said


def test_one_run_with_l3_and_the_other_without_is_not_comparable(built, examined):
    said = _text(_section(built["one-l3"]))
    examined(1, "a pair, one side L3")
    assert "Not comparable: only the baseline's call captured L3 (the candidate's is L2); no position is shown." in said
    assert "changed at token" not in said


def test_a_record_that_does_not_verify_gives_couldn_t_check(examined):
    """The view's own rule: unless both runs' checks read Yes, no position."""
    from onetrace_console import token_levels as tl

    a = _side()
    b = _side(ids=IDS[:4] + ["40", "41"], digests=D[:2] + [digest(100 + i) for i in range(4)])
    said = {
        who: _text(tl.pair_block("model_call.json", a, b, ok))
        for who, ok in (("candidate", (True, False)), ("baseline", (False, True)), ("both", (False, False)))
    }
    examined(3, "pairs with a side that does not verify")
    assert said["candidate"] == (
        "model_call.json Couldn't check: the candidate's records do not verify (its check does "
        "not read Yes), so no position is shown."
    )
    assert "the baseline's records do not verify" in said["baseline"]
    assert "the baseline's and the candidate's records do not verify" in said["both"]
    assert all("changed at token" not in t for t in said.values())


def test_on_a_page_a_record_that_does_not_verify_shows_no_position(built, examined):
    """onetrace refuses a comparison whose runs do not verify, so the page has no first difference and no view."""
    page = built["unverifiable"]
    examined(1, "a pair, one record failing onetrace-verify")
    assert _section(page) == "" and "changed at token" not in _text(page)
    assert "does not verify" in _text(page)


def test_the_non_claims_are_said(built, examined):
    said = _text(_section(built["row-first"]))
    examined(1, "non-claims")
    for words in (
        "L3 shows whether the row the sampler chose from was the same bytes, not why it changed.",
        "The cost and repeat figures in onetrace's docs are from one GPU, two models and greedy decoding.",
        "A digest difference is not a verdict and changes no verdict.",
    ):
        assert words in said, words


# ---------------------------------------------------------------- the reading itself, and its sabotage
def _side(level="L3", method="sha256-tree-512/v0", ids=IDS, digests=D, surplus="0"):
    rec = {
        "steps.level": {"status": "observed", "value": level, "source": "x"},
        "steps.method": {"status": "observed", "value": method, "source": "x"},
    }
    if level == "L3":
        rec["steps.surplus"] = {"status": "observed", "value": surplus, "source": "x"}
    doc = {"level": level, "method": method, "token_ids": list(ids)}
    if level == "L3":
        doc["digests"] = list(digests)
    return rec, doc


def test_mixed_digest_methods_are_not_comparable(examined):
    from onetrace_console import token_levels as tl

    got = tl.l3_reading(*_side(), *_side(method="sha256/v9"))
    examined(1, "a pair with two digest methods")
    assert got.kind == "not-comparable" and "the digest methods differ: sha256-tree-512/v0 and sha256/v9" in got.why


def test_neither_side_at_l3_gives_no_l3_reading(examined):
    from onetrace_console import token_levels as tl

    examined(1, "a pair with no L3")
    assert tl.l3_reading(*_side("L2", "top-k-ids"), *_side("L2", "top-k-ids")) is None


def test_only_delivered_tokens_are_compared(examined):
    from onetrace_console import token_levels as tl

    #: The candidate delivered fewer tokens: positions past its last are not compared.
    got = tl.l3_reading(*_side(), *_side(ids=IDS[:3], digests=D[:3]))
    examined(1, "a pair of unequal lengths")
    assert got.kind == "same" and got.compared == 3


def test_sabotage_a_reading_that_counts_the_first_token_change_itself_is_caught(monkeypatch, examined):
    from onetrace_console import token_levels as tl

    real = tl.l3_reading

    def planted(*a):
        got = real(*a)
        return (
            got
            if got is None or got.kind != "positions"
            else tl.L3Reading(
                "positions", row_at=got.row_at, token_at=got.token_at, row_only=got.row_only + 1, compared=got.compared
            )
        )

    monkeypatch.setattr(tl, "l3_reading", planted)
    a = _side()
    b = _side(ids=IDS[:4] + ["40", "41"], digests=D[:2] + [digest(100 + i) for i in range(4)])
    examined(1, "a planted off-by-one")
    assert tl.l3_reading(*a, *b).row_only != real(*a, *b).row_only


def test_a_step_without_steps_files_gives_a_byte_identical_page(tmp_path, monkeypatch, examined):
    """A pair whose records hold no capture: the page is the page drawn with the view taken out."""
    from onetrace_console import token_levels as tl
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.frame import rendering
    from onetrace_console.render import render_diff
    from onetrace_console.store import Store
    from tests.model_call_runs import record_run as record_10
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver

    store = Store(tmp_path / "store")
    ra = run_and_record(_deliver(record_10(tmp_path / "a", "nc-a"), store, outputs=True), store, ran_at=FIXED_RAN_AT)
    rb = run_and_record(
        _deliver(record_10(tmp_path / "b", "nc-b", output="sha256:" + "e" * 64), store, outputs=True),
        store,
        ran_at=FIXED_RAN_AT,
    )
    c = compare(ra, rb, store, ran_at=FIXED_RAN_AT)
    with rendering(onedoor=False, sign_in=False, public=False):
        page = render_diff(c, store, generated_at=GENERATED_AT)
        monkeypatch.setattr(tl, "section", lambda *a, **k: "")
        without = render_diff(c, store, generated_at=GENERATED_AT)
    examined(1, "a pair without steps files")
    assert page == without


@pytest.mark.parametrize(
    "docs, why",
    [
        ((None, {"method": "m", "token_ids": [], "digests": []}), "the baseline's steps file wasn't read"),
        (({"method": "m", "token_ids": [], "digests": []}, None), "the candidate's steps file wasn't read"),
        ((None, None), "neither call's steps file was read"),
    ],
    ids=["baseline's not read", "candidate's not read", "neither read"],
)
def test_l3_on_both_with_a_steps_file_not_read_is_not_comparable_and_never_raises(docs, why, examined):
    """Where both records state L3 but a steps file isn't kept or can't be read, the reading says not comparable,
    with the reason, as for mixed levels."""
    from onetrace_console import token_levels as tl

    record = {"steps.level": {"status": "observed", "value": "L3", "source": "test"}}
    got = tl.l3_reading(record, docs[0], record, docs[1])
    examined(1, "a pair at L3 with a steps file missing")
    assert got is not None and got.kind == "not-comparable" and got.why == why, got
