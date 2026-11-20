"""A model call's own pages: Overview, Decode steps, Inputs & outputs, Receipt and Compare, one row of tabs linking them.

Each page shows only what the record and its steps file hold, each value beside the record field it is read from. A
mock-up's value the record does not hold (sampler replay, a sampling-state or seed digest, the teacher-forced check,
L4, the call's latency) reads "not recorded", never a filler. Where the capture holds no probabilities (a self-hosted
L2 or L3 steps file holds ids), the timeline shows positions only and says so; a hosted capture's log-probabilities
draw its bars. Against a held comparison: the first output-token divergence, every level checked in order, and the
decode steps around it, those after it marked as generated from different histories.

The runs are example data, constructed through onetrace's own writer (`tests/token_level_runs.py`).
"""

from __future__ import annotations

import html
import re

import pytest

from tests.token_level_runs import digest, hosted_call, l3_call, record_run

GENERATED_AT = "2026-11-18T23:00:00+00:00"
IDS = ["11", "12", "13", "14", "15", "16"]
D = [digest(i) for i in range(6)]
#: The candidate's logits row changes at step 2, its chosen token at step 4.
CANDIDATE = l3_call(IDS[:4] + ["40", "41"], D[:2] + [digest(100 + i) for i in range(4)])
TABS = ("Overview", "Decode steps", "Inputs & outputs", "Receipt", "Compare")


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _hosted_steps():
    def tok(text, lp):
        return {"text": text, "logprob": lp}

    return [
        {"chosen": tok("Yes", "-0.10"), "candidates": [tok("Yes", "-0.10"), tok("No", "-2.40")]},
        {"chosen": tok(",", "-0.05"), "candidates": [tok(",", "-0.05"), tok(".", "-3.00")]},
        {"chosen": tok("ok", "-1.20"), "candidates": [tok("ok", "-1.20"), tok("fine", "-1.30")]},
    ]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver

    folder = tmp_path_factory.mktemp("model-call-pages")
    store = Store(folder / "store")

    def held(name, call):
        return run_and_record(
            _deliver(record_run(folder / name, name, call), store, outputs=True), store, ran_at=FIXED_RAN_AT
        )

    a, b, h = held("call-a", l3_call(IDS, D)), held("call-b", CANDIDATE), held("call-h", hosted_call(_hosted_steps()))
    compare(a, b, store, ran_at=FIXED_RAN_AT)
    with rendering(onedoor=False, sign_in=False, public=False):
        pages = {r.key: render_execution(r, store, generated_at=GENERATED_AT).pages for r in (a, b, h)}
    return {"a": pages[a.key], "b": pages[b.key], "h": pages[h.key], "ids": (a.run_id, b.run_id)}


def test_each_record_has_its_five_pages_linked_by_one_row_of_tabs(built, examined):
    pages = built["b"]
    names = ["call-1.html", "call-1-decode.html", "call-1-io.html", "call-1-receipt.html", "call-1-compare.html"]
    examined(len(names), "model-call pages")
    for n in names:
        assert n in pages, sorted(pages)
        nav = re.search(r"<nav[^>]*data-call-tabs.*?</nav>", pages[n], re.S)
        assert nav, n
        assert [_text(t) for t in re.findall(r"<a [^>]*>.*?</a>", nav.group(0))] == list(TABS), n
        assert nav.group(0).count('aria-current="page"') == 1
    #: The step's page links its record's pages.
    assert 'href="call-1.html"' in pages["stage-1.html"]


def test_compare_names_the_first_divergence_and_every_level_in_order(built, examined):
    page = built["b"]["call-1-compare.html"]
    text = _text(page)
    examined(1, "compare page")
    card = _text(re.search(r'<section data-section="first-divergence".*?</section>', page, re.S).group(0))
    assert "Decode step 4" in card and "first output-token divergence" in card.lower()
    assert "python -m onetrace diff" in card
    levels = re.findall(r'<li data-level="([^"]+)"[^>]*>.*?<span class="chip[^"]*"[^>]*>([^<]+)</span>', page, re.S)
    got = dict(levels)
    assert list(got) == [
        "input",
        "envelope",
        "seed",
        "input-tokens",
        "prefill",
        "sampling-state",
        "logits",
        "output-token",
        "after",
    ], got
    assert got["input"] == "Same" and got["input-tokens"] == "Same"
    assert got["seed"] == got["sampling-state"] == got["after"] == got["prefill"] == "Not recorded"
    assert got["logits"] == "Step 2" and got["output-token"] == "Step 4"
    #: The step table around it: the divergence's row marked, the rows after it "Different history".
    rows = re.findall(r'<tr data-decode-row="(\d+)" data-status="([^"]+)"', page)
    status = dict(rows)
    assert status["4"] == "diverged" and status["5"] == "different-history" and status["3"] == "same"
    assert "generated from different histories" in text
    assert "not agreement" in text


def test_the_decode_step_shows_both_runs_and_says_what_is_not_recorded(built, examined):
    page = built["b"]["call-1-decode.html"]
    text = _text(page)
    examined(1, "decode page")
    assert "Decode step 4" in text
    rows = dict(re.findall(r'<tr data-decode-field="([^"]+)" data-result="([^"]+)"', page))
    assert rows["token"] == "differs" and rows["logits"] == "differs" and rows["sampling"] == "same"
    assert rows["sampling-state"] == rows["seed"] == rows["probability"] == "not-recorded"
    #: Self-hosted: ids, no probabilities, so no bars; the top-k ids of both runs, each run's choice marked.
    assert "data-probability-bar" not in page
    assert "chosen by" in text and "40" in text and "14" in text


def test_the_overview_tiles_and_a_timeline_of_positions_only(built, examined):
    page = built["b"]["call-1.html"]
    text = _text(page)
    examined(1, "overview")
    tiles = dict(re.findall(r'<div class="tile" data-tile="([^"]+)"[^>]*>.*?<strong[^>]*>([^<]+)</strong>', page, re.S))
    #: A value the record does not hold is drawn muted, never as the tile's figure.
    assert all(f'data-tile="{k}"' in page for k in ("latency", "replay", "input"))
    assert page.count('<strong class="nr">not recorded</strong>') == 3
    assert tiles["generated"] == "6" and tiles["level"] == "L3"
    assert tiles["latency"] == tiles["replay"] == tiles["input"] == "not recorded"
    assert "positions only" in text and "holds no probabilities" in text
    assert page.count("data-timeline-bar") == 6 and "data-p=" not in page
    #: The first output-token divergence against the held comparison, marked on the timeline.
    assert 'data-divergence="4"' in page


def test_a_hosted_capture_s_log_probabilities_draw_the_bars(built, examined):
    page = built["h"]["call-1.html"]
    examined(1, "hosted overview")
    ps = re.findall(r'data-timeline-bar data-p="([0-9.]+)"', page)
    assert ps == ["0.905", "0.951", "0.301"], ps
    assert "positions only" not in _text(page)


def test_the_receipt_cites_each_field_and_says_what_it_does_not_say(built, examined):
    page = built["b"]["call-1-receipt.html"]
    text = _text(page)
    examined(1, "receipt page")
    fields = re.findall(r'<tr data-field="([^"]+)"', page)
    for f in (
        "format",
        "model.reported",
        "tokenizer.digest",
        "input.token_ids_digest",
        "output.token_ids_digest",
        "steps",
        "engine.name",
    ):
        assert f in fields, fields
    assert "What this receipt does not say" in text and "Check it yourself" in text
    #: The command as a reader types it, a line each: no line end escaped into the text.
    assert "\\u000a" not in page and "onetrace-verify --require-artifacts ." in text
    badges = re.findall(r'<span class="badge" data-badge="([^"]+)"[^>]*>([^<]+)</span>', page)
    said = dict(badges)
    assert said["replay"] == "Replay: not recorded"
    assert said["agree"].startswith("Records agree")
    #: Nothing the record doesn't hold is drawn as held.
    for filler in ("Replay matched", "Executed", "teacher-forced: same", "L4"):
        assert filler not in text


def test_a_run_with_no_comparison_says_so_on_compare_and_decode(built, examined):
    examined(2, "pages")
    for n in ("call-1-compare.html", "call-1-decode.html"):
        assert "No comparison this console holds" in _text(built["h"][n])


def test_a_badge_is_its_question_and_answer_never_the_rung_s_markup(monkeypatch, examined):
    """A signed run's rung says its key and fingerprint in markup (a quoted label, a fold); the badge says the run page's
    question and its answer in plain words, and carries none of it."""
    from onetrace_console import model_call_pages, receipt_page

    said = 'Yes · <q data-words="report">demo key</q> · <details class="fingerprint"><summary>sha256:6e20…</summary></details>'
    monkeypatch.setattr(receipt_page, "_rung_said", lambda rung: ("Yes", said))
    examined(1, "badges")
    badges = model_call_pages._badges("Records agree: yes", object(), object())
    shown = dict(re.findall(r'<span class="badge" data-badge="([^"]+)"[^>]*>([^<]+)</span>', badges))
    assert shown["signed"] == "Signed by a known recorder: Yes"
    assert shown["anchored"] == "Committed by a known time: Yes"
    assert "&lt;" not in badges and "<q" not in badges and "<details" not in badges


def test_the_input_tokens_tile_says_the_record_holds_their_digest_only_where_it_does(built, examined):
    """P12's own record holds `input.token_ids_digest` as not observed (a hosted API does not expose it), so its tile
    says so; a self-hosted record that holds the digest says it holds it."""
    from onetrace import model_call as m

    from onetrace_console.demo_store.invoice_agent import _record
    from onetrace_console.model_call_pages import overview

    def tile(page: str) -> str:
        return _text(re.search(r'<div class="tile" data-tile="input".*?</div>', page, re.S).group(0))

    p12 = tile(overview({"record": _record(m, "sha256:" + "6" * 64, 3), "doc": None, "pairs": []}))
    held = tile(built["b"]["call-1.html"])
    examined(2, "input tiles: P12's and a self-hosted one's")
    assert "holds their digest" not in p12, p12
    assert "input.token_ids_digest" in p12 and "not observed" in p12, p12
    assert "the record holds their digest" in held and "input.token_ids_digest" in held, held


def test_where_one_capture_is_at_l3_the_compare_page_names_the_one_that_is_not(examined):
    """The logits rows are compared only where both captures are at L3; where one is, the sentence names the other,
    and only where neither is does it say neither."""
    from types import SimpleNamespace

    from onetrace_console.model_call_pages import Pair, _compare_one

    comparison = SimpleNamespace(key="k" * 64, verbs=())
    l3 = {"token_ids": ["11", "12", "13"], "digests": [digest(0), digest(1), digest(2)]}
    l2 = {"token_ids": ["11", "40", "13"], "top_k_ids": [["11"], ["40"], ["13"]]}
    l2_other = {"token_ids": ["11", "41", "13"], "top_k_ids": [["11"], ["41"], ["13"]]}

    def said(da, db) -> str:
        p = Pair(comparison, ({}, da), ({}, db), ("run-a", "run-b"), True)
        return _text(re.search(r'<section data-section="first-divergence".*?</section>', _compare_one(p, {}), re.S)[0])

    one, other, neither = said(l3, l2), said(l2, l3), said(l2, l2_other)
    examined(3, "first-divergence cards: candidate at L2, baseline at L2, both at L2")
    assert "both captures are not at L3" not in one + other + neither
    assert "The logits rows were not compared: run-b's capture is not at L3." in one, one
    assert "The logits rows were not compared: run-a's capture is not at L3." in other, other
    assert "The logits rows were not compared: neither capture is at L3." in neither, neither


def test_the_envelope_says_same_over_how_many_fields_both_records_hold(built, examined):
    """P12's record states 2 of the envelope's 13 fields; two of its records are "Same" only in those 2, and the chip
    says so. A field one record states and the other doesn't is not compared, never Same and never Differs; one both
    state with other values Differs."""
    from types import SimpleNamespace

    from onetrace import model_call as m

    from onetrace_console.demo_store.invoice_agent import _record
    from onetrace_console.model_call_pages import ENVELOPE, Pair, levels

    def envelope(ra, rb) -> tuple[str, str]:
        p = Pair(SimpleNamespace(key="k", verbs=()), (ra, None), (rb, None), ("run-a", "run-b"), True)
        [(word, kind)] = [(w, k) for key, _label, w, k in levels(p) if key == "envelope"]
        return word, kind

    p12 = _record(m, "sha256:" + "6" * 64, 3)
    both = [f for f in ENVELOPE if isinstance(p12.get(f), dict) and "value" in p12[f]]
    one_more = {**p12, "engine.name": m.declared("example-engine", "example")}
    other = {**p12, "model.reported": m.declared("another-model", "example")}
    examined(3, "envelope chips: P12 and P12, one field on one side only, one field differing")
    assert len(ENVELOPE) == 13 and len(both) == 2, both
    assert envelope(p12, p12) == ("Same, in the 2 of 13 fields both records hold", "same")
    assert envelope(one_more, p12) == ("Same, in the 2 of 13 fields both records hold", "same")
    assert envelope(other, p12) == ("Differs", "differs")


def test_the_decode_step_s_sampling_row_compares_only_what_both_records_state(examined):
    """The Sampling settings row reads Same only over the settings both records state, saying in how many of the three;
    a setting one record lacks is not read as a difference."""
    from types import SimpleNamespace

    from onetrace import model_call as m

    from onetrace_console.model_call_pages import Pair, _decode_rows

    doc_a, doc_b = {"token_ids": ["11", "12"]}, {"token_ids": ["11", "40"]}
    t = {"sampling.temperature": m.declared("0.0", "example")}
    t_p = {**t, "sampling.top_p": m.declared("1.0", "example")}

    def row(ra, rb) -> tuple[str, str]:
        p = Pair(SimpleNamespace(key="k", verbs=()), (ra, doc_a), (rb, doc_b), ("run-a", "run-b"), True)
        got = re.search(r'<tr data-decode-field="sampling" data-result="([^"]+)">.*?</tr>', _decode_rows(p, 1), re.S)
        return got.group(1), _text(re.search(r'<span class="chip[^"]*"[^>]*>([^<]+)</span>', got.group(0)).group(1))

    examined(3, "sampling rows: one setting on both, one more on one side, all three on both")
    assert row(t, t) == ("same", "Same, in the 1 of 3 fields both records hold")
    assert row(t_p, t) == ("same", "Same, in the 1 of 3 fields both records hold")
    every = {**t_p, "sampling.top_k": m.declared("1", "example")}
    assert row(every, every) == ("same", "Same")


def test_a_field_named_in_a_tile_wraps_inside_it(examined):
    """A record field's name is kept on one line in a table, and wraps inside a tile, so a long one such as
    `input.token_ids_digest` stays within the tile at every width."""
    from onetrace_console.model_call_pages import MODEL_CALL_PAGES_CSS

    examined(1, "stylesheet")
    rule = re.search(r"^\.call-page \.tile \.field\{([^}]*)\}", MODEL_CALL_PAGES_CSS, re.M)
    assert rule and "white-space:normal" in rule.group(1) and "overflow-wrap:anywhere" in rule.group(1), rule
