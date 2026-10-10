"""Home's counts: every number with its denominator, and the exact runs it counted.

    Counts only, each with its denominator. Every count has a link that opens the
    Executions list filtered to exactly the runs it counted. It shows no score, no trend
    arrow, no "health" and no recommendation. An "insight" may only be a count.

WHY A TALLY CARRIES ITS RUNS AND NOT JUST A NUMBER
--------------------------------------------------
Because the check the order asks for is that *every number on Home equals the size of the
filtered list its link opens*. If a count were computed one way and the filtered list
another, that check would be comparing two implementations and would pass whenever they
were wrong together. So a `Tally` **is** its runs: the number is `len(tally.runs)` and the
page it links to renders `tally.runs`. There is one source and the count cannot disagree
with the list.

DENOMINATORS
------------
Every tally's denominator is the number of runs stored, which is the population each count
was taken from. A count without it invites a reader to supply their own, and the one they
supply is usually the one that flatters.

NO SCORE, AND WHERE THAT BITES
------------------------------
There is deliberately no percentage anywhere here, not even one beside its counts, which
the design note's prohibitions would allow. Two counts and a denominator say everything a
percentage would, and a percentage is the shape a score arrives in. `MOST_RECENT` is a
list and not a ranking: it is ordered by arrival, which is a fact about the delivery
rather than a judgement about the run.
"""
from __future__ import annotations

import json
from onetrace_console.bounded_json import load_json_bounded
from dataclasses import dataclass

from onetrace_console.checks import CONTRADICTS, COULD_NOT_CHECK, HOLDS
from onetrace_console.ingest import RUN_ID_REUSED
from onetrace_console.store import StoredRun, Store
from onetrace_console.words import NO_VERDICT, VERDICT_WORDS

#: How many of the most recent runs Home lists. A list, not a ranking.
MOST_RECENT = 5

#: The verdict states a stored run can be in, plus the one for a run the check runner has
#: not reached. Closed, and each with the sentence Home shows.
NOT_CHECKED = "not checked"

#: **The recorded value, named as a field, and never a summary of it.**
#:
#: These were "the trail holds", "the trail contradicts itself" and so on — this channel's
#: own paraphrases. The review asked whether they were quoted from fixed viewer wording with a
#: nameable source; they were not. Measured: nothing in `viewer/sentences.py` says "the trail
#: holds", and the viewer's own fixed sentence is *"trail was checked on {date} — every step
#: checks out"*, which is a different claim about a different thing.
#:
#: So the label is the verdict itself, in the console's plain words for it (`words.VERDICT_WORDS`):
#: one word for each value of the design note's closed set, never a paraphrase of what it means.
#:
#: The fourth is an absence the design note's closed set does not cover — a run the check
#: runner has not reached. It states the record's condition and interprets nothing (an
#: absence sentence, never a blank).
VERDICT_LABELS: dict[str, str] = {
    HOLDS: VERDICT_WORDS[HOLDS],
    CONTRADICTS: VERDICT_WORDS[CONTRADICTS],
    COULD_NOT_CHECK: VERDICT_WORDS[COULD_NOT_CHECK],
    NOT_CHECKED: NO_VERDICT,
}


@dataclass(frozen=True, slots=True)
class Tally:
    """One count, its denominator, and the runs it counted.

    `slug` names the Executions page this tally links to. `reasons` carries the distinct
    reasons behind a count where the count alone would be useless -- "could not be checked:
    4" tells a reader nothing they can act on.
    """
    slug: str
    label: str
    runs: tuple[StoredRun, ...]
    denominator: int
    reasons: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        """The number IS the length of the list. There is no second source to disagree."""
        return len(self.runs)

    @property
    def sentence(self) -> str:
        """`3 runs of 12 — the trail holds`. A count, its denominator, its unit, and what it counted.

        The unit is written out, as it is in the Incidents page's groups, and for the same
        reason: `3 of 12` leaves a reader to supply the noun, and the one they supply is the one
        they were already thinking of.
        """
        unit = "run" if self.count == 1 else "runs"
        return f"{self.count} {unit} of {self.denominator} — {self.label}"

    #: Where this tally's link points, when it is not an Executions page. Incident tallies
    #: link to their rule's own list; run tallies link to a filtered Executions page.
    href_override: str = ""

    @property
    def href(self) -> str:
        return self.href_override or f"executions-{self.slug}.html"


def verdict_of(run: StoredRun) -> str:
    """The run's verdict state, or `not checked` when the runner has not reached it.

    An empty `check_verdict` is not silently folded into any of the three real states. A run
    nobody has checked is its own thing, and calling it anything else would be inventing a
    verdict -- which is the one thing this console must never do.
    """
    return run.check_verdict or NOT_CHECKED


def _envelope(run: StoredRun, store: Store) -> dict | None:
    if not run.check_report:
        return None
    from onetrace_console.store import StoreError
    try:
        envelope = load_json_bounded(store.get(run.check_report).decode("utf-8"), "the check report")
    except (ValueError, UnicodeDecodeError, StoreError, RecursionError):
        return None
    return envelope if isinstance(envelope, dict) else None


def outputs_required_exit(run: StoredRun, store: Store) -> str | None:
    """The exit status of the run's check run again with its output files required (made only
    where the run holds `artifacts/`), or None where it was not made."""
    envelope = _envelope(run, store)
    part = envelope.get("outputs_required") if envelope else None
    exit_status = part.get("exit_status") if isinstance(part, dict) else None
    return exit_status if isinstance(exit_status, str) else None


def artifacts_required(run: StoredRun, store: Store) -> bool:
    """Whether the run's stored check is evidence that its records agree:
    its outputs-required run passed, or -- a report from before that -- the check itself
    was run with `--require-artifacts`."""
    if outputs_required_exit(run, store) == "0":
        return True
    envelope = _envelope(run, store)
    command = envelope.get("command") if envelope else None
    return isinstance(command, list) and "--require-artifacts" in command


#: The Overview's anchoring forms, in their fixed order and words: the stored reading
#: (`StoredRun.anchored`), and what the row says of it.
ANCHOR_FORMS = (("yes", "yes"), ("couldnt-check", "couldn't check"),
                ("failed", "the check failed"), ("not-anchored", "not anchored"))
#: The Overview's signing forms, in their fixed order and words: (slug, the stored
#: readings it counts, what the row says). Not checked is every run its page reads Not checked --
#: the extra wanted, or no own check -- as the page's rung does.
SIGNATURE_FORMS = (("yes", ("yes",), "yes"), ("untrusted", ("untrusted",), "key not trusted"),
                   ("failed", ("failed",), "the check failed"),
                   ("unsigned", ("unsigned",), "unsigned"),
                   ("couldnt-check", ("couldnt-check", "unreadable"), "couldn't check"),
                   ("not-checked", ("not-installed", ""), "not checked"))


def tallies(store: Store) -> tuple[Tally, ...]:
    """Every count Home shows, in the order it shows them.

    Built from one pass over the stored runs. Each tally holds the runs it counted, so the
    page and the number cannot drift apart.
    """
    runs = store.runs()
    total = len(runs)
    out: list[Tally] = [
        Tally(slug="all", label="runs stored", runs=runs, denominator=total),
    ]

    for state, label in VERDICT_LABELS.items():
        matched = tuple(r for r in runs if verdict_of(r) == state)
        reasons = ()
        if state == COULD_NOT_CHECK:
            #: The reason, because the count alone is not actionable. Distinct reasons only,
            #: in first-seen order, and never summarised into one.
            seen: list[str] = []
            for r in matched:
                note = r.check_note or "no reason was recorded"
                if note not in seen:
                    seen.append(note)
            reasons = tuple(seen)
        out.append(Tally(slug=state.replace(" ", "-").replace("_", "-"), label=label,
                         runs=matched, denominator=total, reasons=reasons))

    #: The Overview's "Records agree" (board 1), the run page's rung 1 counted across runs: a
    #: check that held, run with the run's output files required. The confirmation review found
    #: the count read from the verdict alone, as rung 1 did.
    out.append(Tally(slug="records-agree",
                     label="whose records agree: the check held, with the run's output files "
                           "present",
                     runs=tuple(r for r in runs if verdict_of(r) == HOLDS
                                and artifacts_required(r, store)),
                     denominator=total))
    out.append(Tally(slug="run-id-reused", label="whose run id was already used by a stored run",
                     runs=tuple(r for r in runs if RUN_ID_REUSED in r.flags),
                     denominator=total))

    #: The most recent, as a list. `store.runs()` is newest delivery first.
    out.append(Tally(slug="most-recent", label=f"most recent {MOST_RECENT} by arrival",
                     runs=runs[:MOST_RECENT], denominator=total))

    #: The Overview's counts. Tallies like the rest, so each opens exactly the
    #: runs it counted and states its denominator. See `onetrace_console.overview` for what
    #: "pipeline" and "baseline" can mean in a store whose records name neither.
    from onetrace_console.overview import (NOTHING_MISSING, missing_a_declared_stage,
                                           needs_attention, nothing_missing_not_established,
                                           pipelines, vs_baseline)
    out.append(Tally(slug="changed-vs-baseline",
                     label="changed vs baseline, each the candidate of a stored comparison "
                           "that found a first difference",
                     runs=tuple(r for r in runs if vs_baseline(r, store)[0] == "changed"),
                     denominator=total))
    out.append(Tally(slug="needs-attention",
                     label="needing attention first, in the order stated on the Overview",
                     runs=tuple(r for _, r in needs_attention(store)), denominator=total))
    #: Rung 3 across runs, as each run's own page decides it: no declared stage
    #: missing, one missing, or neither established -- three counts, and each opens its runs.
    out.append(Tally(slug="nothing-missing",
                     label="with no declared stage missing, as each run's own page says",
                     runs=tuple(r for r in runs if r.nothing_missing == NOTHING_MISSING),
                     denominator=total))
    out.append(Tally(slug="missing-a-declared-stage", label="missing a declared stage",
                     runs=tuple(r for r in runs if missing_a_declared_stage(r)),
                     denominator=total))
    out.append(Tally(slug="missing-not-established",
                     label="whose declared stages could not be established as all recorded",
                     runs=tuple(r for r in runs if nothing_missing_not_established(r)),
                     denominator=total))
    #: "Committed by a known time?" across runs, as each run's own page reads its own check
    #: Each form, and the runs without that check, over all runs
    #: stored like every other count. Each count opens exactly the runs it counted.
    for reading, words in ANCHOR_FORMS:
        out.append(Tally(slug=f"anchored-{reading}",
                         label=f"committed by a known time: {words}, as each run's own page says",
                         runs=tuple(r for r in runs if r.anchored == reading),
                         denominator=total))
    out.append(Tally(slug="anchored-not-checked",
                     label="committed by a known time: not checked, with no check of this "
                           "console's whose rows the run's page reads",
                     runs=tuple(r for r in runs if not r.anchored), denominator=total))
    #: "Signed by a known recorder?" across runs: each form over all runs
    #: stored, as each run's own page reads it; each count opens exactly the runs it counted.
    for slug, readings, words in SIGNATURE_FORMS:
        out.append(Tally(slug=f"signed-{slug}",
                         label=f"signed by a known recorder: {words}, as each run's own page says",
                         runs=tuple(r for r in runs if r.signed in readings), denominator=total))
    for p in pipelines(store):
        out.append(Tally(slug=f"pipeline-{p.label.lower()}",
                         label=f"declaring {p.label}'s stages", runs=p.runs, denominator=total))
    return tuple(out)


def incident_tallies(store: Store) -> tuple[Tally, ...]:
    """One tally per incident rule, in the rule table's order, including empty ones.

    *"Home gets one count per rule, each linking to exactly that rule's list."*

    A tally's `runs` are the runs the rule touched, so `count` is a count of RUNS and its
    denominator is the runs stored — the shape the order's own example uses ("3 of 41 runs").
    `incidents` carries how many incidents those runs raised, because one run can trip a rule
    twice and a page showing only the run count would be linking to a longer list than it
    named. Both numbers are checked against the page they link to.

    Every rule appears even when it raised nothing: an omitted group would let a reader
    conclude the rule does not exist.
    """
    from onetrace_console.incident_pages import rule_href
    from onetrace_console.incidents import RULES, by_rule, derive

    runs = store.runs()
    every = derive(store)
    grouped = by_rule(every)
    out: list[Tally] = []
    for rule in RULES:
        mine = grouped[rule.id]
        subjects = {i.subject for i in mine}
        touched = tuple(r for r in runs if r.key in subjects)
        #: The incident count carries a denominator in its own unit, every
        #: incident the rules raised from the stored runs (all core incidents are per run).
        word = "incident" if len(mine) == 1 else "incidents"
        out.append(Tally(slug=rule.id.lower(), label=f"runs raising {rule.id}",
                         runs=touched, denominator=len(runs),
                         reasons=tuple(f"{len(mine)} {word} of {len(every)} raised from "
                                       f"stored runs" for _ in (0,) if mine),
                         href_override=rule_href(rule.id)))
    return tuple(out)
