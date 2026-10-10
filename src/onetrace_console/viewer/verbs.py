"""Read what the verbs write: `onetrace-report/0.1`, strictly.

The format is the report format's draft (029), read from the reports the verbs actually wrote at
`c325c94` (the samples kept with the viewer's development history). It **binds by addition** when the
standards channel's item 3 lands, so this reader is built to survive additions:

- **a key it does not know, it ignores** (029 §0's stability promise);
- **the node id is read from `node`, and `stage` stays the bare name.** C029 §7 said the node
  id would appear *in* `stage`; a relay of 2026-09-18 corrected that by addition (R-C006). Rows
  expose `.key` — the node id where one is given, the index otherwise — and **nothing renders a
  node id yet**: §7's *anticipate it, do not build it* still governs, and
  `first_difference_frontier` is unbuilt;
- **a value it does not know in a closed vocabulary, it refuses** — the vocabularies are
  named here and an unlisted value raises `VerbReportUnreadable`. A page that renders an
  unknown verdict has guessed at what it means;
- **a field it reads in a shape the format does not give it, it refuses**.
  Each field has one shape: a list of objects, a list of strings, an object or null,
  a string. A string read as a list of its characters, or a number read as an empty list, is a
  guess; so is `null` where the SDK writes `[]`. An absent key still reads as none.

Two shapes arrive under one format. A verb that could not start writes the **failure shape**,
and 029 §1 says how to tell: **the absence of `mode`** — never by reading stderr.

`exit`, indices and counts are **decimal strings** in the format and stay strings here. They
are identifiers and record values, not arithmetic (E006's spirit: no float, and no number the
page invents).

WHAT THIS MODULE DOES NOT DO
----------------------------
It renders nothing and it decides no sentence: `viewer/model.py` maps these states onto the
translation table. It also does not read the `verifier-<side>-<n>.json` files yet — 029 §8
says those carry `rows[]` machine-readably and that the strict text parser can go the day the
viewer consumes them. That is a separate change, not smuggled into this one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from onetrace_console.bounded_json import TooDeep, load_json_bounded

from onetrace_console.viewer.record import unshowable_bytes

FORMAT = "onetrace-report/0.1"
VERBS = ("diff", "localize", "reproduce")

#: 029 §2. The envelope of a two-run report.
ENVELOPES = ("identical", "diverged", "not comparable", "refused", "could not check")
#: 029 §3. The ladder's closed five.
VERDICTS = ("same", "FIRST DIFFERENCE", "downstream", "reconverged", "COULD NOT CHECK")
#: 029 §4. Single-run `localize`.
SINGLE_RESULTS = ("clean", "located", "COULD NOT CHECK", "refused")

#: 022 §2 / O5: on a topological run `localize` answers with a SET of nodes, and `shape`
#: says so. The only value the SDK emits is "dag" (`report.single_run_dag`), so an unknown
#: shape is refused rather than read as linear — a DAG read as a line is the defect R40
#: existed to prevent and O5 replaced with a real answer.
SHAPES = ("dag",)

#: `localize.walk_dag`'s own two kinds, measured in the SDK: a node unclean on its own
#: check is "located"; a node whose own boundary or an upstream boundary stops the check is
#: "could not check". A third value is a format change, not something to guess at.
DAG_KINDS = ("located", "could not check")
SINGLE_CHECKS = ("outcome", "chain continuity", "absent output", "emission gaps", "coverage",
                 "boundary")
#: 029 §5. `reproduce`.
#: As `reproduce.run` writes them (pinned SDK 0.1.0): one stage is mode "stage", and a record
#: its verifier call refused is result "refused" with no stages. "single-stage" was this
#: reader's word, never the SDK's -- found by the confirmation review.
REPRODUCE_MODES = ("whole-run", "stage")
REPRODUCE_RESULTS = ("all REPRODUCED", "DIVERGED", "COULD NOT CHECK", "refused")
STAGE_OUTCOMES = ("REPRODUCED", "DIVERGED", "COULD NOT CHECK")
#: Only on COULD NOT CHECK, and the three are not interchangeable: `declared` is the record
#: telling the truth about itself, `unavailable` is this reader's reach, `mismatch` is the code
#: on hand not being the code that ran.
CATEGORIES = ("declared", "unavailable", "mismatch")
#: `localize.cause`'s own words where it has no object to give, read from the SDK's source
#: (`localize.py` at the pinned 0.1.0), not from the samples, which carry only objects: the
#: instrument's change is an object, "instrument unchanged" or COULD NOT CHECK, and the
#: constants an object or COULD NOT CHECK. Any other string is refused.
CAUSE_WORDS = {"instrument_change": ("instrument unchanged", "COULD NOT CHECK"),
               "constants": ("COULD NOT CHECK",)}


class VerbReportUnreadable(ValueError):
    """The report exists and cannot be read as one. Surfaced, never guessed past."""


@dataclass(frozen=True, slots=True)
class Failure:
    """A verb that could not start (029 §1). No `mode`, so no report body."""

    verb: str
    envelope: str
    exit_code: str
    reason: str | None
    inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LadderRow:
    index: str
    stage: str
    verdict: str
    baseline: dict | None
    candidate: dict | None
    reason: str | None
    node: str | None = None       # item 3's node id, absent at c325c94

    @property
    def key(self) -> str:
        """What identifies this row: the node id where given, the index otherwise."""
        return self.node or self.index


@dataclass(frozen=True, slots=True)
class TwoRun:
    """`diff`, or `localize --mode two-run`."""

    verb: str
    envelope: str
    exit_code: str
    reason: str | None
    ladder: tuple[LadderRow, ...]
    first_difference: dict | None
    boundary: dict | None
    reconverged_stages: tuple[str, ...]
    could_not_check_stages: tuple[str, ...]
    carried: tuple[dict, ...]
    cause: dict | None


@dataclass(frozen=True, slots=True)
class SingleRun:
    """`localize --mode single-run`."""

    verb: str
    result: str
    exit_code: str
    stage: str | None
    check: str | None
    words: str | None


@dataclass(frozen=True, slots=True)
class DagNode:
    """One minimal unclean node from `single_run_dag`. `node` is the node id, not the stage."""

    node: str
    kind: str
    check: str | None
    words: str | None


@dataclass(frozen=True, slots=True)
class SingleRunDag:
    """`localize --mode single-run` on a run that declares a topology (022 §2).

    `nodes` replaces `stage`/`check`/`words`: the answer on a DAG is a set, not one stage. The
    tuple is kept in the report's own order — **sorting by node id is the page's job**, so that
    a report whose emission order differs from its id order (the exam's `dag-r37/run_R` is
    exactly that) can prove the page sorts rather than passing through.
    """

    verb: str
    result: str
    exit_code: str
    nodes: tuple[DagNode, ...]


@dataclass(frozen=True, slots=True)
class ReproduceRow:
    index: str
    stage: str
    outcome: str
    category: str | None
    reason: str | None
    declared: str | None
    recorded: dict | None
    produced: dict | None
    node: str | None = None       # item 3's node id, absent at c325c94

    @property
    def key(self) -> str:
        """What identifies this row: the node id where given, the index otherwise."""
        return self.node or self.index


@dataclass(frozen=True, slots=True)
class Reproduce:
    verb: str
    mode: str
    result: str
    exit_code: str
    summary: str | None
    stages: tuple[ReproduceRow, ...]
    #: Which run the report is about, as the report names it (`inputs.run.run_id` and
    #: `inputs.run.record_digests.chain_head`). None where it names none. Read so a page can
    #: tell a re-check of THIS run from one of another run; nothing else rests on them.
    run_id: str | None = None
    chain_head: str | None = None
    #: Result "refused" only: the verifier's failed rows the refusal rests on, in its words.
    refused_because: str | None = None


@dataclass(frozen=True, slots=True)
class DagRow:
    """One row of the SDK's two-run DAG ladder (`report.dag_block`): a node, matched across the
    two runs by its id; its verdict; its emission index in each run, None where the node is not
    in that run; and the SDK's own annotations, in its words ("present in B only", ...)."""

    node: str
    verdict: str
    index_baseline: str | None
    index_candidate: str | None
    annotations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TwoRunDag:
    """`diff` (or `localize --mode two-run`) over two graph-shaped runs. Rows in
    the SDK's own order (`topology.order`): nothing re-sorted here."""

    verb: str
    envelope: str
    exit_code: str
    reason: str | None
    ladder: tuple[DagRow, ...]
    first_difference_frontier: tuple[str, ...]
    could_not_check_nodes: tuple[str, ...]
    comparisons_performed: str
    counts: tuple[tuple[str, str], ...]
    carried: tuple[dict, ...]


Report = Failure | TwoRun | TwoRunDag | SingleRun | Reproduce


def _closed(value, allowed, what: str) -> str:
    if value not in allowed:
        raise VerbReportUnreadable(
            f"{what} is {value!r}, which is not one of {list(allowed)}; a page that renders an "
            f"unknown value has guessed at what it means")
    return value


def _string(obj: dict, key: str, what: str) -> str:
    v = obj.get(key)
    if not isinstance(v, str):
        raise VerbReportUnreadable(f"{what}: {key!r} is {v!r}, not a string")
    return v


def _optional(obj: dict, key: str) -> str | None:
    v = obj.get(key)
    if v is None or isinstance(v, str):
        return v
    raise VerbReportUnreadable(f"{key!r} is {v!r}, neither a string nor null")


def _shown(value) -> str:
    """A value as a refusal quotes it: its repr, cut short, since a malformed field can be large."""
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def _object(obj: dict, key: str, what: str) -> dict | None:
    """An object, or null. Absent reads as null. Anything else is refused."""
    v = obj.get(key)
    if v is None or isinstance(v, dict):
        return v
    raise VerbReportUnreadable(f"{what}: {key!r} is {_shown(v)}, neither an object nor null")


def _decimal(obj: dict, key: str, what: str) -> str:
    """A decimal string, as the SDK writes every index (`str(i + 1)`)."""
    v = obj.get(key)
    # Bounded: no run has a billion stages, and a 5000-digit index passed here and then broke
    # `int()` on the console's Diff page (the second confirmation review, N5).
    if not (isinstance(v, str) and v.isascii() and v.isdigit() and len(v) <= 9):
        raise VerbReportUnreadable(f"{what}: {key!r} is {_shown(v)}, not a decimal string")
    return v


def _side(obj: dict, key: str, what: str) -> dict | None:
    """One side of a row: the SDK's `shown` (records.py), an object or null. For a run it is
    `{"outputs": [digest or null, ...], "outcome_class": ...}`, for a summary record `{"digest":
    ..., "read_from": ...}`; each of those, where present, in exactly that shape."""
    side = _object(obj, key, what)
    if side is None:
        return None
    outputs = side.get("outputs", [])
    if not (isinstance(outputs, list) and all(x is None or isinstance(x, str) for x in outputs)):
        raise VerbReportUnreadable(
            f"{what}: {key}.outputs is {_shown(outputs)}, not a list of digests")
    for name in ("outcome_class", "digest", "read_from"):
        if not (side.get(name) is None or isinstance(side.get(name), str)):
            raise VerbReportUnreadable(
                f"{what}: {key}.{name} is {_shown(side.get(name))}, neither a string nor null")
    return side


def _list(obj: dict, key: str, kind: type, what: str) -> list:
    """A list whose every item is a `kind` (dict or str). Absent reads as empty; anything else,
    `null` included, is refused."""
    if key not in obj:
        return []
    v = obj[key]
    if not isinstance(v, list) or not all(isinstance(x, kind) for x in v):
        noun = "objects" if kind is dict else "strings"
        raise VerbReportUnreadable(f"{what}: {key!r} is {_shown(v)}, not a list of {noun}")
    return v


def report_path(where: Path) -> Path:
    """The verb's own report inside an output directory, or the file itself."""
    where = Path(where)
    if where.is_file():
        return where
    found = sorted(p for p in where.glob("*.json") if not p.name.startswith("verifier-"))
    if len(found) != 1:
        raise VerbReportUnreadable(
            f"{where} holds {len(found)} verb reports; expected exactly one beside its "
            f"verifier-* files: {[p.name for p in found]}")
    return found[0]


def read_report(where: Path, *, two_run_dag: bool = False) -> Report:
    """Read one verb's report. Raises `VerbReportUnreadable`; never returns a guess.

    `two_run_dag=True` is for a page that draws a comparison of two graph-shaped runs (the
    console's compare page); every other caller keeps refusing that report in
    the words it always has."""
    path = report_path(where)
    raw = path.read_bytes()
    try:
        data = load_json_bounded(raw.decode("utf-8"), path.name, "show")
    except TooDeep:
        raise VerbReportUnreadable(f"{path.name} is nested too deeply to show") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise VerbReportUnreadable(f"{path.name} is not readable JSON: {e}") from None
    except RecursionError:
        raise VerbReportUnreadable(f"{path.name} is nested too deeply to show") from None
    if not isinstance(data, dict):
        raise VerbReportUnreadable(f"{path.name} is not a JSON object")
    why = unshowable_bytes(raw, data)
    if why is not None:
        raise VerbReportUnreadable(f"{path.name} cannot be shown: {why}")
    if data.get("format") != FORMAT:
        raise VerbReportUnreadable(
            f"{path.name} declares format {data.get('format')!r}, not {FORMAT!r}")
    verb = _closed(data.get("verb"), VERBS, f"{path.name}: verb")

    # 029 §1: the failure shape is told by the ABSENCE of `mode`, not by reading stderr.
    if "mode" not in data:
        inputs = data.get("inputs")
        if not isinstance(inputs, list) or not all(isinstance(x, str) for x in inputs):
            raise VerbReportUnreadable(f"{path.name}: a failure report's `inputs` is not a list "
                                       f"of paths: {inputs!r}")
        return Failure(verb=verb,
                       envelope=_closed(data.get("envelope"), ENVELOPES,
                                        f"{path.name}: envelope"),
                       exit_code=_string(data, "exit", path.name),
                       reason=_optional(data, "reason"), inputs=tuple(inputs))

    mode = _string(data, "mode", path.name)

    if verb == "reproduce":
        rows = []
        for raw in _list(data, "stages", dict, path.name):
            outcome = _closed(raw.get("outcome"), STAGE_OUTCOMES,
                              f"{path.name}: stage {raw.get('index')!r} outcome")
            category = raw.get("category")
            if outcome == "COULD NOT CHECK":
                category = _closed(category, CATEGORIES,
                                   f"{path.name}: stage {raw.get('index')!r} category")
            elif category is not None:
                raise VerbReportUnreadable(
                    f"{path.name}: stage {raw.get('index')!r} is {outcome} and carries a "
                    f"category {category!r}; 029 §5 puts a category only on COULD NOT CHECK")
            rows.append(ReproduceRow(
                index=_string(raw, "index", path.name), stage=_string(raw, "stage", path.name),
                outcome=outcome, category=category, reason=_optional(raw, "reason"),
                declared=_optional(raw, "declared"),
                recorded=_side(raw, "recorded", f"{path.name}: stage {raw.get('index')!r}"),
                produced=_side(raw, "produced", f"{path.name}: stage {raw.get('index')!r}"),
                node=_optional(raw, "node")))
        about = (data.get("inputs") or {}).get("run") if isinstance(data.get("inputs"), dict)             else None
        about = about if isinstance(about, dict) else {}
        digests = about.get("record_digests") if isinstance(about.get("record_digests"),
                                                           dict) else {}
        result = _closed(data.get("result"), REPRODUCE_RESULTS, f"{path.name}: result")
        refused_because = None
        if result == "refused":
            preflight = _object(data, "preflight", path.name) or {}
            run = _object(preflight, "run", f"{path.name}: preflight") or {}
            failed = _list(run, "failed_rows", dict, f"{path.name}: preflight.run")
            for row in failed:
                _string(row, "name", f"{path.name}: a failed row")
                _string(row, "detail", f"{path.name}: a failed row")
            refused_because = "; ".join(f"{r['name']}: {r['detail']}" if r["detail"] else r["name"]
                                        for r in failed) or None
        return Reproduce(
            verb=verb, mode=_closed(mode, REPRODUCE_MODES, f"{path.name}: mode"),
            result=result,
            exit_code=_string(data, "exit", path.name), summary=_optional(data, "summary"),
            stages=tuple(rows),
            run_id=about["run_id"] if isinstance(about.get("run_id"), str) else None,
            chain_head=(digests["chain_head"] if isinstance(digests.get("chain_head"), str)
                        else None),
            refused_because=refused_because)

    if mode == "single-run":
        result = _closed(data.get("result"), SINGLE_RESULTS, f"{path.name}: result")
        if data.get("shape") is not None:
            _closed(data.get("shape"), SHAPES, f"{path.name}: shape")
            for key in ("stage", "check", "words"):
                if data.get(key) is not None:
                    raise VerbReportUnreadable(
                        f"{path.name}: shape is 'dag' and yet {key!r} is set; 022 §2 has `nodes` "
                        f"replace stage/check/words on a topological read")
            raw_nodes = data.get("nodes")
            if not isinstance(raw_nodes, list):
                raise VerbReportUnreadable(
                    f"{path.name}: shape is 'dag' and `nodes` is not a list: {raw_nodes!r}")
            nodes = []
            for raw in raw_nodes:
                if not isinstance(raw, dict):
                    raise VerbReportUnreadable(f"{path.name}: a node is not an object: {raw!r}")
                nodes.append(DagNode(
                    node=_string(raw, "node", path.name),
                    kind=_closed(raw.get("kind"), DAG_KINDS,
                                 f"{path.name}: node {raw.get('node')!r} kind"),
                    check=_optional(raw, "check"), words=_optional(raw, "words")))
            if result == "clean" and nodes:
                raise VerbReportUnreadable(
                    f"{path.name}: result is 'clean' and yet {len(nodes)} node(s) are named")
            return SingleRunDag(verb=verb, result=result,
                                exit_code=_string(data, "exit", path.name), nodes=tuple(nodes))
        check = _optional(data, "check")
        if check is not None:
            _closed(check, SINGLE_CHECKS, f"{path.name}: check")
        if result == "clean" and any(x is not None for x in (data.get("stage"), check)):
            raise VerbReportUnreadable(
                f"{path.name}: result is 'clean' and yet a stage or check is named; 029 §4 has "
                f"both null when clean")
        return SingleRun(verb=verb, result=result, exit_code=_string(data, "exit", path.name),
                         stage=_optional(data, "stage"), check=check,
                         words=_optional(data, "words"))

    # The SDK's `two_run_dag` (report.py) keys its rows by node and carries no index. This
    # release's pages draw only a comparison of two linear runs, and say that in words, rather
    # than refusing the rows as malformed (review note 6).
    if data.get("shape") is not None:
        if not two_run_dag:
            shape = _shown(data.get("shape"))
            raise VerbReportUnreadable(
                f"{path.name} compares two graph-shaped runs (shape {shape}); "
                f"this release's pages show only a comparison of two linear runs")
        return _two_run_dag(data, verb, path.name)
    ladder = []
    for raw in _list(data, "ladder", dict, path.name):
        row = f"{path.name}: ladder row {raw.get('index')!r}"
        ladder.append(LadderRow(
            index=_decimal(raw, "index", path.name), stage=_string(raw, "stage", path.name),
            verdict=_closed(raw.get("verdict"), VERDICTS, f"{row} verdict"),
            baseline=_side(raw, "baseline", row), candidate=_side(raw, "candidate", row),
            reason=_optional(raw, "reason"), node=_optional(raw, "node")))
    first = _object(data, "first_difference", path.name)
    if first is not None:
        _decimal(first, "index", f"{path.name}: first_difference")
        _string(first, "stage", f"{path.name}: first_difference")
    boundary = _object(data, "boundary", path.name)
    if boundary is not None:
        index = boundary.get("index")
        if not (isinstance(index, str) and index.isascii() and index.isdigit()):
            raise VerbReportUnreadable(
                f"{path.name}: the boundary's index is {_shown(index)}, not a decimal string")
    cause = _object(data, "cause", path.name)
    if cause is not None:
        for key in ("instrument_change", "constants", "blast_radius"):
            if cause.get(key) not in CAUSE_WORDS.get(key, ()):
                _object(cause, key, f"{path.name}: cause")
        _optional(cause, "instrument_reason")
    return TwoRun(
        verb=verb, envelope=_closed(data.get("envelope"), ENVELOPES, f"{path.name}: envelope"),
        exit_code=_string(data, "exit", path.name), reason=_optional(data, "reason"),
        ladder=tuple(ladder), first_difference=first, boundary=boundary,
        reconverged_stages=tuple(_list(data, "reconverged_stages", str, path.name)),
        could_not_check_stages=tuple(_list(data, "could_not_check_stages", str, path.name)),
        carried=tuple(_list(data, "carried", dict, path.name)), cause=cause)


def _two_run_dag(data: dict, verb: str, name: str) -> TwoRunDag:
    """The SDK's `dag_block`, read strictly: every field it writes, and every relation between
    them that it guarantees, checked -- a report that breaks one is refused, never drawn."""
    _closed(data.get("shape"), SHAPES, f"{name}: shape")
    rows, seen = [], set()
    for raw in _list(data, "ladder", dict, name):
        node = _string(raw, "node", name)
        if not node or node in seen:
            raise VerbReportUnreadable(f"{name}: node {_shown(node)} is empty or named twice")
        seen.add(node)
        where = f"{name}: node {node!r}"
        indexes = []
        for key in ("index_baseline", "index_candidate"):
            indexes.append(None if raw.get(key) is None else _decimal(raw, key, where))
        if indexes == [None, None]:
            raise VerbReportUnreadable(f"{where} is in neither run")
        notes = raw.get("annotations")
        if not (isinstance(notes, list) and all(isinstance(n, str) for n in notes)):
            raise VerbReportUnreadable(f"{where}: annotations are not a list of words")
        rows.append(DagRow(node=node, verdict=_closed(raw.get("verdict"), VERDICTS,
                                                      f"{where} verdict"),
                           index_baseline=indexes[0], index_candidate=indexes[1],
                           annotations=tuple(notes)))
    frontier = tuple(_list(data, "first_difference_frontier", str, name))
    if frontier != tuple(r.node for r in rows if r.verdict == "FIRST DIFFERENCE"):
        raise VerbReportUnreadable(
            f"{name}: the frontier is not the rows marked FIRST DIFFERENCE")
    unchecked = tuple(_list(data, "could_not_check_nodes", str, name))
    if unchecked != tuple(r.node for r in rows if r.verdict == "COULD NOT CHECK"):
        raise VerbReportUnreadable(f"{name}: could_not_check_nodes is not the rows marked so")
    counts = _object(data, "counts", name) or {}
    tally = {v: sum(1 for r in rows if r.verdict == v) for v in VERDICTS}
    if set(counts) != set(VERDICTS) or any(
            _decimal(counts, v, f"{name}: counts") != str(n) for v, n in tally.items()):
        raise VerbReportUnreadable(f"{name}: counts are not the ladder's own tally")
    performed = _decimal(data, "comparisons_performed", name)
    if performed != str(sum(1 for r in rows if r.verdict != "COULD NOT CHECK")):
        raise VerbReportUnreadable(f"{name}: comparisons_performed is not the rows compared")
    envelope = _closed(data.get("envelope"), ENVELOPES, f"{name}: envelope")
    expected = ("diverged" if frontier else "could not check" if unchecked else "identical")
    if envelope != expected:
        raise VerbReportUnreadable(f"{name}: envelope {envelope!r} where the ladder says "
                                   f"{expected!r}")
    return TwoRunDag(verb=verb, envelope=envelope, exit_code=_string(data, "exit", name),
                     reason=_optional(data, "reason"), ladder=tuple(rows),
                     first_difference_frontier=frontier, could_not_check_nodes=unchecked,
                     comparisons_performed=performed,
                     counts=tuple((v, counts[v]) for v in VERDICTS),
                     carried=tuple(_list(data, "carried", dict, name)))


def boundary_covers(report: TwoRun, row: LadderRow) -> bool:
    """029 §6: a ladder row is past a declared boundary.

    `verdict = COULD NOT CHECK` **and** the report's `boundary` is set **and** the row is at or
    after the boundary's index. All three, because a COULD NOT CHECK row before a boundary is
    unchecked for some other reason and must not borrow the boundary's sentence.
    """
    if row.verdict != "COULD NOT CHECK" or not report.boundary:
        return False
    try:
        return int(row.index) >= int(str(report.boundary.get("index")))
    except (TypeError, ValueError):
        raise VerbReportUnreadable(
            f"a boundary index that is not a decimal string: {report.boundary!r}") from None
