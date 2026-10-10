"""The Overview's facts (v6 board 1), from what the store already holds.

    Release 1: ... The Overview has no permit or decision figures; its cards are runs,
    records agree, changed vs baseline, and open incidents.
    Needs-attention ordering, by a rule stated on the page ... The pipelines table, from the
    data already stored.

No HTML here. Everything is derived from stored runs, stored comparisons and the stored
bundles, and each derivation says in words what it rests on, because two of the canvas's
nouns do not exist in the records:

- **A pipeline is a declared stage list.** No record names its pipeline -- not the manifest,
  not a receipt -- and the stored `pipeline` index field is the manifest's own digest, which
  is one per run. Runs that declare the same stages, in the same order, are one pipeline
  here, labelled P1, P2 ... in order of first arrival, so a label never moves once given.
- **A baseline is the run a comparison was asked against.** This console picks none
  (no automatic partner-finding). A run is "changed vs baseline" when it is
  the candidate of a stored comparison whose diff found a first difference.
"""
from __future__ import annotations

import json
from onetrace_console.bounded_json import load_json_bounded
import re
from dataclasses import dataclass

from onetrace_console.checks import CONTRADICTS, COULD_NOT_CHECK
from onetrace_console.store import StoredRun, Store

PIPELINE_RULE = ("A pipeline here is a declared stage list: runs that declare the same stages, "
                 "in the same order. No record names its pipeline.")

#: The needs-attention order, as the page states it. v6 board 1's order, with the states this
#: store records: "gaps" is a declared stage with no receipt, and a run no check has reached
#: is its own state (the three-outcome rule), placed after the two the check did reach.
#: "Last attempt failed" comes after a declared stage missing; the order's own sentence names it
#: there in the reason's fixed words, so the stated order stays true.
ATTENTION_RULE = ("Order: contradicts itself, then couldn't check, then not checked, then a "
                  "declared stage missing, then last attempt failed, then changed vs baseline; "
                  "newest first within each.")
ATTENTION_KINDS = ("contradicts", "couldnt-check", "not-checked", "missing-stage",
                   "last-attempt-failed", "changed")
ATTENTION_WORDS = {
    "contradicts": "Contradicts itself",
    "couldnt-check": "Couldn't check",
    "not-checked": "Not checked",
    "missing-stage": "A declared stage missing",
    "last-attempt-failed": "Last attempt failed",
    "changed": "Changed vs baseline",
}


@dataclass(frozen=True, slots=True)
class Pipeline:
    """`stages` is the first LIST_CAP of them, as the runs record them to show; `more` is how
    many more there are."""
    label: str
    stages: tuple[str, ...]
    runs: tuple[StoredRun, ...]
    more: int = 0


def declared_list(run: StoredRun) -> tuple:
    """What a run is grouped and matched by: every stage it declares, by their digest, beside
    the names it keeps to show."""
    return (run.declared_digest, tuple(run.declared_stages))


def pipelines(store: Store) -> tuple[Pipeline, ...]:
    """Runs grouped by their declared stage list, labelled in order of first arrival."""
    groups: dict[tuple, list[StoredRun]] = {}
    for run in sorted(store.runs(), key=lambda r: (r.received_at, r.key)):
        groups.setdefault(declared_list(run), []).append(run)
    return tuple(Pipeline(f"P{i}", runs[0].declared_stages, tuple(runs),
                          max(0, runs[0].stage_count - len(runs[0].declared_stages)))
                 for i, runs in enumerate(groups.values(), start=1))


#: Rung 3's states, as a run's page decides them and its record keeps them.
NOTHING_MISSING, SOMETHING_MISSING = "yes", "no"


def missing_a_declared_stage(run: StoredRun) -> bool:
    """The run's own page says part of it wasn't recorded: rung 3, "nothing missing", is No.

    Not a count of the chain against the declared stages any more: the pinned SDK's manifest
    declares none, so an early-stopped run "declared" what it recorded."""
    return run.nothing_missing == SOMETHING_MISSING


def nothing_missing_not_established(run: StoredRun) -> bool:
    """Neither yes nor no: the receipts do not say, or say it in a shape that cannot be read,
    or the viewer could not read the record at all."""
    return run.nothing_missing not in (NOTHING_MISSING, SOMETHING_MISSING)


def _diff_of(comparison, store: Store) -> dict | None:
    """The stored diff report of a comparison, parsed, or None where there is none to read."""
    from onetrace_console.compare import DIFF
    run = comparison.verb(DIFF)
    if run is None or run.note:
        return None
    key = dict(run.reports).get("diff.json")
    if key is None:
        return None
    from onetrace_console.store import StoreError
    try:
        data = load_json_bounded(store.get(key).decode("utf-8"), "diff.json")
    except (ValueError, UnicodeDecodeError, StoreError, RecursionError):
        #: StoreError and RecursionError too: a stored report whose bytes moved, or that is
        #: nested past what JSON reads, blanked Home and every list (the third review, NEW-6).
        return None
    return data if isinstance(data, dict) else None


def vs_baseline(run: StoredRun, store: Store) -> tuple[str, str]:
    """(state, words): the run as the candidate of its most recent stored comparison.

    `changed` names the first differing stage; `same` is a diff that found none; a diff that
    could not be read or did not decide is `couldnt-check`; a run that is no comparison's
    candidate is `not-compared` -- including a run that was only ever a baseline.
    """
    from onetrace_console.pages import latest_as_candidate
    #: The comparison the run page's marks come from too: the Comparisons index's own order
    #: So the Overview and the run page never name different ones.
    latest = latest_as_candidate(run, store)
    if latest is None:
        return "not-compared", "Not compared"
    diff = _diff_of(latest, store)
    if diff and diff.get("shape") == "dag":
        return _vs_baseline_graph(latest, store)
    envelope = diff.get("envelope") if diff else None
    first = diff.get("first_difference") if diff else None
    if envelope == "diverged" and isinstance(first, dict) \
            and isinstance(first.get("index"), str) and isinstance(first.get("stage"), str):
        from onetrace_console.viewer.model import name_shown
        return "changed", (f"First difference · stage {first['index']} · "
                           f"{name_shown(first['stage'])}")
    if envelope == "identical":
        return "same", "Same"
    return "couldnt-check", "Couldn't check"


def _vs_baseline_graph(comparison, store: Store) -> tuple[str, str]:
    """A two-run graph `diff` names no single first difference: it names a frontier, every node
    where the runs first differ. Read only through the viewer's strict reader, as the run page's
    marks are; a report that does not pass it decides nothing."""
    from onetrace_console.viewer.model import name_shown
    from onetrace_console.viewer.verbs import TwoRunDag

    from onetrace_console.pages import _strict_diff_report
    report = _strict_diff_report(comparison, store)
    if not isinstance(report, TwoRunDag):
        return "couldnt-check", "Couldn't check"
    if report.envelope == "diverged" and report.first_difference_frontier:
        names = [name_shown(n) for n in report.first_difference_frontier]
        #: One node, or several in the report's order.
        head = "First difference" if len(names) == 1 else "First differences"
        return "changed", f"{head} · {', '.join(names)}"
    if report.envelope == "identical":
        return "same", "Same"
    return "couldnt-check", "Couldn't check"


def last_failed(run) -> list[list[str]]:
    """[[stage, error type], ...], the declared stages whose last recorded
    attempt failed, as derived when the run was checked. Empty where none did, where the run was
    derived before this was, or where the kept value is not that shape."""
    import json
    try:
        kept = load_json_bounded(getattr(run, "last_failed", "") or "[]", "the run's failed last attempts")
    except ValueError:
        return []
    ok = isinstance(kept, list) and all(isinstance(x, list) and len(x) == 2
                                        and all(isinstance(s, str) for s in x) for x in kept)
    return kept if ok else []


def attention_kind(run: StoredRun, store: Store) -> str | None:
    """The first kind of attention a run needs, in the stated order, or None."""
    if run.check_verdict == CONTRADICTS:
        return "contradicts"
    from onetrace_console.checks import is_preview_not_verified
    if run.check_verdict == COULD_NOT_CHECK and not is_preview_not_verified(run):
        #: A preview run's NOT VERIFIED does not need attention.
        return "couldnt-check"
    if not run.check_verdict:
        return "not-checked"
    if missing_a_declared_stage(run):
        return "missing-stage"
    if last_failed(run):
        return "last-attempt-failed"
    if vs_baseline(run, store)[0] == "changed":
        return "changed"
    return None


def needs_attention(store: Store) -> list[tuple[str, StoredRun]]:
    """Every run needing attention, in the order `ATTENTION_RULE` states."""
    found = [(attention_kind(r, store), r) for r in store.runs()]
    found = [(k, r) for k, r in found if k is not None]
    #: Stable sorts, last key first: kind, then newest arrival, then key for a fixed order.
    found.sort(key=lambda kr: kr[1].key)
    found.sort(key=lambda kr: kr[1].received_at, reverse=True)
    found.sort(key=lambda kr: ATTENTION_KINDS.index(kr[0]))
    return found


# ------------------------------------------------------------ verdicts by day, the marker

#: What a change marker reads, per stage, from a run's receipts: its recorded settings and
#: the digest of the code that ran it: "an envelope, settings, instrument or pipeline digest
#: that differs from the day before" -- recorded, never inferred.
DIGEST_FIELDS = (("settings", "config_digest"), ("instrument", "manifest_digest"))


#: A recorded digest as the SDK writes one. Anything else in that field is not read as one (the
#: second confirmation review, B1: a lone surrogate there reached the page and broke it).
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def recorded_digests(run: StoredRun, store: Store) -> dict[tuple[str, str], str] | None:
    """{(stage name, what): digest} from the run's own receipts, in its chain's order; None
    where they cannot be read that far, so nothing is claimed about it -- or where a digest is
    not one, since a marker would quote it.

    Read from the run's record where its check kept them (`StoredRun.digests`): a
    later render then reads no receipt. A run not yet derived is read from its stored bytes."""
    if run.digests:
        try:
            kept = load_json_bounded(run.digests, "the run's recorded digests")
        except ValueError:
            kept = None
        if kept is None or not (isinstance(kept, list) and all(
                isinstance(d, list) and len(d) == 3 and all(isinstance(x, str) for x in d)
                for d in kept)):
            return None
        return {(stage, what): value for stage, what, value in kept}
    from onetrace_console.ingest import same_file
    from onetrace_console.store import StoreError
    files = {same_file(p): k for p, k in run.listing}
    try:
        found = digests_in(lambda name: store.get(files[same_file(name)]))
    except StoreError:
        return None
    return None if found is None else {(stage, what): value for stage, what, value in found}


def digests_in(read) -> list[list[str]] | None:
    """[stage name, what, digest] from a run's receipts in its chain's order, `read(name)` giving
    a file's bytes by the name the chain uses; None where they cannot be read that far or a
    digest is not one. Names are looked up as this host resolves them (a chain spelling
    `./receipts/...` was once read as naming no file); a stage name is kept as recorded and
    shown escaped."""
    try:
        manifest = load_json_bounded(read("MANIFEST.json").decode("utf-8"), "MANIFEST.json")
        out: list[list[str]] = []
        for entry in manifest["chain"]:
            receipt = load_json_bounded(read(entry["file"]).decode("utf-8"), entry["file"])
            stage = str(entry.get("stage") or receipt["stage"]["name"])
            instrument = receipt["instrument"]
            for what, field in DIGEST_FIELDS:
                value = instrument.get(field)
                if isinstance(value, str) and value:
                    if not _DIGEST.fullmatch(value):
                        return None
                    out.append([stage, what, value])
        return out
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, AttributeError, RecursionError,
            OSError):
        return None


@dataclass(frozen=True, slots=True)
class Day:
    date: str                       # YYYY-MM-DD, as the arrival time records it
    runs: tuple[StoredRun, ...]


@dataclass(frozen=True, slots=True)
class Marker:
    """What changed between one day and the next: pipeline, stage, what, the two sets."""
    pipeline: str
    stage: str
    what: str
    before: tuple[str, ...]
    after: tuple[str, ...]


def days(store: Store) -> tuple[Day, ...]:
    """Runs by the date of their arrival, oldest day first."""
    by: dict[str, list[StoredRun]] = {}
    for run in store.runs():
        by.setdefault(run.received_at[:10], []).append(run)
    return tuple(Day(d, tuple(by[d])) for d in sorted(by))


def markers(store: Store) -> tuple[list[list[Marker]], int]:
    """(markers[i] -- what changed between day i and day i+1 -- and how many runs' receipts
    could not be read). A marker stands only where a pipeline has runs on both days and a
    stage's recorded digests on the later day are not the ones on the earlier."""
    label = {r.key: p.label for p in pipelines(store) for r in p.runs}
    found = days(store)
    unreadable = 0
    per_day: list[dict[tuple[str, str, str], set[str]]] = []
    for day in found:
        seen: dict[tuple[str, str, str], set[str]] = {}
        for run in day.runs:
            digests = recorded_digests(run, store)
            if digests is None:
                unreadable += 1
                continue
            for (stage, what), value in digests.items():
                seen.setdefault((label[run.key], stage, what), set()).add(value)
        per_day.append(seen)
    out: list[list[Marker]] = []
    for before, after in zip(per_day, per_day[1:]):
        shared = sorted(set(before) & set(after))
        out.append([Marker(k[0], k[1], k[2], tuple(sorted(before[k])), tuple(sorted(after[k])))
                    for k in shared if before[k] != after[k]])
    return out, unreadable


# ------------------------------------------------------ other runs with the same change

#: The recorded digests a change can be matched on, in the order tried, and their words.
CHANGE_WHAT = (("settings", "settings"), ("instrument", "code"))


@dataclass(frozen=True, slots=True)
class SameChange:
    """Other runs with the same change, for one comparison. `state` is `found`, `unchanged` (no
    recorded digest at the first differing stage differs), `unreadable`, `none` (the two runs
    are identical: `identical` is then true), `graph` (two graph-shaped runs, whose diff report
    names a frontier of nodes rather than one first difference, which this matching does not
    read), or `undecided` (no diff report this console can read named a first difference:
    none stored, unreadable, or not comparable, refused, could not check). Only `none` says
    the comparison found no first difference."""
    state: str
    index: str = ""
    stage: str = ""
    what: str = ""
    digest: str = ""
    pipeline: str = ""
    in_pipeline: int = 0
    matches: tuple[StoredRun, ...] = ()
    identical: bool = False


def same_change(comparison, store: Store) -> SameChange:
    """Other runs carrying the candidate's changed digest at the first differing stage.

    Matched on the recorded digest that differs between the pair at that stage -- settings,
    else code -- by exact equality, within the candidate's pipeline. Not on the stage's
    inputs: by the ladder every stage before the first difference is the same in both runs,
    so the stage's inputs are too, and cannot be what changed.
    """
    diff = _diff_of(comparison, store)
    first = diff.get("first_difference") if diff else None
    if diff and diff.get("envelope") == "identical":
        return SameChange("none", identical=True)
    if diff and "first_difference_frontier" in diff:
        #: A graph comparison's report has no `first_difference`, and
        #: reading its absence as "none" put "found no first difference" on a page that shows
        #: one first difference or more.
        return SameChange("graph")
    if not (diff and diff.get("envelope") == "diverged" and isinstance(first, dict)
            and isinstance(first.get("index"), str) and isinstance(first.get("stage"), str)):
        return SameChange("undecided")
    index, stage = first["index"], first["stage"]
    from onetrace_console.store import StoreError
    try:
        baseline, candidate = store.get_run(comparison.run_a), store.get_run(comparison.run_b)
    except StoreError:
        #: A run record the store cannot read: nothing is matched on its account.
        return SameChange("unreadable", index, stage)
    before = recorded_digests(baseline, store) if baseline else None
    after = recorded_digests(candidate, store) if candidate else None
    if before is None or after is None:
        return SameChange("unreadable", index, stage)
    for key, words in CHANGE_WHAT:
        value = after.get((stage, key))
        if value and before.get((stage, key)) != value:
            break
    else:
        return SameChange("unchanged", index, stage)
    label = {r.key: p.label for p in pipelines(store) for r in p.runs}
    in_pipeline = [r for r in store.runs() if label[r.key] == label[candidate.key]]
    matches = tuple(r for r in in_pipeline if r.key != candidate.key
                    and (recorded_digests(r, store) or {}).get((stage, key)) == value)
    return SameChange("found", index, stage, words, value, label[candidate.key],
                      len(in_pipeline), matches)
