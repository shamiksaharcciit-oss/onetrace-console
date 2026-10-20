"""Rung 1, "Records agree": the one reading of it, for every page, table, count and the start-up list.

A run's rung 1 is decided once, as its own page decides it (`viewer.model.records_agree_reading`),
when the run is checked, and kept on its record (`StoredRun.agree`). Every page that says or counts
it reads `state` here and nothing else, so a run reads one way everywhere:

    yes            Records agree           the check held, with the run's output files required
    no             Contradicts its record  the check, or its run with the output files required, failed
    couldnt-check  Couldn't check          the check could not settle it
    not-checked    Not checked             the check did not look at what rung 1 needs; where it held
                                           without the run's output files required, that is said
    no-verdict     No verdict recorded     the check has not reached the run (it has no page)

The verifier's own verdict ("Verified" and the rest) is the verifier's output: it is shown only where
a page presents that output, never as a count of runs.
"""
from __future__ import annotations

from onetrace_console.store import Store, StoredRun

YES, NO, COULDNT, NOT_CHECKED, NO_VERDICT = "yes", "no", "couldnt-check", "not-checked", "no-verdict"
#: In the order every summary counts them.
STATES = (YES, NO, COULDNT, NOT_CHECKED, NO_VERDICT)
#: What a summary counts each state under, and what a one-line list says of one run.
LABEL = {YES: "Records agree", NO: "Contradicts its record", COULDNT: "Couldn't check",
         NOT_CHECKED: "Not checked", NO_VERDICT: "No verdict recorded"}
#: Each state as a count says it in a sentence: "28 of 31 records agree".
COUNTED = {YES: "records agree", NO: "contradict their record", COULDNT: "couldn't check",
           NOT_CHECKED: "not checked", NO_VERDICT: "no verdict recorded"}
#: The one reason a count says: a check that held, without the run's output files required.
HELD_WITHOUT = "held without its output files required"


def counted(wanted: str, runs, store: Store) -> str:
    """`COUNTED[wanted]` for a count of `runs`, all in that state, with the reason where there is
    one: "not checked (held without its output files required)" where it is every run's, or how
    many of them it is where it is some."""
    words = COUNTED[wanted]
    if wanted != NOT_CHECKED:
        return words
    held = sum(1 for r in runs if why(r, store))
    if not held:
        return words
    return f"{words} ({HELD_WITHOUT})" if held == len(runs) else f"{words} ({held} {HELD_WITHOUT})"


def state(run: StoredRun, store: Store) -> str:
    """The run's rung 1 state: its own page's, as recorded when it was checked.

    A run with no reading of its own check kept -- the viewer refused its record, or it was
    recorded before this was kept -- is read from what the store holds of that check, by the same
    rule: a check that held is a yes only with the run's output files required, a no where that
    run failed, otherwise not checked."""
    if not run.check_verdict:
        return NO_VERDICT
    if run.agree in (YES, NO, COULDNT, NOT_CHECKED):
        return run.agree
    from onetrace_console.checks import CONTRADICTS, HOLDS
    if run.check_verdict == CONTRADICTS:
        return NO
    if run.check_verdict != HOLDS:
        return COULDNT
    from onetrace_console.home import artifacts_required, outputs_required_exit
    if artifacts_required(run, store):
        return YES
    return NO if outputs_required_exit(run, store) not in (None, "0") else NOT_CHECKED


def why(run: StoredRun, store: Store) -> str:
    """`HELD_WITHOUT` where the run is not checked because its check held without its output files
    required; otherwise empty."""
    if state(run, store) != NOT_CHECKED:
        return ""
    if run.agree:
        return HELD_WITHOUT if run.agree_why == "no-outputs" else ""
    from onetrace_console.checks import HOLDS
    return HELD_WITHOUT if run.check_verdict == HOLDS else ""


def said(run: StoredRun, store: Store) -> str:
    """One run's rung 1 in a one-line list: its label, and the reason where there is one."""
    s, reason = state(run, store), why(run, store)
    return f"{LABEL[s]} ({reason})" if reason else LABEL[s]


def runs_in(runs, store: Store, wanted: str) -> tuple[StoredRun, ...]:
    """The runs of `runs` whose rung 1 is `wanted`, in their order."""
    return tuple(r for r in runs if state(r, store) == wanted)


#: A comparison with a side whose rung 1 reads "Couldn't check": what the SDK's `diff` says of
#: the pair is never shown as a finding. {name}: that run, {role}: baseline or candidate.
UNCHECKED_SIDE = ("Couldn't check {name}, the {role}: its own check could not be done, so this "
                  "comparison shows no verdict.")
#: The run page's reason, in its "Couldn't be checked from here" frame.
UNCHECKED_MARKS = "{name}, the {role}, couldn't be checked, so this comparison shows no verdict"
#: The start-up list's line for such a comparison. {names}: the folders, " and "-joined.
UNCHECKED_SAID = "Couldn't check {names}, so no verdict is shown"


def unchecked_sides(comparison, store: Store) -> tuple[tuple[str, StoredRun], ...]:
    """(role, run) for each side of `comparison` whose "Records agree" reads "Couldn't check",
    baseline first. The SDK's `diff` reads only the receipts it is given and calls a run the
    verifier refuses identical to its baseline, so a pair with such a side shows no verdict from
    `diff`: every page that reads a comparison asks this first."""
    out = []
    for role, key in (("baseline", getattr(comparison, "run_a", None)),
                      ("candidate", getattr(comparison, "run_b", None))):
        if not key:
            continue
        try:
            run = store.get_run(key)
        except Exception:  # noqa: BLE001 - a record that can't be read is said where it is read
            run = None
        if run is not None and state(run, store) == COULDNT:
            out.append((role, run))
    return tuple(out)
