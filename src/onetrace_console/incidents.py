"""Incidents: a record that a stored report says a specific thing. Derived, never judged.

    An incident is a **record that a stored report says a specific thing**. It is raised
    mechanically, by a named rule, from a report that already exists. The console **never**
    decides that something is an incident on its own judgement.

    No severity, no score, no ranking, no "risk". No acknowledge, assign, close or comment
    actions. An incident **never** re-states a verdict in its own words. It quotes the
    report's field, and it links to the report.
                                        -- the work order, and its whole shape

WHAT IS ABSENT, LISTED BECAUSE IT IS THE POINT
----------------------------------------------
There is no severity field, no score, no rank, no ordering by importance, and no action of
any kind. `Incident` carries the rule that raised it, the **quoted words of the report's own
field**, the field's path, and a link to the evidence. Nothing here forms an opinion about
what an incident means, and there is no place to put one.

Incidents are ordered by `(rule id, subject, field path)` — a stable name, not a judgement.
Ordering by anything else would be a ranking with the word filed off.

DERIVED, NOT STORED AS A JUDGEMENT
----------------------------------
`derive()` reads stored reports and produces incidents every time. Nothing is written. A
cache, if one is ever added, must be keyed on `RULE_TABLE_DIGEST` as well as the store's
state, so that changing a rule re-derives and cannot leave a stale incident behind; the
digest is computed from the table itself, below, so it cannot drift from the rules it names.

An incident's id is `sha256(rule id + source sha + field path)`, so the same inputs always
give the same id, and two different field paths under one rule never collide.

I-DIFF-REGRESSION IS NOT BUILT, AND THAT IS NOT A GAP IN THE SDK
----------------------------------------------------------------
The work order makes it conditional: *"Use the SDK's own label; if the SDK has no such
label, leave this rule out."* The SDK has no such label **by design**. Its own spec
addendum, on the instrument-change diff:

    The report names the config that changed; it does not characterize the change as safe,
    a regression, or intentional. That judgment stays with whoever reads it, per every other
    decision this week.

And the closed verdict vocabulary is `same · FIRST DIFFERENCE · downstream · reconverged ·
COULD NOT CHECK` — no regression among them. So building the rule would mean this console
making exactly the judgement the SDK reserves for the reader. Left out, and recorded in
DESIGN_GAPS.md.
"""
from __future__ import annotations

import hashlib
from onetrace_console.bounded_json import load_json_bounded
import json
import sys
from dataclasses import dataclass, field
from typing import Callable

from onetrace_console.checks import COULD_NOT_CHECK
from onetrace_console.ingest import RUN_ID_REUSED
from onetrace_console.store import StoredRun, Store, digest

MANIFEST_NAME = "MANIFEST.json"

#: The flag the store records when a delivery's header contradicts its
#: manifest. Matched as a prefix, because the flag names the field and the two values.
HEADER_DISAGREES_PREFIX = "header "


@dataclass(frozen=True, slots=True)
class Incident:
    """One record that one stored report says one specific thing.

    `quoted` is **the report's own words**, lifted unchanged. `field_path` says where in the
    source they came from, so a reader can go and look. `evidence` is the page that shows the
    source. There is deliberately nothing else.
    """
    id: str
    rule: str
    subject: str            # the run key, or the comparison key for a pair
    subject_kind: str       # "run" | "comparison"
    source_sha: str         # the sha of the source report or immutable source object
    field_path: str
    quoted: str
    evidence: str           # the page that shows the source

    def to_json(self) -> dict:
        return {"id": self.id, "rule": self.rule, "subject": self.subject,
                "subject_kind": self.subject_kind, "source_sha": self.source_sha,
                "field_path": self.field_path, "quoted": self.quoted,
                "evidence": self.evidence}


@dataclass(frozen=True, slots=True)
class Rule:
    """One row of the rule table, and the code that raises it.

    `raise_for` returns zero or more incidents for one run. It is given the store so it can
    read the stored report; it never writes.
    """
    id: str
    source: str             # which stored report, in words
    field: str              # which field of it, in words
    condition: str          # the exact condition, in words
    words: str              # what the page shows above the quoted field
    raise_for: Callable[[StoredRun, Store], list[Incident]] = field(repr=False,
                                                                   default=None)
    #: The word for what `subject` counts -- "run" for every base rule. The onedoor
    #: extension's rules count decisions, not runs, and say so; not part of `row()`
    #: (and so not part of the digest), the same way `raise_for` is excluded -- it is
    #: a rendering detail, not part of what the rule table documents a rule to mean.
    unit: str = "run"

    def row(self) -> str:
        """The table row, as `RULES.md` carries it. The digest is taken over these."""
        return " | ".join((self.id, self.source, self.field, self.condition, self.words))


def incident_id(rule_id: str, source_sha: str, field_path: str) -> str:
    """`sha256(rule + source sha + field path)`, with separators so parts cannot run together.

    The work order: *"An incident's id is deterministic: the rule id plus the sha of the source
    report plus the field path."* Separated by a NUL so that two different splits of the same
    characters cannot produce one id.
    """
    return hashlib.sha256("\0".join((rule_id, source_sha, field_path))
                          .encode("utf-8")).hexdigest()


def _manifest_sha(run: StoredRun) -> str:
    """The run's own manifest object key: immutable, content-addressed, and always present.

    Used as the source sha for the two rules whose source is the **store's flag** rather than
    a report. A flag is recorded about a delivery, and the delivery's manifest is the
    immutable thing it was recorded about — so an incident's id does not move when the run's
    record later gains a verdict.
    """
    for path, key in run.listing:
        if path == MANIFEST_NAME:
            return key
    raise ValueError(f"run {run.run_id} has no {MANIFEST_NAME} in its listing")


#: The field an I-CONTRADICTS incident quotes when the report's rows cannot be read one by one
#: (30bv §3.3): the check's whole output, shown escaped rather than row by row.
WHOLE_OUTPUT = "stdout[whole]"


def _evidence_for_run(run: StoredRun) -> str:
    """The run page's "Proof" view, which shows the check's report: a path from the site's root,
    linked relative to the page that shows the incident (`incident_pages`). It was the free viewer
    file's `execution-<id>.html`, a page the console has never served."""
    return f"runs/{run.key}/proof.html"


# ----------------------------------------------------------------------- the five rules

def _contradicts(run: StoredRun, store: Store) -> list[Incident]:
    """One incident per run whose stored verifier report carries a failing verdict.

    *"listing each contradicting node or receipt as the report names it"* — so the quoted
    text is the report's own `[FAIL   ]` lines, joined, unedited. The console does not
    summarise them and does not say the word "contradicts" in its own voice; that word is in
    the rule's `words` as a label for the rule, and the evidence is the report's lines.
    """
    if run.check_verdict != "contradicts" or not run.check_report:
        return []
    envelope = load_json_bounded(store.get(run.check_report).decode("utf-8"), "the check report")
    #: Rows a record broke apart cannot be quoted row by row -- the row a
    #: record cut at its own CR would be quoted cut short. The whole output is the field then.
    from onetrace_console.viewer.report import ReportUnreadable, parse
    try:
        rows_readable = parse(envelope).rows_readable
    except ReportUnreadable:
        rows_readable = True
    if not rows_readable:
        return [Incident(
            id=incident_id("I-CONTRADICTS", run.check_report, WHOLE_OUTPUT),
            rule="I-CONTRADICTS", subject=run.key, subject_kind="run",
            source_sha=run.check_report, field_path=WHOLE_OUTPUT,
            quoted=envelope.get("stdout", ""), evidence=_evidence_for_run(run))]
    failing = [ln for ln in envelope.get("stdout", "").splitlines()
               if ln.startswith("[FAIL")]
    if not failing:
        #: The record says `contradicts` but its report shows no failing row. That is a
        #: disagreement inside the stored data, and it is NOT quietly turned into an
        #: incident with invented words — nor swallowed. It raises, so somebody looks.
        raise ValueError(
            f"run {run.run_id} is recorded as contradicting but its stored report carries no "
            f"[FAIL] row. An incident must quote the report's own field, and there is "
            f"nothing here to quote.")
    return [Incident(
        id=incident_id("I-CONTRADICTS", run.check_report, "stdout[FAIL]"),
        rule="I-CONTRADICTS", subject=run.key, subject_kind="run",
        source_sha=run.check_report, field_path="stdout[FAIL]",
        quoted="\n".join(failing), evidence=_evidence_for_run(run))]


def _flagged(flag_test, rule_id: str, field_name: str):
    """Build a `raise_for` for a rule whose source is one of the store's flags."""
    def raise_for(run: StoredRun, store: Store) -> list[Incident]:
        out = []
        for flag in run.flags:
            if not flag_test(flag):
                continue
            path = f"flags[{field_name}]"
            out.append(Incident(
                id=incident_id(rule_id, _manifest_sha(run), path),
                rule=rule_id, subject=run.key, subject_kind="run",
                source_sha=_manifest_sha(run), field_path=path,
                quoted=flag, evidence=_evidence_for_run(run)))
        return out
    return raise_for


def _could_not_check(run: StoredRun, store: Store) -> list[Incident]:
    """Every check the runner recorded as not run, **with its stated reason**.

    One stored reason: `check_note`, when the report could not be read. A run's
    `topology_note` is a line on its page, never an incident (see `checks.topology_note`).
    A check recorded as not run with **no** reason raises
    no incident and is reported by the test that counts them, because an incident with
    nothing to quote is the thing this whole slice refuses.
    """
    from onetrace_console.checks import is_preview_not_verified
    if is_preview_not_verified(run):
        #: A stored preview run's NOT VERIFIED is a known, permanent state,
        #: not an event someone must act on. Any other could-not-check still raises.
        return []
    out = []
    sources = (("check_note", run.check_note, run.check_report or _manifest_sha(run)),)
    for name, note, source in sources:
        if not note:
            continue
        path = f"{name}"
        out.append(Incident(
            id=incident_id("I-COULD-NOT-CHECK", source, path),
            rule="I-COULD-NOT-CHECK", subject=run.key, subject_kind="run",
            source_sha=source, field_path=path, quoted=note,
            evidence=_evidence_for_run(run)))
    if run.check_verdict == COULD_NOT_CHECK and not out:
        raise ValueError(
            f"run {run.run_id} is recorded as `{COULD_NOT_CHECK}` with no stated reason, so "
            f"there is nothing for an incident to quote. A reason is required at the point "
            f"the check runner records the outcome, not invented here.")
    return out


def _head_shared(run: StoredRun, store: Store) -> list[Incident]:
    """One incident per other folder carrying the same run and chain head as this run's folder
    whose files differ from this one's (`twins`). Its source is the store's own records of the two
    deliveries, so it quotes the rule's sentence naming both folders, and the field path names this
    run's folder so the two folders' incidents never share an id."""
    from onetrace_console.twins import differ_said, folder_named, twins
    out = []
    for other, same in twins(run, store):
        if same:
            continue
        path = f"folder[{folder_named(run)}|{folder_named(other)}]"
        out.append(Incident(
            id=incident_id("I-HEAD-SHARED", _manifest_sha(run), path),
            rule="I-HEAD-SHARED", subject=run.key, subject_kind="run",
            source_sha=_manifest_sha(run), field_path=path,
            quoted=differ_said(run, other), evidence=_evidence_for_run(run)))
    return out


#: The table. **This tuple is the rule table**: `RULES.md` documents it and
#: `RULE_TABLE_DIGEST` is taken over it, so a rule cannot change without the digest moving.
RULES: tuple[Rule, ...] = (
    Rule(id="I-CONTRADICTS",
         source="the run's stored verifier report (`check_report`)",
         field="`stdout`, its `[FAIL   ]` rows, or all of it where the rows cannot be read "
               "line by line",
         condition="the run's recorded verdict is `contradicts`",
         words="the verifier's report carries a failing row",
         raise_for=_contradicts),
    Rule(id="I-RUNID-REUSED",
         source="the run's own record, as the store wrote it",
         field="`flags`, the `run_id reused` entry",
         condition=f"the store flagged `{RUN_ID_REUSED!r}` at ingest",
         words="two chains arrived under one run name",
         raise_for=_flagged(lambda f: f == RUN_ID_REUSED, "I-RUNID-REUSED",
                            RUN_ID_REUSED)),
    Rule(id="I-HEADER-DISAGREES",
         source="the run's own record, as the store wrote it",
         field="`flags`, the header entry",
         condition="the store flagged that a delivery header disagrees with the manifest",
         words="the delivery's header contradicted its own manifest",
         raise_for=_flagged(lambda f: f.startswith(HEADER_DISAGREES_PREFIX),
                            "I-HEADER-DISAGREES", "header")),
    Rule(id="I-COULD-NOT-CHECK",
         source="the check runner's record on the run",
         field="`check_note` and `topology_note`",
         condition="the runner recorded a check it did not run, with a stated reason",
         words="a check was not run, and the record says why",
         raise_for=_could_not_check),
    Rule(id="I-HEAD-SHARED",
         source="the store's records of two run folders",
         field="each folder's listing of its files and their object keys",
         condition="two run folders carry the same run and chain head, and their files differ",
         words="Two folders share a chain head but their contents differ",
         raise_for=_head_shared),
)

#: Left out deliberately; see this module's docstring and DESIGN_GAPS.md.
NOT_BUILT: tuple[str, ...] = ("I-DIFF-REGRESSION",)


def rule_table_digest(rules: tuple[Rule, ...] = RULES) -> str:
    """A digest over the table as built, so a cache key can include it.

    Taken over the rows' own text — id, source, field, condition and words — because those
    are what a reader of `RULES.md` is told. A change to a rule's condition moves this digest;
    a change to a comment does not. Takes an explicit `rules` so the onedoor extension can
    show a digest over ITS merged table (the base rules plus its own) without this module's own
    `RULE_TABLE_DIGEST` constant -- computed over the base `RULES` alone -- ever moving.
    """
    body = "\n".join(rule.row() for rule in rules) + "\n"
    return digest(body.encode("utf-8"))


RULE_TABLE_DIGEST = rule_table_digest()


def derive(store: Store, rules: tuple[Rule, ...] = RULES,
           extra_incidents: tuple[Incident, ...] = ()) -> tuple[Incident, ...]:
    """Every incident the rules raise from what is stored. Reads only; writes nothing.

    `extra_incidents` is the hook for the onedoor extension: incidents already
    derived elsewhere (from decision exports, not runs), folded in here so a single
    call still produces one sorted, complete list. A rule with no `raise_for` (the
    extension's own rule stubs, carried only for their id/words/condition so the
    grouping and page-rendering helpers below can label a group) is skipped rather
    than called -- it contributed nothing through this loop; its incidents arrived
    already-made, via `extra_incidents`.

    Ordered by `(rule id, subject, field path)` — a stable name. Sorting by anything that
    looked like importance would be a ranking, which this slice does not have.
    """
    out: list[Incident] = list(extra_incidents)
    failed: list[str] = []
    for run in store.runs():
        for rule in rules:
            if rule.raise_for is None:
                continue
            try:
                out.extend(rule.raise_for(run, store))
            except Exception as e:  # noqa: BLE001 - named on the pages that count, and logged
                #: A stored object this run's rule reads has gone or moved (the third
                #: confirmation review, NEW-6), or the stored data disagrees with itself in a
                #: way a rule refuses to quote -- a `contradicts` with no failing row: it blanked
                #: Home, the Incidents page and every other run's pages. Named on
                #: those pages, and the other runs' incidents still derived.
                said = f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"
                failed.append(f"{run.run_id} ({run.key[:12]}): rule {rule.id}: {said}")
                print(f"incidents: rule {rule.id} skipped run {run.key}: {said}",
                      file=sys.stderr)
    store.underived = tuple(failed)
    return tuple(sorted(out, key=lambda i: (i.rule, i.subject, i.field_path)))


def by_rule(incidents: tuple[Incident, ...],
            rules: tuple[Rule, ...] = RULES) -> dict[str, tuple[Incident, ...]]:
    """Grouped by rule, **every rule present** including the ones that raised nothing.

    A rule with no incidents is shown as `0 of N`, not omitted. An absent group would let a
    reader think the rule does not exist: an absence is said, never left blank.
    """
    grouped = {rule.id: tuple(i for i in incidents if i.rule == rule.id) for rule in rules}
    return grouped


def as_json(incidents: tuple[Incident, ...]) -> str:
    """Canonical output, for the determinism check: sorted keys, one shape, trailing newline."""
    return json.dumps([i.to_json() for i in incidents], indent=1, sort_keys=True,
                      ensure_ascii=False) + "\n"
