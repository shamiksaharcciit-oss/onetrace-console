"""The colour of a state, by one rule on every page: colour says what kind of answer it is, not how
bad it sounds.

    a check ran and held                              green  (ok)
    a check ran and failed                            red    (bad)
    a check couldn't be done, or wasn't done          amber  (cc)
    the evidence wasn't made, by choice or by design  neutral (neu)

Every state the console can show is placed in one of those four kinds, here and nowhere else, and
its chip takes that kind's tone. Every chip keeps its words: colour never carries a state alone.
tests/test_tones.py holds each table below to the rule, and the pages to the tables.
"""
from __future__ import annotations

HELD, FAILED, NOT_DONE, NOT_MADE = "held", "failed", "not-done", "not-made"

#: The four kinds and their tones: the skin's four chip pairs (`frame.CHIP_CSS`).
TONE = {HELD: "ok", FAILED: "bad", NOT_DONE: "cc", NOT_MADE: "neu"}

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
    "signed-untrusted": NOT_DONE,      # a valid signature, its key not on the trust list
    "unsigned": NOT_MADE,
    "not-anchored": NOT_MADE,
    "not-declared": NOT_MADE,          # no approved plan
    "not-a-graph-run": NOT_MADE,
    "no-records": NOT_MADE,
    "not-yet-available": NOT_MADE,
}

#: The Overview's "Needs attention first" reasons.
ATTENTION = {
    "contradicts": FAILED,
    "missing-stage": FAILED,           # the check found a declared stage with no receipt
    "couldnt-check": NOT_DONE,
    "not-checked": NOT_DONE,
    #: A stage's last attempt raised an error, which the record keeps; no check failed. Amber,
    #: as the boards draw it: the run did not finish what it declared, and nothing here says why.
    "last-attempt-failed": NOT_DONE,
    "changed": NOT_MADE,               # a change is not a fault, and no check failed
}

#: A run against its baseline (the Overview's "Vs baseline").
BASELINE = {"same": HELD, "changed": NOT_MADE, "couldnt-check": NOT_DONE, "not-compared": NOT_MADE}

#: A run's recorded verdict.
VERDICT = {"holds": HELD, "contradicts": FAILED, "could_not_check": NOT_DONE, "not checked": NOT_DONE}


#: An incident's rule, by what raised it: a check that ran and failed is red; a check that couldn't
#: be done is amber; a fact the store recorded (a run id used twice) is neutral.
INCIDENT = {"I-CONTRADICTS": FAILED, "I-HEADER-DISAGREES": FAILED, "I-COULD-NOT-CHECK": NOT_DONE,
            "I-RUNID-REUSED": NOT_MADE}


#: A stage's verdict in a comparison of two runs (the Compare page's graph). A first difference
#: is the comparison's finding, drawn in the red state colour as the work order sets it for the
#: headline; "changed after it" is a change, not a fault, so neutral; a stage the comparison
#: couldn't check is amber.
DIFF = {"same": HELD, "reconverged": HELD, "FIRST DIFFERENCE": FAILED, "downstream": NOT_MADE,
        "COULD NOT CHECK": NOT_DONE}


def tone(table: dict[str, str], state: str) -> str:
    """The tone of `state` in `table`; a state the table doesn't place is neutral, never a verdict."""
    return TONE[table.get(state, NOT_MADE)]
