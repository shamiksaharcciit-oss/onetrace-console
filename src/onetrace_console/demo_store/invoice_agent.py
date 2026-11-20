"""P12, the invoice agent: a model call and a onedoor decision on one run, recorded with onetrace 0.9.

    read_invoice --> recall_vendor --> propose_payment --> pay --> remember_vendor

`read_invoice` reads a one-line invoice. `recall_vendor` reads the vendor's note from the agent's memory, the note an
earlier P12 run wrote (`ot.state.read`, its bytes kept beside the record; the first run finds none, and a read that
found nothing has no value to keep). `propose_payment` is the model call: a hosted model
reads the invoice and the note and proposes a payment, recorded as `model_call.json` in `model-call-record/1.1` with
its L2-hosted steps file (each output token with the provider's log-probabilities). `pay` is the gated step: it cites
the onedoor decision on the proposal, with a permit bound to the action it takes, then pays or is refused. And
`remember_vendor` writes the vendor's note back to memory (`ot.state.write`) for the next run to read.

The runs, in the order recorded: one whose permit covers another amount than the one paid (broken on purpose; it is
the first, so its memory holds no note yet, and it writes the note each later run reads); a good one; one where the
model read the invoice's 40.00 as 4,000.00 (its decision denies a payment over the approver's limit, and `pay` is
refused); and one whose provider fingerprint differs from the others' (`provider.fingerprint`), with the same answer.

Everything here is invented example data: no model is called, nothing is paid, and the decisions are made by the
builder, never by onedoor (`onedoor_demo.Issuer`). The records say so in their own words.
"""

from __future__ import annotations

import json
from pathlib import Path

STAGES = ["read_invoice", "recall_vendor", "propose_payment", "pay", "remember_vendor"]
EXAMPLE = "invented example data"
SOURCE = "example data, constructed for the demo; no model was called"
VENDOR = "Example Office Supply"
MEMORY = "agent-memory.vendor-notes"
#: The approver's limit, in cents: a proposal over it is denied.
LIMIT_CENTS = 100000
#: The runs' variants: what each changes.
VARIANTS = ("good", "misread", "permit-other-amount", "fingerprint-changed")
FINGERPRINTS = {"usual": "fp_example_7c1d", "changed": "fp_example_9e40"}
INVOICE = "INV-2207,Example Office Supply,toner cartridges,40.00 EUR"
#: When each run read the invoice: invented, one per run, so the runs differ there and only there at `read_invoice`. The
#: demo marks it as noise (`demo_store.NOISE`).
READ_AT = {
    "permit-other-amount": "2026-11-12T09:00:00Z",
    "good": "2026-11-13T09:00:00Z",
    "misread": "2026-11-14T09:00:00Z",
    "fingerprint-changed": "2026-11-15T09:00:00Z",
}


def invoice_bytes() -> bytes:
    """The invoice as a run keeps it: its text as a JSON string, the form onetrace keeps a text input in (as P8's)."""
    return json.dumps(INVOICE + "\n").encode("utf-8")


def kept_inputs(args: dict) -> list[bytes]:
    """The bytes of every input a run keeps: its invoice."""
    return [invoice_bytes()]


def note_bytes(paid: str) -> bytes:
    """The vendor's note, as `remember_vendor` writes it."""
    return json.dumps({"vendor": VENDOR, "last_paid_eur": paid, "data": EXAMPLE}, sort_keys=True).encode("utf-8")


def _tokens(amount: str) -> list[dict]:
    """The model's proposal as its output tokens, each with the provider's log-probability: invented, rounded to 2."""
    lead = [('{"pay_eur": "', "-0.02")]
    if amount == "40.00":
        middle = [("40", "-0.21"), (".00", "-0.04")]
    else:
        middle = [("4", "-1.61"), (",000", "-0.92"), (".00", "-0.05")]
    tail = [('", "to": "Example Office Supply"}', "-0.03")]
    out = []
    for text, lp in lead + middle + tail:
        others = {"40": [("4", "-1.70"), ("400", "-3.10")], "4": [("40", "-0.25"), ("400", "-3.00")]}.get(
            text, [("\n", "-4.60")]
        )
        out.append(
            {
                "chosen": {"text": text, "logprob": lp},
                "candidates": [{"text": text, "logprob": lp}] + [{"text": t, "logprob": p} for t, p in others],
            }
        )
    return out


def _record(m, fingerprint: str, steps_n: int) -> dict:
    """The model call's record: a hosted call. The record is constructed, so each value it gives of the call is
    declared, with its source saying it is example data, as the capture store's example records state theirs; what a
    hosted API hides is not observed. Observed are only what onetrace reads from the steps file it wrote: its digest
    (`main`, by `write_steps`), and its level, method, count and returned candidates, which `onetrace-verify` reads
    again from the file's bytes."""
    from onetrace.model_call import record as r

    out = {
        "format": r.FORMAT_1_1,
        "call.kind": "hosted",
        "call.api": "v1/chat/completions",
        "credential": "absent",
        "model.requested": m.declared("example-hosted-model", SOURCE),
        "model.reported": m.declared("example-hosted-model-2026-10", SOURCE),
        "provider.fingerprint": m.declared(fingerprint, SOURCE),
        "input.request_digest": m.declared("sha256:" + "4" * 64, SOURCE),
        "output.finish": m.declared("stop", SOURCE),
        "output.text_digest": m.declared("sha256:" + "5" * 64, SOURCE),
    }
    for k in (
        ("model.files_digest", "tokenizer.digest", "engine.name", "engine.version")
        + r.RUNTIME
        + (
            "dtype",
            "attention_backend",
            "batch.size",
            "batch.executed_size",
            "batch.padded_width",
            "batch.position",
            "batch.members",
            "batch.fillers",
            "batch.batch_invariant",
            "input.token_ids_digest",
            "output.token_ids_digest",
        )
    ):
        out[k] = m.not_observed("hosted API: not exposed by the provider")
    out["sampling.temperature"] = m.declared("0.0", SOURCE)
    out["fingerprints"] = [m.fingerprint("tolerant", "provider-logprobs", 16, 2, m.not_observed(SOURCE))]
    out["steps.level"] = m.observed("L2-hosted", SOURCE)
    out["steps.method"] = m.observed("provider-text", SOURCE)
    out["steps.count"] = m.observed(str(steps_n), SOURCE)
    out["steps.k_requested"] = m.declared("3", SOURCE)
    out["steps.k_returned_min"] = m.observed("2", SOURCE)
    out["steps.k_returned_max"] = m.observed("3", SOURCE)
    out["steps.logprobs"] = m.declared("rounded-2", SOURCE)
    return out


def _cents(text: str) -> int:
    whole, _, cents = text.replace(",", "").partition(".")
    return int(whole) * 100 + int((cents + "00")[:2])


def main(out_dir, run_id: str, variant: str, issuer, note: bytes | None) -> bytes:
    """Record one run; returns the note its `remember_vendor` wrote. `note`: the note an earlier run wrote, which
    `recall_vendor` reads (None: it finds none)."""
    import onetrace as ot
    from onetrace import model_call as m
    from onetrace.emit import Instrument, Recorder, Refusal, current_stage

    from onetrace_console.bounded_json import load_json_bounded

    if variant not in VARIANTS:
        raise ValueError(f"no variant {variant!r}")
    rec = Recorder(
        out_dir,
        run_id=run_id,
        declared_stages=STAGES,
        manifest=Path(__file__),
        policy="fail-closed",
        anchor_reason="a demo record; anchoring is not part of this demo",
        gated_stages=["pay"],
    )
    data = invoice_bytes()
    amount = "4,000.00" if variant == "misread" else "40.00"
    fingerprint = FINGERPRINTS["changed" if variant == "fingerprint-changed" else "usual"]
    written: dict[str, bytes] = {}

    def read_invoice(ctx):
        ctx.read_memory(data, "application/json", name="invoice", trust_class="externally-sourced")
        ctx.keep_declared = True
        ctx.keep_input("invoice", data)
        ctx.constant("data", EXAMPLE)
        number, vendor, item, total = load_json_bounded(data.decode("utf-8"), "the invoice file").strip().split(",")
        return ctx.write_json(
            "invoice.json",
            {"number": number, "vendor": vendor, "item": item, "total": total, "read_at": READ_AT[variant]},
        )

    def recall_vendor(ctx, inv):
        ctx.read_receipt("read_invoice")
        ctx.constant("data", EXAMPLE)
        if note is None:
            ot.state.read(MEMORY, VENDOR, kind="kv", found=False)
            said = {"vendor": VENDOR, "note": None}
        else:
            ot.state.read(MEMORY, VENDOR, note, kind="kv", keep=True)
            said = {"vendor": VENDOR, "note": load_json_bounded(note.decode("utf-8"), "the vendor's note")}
        return ctx.write_json("vendor_note.json", said)

    def propose_payment(ctx, recalled):
        ctx.read_receipt("recall_vendor")
        ctx.constant("data", EXAMPLE)
        steps = {"level": "L2-hosted", "method": "provider-text", "steps": _tokens(amount)}
        record = _record(m, fingerprint, len(steps["steps"]))
        digest, name = m.write_steps(current_stage(), "model_call.json", steps)
        record["steps"] = m.observed(digest, name)
        current_stage().write("model_call.json", m.record_bytes(record), "application/json")
        return ctx.write_json("proposal.json", {"pay_eur": amount, "to": VENDOR, "invoice": "INV-2207"})

    def pay(ctx, proposed):
        ctx.read_receipt("propose_payment")
        p = ctx.read_json(proposed)
        cents = _cents(p["pay_eur"])
        request = f"{run_id}/pay"
        action = {"action": "pay", "invoice": p["invoice"], "amount_eur": p["pay_eur"].replace(",", "")}
        over = cents > LIMIT_CENTS
        if over:
            ctx.decision(issuer.decide(request, "deny"))
        elif variant == "permit-other-amount":
            other = {**action, "amount_eur": "400.00"}
            ctx.decision(issuer.decide(request, "permit"), permit=issuer.permit(other), action=action)
        else:
            ctx.decision(issuer.decide(request, "permit"), permit=issuer.permit(action), action=action)
        if over:
            raise Refusal(f"a payment of {p['pay_eur']} EUR is over the approver's limit of 1,000.00 EUR")
        return ctx.write_json("payment.json", {"paid_eur": p["pay_eur"], "to": p["to"], "data": EXAMPLE})

    def remember_vendor(ctx, paid):
        ctx.read_receipt("pay")
        ctx.constant("data", EXAMPLE)
        new = note_bytes(ctx.read_json(paid)["paid_eur"])
        ot.state.write(MEMORY, VENDOR, new, kind="kv", keep=True)
        written["note"] = new
        return ctx.write_json("remembered.json", {"vendor": VENDOR, "written": True})

    inv = rec.run_node(
        "read_invoice", None, Instrument("invoice-reader", "reader", "1.0.0", {"format": "csv"}), read_invoice
    )
    recalled = rec.run_node(
        "recall_vendor", None, Instrument("agent-memory", "memory", "1.0.0", {"store": MEMORY}), recall_vendor, inv
    )
    proposed = rec.run_node(
        "propose_payment",
        None,
        Instrument("payment-proposer", "model", "1.0.0", {"model": "example-hosted-model"}),
        propose_payment,
        recalled,
    )
    paid = rec.run_node(
        "pay", None, Instrument("payment", "policy", "1.0.0", {"approver_limit": "1,000.00 EUR"}), pay, proposed
    )
    if paid is None:
        #: Refused (the decision denied it): nothing paid, and no note written.
        rec.close()
        return b""
    rec.run_node(
        "remember_vendor", None, Instrument("agent-memory", "memory", "1.0.0", {"store": MEMORY}), remember_vendor, paid
    )
    rec.close()
    return written.get("note", b"")
