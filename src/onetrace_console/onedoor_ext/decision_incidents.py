"""Incidents from decisions.

    A deny or a propose raises a derived incident, in the same store and with the
    same rules as the existing derived incidents. It is shown on the Incidents page,
    marked with its source ("onedoor decision"). ... The extension raises no
    incident from anything else.

Reuses `onetrace_console.incidents.Incident` and the Incidents-page rendering
machinery unchanged (`incident_pages.render_incidents`'s `extra_rules`/
`extra_incidents`/`extra_totals` hook) rather than building a parallel page. The
"same rules" is read as: the same SHAPE of rule (an id, a stated source/field/
condition, no severity, a quoted field, an evidence link) and the same machinery
that groups and counts them -- not literally one of the four existing `RULES`
entries, which are all about stored SDK runs and have nothing to say about a
decision export.

NOT BUILT: "a propose later shown resolved shows as resolved, with that link"
--------------------------------------------------------------------------------
Checked against real data, not guessed. The fixture
(`947666e`, see `tests/fixtures/onedoor/PROVENANCE.md`) includes an actual propose,
approved and resumed. Its resumption is exported as two ordinary rows (`exec_intent`
then `exec_result`) under a BRAND NEW `request_id` -- onedoor's own
`docs/decision-ref.md`: "the resumption runs as a fresh decide with its own new
request id." Neither resumption row carries the propose row's `request_id`, `id`, or
its `approval_id` (`1`) in any column; onedoor's `approvals` table does hold that
link (`approvals.audit_id`, set by `guardrail/approvals.py`'s `mark_executed`), but
that table is never part of any export. **This is recorded as a gap owned by
onedoor** (the field is to be added there), not inferred from a
shared `request_id` alone, and not built here.
"""
from __future__ import annotations

from onetrace_console.incidents import Incident, Rule, incident_id
from onetrace_console.onedoor_ext.decisions import DecisionRow, StoredDecisionExport
from onetrace_console.onedoor_ext.policy_pages import all_decisions
from onetrace_console.store import Store

#: The words onedoor itself uses for the two verdicts this rule raises from -- never
#: "allowed" or "authorised", and never a word this extension invented.
_RAISES_FROM = ("denied", "proposed")


def _evidence_for(request_id: str) -> str:
    from onetrace_console.onedoor_ext.policy_pages import _decision_href
    return _decision_href(request_id)


def _raise_from_decisions(store: Store) -> tuple[Incident, ...]:
    out = []
    for d in all_decisions(store):
        #: An incident quotes the row's value, so none is raised from a row
        #: whose value cannot be shown. The incidents pages name that row instead.
        if not d.shown:
            continue
        row = d.representative
        if row.decision not in _RAISES_FROM or d.request_id is None:
            continue
        field_path = f"rows[{d.request_id}].decision"
        out.append(Incident(
            id=incident_id("I-ONEDOOR-DECISION", d.export.key, field_path),
            rule="I-ONEDOOR-DECISION", subject=d.request_id, subject_kind="onedoor decision",
            source_sha=d.export.key, field_path=field_path, quoted=row.decision,
            evidence=_evidence_for(d.request_id)))
    return tuple(out)


#: The rule-table row this extension contributes. `raise_for` is left `None` --
#: incidents.derive()'s loop skips rules whose `raise_for` is `None`, since these
#: incidents are supplied already-made, via `extra_incidents` (they are derived by
#: iterating decision exports, not runs; `derive()`'s own loop only knows how to
#: call a rule with a `StoredRun`). See `incidents.py`'s docstring on that parameter.
RULE = Rule(
    id="I-ONEDOOR-DECISION",
    source="an ingested onedoor decision export",
    field="`decision`",
    condition="the decision recorded for a request is denied or proposed",
    words="onedoor recorded a denied or proposed decision",
    unit="decision",
)


def derive_decision_incidents(store: Store) -> tuple[Incident, ...]:
    return _raise_from_decisions(store)


def couldnt_check_notes(store: Store) -> tuple[str, ...]:
    """Every stored decision row that cannot be checked against its delivery, each as its
    "couldn't check" sentence naming the row. Such a row raises no incident (above), so the
    incidents pages say so rather than simply showing one fewer."""
    from onetrace_console.onedoor_ext.policy_pages import checked_rows
    return tuple(c.couldnt_check for c in checked_rows(store) if c.problem)


def incident_page_args(store: Store) -> dict:
    """What the Incidents page and this rule's list need from the extension: one place, so
    serve.py and the tests build exactly the same pages."""
    return {"extra_rules": (RULE,),
            "extra_incidents": derive_decision_incidents(store),
            "extra_totals": {"decision": len(all_decisions(store))},
            "extra_notes": {RULE.id: couldnt_check_notes(store)}}
