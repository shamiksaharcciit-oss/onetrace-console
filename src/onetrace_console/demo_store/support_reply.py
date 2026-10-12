"""P4, the demo store's support reply: a model stage whose wording varies on every run, and a later
stage whose recorded setting changes. Recorded with onetrace.

    question --> draft --> policy_check --> send

A customer's question comes in; `draft` writes a reply; `policy_check` sets the refund window in
the reply from its recorded setting `refund_days`; `send` records the reply that would go out.
`draft`'s reply leaves the window as the placeholder `{days}` by design, so a page showing its
output shows `{days}`; `policy_check`'s output has the number in its place.

`draft` is a STUB, not a hosted model: it picks one of a few fixed phrasings by a seed taken from
the run's id, as a sampled model call varies from call to call. Its receipt says so: it is marked
not re-runnable (`rederivable="false"`), with a note. Nothing here contacts a network or a model.

The demo's two runs of it differ in two ways: `draft`'s wording (its seed), and `policy_check`'s
`refund_days`, 30 in the first and 14 in the second -- the change a comparison should find, past a
first difference that is only the stub's variance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from onetrace.emit import Instrument, Recorder

from onetrace_console.bounded_json import load_json_bounded

STAGES = ["question", "draft", "policy_check", "send"]

#: The question, made up for this demo.
QUESTION = "I bought a kettle last week and it leaks. Can I return it for a refund?"

#: The stub's phrasings: one is picked by the run's seed, as a sampled model call varies.
PHRASINGS = [
    "Sorry to hear about the kettle. You can return it for a full refund within {days} days of "
    "delivery.",
    "Thanks for letting us know. A leaking kettle can be returned within {days} days of delivery, "
    "and we'll refund you in full.",
    "We're sorry the kettle leaks. Please send it back within {days} days of delivery for a full "
    "refund.",
]

STUB_NOTE = ("a stub standing in for a sampled model call: its wording is picked by a seed that "
             "changes per run, so its output is recorded, not replayed")


def _seed(run_id: str) -> int:
    """The stub's seed for a run: the first byte of the sha256 of its id, so each run differs."""
    return hashlib.sha256(run_id.encode("utf-8")).digest()[0]


def main(out_dir, run_id: str, refund_days: str, *, sign_with=None) -> None:
    """Record one run into `out_dir`, the refund window set to `refund_days`."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    question_path = out / "question.json"
    question_path.write_text(json.dumps({"question": QUESTION}, sort_keys=True), encoding="utf-8")
    rec = Recorder(out_dir, run_id=run_id, declared_stages=STAGES, manifest=Path(__file__),
                   policy="fail-closed", sign_with=sign_with,
                   anchor_reason="a demo record; anchoring is not part of this demo")
    seed = _seed(run_id)

    def question(ctx):
        q = load_json_bounded(ctx.read_external(question_path, "application/json", name="question",
                                                trust_class="operator-authored"), "question")
        return ctx.write_json("question.json", q)

    def draft(ctx, asked):
        ctx.read_receipt("question")
        q = ctx.read_json(asked)
        #: The stub's pick; the window is left as a placeholder for the policy stage to set.
        return ctx.write_json("draft.json", {"question": q["question"],
                                             "reply": PHRASINGS[seed % len(PHRASINGS)]})

    def policy_check(ctx, drafted):
        ctx.read_receipt("draft")
        d = ctx.read_json(drafted)
        ctx.constant("refund_days", refund_days)
        return ctx.write_json("checked.json", {"question": d["question"],
                                               "reply": d["reply"].format(days=refund_days)})

    def send(ctx, checked):
        ctx.read_receipt("policy_check")
        c = ctx.read_json(checked)
        return ctx.write_json("sent.json", {"reply": c["reply"]})

    asked = rec.run_node("question", None, Instrument("ticket-intake", "reader", "1.0.0",
                                                      {"source": "question.json"}), question)
    drafted = rec.run_node("draft", None, Instrument(
        "reply-stub", "model-stub", "1.0.0", {"phrasings": str(len(PHRASINGS))},
        rederivable="false", rederivable_note=STUB_NOTE), draft, asked)
    checked = rec.run_node("policy_check", None, Instrument("refund-policy", "checker", "1.0.0",
                                                            {"policy": "refund window"}),
                           policy_check, drafted)
    rec.run_node("send", None, Instrument("reply-outbox", "writer", "1.0.0", {"channel": "email"}),
                 send, checked)
    rec.close()
