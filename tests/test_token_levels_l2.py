"""L2 at the first difference: where both runs' model calls carry L2 (self-hosted ids, L3 with them, or the hosted form),
at the first position whose chosen token differs, whether each run's token is among the other's top-k there and its
rank, or that it is not, with k as recorded; ids only for a self-hosted call (no vocabulary is loaded); for a hosted call
on a local console, the candidates' text where the run kept its steps file, labelled as the provider returned it, and
ranks only where it did not; on a public console, ranks only, and text only for the demo's own example data, labelled
as such; the capture as recorded, and where sampling was not greedy, that a token outside the other's top-k can come
from sampling alone; "not comparable" for mixed levels and a differing k; and the non-claims.

The runs are example data, constructed through onetrace 0.7.1's own writer (`tests/token_level_runs.py`).
"""

from __future__ import annotations

import html
import re

import pytest

from tests.token_level_runs import digest, hosted_call, l2_call, l3_call, record_run

GENERATED_AT = "2026-11-09T12:00:00+00:00"
IDS = ["11", "12", "13", "14"]
TOP = [[t, "9001", "9002", "9003"] for t in IDS]


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _l2(page: str) -> str:
    m = re.search(r'<div data-token-level="L2".*?</div>\s*(?=<div data-token-level|</div></section>)', page, re.S)
    return m.group(0) if m else ""


def _tok(text, lp=None):
    return {"text": text, **({"logprob": lp} if lp is not None else {})}


def _hosted_steps(choices, *, lps=True):
    """One hosted step per (chosen, [candidates]); each candidate's logprob invented, falling by 0.3 a rank."""
    steps = []
    for chosen, cands in choices:
        cs = [_tok(c, f"-{0.1 + 0.3 * i:.2f}" if lps else None) for i, c in enumerate(cands)]
        ch = next((c for c in cs if c["text"] == chosen), _tok(chosen, "-3.00" if lps else None))
        steps.append({"chosen": ch, "candidates": cs})
    return steps


SAME_START = [("Yes", ["Yes", "No", "Maybe"]), (",", [",", ".", "!"])]
PAIRS = {
    #: At token 2 the candidate chose the baseline's 2nd candidate, and the baseline chose the candidate's 2nd.
    "rank-2": (
        l2_call(IDS, TOP),
        {**l2_call(IDS[:2] + ["9001", "14"], TOP[:2] + [["9001", "13", "9002", "9003"], TOP[3]]), "answer": "2"},
    ),
    "outside": (
        l2_call(IDS, TOP),
        {**l2_call(IDS[:2] + ["77", "14"], TOP[:2] + [["77", "9004", "9005", "9006"], TOP[3]]), "answer": "2"},
    ),
    "same": (l2_call(IDS, TOP), {**l2_call(IDS, TOP), "answer": "2"}),
    "k": (l2_call(IDS, TOP, k=4), {**l2_call(IDS[:2] + ["9001", "14"], [x[:2] for x in TOP], k=2), "answer": "2"}),
    "mixed": (l2_call(IDS, TOP), {**l3_call(IDS[:2] + ["40", "14"], [digest(i) for i in range(4)]), "answer": "2"}),
    "sampled": (
        l2_call(IDS, TOP, temperature="0.7"),
        {
            **l2_call(IDS[:2] + ["9001", "14"], TOP[:2] + [["9001", "13", "9002", "9003"], TOP[3]], temperature="0.7"),
            "answer": "2",
        },
    ),
    #: Both at L3: the row and the choice, side by side.
    "both-l3": (
        l3_call(IDS, [digest(i) for i in range(4)]),
        {**l3_call(IDS[:2] + ["40", "14"], [digest(0), digest(101), digest(102), digest(103)]), "answer": "2"},
    ),
    "hosted": (
        hosted_call(_hosted_steps(SAME_START + [("no", ["no", "yes", "maybe"])])),
        {**hosted_call(_hosted_steps(SAME_START + [("yes", ["yes", "no", "maybe"])])), "answer": "2"},
    ),
    "hosted-not-kept": (
        hosted_call(_hosted_steps(SAME_START + [("no", ["no", "yes", "maybe"])]), steps_kept=False),
        {**hosted_call(_hosted_steps(SAME_START + [("yes", ["yes", "no", "maybe"])]), steps_kept=False), "answer": "2"},
    ),
}


def _build(tmp, names, public: bool):
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.frame import rendering
    from onetrace_console.render import render_diff
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver

    store = Store(tmp / "store")
    pages = {}
    for name in names:
        a, b = PAIRS[name]
        ra = run_and_record(
            _deliver(record_run(tmp / name / "a", f"{name}-a", a), store, outputs=True), store, ran_at=FIXED_RAN_AT
        )
        rb = run_and_record(
            _deliver(record_run(tmp / name / "b", f"{name}-b", b), store, outputs=True), store, ran_at=FIXED_RAN_AT
        )
        c = compare(ra, rb, store, ran_at=FIXED_RAN_AT)
        with rendering(onedoor=False, sign_in=False, public=public):
            pages[name] = render_diff(c, store, generated_at=GENERATED_AT)
    return pages


@pytest.fixture(scope="module")
def local(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("l2-local"), PAIRS, public=False)


@pytest.fixture(scope="module")
def public(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("l2-public"), ("rank-2", "hosted"), public=True)


def test_the_other_run_s_token_at_rank_2(local, examined):
    said = _text(_l2(local["rank-2"]))
    examined(1, "a pair whose candidate chose the baseline's 2nd candidate")
    assert "At token 2, the first token whose choice differs:" in said
    assert "the candidate's token 9001 was the baseline's 2nd candidate" in said
    assert "the baseline's token 13 was the candidate's 2nd candidate" in said
    assert "k as recorded: 4 and 4" in said


def test_a_token_outside_the_other_s_top_k(local, examined):
    said = _text(_l2(local["outside"]))
    examined(1, "a pair whose candidate chose outside the baseline's top-k")
    assert "the candidate's token 77 is not among the baseline's top 4" in said
    assert "the baseline's token 13 is not among the candidate's top 4" in said


def test_equal_choices_give_no_rank(local, examined):
    said = _text(_l2(local["same"]))
    examined(1, "a pair choosing the same token at every step")
    assert "The chosen tokens are the same at every delivered token (4); no rank is shown." in said
    assert "candidate's token" not in said


@pytest.mark.parametrize(
    "name, why",
    [
        ("k", "k differs: 4 and 2"),
        ("mixed", "the capture levels differ: L2 and L3"),
    ],
)
def test_mixed_levels_and_a_differing_k_are_not_comparable(local, name, why, examined):
    said = _text(_l2(local[name]))
    examined(1, f"a pair: {why}")
    assert f"Not comparable: {why}; no rank is shown." in said
    assert "candidate's token" not in said


def test_not_greedy_sampling_is_said(local, examined):
    sampled, greedy = _text(_l2(local["sampled"])), _text(_l2(local["rank-2"]))
    examined(2, "pairs, sampled and greedy")
    words = "a token outside the other run's top-k can come from sampling alone"
    assert words in sampled and "temperature 0.7" in sampled
    assert words not in greedy


def test_self_hosted_shows_ids_and_ranks_only(local, examined):
    section = _l2(local["rank-2"])
    examined(1, "a self-hosted pair")
    assert "model-generated, as the provider returned it" not in _text(section)
    assert "<code>9001</code>" in section


def test_hosted_on_a_local_console_shows_the_candidates_text_labelled(local, examined):
    said = _text(_l2(local["hosted"]))
    examined(1, "a hosted pair, its steps files kept")
    assert "the candidate's token “yes” was the baseline's 2nd candidate" in said
    assert "model-generated, as the provider returned it" in said


def test_a_steps_file_not_kept_is_said_and_no_rank_is_shown(local, examined):
    """A run that keeps no outputs holds neither its steps file nor its record; its receipt still names both. The
    first difference's section says the steps file wasn't kept, and shows no candidate or rank."""
    page = local["hosted-not-kept"]
    said = _text(page)
    examined(1, "a hosted pair, its steps files not kept")
    assert 'data-section="token-levels"' in page
    assert "The steps file wasn't kept, so no candidates or ranks can be shown." in said
    assert "“yes”" not in said and "“no”" not in said and "candidate's token" not in said


def test_a_public_console_shows_no_id_or_text_from_a_real_run(public, examined):
    selfh, hosted = _l2(public["rank-2"]), _text(_l2(public["hosted"]))
    examined(2, "pairs on a public console")
    assert "<code>9001</code>" not in selfh and "<code>13</code>" not in selfh
    assert "the candidate's token was the baseline's 2nd candidate" in _text(selfh)
    assert "“yes”" not in hosted and "“no”" not in hosted
    assert "ranks only on a public console" in _text(selfh) and "ranks only on a public console" in hosted


def test_the_non_claims_are_said(local, examined):
    said = _text(_l2(local["rank-2"]))
    examined(1, "non-claims")
    for words in (
        "A rank shows how the candidates were ordered, not why a different one was chosen.",
        "L2 shows no probabilities unless the record holds them.",
        "A candidate difference is not a verdict and changes no verdict.",
    ):
        assert words in said, words


def test_sabotage_a_rank_counted_from_zero_is_caught(monkeypatch, examined):
    from onetrace_console import token_levels as tl

    examined(1, "a planted rank")
    assert tl.ordinal(2) == "2nd" and tl.rank_of("9001", ["13", "9001", "9002"]) == 2
    monkeypatch.setattr(tl, "rank_of", lambda t, xs: xs.index(t) if t in xs else None)
    assert tl.rank_of("9001", ["13", "9001", "9002"]) != 2


def test_with_l3_present_too_the_row_and_the_choice_sit_together(local, examined):
    page = local["both-l3"]
    l3 = page.find('data-token-level="L3"')
    l2 = page.find('data-token-level="L2"')
    examined(1, "a pair, both at L3")
    assert 0 <= l3 < l2
    said = _text(page)
    assert "The logits row changed at token 1; the chosen token first changed at token 2." in said
    assert "At token 2, the first token whose choice differs:" in said


def test_a_public_comparison_page_drawn_as_the_console_draws_it_shows_no_id(tmp_path, examined):
    """The console draws a comparison page with `render_diff(..., public=...)` and no render around it
    (`serve._render_diff_page`): the page's own flag decides, not a render that isn't there."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.render import render_diff
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver

    store = Store(tmp_path / "store")
    a, b = PAIRS["rank-2"]
    ra = run_and_record(
        _deliver(record_run(tmp_path / "a", "pub-a", a), store, outputs=True), store, ran_at=FIXED_RAN_AT
    )
    rb = run_and_record(
        _deliver(record_run(tmp_path / "b", "pub-b", b), store, outputs=True), store, ran_at=FIXED_RAN_AT
    )
    c = compare(ra, rb, store, ran_at=FIXED_RAN_AT)
    public, local = (render_diff(c, store, generated_at=GENERATED_AT, public=p) for p in (True, False))
    examined(2, "pages drawn as the console draws them, public and local")
    assert "<code>9001</code>" not in _l2(public) and "ranks only on a public console" in _text(_l2(public))
    assert "<code>9001</code>" in _l2(local)
