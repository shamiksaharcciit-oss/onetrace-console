"""The "Decisions cited" panel, its join corrected to choose a row by digest (below).

Tested on **synthetic** receipts (`tests/fixtures/synthetic_receipts/`), because the
SDK does not emit `decision_refs` yet -- so there is no live page to splice this onto
today. `join_stage`/`render_panel`/`citation_incidents` are complete and tested
against the specified `decision_refs` shape; wiring a real run's receipts through them is a
later order's work, once the SDK actually produces `decision_refs` and
`gated_stages` (out of scope here: both come from the SDK after 0.1.1).

THE JOIN: request_id CAN NAME MORE THAN ONE ROW -- CHOOSE BY DIGEST, NEVER BY
KIND OR POSITION
--------------------------------------------------------------------------------
The first version of this join picked one "representative" row per `request_id`
(onedoor's own `exec_result` > `exec_intent` > `decision` precedence, still used
by the Policy page's list view for a different purpose) and compared the
reference's digest against only that row. That was wrong: a
`request_id` can legitimately name more than one row with DIFFERENT digests (the
adversarial case onedoor's own `tests/test_decision_ref_checker.py` tests
directly, and the real, unadversarial case this extension's own fixture
demonstrates -- `ActionResult.decision_ref`'s docstring: a permit reference names
the `exec_intent` row, not the `exec_result` row it executed as). The rule:
*"Join on `request_id`, then choose the row whose digest equals the
reference's `decision_digest`... Never choose a row by kind or by position."*

So the join now searches every row sharing a `request_id` for the one whose
`decision_digest` matches the reference's, and shows THAT row's own `decision`
word -- never a "representative" row chosen by kind, never the first one found.
`request_id` matching rows, none by digest: state 2. `request_id` matching none
at all: state 3.

THE VERDICT WORD, SETTLED (WAS FLAGGED)
------------------------------------------
The first version of this module flagged that nothing mapped onedoor's own
`Decision` enum to the panel's `permit/deny/propose` vocabulary. That is settled
**on onedoor's own side**: `decision_ref.verdict` is computed by onedoor
itself at decide time (`docs/decision-ref.md`'s verdict-mapping table), already
in that vocabulary, never guessed at here. This module still shows the matched
EXPORT ROW's own `decision` column (`executed`/`denied`/`proposed`/...), not the
reference's `verdict` field, because the join's job is to prove the reference
names an unaltered row -- once it does, showing that row's own recorded word is
the more direct claim, and remains true even for a citation built by hand (this
module's own synthetic-receipt tests) rather than by onedoor itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from onetrace_console.words import escape

from onetrace_console.incidents import Incident, Rule, incident_id
from onetrace_console.onedoor_ext.policy_pages import Decision, all_decisions, checked_rows
from onetrace_console.store import Store

STATE_MATCH = "matches"
STATE_MISMATCH = "mismatch"
STATE_UNKNOWN = "unknown"
STATE_MISSING = "missing"       # gated, no ref
STATE_NONE = "none"             # neither cited nor gated -- shows nothing
#: The cited row, or a row it could be, cannot be checked against its
#: delivery. Never reported as "unknown", and never as "matches".
STATE_COULDNT_CHECK = "couldnt-check"

#: Printed on the panel in plain words, per the specification's own requirement.
LIMIT_SENTENCE = ("A citation shows that the run names an existing, unaltered "
                 "decision. It does not show that every action was gated.")

PANEL_TITLE = "Decisions cited"


@dataclass(frozen=True, slots=True)
class StageCitation:
    stage: str
    state: str
    request_id: str | None = None
    verdict: str | None = None        # onedoor's own row word; STATE_MATCH only
    reason: str | None = None         # STATE_COULDNT_CHECK only: the sentence naming the row


def _decisions_by_request_id(store: Store) -> dict[str, Decision]:
    """`request_id -> its Decision`, every row that shares it across every ingested export,
    read from the delivery. A `request_id` may legitimately map to more than one row
    -- this is the thing a citation is searched against, never a single
    "representative" chosen ahead of time.
    """
    return {d.request_id: d for d in all_decisions(store) if d.request_id is not None}


def join_stage(stage: str, ref: dict | None, gated: bool, store: Store,
              *, _trust_receipt_verdict: bool = False,
              _pick_first_row: bool = False) -> StageCitation:
    """One stage's state, one of the five, its row chosen by digest (see the module docstring).

    `_trust_receipt_verdict` exists only for the sabotage test named in step 5's own
    check: set true, the join accepts `ref["verdict"]` on its own word, without ever
    looking at the ingested export -- which must make states 2 (mismatch) and 3
    (unknown) impossible to reach, exactly what that sabotage is required to prove.

    `_pick_first_row` exists only for the sabotage of that digest join: set
    true, the join picks whichever row happens to come first for a `request_id`
    without ever comparing its digest -- which must make a reference correctly
    naming the SECOND of two same-`request_id` rows read as a false match.
    """
    if ref is None:
        return StageCitation(stage, STATE_MISSING if gated else STATE_NONE)

    request_id = ref.get("request_id")
    if _trust_receipt_verdict:
        return StageCitation(stage, STATE_MATCH, request_id, ref.get("verdict"))

    #: A delivery that cannot be read leaves rows with no trustworthy request id, and the
    #: cited row may be among them: neither "not in any ingested export" nor "does not match"
    #: can then be shown.
    unreadable = next((c for c in checked_rows(store) if c.delivered is None), None)
    d = _decisions_by_request_id(store).get(request_id)
    if d is None:
        if unreadable is not None:
            return StageCitation(stage, STATE_COULDNT_CHECK, request_id,
                                 reason=unreadable.couldnt_check)
        return StageCitation(stage, STATE_UNKNOWN, request_id)

    if _pick_first_row:
        matched = d.rows[0]
    else:
        wanted = ref.get("decision_digest")
        matched = next((r for r in d.rows if r.decision_digest == wanted), None)

    if matched is not None:
        problem = d.couldnt_check(matched)
        if problem is not None:
            return StageCitation(stage, STATE_COULDNT_CHECK, request_id, reason=problem)
        return StageCitation(stage, STATE_MATCH, request_id, matched.decision)
    #: No delivered row carries the cited digest. A mismatch is a claim that the cited
    #: record differs from what was delivered; it cannot be made while a row of this
    #: request cannot itself be checked.
    unchecked = next((p for p in (d.couldnt_check(r) for r in d.rows) if p), None)
    if unchecked is not None:
        return StageCitation(stage, STATE_COULDNT_CHECK, request_id, reason=unchecked)
    if unreadable is not None:
        return StageCitation(stage, STATE_COULDNT_CHECK, request_id,
                             reason=unreadable.couldnt_check)
    return StageCitation(stage, STATE_MISMATCH, request_id)


def join_run(stages: list[dict], store: Store,
            *, _trust_receipt_verdict: bool = False) -> tuple[StageCitation, ...]:
    """`stages` is the synthetic-receipt shape: `[{"stage", "gated", "decision_ref"}]`."""
    return tuple(
        join_stage(s["stage"], s.get("decision_ref"), bool(s.get("gated", False)), store,
                  _trust_receipt_verdict=_trust_receipt_verdict)
        for s in stages)


def _state_sentence(c: StageCitation) -> str | None:
    if c.state == STATE_MATCH:
        return f"cites decision {c.request_id} · {c.verdict} · matches export"
    if c.state == STATE_MISMATCH:
        return "cited decision does not match the export"
    if c.state == STATE_UNKNOWN:
        return "cited decision not in any ingested export"
    if c.state == STATE_COULDNT_CHECK:
        return c.reason or "couldn't check"
    if c.state == STATE_MISSING:
        return "no decision cited"
    return None                                            # STATE_NONE: shows nothing


def render_panel(citations: tuple[StageCitation, ...]) -> str:
    """The panel: one line per stage that has something to say, in the specification's own
    five states, plus the limit sentence in plain words. The words "allowed" and
    "authorised" appear nowhere here -- checked directly by this module's own tests.
    """
    items = []
    for c in citations:
        sentence = _state_sentence(c)
        if sentence is None:
            continue
        items.append(
            f'<li data-stage="{escape(c.stage, quote=True)}" '
            f'data-state="{escape(c.state, quote=True)}">'
            f"<strong>{escape(c.stage)}</strong>: {escape(sentence)}</li>")
    return (
        f'<section data-section="decisions-cited"><h2>{escape(PANEL_TITLE)}</h2>'
        f'<ul class="plain">{"".join(items)}</ul>'
        f'<p class="limit" data-section="citation-limit">{escape(LIMIT_SENTENCE)}</p>'
        "</section>")


# ------------------------------------------------------------------- incidents

#: State 2 and state 4 each raise an incident (the specification's own words). `raise_for`
#: is left `None` for the same reason `decision_incidents.RULE` leaves it `None`:
#: these incidents are supplied already-made, via `derive()`'s `extra_incidents`,
#: because they come from a run's synthetic receipts, not from iterating `StoredRun`.
MISMATCH_RULE = Rule(
    id="I-ONEDOOR-CITATION-MISMATCH",
    source="a run's decision_refs (synthetic receipt)",
    field="`decision_digest`",
    condition="a cited decision's digest disagrees with the ingested export",
    words="a cited decision does not match what was ingested",
    unit="stage",
)

MISSING_RULE = Rule(
    id="I-ONEDOOR-CITATION-MISSING",
    source="a run's decision_refs (synthetic receipt)",
    field="`decision_ref`",
    condition="a stage the run declared gated cites no decision",
    words="a gated stage cites no decision",
    unit="stage",
)


def citation_incidents(run_key: str, citations: tuple[StageCitation, ...]) -> tuple[Incident, ...]:
    out = []
    for c in citations:
        if c.state == STATE_MISMATCH:
            path = f"stages[{c.stage}].decision_ref.decision_digest"
            out.append(Incident(
                id=incident_id(MISMATCH_RULE.id, run_key, path),
                rule=MISMATCH_RULE.id, subject=f"{run_key}:{c.stage}",
                subject_kind="stage", source_sha=run_key, field_path=path,
                quoted=f"stage {c.stage!r} cites request_id {c.request_id!r}",
                evidence=f"runs/{run_key}/case.html"))
        elif c.state == STATE_MISSING:
            path = f"stages[{c.stage}].decision_ref"
            out.append(Incident(
                id=incident_id(MISSING_RULE.id, run_key, path),
                rule=MISSING_RULE.id, subject=f"{run_key}:{c.stage}",
                subject_kind="stage", source_sha=run_key, field_path=path,
                quoted=f"stage {c.stage!r} is gated and cites nothing",
                evidence=f"runs/{run_key}/case.html"))
    return tuple(out)
