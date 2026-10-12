"""P3, the demo store's ticket triage: a small pipeline shaped as a graph, recorded with onetrace.

               +--> classify -------+
    intake ----+                    +--> draft_reply --> route
               +--> lookup_account -+

A support ticket comes in; it is classified by keyword rules and, in parallel, its account is
looked up; a reply is drafted from both; the ticket is routed to the queue its class names. The
run declares that graph as its approved plan (`declared_edges`), so the record is graph-shaped:
the demo store's case of a run that is not a straight line.

The tickets and accounts are made up for this demo. Nothing here contacts a network or a model:
the classifier is an ordered list of keyword rules, the first rule with a matching word wins,
and the rules' version is recorded as a setting. Version 2 checks the technical rule before the
billing rule: the demo's "rule edit", which routes a ticket that names both differently.

`fault="lookup-once"` makes the account lookup's first attempt raise, and the error it records
says so; the pipeline retries it once, and the failed attempt is kept in the record.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from onetrace.emit import Instrument, Recorder

from onetrace_console.bounded_json import load_json_bounded

STAGES = ["intake", "classify", "lookup_account", "draft_reply", "route"]

APPROVED = [{"from": a, "to": b} for a, b in (
    ("intake", "classify"), ("intake", "lookup_account"), ("classify", "draft_reply"),
    ("lookup_account", "draft_reply"), ("draft_reply", "route"))]

#: The tickets, made up for this demo.
TICKETS = {
    "T-1": {"account": "acct-01", "text": "I was charged twice for one order, and then the app "
                                         "crashed at checkout."},
    "T-2": {"account": "acct-02", "text": "My invoice shows the wrong billing address."},
    "T-3": {"account": "acct-03", "text": "The app shows an error every time I log in."},
    "T-4": {"account": "acct-01", "text": "The login page keeps reloading and I cannot reach my "
                                         "orders."},
}

#: The accounts the lookup reads, made up for this demo.
ACCOUNTS = {"acct-01": {"plan": "standard", "region": "north"},
            "acct-02": {"plan": "business", "region": "south"},
            "acct-03": {"plan": "standard", "region": "south"}}

#: The classifier's rules, by version: (class, keywords), checked in order.
RULES = {
    "1": [("billing", ["charged", "invoice", "refund", "payment", "billing"]),
          ("technical", ["app", "error", "crash", "crashed", "login", "log"])],
    "2": [("technical", ["app", "error", "crash", "crashed", "login", "log"]),
          ("billing", ["charged", "invoice", "refund", "payment", "billing"])],
}

LOOKUP_FAULT = ("set by the demo to show a retry: the first attempt raises this instead of "
                "running; nothing else went wrong")

QUEUES = {"billing": "billing-desk", "technical": "tech-support", "other": "front-desk"}

REPLIES = {
    "billing": "Thanks for telling us about a billing problem. Our billing desk will check your "
               "account and reply within one working day.",
    "technical": "Thanks for reporting a technical problem. Our support team will look into it "
                 "and reply within one working day.",
    "other": "Thanks for your message. We will reply within two working days.",
}


def classify_text(text: str, version: str) -> tuple[str, str]:
    """The class and the word that decided it, by the first rule with a matching word."""
    found = re.findall(r"[a-z]+", text.lower())
    for name, keywords in RULES[version]:
        for w in found:
            if w in keywords:
                return name, w
    return "other", ""


def main(out_dir, run_id: str, ticket: str, rules: str, *, fault: str = "",
         sign_with=None) -> None:
    """Record one run into `out_dir`: `ticket` triaged with the classifier's rules version `rules`."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ticket_path = out / "ticket.json"
    ticket_path.write_text(json.dumps({"id": ticket, **TICKETS[ticket]}, sort_keys=True),
                           encoding="utf-8")
    accounts_path = out / "accounts.json"
    accounts_path.write_text(json.dumps(ACCOUNTS, sort_keys=True), encoding="utf-8")

    rec = Recorder(out_dir, run_id=run_id, declared_stages=STAGES, manifest=Path(__file__),
                   policy="fail-closed", declared_edges=APPROVED, sign_with=sign_with,
                   anchor_reason="a demo record; anchoring is not part of this demo")

    def intake(ctx):
        t = load_json_bounded(ctx.read_external(ticket_path, "application/json", name="ticket",
                                                trust_class="operator-authored"), "ticket")
        return ctx.write_json("ticket.json", t)

    def classify(ctx, taken):
        ctx.read_receipt("intake")
        t = ctx.read_json(taken)
        ctx.constant("rules", rules)
        name, word = classify_text(t["text"], rules)
        return ctx.write_json("class.json", {"ticket": t["id"], "class": name, "matched": word})

    def lookup_account(ctx, taken, attempt):
        ctx.read_receipt("intake")
        t = ctx.read_json(taken)
        if attempt:
            ctx.constant("attempt", attempt)
        if attempt == "1":
            raise TimeoutError(LOOKUP_FAULT)
        accounts = load_json_bounded(ctx.read_external(accounts_path, "application/json",
                                                       name="accounts",
                                                       trust_class="operator-authored"), "accounts")
        return ctx.write_json("account.json", {"account": t["account"], **accounts[t["account"]]})

    def draft_reply(ctx, classed, account, looked_up):
        ctx.read_receipt("classify")
        ctx.read_receipt(looked_up)
        c = ctx.read_json(classed)
        a = ctx.read_json(account)
        return ctx.write_json("reply.json", {"ticket": c["ticket"], "class": c["class"],
                                             "plan": a["plan"], "reply": REPLIES[c["class"]]})

    def route(ctx, drafted):
        ctx.read_receipt("draft_reply")
        d = ctx.read_json(drafted)
        return ctx.write_json("route.json", {"ticket": d["ticket"], "queue": QUEUES[d["class"]]})

    taken = rec.run_node("intake", None, Instrument("ticket-intake", "reader", "1.0.0",
                                                    {"source": "ticket.json"}), intake)
    classed = rec.run_node("classify", None, Instrument("keyword-rules", "classifier", "1.0.0",
                                                        {"rules": rules}), classify, taken)
    lookup = Instrument("account-lookup", "reader", "1.0.0", {"source": "accounts.json"})
    if fault == "lookup-once":
        try:
            rec.run_node("lookup_account", "1", lookup, lookup_account, taken, "1")
        except TimeoutError:
            pass  # recorded as an error and kept; the pipeline retries once
        account = rec.run_node("lookup_account", "2", lookup, lookup_account, taken, "2")
        looked_up = "lookup_account#2"
    elif fault:
        raise ValueError(f"no fault {fault!r}")
    else:
        account = rec.run_node("lookup_account", None, lookup, lookup_account, taken, "")
        looked_up = "lookup_account"
    drafted = rec.run_node("draft_reply", None, Instrument("reply-templates", "writer", "1.0.0",
                                                           {"templates": "v1"}),
                           draft_reply, classed, account, looked_up)
    rec.run_node("route", None, Instrument("queue-router", "tool", "1.0.0", {"queues": "v1"}),
                 route, drafted)
    rec.close()
