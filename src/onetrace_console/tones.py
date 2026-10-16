"""The colour of a state, by one rule on every page: colour says what kind of answer it is, not how
bad it sounds.

    a check ran and held                              green  (ok)
    a check ran and failed                            red    (bad)
    a check couldn't be done, or wasn't done          amber  (cc)
    the evidence wasn't made, by choice or by design  neutral (neu)
    a step declined by its own rule, and the run       blue outline (dec)
    stopped there

Every state the console can show is placed in one of those five kinds, here and nowhere else, and
its chip takes that kind's tone. Every chip keeps its words: colour never carries a state alone.
tests/test_tones.py holds each table below to the rule, and the pages to the tables.
"""
from __future__ import annotations

HELD, FAILED, NOT_DONE, NOT_MADE = "held", "failed", "not-done", "not-made"
#: A step's own rule declined and the run stopped there (the declined-runs work order): never red --
#: the check ran, and a rule refused.
DECLINED = "declined"
#: A comparison's first difference and a step changed after it: a comparison's findings, never a
#: check's result, drawn amber (filled, and outlined) as the visual target draws them.
FIRST_DIFFERENCE, CHANGED_AFTER = "first-difference", "changed-after"

#: The kinds and their tones: the skin's four chip pairs, and the declined outline
#: (`frame.CHIP_CSS`).
TONE = {HELD: "ok", FAILED: "bad", NOT_DONE: "cc", NOT_MADE: "neu", DECLINED: "dec",
        FIRST_DIFFERENCE: "fd", CHANGED_AFTER: "ca"}

#: A run stopped by a step: its chip on the run header and in the runs list.
STOPPED = {"declined": DECLINED}

#: A run ladder's rung, or a stage page's badge, by the state it shows (`data-state`).
RUNG = {
    "yes": HELD,
    #: "No" is only ever a check that ran and failed: the records contradict themselves, a
    #: signature or an anchor that fails, a declared stage missing, a re-run that differs, a run
    #: that departs from its approved plan.
    "no": FAILED,
    "couldnt-check": NOT_DONE,
    "does-not-verify": NOT_DONE,       # "Ran as approved": the run doesn't verify, so not read
    "not-checked": NOT_DONE,
    "no-verdict": NOT_DONE,            # "Records agree" for a run the check has not reached
    "signed-untrusted": NOT_DONE,      # a valid signature, its key not on the trust list
    "unsigned": NOT_MADE,
    "not-anchored": NOT_MADE,
    "not-declared": NOT_MADE,          # no approved plan
    "not-a-graph-run": NOT_MADE,
    "no-records": NOT_MADE,
    "not-yet-available": NOT_MADE,
    #: Rung 3 where the run stopped at a step's own rule: the steps after it were not reached.
    "not-reached": DECLINED,
}

#: The Overview's "Needs attention first" reasons.
ATTENTION = {
    "contradicts": FAILED,
    "missing-stage": FAILED,           # the check found a declared stage with no receipt
    "couldnt-check": NOT_DONE,
    "not-checked": NOT_DONE,
    "no-verdict": NOT_DONE,
    #: A stage's last attempt raised an error, which the record keeps; no check failed. Amber,
    #: as the boards draw it: the run did not finish what it declared, and nothing here says why.
    "last-attempt-failed": NOT_DONE,
    "stopped-at-a-step": DECLINED,     # a step's own rule declined; the steps after it not reached
    "changed": NOT_MADE,               # a change is not a fault, and no check failed
}

#: A run against its baseline (the Overview's "Vs baseline").
BASELINE = {"same": HELD, "changed": NOT_MADE, "couldnt-check": NOT_DONE, "not-compared": NOT_MADE}

#: An incident's rule, by what raised it: a check that ran and failed is red; a check that couldn't
#: be done is amber; a fact the store recorded (a run id used twice) is neutral.
INCIDENT = {"I-CONTRADICTS": FAILED, "I-HEADER-DISAGREES": FAILED, "I-COULD-NOT-CHECK": NOT_DONE,
            "I-RUNID-REUSED": NOT_MADE}


#: A stage's verdict in a comparison of two runs (the Compare page's graph). A first difference
#: is the comparison's finding, amber filled; "changed after it" a change, not a fault, amber
#: outlined; "same" green; a stage the comparison couldn't check amber.
DIFF = {"same": HELD, "reconverged": HELD, "FIRST DIFFERENCE": FIRST_DIFFERENCE,
        "downstream": CHANGED_AFTER, "COULD NOT CHECK": NOT_DONE}


def tone(table: dict[str, str], state: str) -> str:
    """The tone of `state` in `table`; a state the table doesn't place is neutral, never a verdict."""
    return TONE[table.get(state, NOT_MADE)]
