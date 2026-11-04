"""The line at the top of a comparison page: what kind of thing differs at the first difference.

One planted run pair for each kind, with its expected sentence:

1. inputs differ: a step whose own input differs;
2. a model call with equal inputs, named by the comparator's first differing field in its groups:
   model identity, engine settings, sampling settings, the output alone; and a batch context that
   differs, said in the comparator's words as a could-not-compare;
3. a decision step: both verdicts, and the policy version where both runs' decisions are in a held
   export (differing, or the same), "not recorded" where they are not;
4. a kept output absent: the step's output delivered without its file.

A step none of these covers (a step recorded with the instrument kind `tool`, outputs kept and
differing) gets no line, and the page is as it was. The line is first on the page, before the short
answer, and never says what produced the difference. On the demo as the public build draws it, the
pairs whose first difference is an input carry the inputs line.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

from onetrace_console import first_kind

GENERATED_AT = "2026-09-26T12:00:00+02:00"
ISSUER = "https://approver.example/issuer"


def _said(page: str) -> tuple[str | None, str | None]:
    """(the line's kind, its words with each `<code>` name between backticks), or (None, None)."""
    m = re.search(r'<p class="first-kind" data-section="first-kind" data-kind="([^"]+)">(.*?)</p>', page, re.S)
    if m is None:
        return None, None
    words = re.sub(r"<code>(.*?)</code>", r"`\1`", m.group(2), flags=re.S)
    return m.group(1), html.unescape(re.sub(r"<[^>]+>", "", words))


def _row(request_id: str, verdict: str, version: str | None) -> dict:
    row = {"request_id": request_id, "action_type": "pay",
           "decision": {"permit": "executed", "deny": "denied"}[verdict]}
    if version is not None:
        row["policy_version"] = version
    return row


def _ref(row: dict, verdict: str) -> dict:
    from onetrace import onedoor_ref
    return {"format": "onedoor-decision-ref/1", "request_id": row["request_id"],
            "decision_digest": onedoor_ref.decision_digest(row), "verdict": verdict, "issuer": ISSUER}


def _step_run(folder: Path, run_id: str, *, question: bytes = b"what is due?", answer: str = "a",
              kind: str = "model", ref: dict | None = None) -> Path:
    """A one-step run: the step reads `question`, records `ref` where given, and writes `answer`."""
    from onetrace.emit import Instrument, Recorder
    out = folder / run_id
    gated = {"gated_stages": ["step"]} if ref is not None else {}
    rec = Recorder(str(out), run_id=run_id, declared_stages=["step"], manifest=Path(__file__),
                   policy="fail-closed", anchor_reason="a test", **gated)

    def step(ctx):
        ctx.read_memory(question, "text/plain", name="question", trust_class="externally-sourced")
        if ref is not None:
            ctx.decision(ref)
        return ctx.write_json("answer.json", {"answer": answer})

    rec.run_node("step", None, Instrument("example-step", kind, "1.0.0", {}), step)
    rec.close()
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.frame import rendering
    from onetrace_console.onedoor_ext.decisions import accept_export
    from onetrace_console.render import render_diff
    from onetrace_console.store import Store
    from tests.model_call_runs import record_run
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    from tests.test_policy_pages import _delivery
    folder = tmp_path_factory.mktemp("first-kind")
    rows = {"held-a": _row("held-a", "permit", "v1"), "held-b": _row("held-b", "deny", "v2"),
            "same-a": _row("same-a", "permit", "v3"), "same-b": _row("same-b", "deny", "v3"),
            "gone-a": _row("gone-a", "permit", "v1"), "gone-b": _row("gone-b", "deny", "v2")}
    s = folder / "s"
    made = {
        "in-a": (_step_run(s, "in-a"), True), "in-b": (_step_run(s, "in-b", question=b"what is owed?", answer="b"), True),
        "dec-a": (_step_run(s, "dec-a", ref=_ref(rows["held-a"], "permit")), True),
        "dec-b": (_step_run(s, "dec-b", answer="b", ref=_ref(rows["held-b"], "deny")), True),
        "same-a": (_step_run(s, "same-a", ref=_ref(rows["same-a"], "permit")), True),
        "same-b": (_step_run(s, "same-b", answer="b", ref=_ref(rows["same-b"], "deny")), True),
        "gone-a": (_step_run(s, "gone-a", ref=_ref(rows["gone-a"], "permit")), True),
        "gone-b": (_step_run(s, "gone-b", answer="b", ref=_ref(rows["gone-b"], "deny")), True),
        "kept-a": (_step_run(s, "kept-a"), False), "kept-b": (_step_run(s, "kept-b", answer="b"), False),
        "tool-a": (_step_run(s, "tool-a", kind="tool"), True),
        "tool-b": (_step_run(s, "tool-b", kind="tool", answer="b"), True),
        "mc": (record_run(folder / "mc", "mc"), True),
        "mc-files": (record_run(folder / "mc-files", "mc-files", files_digest="sha256:" + "f" * 64), True),
        "mc-out": (record_run(folder / "mc-out", "mc-out", fingerprint="sha256:" + "d" * 64,
                              output="sha256:" + "e" * 64), True),
        "mc-set-a": (record_run(folder / "mc-set-a", "mc-set-a", extra={"engine.settings.max_new_tokens": "64"}), True),
        "mc-set-b": (record_run(folder / "mc-set-b", "mc-set-b", extra={"engine.settings.max_new_tokens": "128"}), True),
        "mc-samp-a": (record_run(folder / "mc-samp-a", "mc-samp-a", extra={"sampling.temperature": "0"}), True),
        "mc-samp-b": (record_run(folder / "mc-samp-b", "mc-samp-b", extra={"sampling.temperature": "0.7"}), True),
        "mc-batch": (record_run(folder / "mc-batch", "mc-batch", extra={"batch.size": "2"}), True),
    }
    store = Store(folder / "store")
    export = [rows[k] for k in ("held-a", "held-b", "same-a", "same-b")]
    accept_export(_delivery("decisions.jsonl", "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n"
                                                       for r in export).encode("utf-8")), store)
    runs = {k: run_and_record(_deliver(p, store, outputs=kept), store, ran_at=FIXED_RAN_AT)
            for k, (p, kept) in made.items()}
    pairs = {"inputs": ("in-a", "in-b"), "decision": ("dec-a", "dec-b"), "decision-same": ("same-a", "same-b"),
             "decision-gone": ("gone-a", "gone-b"), "not-kept": ("kept-a", "kept-b"), "tool": ("tool-a", "tool-b"),
             "identity": ("mc", "mc-files"), "output": ("mc", "mc-out"), "settings": ("mc-set-a", "mc-set-b"),
             "sampling": ("mc-samp-a", "mc-samp-b"), "batch": ("mc", "mc-batch")}
    comparisons = {k: compare(runs[a], runs[b], store, ran_at=FIXED_RAN_AT) for k, (a, b) in pairs.items()}
    with rendering(onedoor=False, sign_in=False, public=True):
        pages = {k: render_diff(c, store, generated_at=GENERATED_AT) for k, c in comparisons.items()}
    return {"pages": pages, "store": store, "comparisons": comparisons}


#: Each planted pair: (the kind, the line as a reader reads it).
WANT = {
    "inputs": ("inputs", "The first difference is upstream: this step's inputs already differed."),
    "identity": ("model-call", "The model's output differed on equal inputs; the comparator's kind of change: "
                               "model identity (first differing field `model.files_digest`)."),
    "settings": ("model-call", "The model's output differed on equal inputs; the comparator's kind of change: "
                               "engine settings (first differing field `engine.settings.max_new_tokens`)."),
    "sampling": ("model-call", "The model's output differed on equal inputs; the comparator's kind of change: "
                               "sampling settings (first differing field `sampling.temperature`)."),
    "output": ("model-call", "The model's output differed on equal inputs; the comparator's kind of change: "
                             "the output alone (first differing field `fingerprint (tolerant, first-token-logprobs)`)."),
    "batch": ("model-call-batch", "At this step's model call, the comparator's result is: "
                                  "could not compare: batch context differs: batch.size."),
    "decision": ("decision", "The policy decision differed: `permit` in the baseline, `deny` in the candidate. "
                             "The policy version differed: `v1` in the baseline, `v2` in the candidate."),
    "decision-same": ("decision", "The policy decision differed: `permit` in the baseline, `deny` in the candidate. "
                                  "The policy version is the same in both: `v3`."),
    "decision-gone": ("decision", "The policy decision differed: `permit` in the baseline, `deny` in the candidate. "
                                  "The policy version is not recorded."),
    "not-kept": ("output-not-kept", "This step's output was not kept, so only its digest is compared."),
    "tool": (None, None),
}


def test_each_planted_kind_has_its_sentence(built, examined):
    examined(len(WANT), "planted pairs")
    assert {k: _said(built["pages"][k]) for k in WANT} == WANT


def test_the_line_is_first_before_the_short_answer(built, examined):
    pages = {k: p for k, p in built["pages"].items() if WANT[k][0]}
    examined(len(pages), "pages with a line")
    for k, page in pages.items():
        line = page.index('data-section="first-kind"')
        assert line < page.index('data-section="short-answer"'), k
        assert 'data-section="first-difference"' in page, k


def test_a_tool_step_gets_no_line_and_its_page_is_otherwise_the_same(built, examined):
    page = built["pages"]["tool"]
    examined(1, "the tool pair's page")
    assert 'data-section="first-kind"' not in page
    assert 'data-section="short-answer"' in page and 'data-section="first-difference"' in page


@pytest.mark.parametrize("word", ["caused", "because", "why"])
def test_no_line_says_what_produced_the_difference(word, examined):
    lines = [first_kind.INPUTS, first_kind.MODEL, first_kind.BATCH, first_kind.DECISION, first_kind.POLICY_SAME,
             first_kind.POLICY_DIFFERS, first_kind.POLICY_NOT_RECORDED, first_kind.NOT_KEPT]
    examined(len(lines), "lines")
    assert not any(re.search(rf"\b{word}\b", s, re.I) for s in lines)


def test_the_groups_are_the_comparator_s_own(examined):
    from onetrace.model_call.comparator import IDENTITY
    examined(len(IDENTITY), "identity fields")
    assert {first_kind.model_kind(f) for f in IDENTITY} == {first_kind.IDENTITY}
    assert first_kind.model_kind("engine.settings.x") == first_kind.ENGINE
    assert first_kind.model_kind("sampling.top_p") == first_kind.SAMPLING
    assert first_kind.model_kind("output.finish") == first_kind.OUTPUT


def test_sabotage_without_the_inputs_check_the_inputs_pair_has_no_line(built, monkeypatch, examined):
    """With the inputs check off, the inputs pair says nothing: the check is what gives its line."""
    monkeypatch.setattr(first_kind, "_inputs_differ", lambda *a: False)
    from onetrace_console.render import read_diff
    c = built["comparisons"]["inputs"]
    report, _ = read_diff(c, built["store"])
    examined(1, "the inputs pair")
    assert first_kind.chosen(report, c, built["store"]) is None


def test_the_demo_s_input_pairs_carry_the_inputs_line(shared_demo, examined):
    from onetrace_console.store import Store
    store = Store(shared_demo["folder"] / "store" / "store")
    ids = {r.key: r.run_id for r in store.runs()}
    pages = shared_demo["folder"] / "store" / "pages" / "diff"
    got = {}
    for c in store.comparisons():
        page = pages / f"{c.key}.html"
        if page.exists():
            got[(ids.get(c.run_a), ids.get(c.run_b))] = _said(page.read_text(encoding="utf-8"))[0]
    examined(len(got), "demo comparison pages")
    assert got[("p8-43-invoice-tolerance-5pct", "p8-44-invoice-quantity-changed")] == "inputs"
    assert got[("p9-46-torque-baseline", "p9-48-torque-one-bolt-low")] == "inputs"
    assert got[("p1-02-baseline-set2", "p1-08-candidate-set2")] is None
