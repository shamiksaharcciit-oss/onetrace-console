"""The two views: a run's neighbours (`suggestions`) and the nearness ladder of a comparison (`ladder`).

Both read the derived file of vectors for the embedder in use (`batches.current`) and embed nothing.
Nearness is the cosine of two L2-normalised vectors. Where two digests are equal the nearness is 1.00 by
the record, and nothing is embedded or read for it. No threshold is fitted anywhere: the numbers are
shown and ordered, and nothing here says which difference changed anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: How a number was got.
BY_RECORD, BY_EMBEDDER = "record", "embedder"


@dataclass(frozen=True)
class Near:
    value: float
    how: str            # BY_RECORD or BY_EMBEDDER


def near(a, b, vectors: dict) -> Near | None:
    """The nearness of two parts (each with `.digest` and `.text`), or None where it can't be said: one
    side kept nothing, or a kept text is not embedded yet."""
    if a.digest == b.digest:
        return Near(1.0, BY_RECORD)
    if a.text is None or b.text is None or a.digest not in vectors or b.digest not in vectors:
        return None
    from onetrace_console.neighbours.batches import decode
    return Near(float(decode(vectors[a.digest]) @ decode(vectors[b.digest])), BY_EMBEDDER)


# ------------------------------------------------------------------------------ a run's neighbours

@dataclass(frozen=True)
class Row:
    other: object                 # the other StoredRun
    step: str
    name: str
    near: Near


@dataclass
class Suggestions:
    signature: str
    kept_nothing: bool = False
    rows: list = field(default_factory=list)
    not_embedded: int = 0

    @property
    def runs(self) -> int:
        return len({r.other.key for r in self.rows})


def suggestions(run, store) -> Suggestions | None:
    """The runs of `run`'s group whose kept inputs are near its own, nearest first; None where
    neighbours are not on here."""
    from onetrace_console.neighbours import active, batches, grouping, kept
    if not active(store):
        return None
    got = batches.current(store)
    if got is None:
        return None
    _who, vectors = got
    signature = grouping.signatures(store).get(run.key, "")
    mine = kept.kept_inputs(run, store)
    out = Suggestions(signature, kept_nothing=not mine)
    if not mine:
        return out
    order = {k: i for i, k in enumerate(grouping.signatures(store))}
    for key in grouping.group_of(store, run.key):
        other = store.get_run(key)
        if other is None:
            continue
        theirs = {(p.step, p.name): p for p in kept.kept_inputs(other, store)}
        for p in mine:
            q = theirs.get((p.step, p.name))
            if q is None:
                continue
            n = near(p, q, vectors)
            if n is None:
                out.not_embedded += 1
                continue
            out.rows.append(Row(other, p.step, p.name, n))
    out.rows.sort(key=lambda r: (-r.near.value, order.get(r.other.key, 0), r.step, r.name))
    return out


# ------------------------------------------------------------------------------ the nearness ladder

@dataclass(frozen=True)
class Rung:
    step: str
    inputs: Near | None           # None: "not kept"
    outputs: Near | None
    input_name: str = ""          # the least near input, where the step has more than one
    output_name: str = ""
    facts: tuple = ()             # what differs exactly at this step, as the records state it

    @property
    def drop(self) -> float | None:
        if self.inputs is None or self.outputs is None:
            return None
        return self.inputs.value - self.outputs.value


def _least(pairs, vectors) -> tuple[Near | None, str, int]:
    """The least near of a step's paired parts, by name; (None, "", n) where none can be said."""
    said = [(n, a.name) for a, b in pairs if (n := near(a, b, vectors)) is not None]
    if not said or len(said) < len(pairs):
        return None, "", len(pairs)
    n, name = min(said, key=lambda x: (x[0].value, x[1]))
    return n, name, len(pairs)


def _facts(ra: dict, rb: dict, pa, pb) -> tuple:
    """What differs exactly at one step: settings by name, the instrument, inputs and outputs by name."""
    from onetrace_console.run_index import _settings
    facts = []
    sa, sb = _settings(ra), _settings(rb)
    for k in sorted(sa.keys() | sb.keys()):
        if sa.get(k) != sb.get(k) and not k.startswith("onetrace."):
            facts.append(f"setting {k}: {sa.get(k, '(none)')} → {sb.get(k, '(none)')}")
    ia = ra.get("instrument") if isinstance(ra.get("instrument"), dict) else {}
    ib = rb.get("instrument") if isinstance(rb.get("instrument"), dict) else {}
    if any(ia.get(k) != ib.get(k) for k in ("id", "version", "config_digest")):
        facts.append("the instrument's configuration differs")
    names_in = sorted({a.name for a, b in pa if a.digest != b.digest})
    names_out = sorted({a.name for a, b in pb if a.digest != b.digest})
    if names_in:
        facts.append("input digest differs: " + ", ".join(names_in))
    if names_out:
        facts.append("output digest differs: " + ", ".join(names_out))
    return tuple(facts)


def ladder(comparison, store) -> list[Rung] | None:
    """Per step, the nearness of its inputs and of its outputs across the comparison's two runs; None
    where neighbours are not on here, or the two runs are not neighbours (another group, or either kept
    nothing)."""
    from onetrace_console.neighbours import active, batches, grouping, kept
    from onetrace_console.stage_pages import _stage_name, _steps
    if not active(store):
        return None
    a, b = store.get_run(comparison.run_a), store.get_run(comparison.run_b)
    if a is None or b is None or a.key == b.key:
        return None
    sig = grouping.signatures(store)
    if not sig.get(a.key) or sig.get(a.key) != sig.get(b.key):
        return None
    if not kept.kept_inputs(a, store) or not kept.kept_inputs(b, store):
        return None
    got = batches.current(store)
    if got is None:
        return None
    _who, vectors = got
    parts_a, parts_b = kept.parts(a, store), kept.parts(b, store)
    receipts_b = {_stage_name(s["receipt"]): s["receipt"] for s in _steps(b, store)}
    rungs = []
    for s in _steps(a, store):
        step = _stage_name(s["receipt"])
        if step not in receipts_b:
            continue

        def paired(kind):
            xa = {p.name: p for p in parts_a if p.step == step and p.kind == kind}
            xb = {p.name: p for p in parts_b if p.step == step and p.kind == kind}
            return [(xa[n], xb[n]) for n in xa if n in xb]

        pi, po = paired(kept.INPUT), paired(kept.OUTPUT)
        ni, name_i, count_i = _least(pi, vectors)
        no, name_o, count_o = _least(po, vectors)
        rungs.append(Rung(step, ni, no, name_i if count_i > 1 else "", name_o if count_o > 1 else "",
                          _facts(s["receipt"], receipts_b[step], pi, po)))
    return rungs


def largest_drop(rungs: list[Rung]) -> int | None:
    """The index of the rung with the largest drop from input to output nearness, the first on a tie;
    None where no rung has both numbers."""
    drops = [(r.drop, -i) for i, r in enumerate(rungs) if r.drop is not None]
    if not drops:
        return None
    return -max(drops)[1]
