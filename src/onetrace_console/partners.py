"""Candidate partner runs, from declared fields only, never from a score.

    For this slice the user chooses the partner explicitly, as two run ids. Do **not** build
    automatic partner-finding. The Execution page may list candidate partners, but only runs
    that share a declared identity field with this run. Label each by the fields they share,
    **never by a similarity score**. If no declared field exists to match on, show no
    candidates, and write that into DESIGN_GAPS.md.

WHAT A CANDIDATE IS, AND WHAT IT IS NOT
--------------------------------------
A candidate is a run that **declares** something this run also declares. Nothing here ranks,
weights, scores, or orders by closeness. The label on a candidate is the list of fields the
two runs share, so a reader can see the whole reason a run is on the list and disagree with
it. That is the difference between an index and a recommendation.

There is no "best" candidate and no default selection. The user names two run ids.

THE FIELDS ARE A CLOSED SET, AND THEY ARE DECLARED
--------------------------------------------------
Only `MATCHABLE` below. Each is a member an emitter *wrote into the manifest* -- not
something this console inferred, counted or derived. `received_at` is deliberately absent:
two runs arriving close together share nothing about themselves, and time-proximity is the
first thing that turns into a similarity score when nobody is watching.
"""
from __future__ import annotations

from dataclasses import dataclass

from onetrace_console.store import StoredRun, Store

#: The declared identity fields a candidate may be matched on, and the label each carries.
#:
#: `run_id` is the name the emitter gave the run. `declared_stages` is the stage list the
#: manifest declares. Both are written by the emitter and read here unchanged. The stored
#: `pipeline` field, a digest of the manifest, is not among them: it is left unread in
#: release 1 (BACKLOG.md R2-1), and calling a manifest digest "the same
#: declared pipeline" named something the record does not declare.
MATCHABLE: dict[str, str] = {
    "run_id": "the same run name",
    "declared_stages": "the same declared stages",
}

#: Said on the page when a run declares nothing that any other run declares too. An absence
#: sentence, never a blank, and never a list of runs that share nothing.
NO_DECLARED_FIELD = (
    "No other stored run declares a field this one declares, so there is nothing to offer "
    "as a candidate. Choose a partner by run id.")


@dataclass(frozen=True, slots=True)
class Candidate:
    """A run that shares at least one declared field, and the fields it shares."""
    run: StoredRun
    shared: tuple[str, ...]

    @property
    def labels(self) -> tuple[str, ...]:
        """The reason this run is a candidate, in words, one per shared field."""
        return tuple(MATCHABLE[f] for f in self.shared)


def _value(run: StoredRun, field: str):
    if field == "declared_stages":
        #: All of them, by their digest beside the names kept: a run keeps the first LIST_CAP
        #: names only, and two runs sharing those need not declare the same stages.
        from onetrace_console.overview import declared_list
        return declared_list(run) if run.declared_stages else ()
    value = getattr(run, field, None)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return value


def shared_fields(run: StoredRun, other: StoredRun) -> tuple[str, ...]:
    """Which declared fields these two runs share, in `MATCHABLE`'s own order.

    A field both runs leave empty is **not** shared. Two runs that both declare nothing have
    nothing in common, and treating an absence as a match is how a list of everything gets
    presented as a list of relatives.
    """
    out = []
    for field in MATCHABLE:
        mine, theirs = _value(run, field), _value(other, field)
        if not mine or not theirs:
            continue
        if mine == theirs:
            out.append(field)
    return tuple(out)


def candidates(run: StoredRun, store: Store) -> tuple[Candidate, ...]:
    """Every other stored run that shares a declared field, with the fields it shares.

    Ordered by run id, which is a stable name and not a ranking. Deliberately not ordered by
    how many fields are shared: "3 fields in common" sorted to the top is a similarity score
    with the number filed off.
    """
    out = []
    for other in store.runs():
        if other.key == run.key:
            continue
        shared = shared_fields(run, other)
        if shared:
            out.append(Candidate(run=other, shared=shared))
    return tuple(sorted(out, key=lambda c: (c.run.run_id, c.run.key)))
