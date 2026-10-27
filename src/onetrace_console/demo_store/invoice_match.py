"""P8, the demo store's invoice match: a supplier's invoice to paying it or holding it, recorded with
onetrace.

    read_invoice --> match --> approve_payment

A supplier's invoice comes in as a small file; `read_invoice` reads it -- from outside the pipeline,
kept beside its digest, as invented example data the demo builder marks as such; `match` holds it
against the purchase order and the goods receipt, line by line: the quantity invoiced must be the
quantity received, and the unit price is over the order's by no more than a price tolerance, a
setting of its instrument; `approve_payment` pays a matched invoice and holds one that is not, and
declines by its own rule to pay an invoice over the approver's limit -- the run then stops there.

Every invoice, order, price and name here is invented example data, made in this module, the same
on every build: no real supplier, buyer, product or payment. Nothing contacts a network or any
payment system; the demo records and compares, and never pays anything. Amounts are whole cents
and tolerances whole basis points, so nothing is rounded.

The demo's runs of it: an invoice held at a 2% price tolerance; the same invoice paid at 5%, so the
comparison shows the setting that changed at `match` and the decision it changes; the same invoice
with one line's quantity changed, from 40 to 400, held at 5%; and a larger invoice that matches,
declined by `approve_payment` as over the approver's limit.

With onetrace 0.5, where the builder gives an `issuer` (`onedoor_demo`), `approve_payment` is a gated
step: before it pays or holds, it cites the onedoor decision that allowed that action, with a permit
bound to it; the over-limit invoice cites a denial and is not paid. Two more runs are broken on purpose
(`plant`): one pays on a denied decision, and one carries a permit for another amount than the payment
it records. The decisions are made by the builder, never by onedoor: invented example data.
"""
from __future__ import annotations

import json
from pathlib import Path

from onetrace.emit import Instrument, Recorder, Refusal

from onetrace_console.bounded_json import load_json_bounded

STAGES = ["read_invoice", "match", "approve_payment"]

EXAMPLE = "invented example data"
#: The approver's limit: an invoice over it is not paid by this pipeline. In cents: 2,500.00.
APPROVER_LIMIT_CENTS = 250000

#: Each invoice the demo uses, invented: its number, and its one line (item, quantity, unit price in
#: cents). The purchase order and goods receipt it is matched against are below, by invoice.
INVOICES = {
    "base": {"invoice": "INV-1001", "order": "PO-501", "item": "steel bracket, 40 mm",
             "quantity": 40, "unit_price_cents": 1280},
    "quantity-400": {"invoice": "INV-1001", "order": "PO-501", "item": "steel bracket, 40 mm",
                     "quantity": 400, "unit_price_cents": 1280},
    "large": {"invoice": "INV-1002", "order": "PO-502", "item": "steel bracket, 40 mm",
              "quantity": 300, "unit_price_cents": 1280},
}
#: The purchase order's quantity and unit price, and the quantity the goods receipt records.
ORDERS = {
    "PO-501": {"quantity": 40, "unit_price_cents": 1250, "received": 40},
    "PO-502": {"quantity": 300, "unit_price_cents": 1250, "received": 300},
}


def _money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def _percent(basis_points: int) -> str:
    return f"{basis_points // 100}.{basis_points % 100:02d}%"


def invoice_text(invoice: str) -> str:
    """The invoice's file, a CSV with one line: what was invoiced, how many, at what unit price."""
    inv = INVOICES[invoice]
    rows = ["# invented example data for this demo",
            f"# invoice {inv['invoice']}, against purchase order {inv['order']}",
            "item,quantity,unit_price",
            f"{inv['item']},{inv['quantity']},{_money(inv['unit_price_cents'])}"]
    return "\n".join(rows) + "\n"


def invoice_bytes(invoice: str) -> bytes:
    """The invoice's file as `read_invoice` reads it, and keeps it: a JSON string of its text, the
    bytes its digest is computed over."""
    return json.dumps(invoice_text(invoice)).encode("utf-8")


def kept_inputs(args: dict) -> list[bytes]:
    """The bytes of every input a run with `args` keeps: its invoice file."""
    return [invoice_bytes(args["invoice"])]


def _cents(text: str) -> int:
    whole, _, cents = text.partition(".")
    return int(whole) * 100 + int((cents + "00")[:2])


#: The two ways the builder breaks a gated run on purpose.
PLANTS = ("pay-on-deny", "permit-other-amount")


def main(out_dir, run_id: str, invoice: str, tolerance_bp: str, plant: str = "", issuer=None) -> None:
    """Record one run: which invoice, and `match`'s price tolerance in basis points (200 is 2%).
    `issuer` (`onedoor_demo.Issuer`): `approve_payment` is gated, and cites its decision; `plant`
    breaks that on purpose (`PLANTS`)."""
    if plant and plant not in PLANTS:
        raise ValueError(f"no plant {plant!r}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    gated = {"gated_stages": ["approve_payment"]} if issuer is not None else {}
    rec = Recorder(out_dir, run_id=run_id, declared_stages=STAGES, manifest=Path(__file__),
                   policy="fail-closed", anchor_reason="a demo record; anchoring is not part of this demo",
                   **gated)
    data = invoice_bytes(invoice)
    tolerance = int(tolerance_bp)

    def read_invoice(ctx):
        ctx.read_memory(data, "application/json", name="invoice", trust_class="externally-sourced")
        ctx.keep_declared = True
        ctx.keep_input("invoice", data)
        ctx.constant("data", EXAMPLE)
        lines = load_json_bounded(data.decode("utf-8"), "the invoice file").splitlines()
        order = lines[1].rsplit(" ", 1)[1]
        item, quantity, price = lines[3].rsplit(",", 2)
        return ctx.write_json("invoice.json", {"order": order, "item": item, "quantity": quantity,
                                               "unit_price": price})

    def match(ctx, read):
        ctx.read_receipt("read_invoice")
        inv = ctx.read_json(read)
        po = ORDERS[inv["order"]]
        ctx.constant("order_quantity", str(po["quantity"]))
        ctx.constant("order_unit_price", _money(po["unit_price_cents"]))
        ctx.constant("received_quantity", str(po["received"]))
        #: The tolerance as a recorded constant too, so a comparison names it with both values; the
        #: instrument's setting of the same name stays, kept as its configuration's digest.
        ctx.constant("price_tolerance", _percent(tolerance))
        quantity, price = int(inv["quantity"]), _cents(inv["unit_price"])
        over_bp = (price - po["unit_price_cents"]) * 10000 // po["unit_price_cents"]
        problems = []
        if quantity != po["received"]:
            problems.append(f"quantity invoiced {quantity}, quantity received {po['received']}")
        if over_bp > tolerance:
            problems.append(f"unit price {_money(price)} is {_percent(over_bp)} over the order's "
                            f"{_money(po['unit_price_cents'])}, past the tolerance of {_percent(tolerance)}")
        return ctx.write_json("match.json", {"order": inv["order"], "matched": not problems,
                                             "problems": problems,
                                             "amount": _money(quantity * price)})

    def approve_payment(ctx, matched):
        ctx.read_receipt("match")
        m = ctx.read_json(matched)
        amount = _cents(m["amount"])
        over = m["matched"] and amount > APPROVER_LIMIT_CENTS
        if issuer is not None:
            #: The decision that allowed what the step does, cited before it does it. Numbers in an
            #: action are decimal strings, as onedoor's are.
            request = f"{run_id}/approve_payment"
            action = {"action": "pay" if m["matched"] else "hold", "order": m["order"],
                      "amount_eur": m["amount"]}
            if over or plant == "pay-on-deny":
                ctx.decision(issuer.decide(request, "deny"))
            elif plant == "permit-other-amount":
                ctx.decision(issuer.decide(request, "permit"),
                             permit=issuer.permit({**action, "amount_eur": _money(amount + 100000)}), action=action)
            else:
                ctx.decision(issuer.decide(request, "permit"), permit=issuer.permit(action), action=action)
        if over:
            raise Refusal(f"an invoice of {m['amount']} is over the approver's limit of "
                          f"{_money(APPROVER_LIMIT_CENTS)}")
        return ctx.write_json("payment.json", {"decision": "pay" if m["matched"] else "hold",
                                               "amount": m["amount"], "problems": m["problems"]})

    read = rec.run_node("read_invoice", None, Instrument("invoice-reader", "reader", "1.0.0",
                                                         {"format": "csv, one line"}), read_invoice)
    matched = rec.run_node("match", None, Instrument("three-way-match", "checker", "1.0.0",
                                                     {"price_tolerance": _percent(tolerance)}),
                           match, read)
    rec.run_node("approve_payment", None, Instrument("payment-approval", "policy", "1.0.0",
                                                     {"approver_limit": _money(APPROVER_LIMIT_CENTS)}),
                 approve_payment, matched)
    rec.close()
