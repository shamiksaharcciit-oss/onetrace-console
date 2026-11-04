"""A run's configuration against its pipeline's reference run, step by step, beside "What changed?".

The reference run. The run the pipeline's current sealed reference was made from: the first of the
reference's `made_from.run_ids`, where "current" is the reference `verdicts` would read a new
verdict against now (`verdicts.reference_record`). The section names that reference by its seal and
the run by its id, linked. Where the pipeline has no current reference the section says so and
compares nothing: it never falls back to a benchmark. On the reference run's own page it says this
run is the pipeline's reference run.

One source. Every item is read from the two runs' own receipts and records, never from the sealed
reference: the reference's settings were taken from the reference run, so they agree.

What is compared: the parts that should not change between runs, per step --
- the configuration fingerprint (the receipt's `instrument.config_digest`);
- the declared settings (the receipt's `assertions.constants`, without onetrace's own `onetrace.*`);
- the code fingerprint (`instrument.manifest_digest`);
- per model-call record, paired by name, the groups `onetrace.model_call.comparator` names:
  identity (`IDENTITY`), engine settings (`engine.settings.*`) and sampling settings (`sampling.*`);
- the policy version behind each decision the step cites, read from the held onedoor exports, only
  where both runs' rows are held.

The pipeline's declaration is not compared: the console groups runs into a pipeline by it, so two
runs of one pipeline always declare the same stages. Steps are paired by stage name and instance
(`name#instance`), in order. Inputs and outputs are not compared, and the section says so. An item
one record lacks reads "not recorded", never "same", and a model-call record the console's reader
refuses reads "not read", with its reason; a step only one run holds reads "not in the reference run"
or "not in this run".

A line names what differs as the records give it, and nothing about what produced it. The console
reads stored records only: no network calls. A public console draws the section only for the
demo's runs, and runs nothing: it reads the reference its build kept.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from onetrace_console.store import StoreError
from onetrace_console.words import NO_REFERENCE_YET, escape

HEADING = "Configuration against the reference"
WITHIN = "Runs are compared within their pipeline, as this console groups them by their declared stages."
AGAINST = "This run's configuration, step by step, against the pipeline's reference run, {run}: the run the reference {seal} was made from."
NOT_COMPARED = "Inputs and outputs are not compared here."
NO_REFERENCE = NO_REFERENCE_YET
#: Where no reference is held: the command that makes one, named as `verdicts` names it.
HOW_MADE = ("A reference is made by {command} from the pipeline's benchmark; on a local console, marking a "
            "run as a benchmark makes one.")
COMMAND = "python -m onetrace reference make"
OWN_RUN = "This run is the pipeline's reference run: the reference {seal} was made from it."
#: The run the reference names is not one this console holds.
NOT_HELD = "The reference {seal} was made from run {run_id}, which this console does not hold, so nothing is compared."
NON_CLAIMS = ("A configuration difference is a fact about the records, not a reason for any output.",
              "Equal configuration does not mean an equal environment: data sources and external services "
              "are not covered.")
#: A step's word.
SAME, DIFFERS = "configuration same", "configuration differs"
NOT_IN_REFERENCE, NOT_IN_THIS = "not in the reference run", "not in this run"
#: An item's word.
ITEM_SAME, ITEM_DIFFERS, NOT_RECORDED = "same", "differs", "not recorded"
#: Beside a policy version not recorded: where it is read from. "onedoor" is a word no page shows
#: (`tests/test_ux_screens.NOT_ON_A_PAGE`).
POLICY_NOT_HELD = "read only where both runs' decision rows are held in decision exports this console reads"
#: A model-call record a step holds but the console's reader refuses: its reason, never same.
NOT_READ = "not read"


@dataclass(frozen=True)
class Item:
    """One compared item at one step: its name as the records give it, its word, and each side's value
    ("" where that side records none)."""
    name: str
    word: str
    reference: str = ""
    this: str = ""
    note: str = ""


def _public() -> bool:
    from onetrace_console.frame import rendering_public
    return rendering_public()


def node_id(receipt: dict) -> str:
    """A step's stage name and instance, as "What changed?" pairs steps: `name#instance`."""
    stage = receipt.get("stage") if isinstance(receipt.get("stage"), dict) else {}
    name, inst = str(stage.get("name", "")), stage.get("instance")
    return f"{name}#{inst}" if inst else name


@dataclass(frozen=True)
class Step:
    node: str
    receipt: dict
    file: str
    read: object


def steps_of(run, store) -> list[Step]:
    """The run's steps in its chain's order, each with a reader of the run's own files."""
    from onetrace_console.stage_pages import _files, _read, _steps
    files = _files(run, store)
    return [Step(node_id(s["receipt"]), s["receipt"], s["file"], lambda path, files=files: _read(files, store, path))
            for s in _steps(run, store)]


def paired(ref_steps: list[Step], my_steps: list[Step]) -> list[tuple[str, Step | None, Step | None]]:
    """[(node, the reference run's step, this run's)], paired by node and, for a node met more than
    once, by its turn: the reference run's order, then this run's steps it does not hold."""
    def keyed(steps):
        seen, out = {}, []
        for s in steps:
            n = seen[s.node] = seen.get(s.node, 0) + 1
            out.append(((s.node, n), s))
        return out
    mine = dict(keyed(my_steps))
    out, used = [], set()
    for key, s in keyed(ref_steps):
        out.append((key[0], s, mine.get(key)))
        used.add(key)
    out += [(key[0], None, s) for key, s in keyed(my_steps) if key not in used]
    return out


def compare_values(name: str, ref, mine, note: str = "") -> Item:
    """One item from each side's value, None where that side records none."""
    if ref is None or mine is None:
        return Item(name, NOT_RECORDED, "" if ref is None else str(ref), "" if mine is None else str(mine), note)
    return Item(name, ITEM_SAME if ref == mine else ITEM_DIFFERS, str(ref), str(mine), note)


def _instrument(receipt: dict) -> dict:
    inst = receipt.get("instrument")
    return inst if isinstance(inst, dict) else {}


def _recorded(value):
    return value if isinstance(value, str) and value else None


def config_fingerprint(ref: Step, mine: Step, store) -> list[Item]:
    """The instrument's configuration fingerprint (`instrument.config_digest`)."""
    return [compare_values("configuration fingerprint", _recorded(_instrument(ref.receipt).get("config_digest")),
                           _recorded(_instrument(mine.receipt).get("config_digest")))]


def _constants(receipt: dict) -> dict:
    """The step's declared settings (`assertions.constants`), without onetrace's own `onetrace.*`."""
    assertions = receipt.get("assertions") if isinstance(receipt.get("assertions"), dict) else {}
    held = assertions.get("constants") if isinstance(assertions.get("constants"), dict) else {}
    return {k: v for k, v in held.items() if isinstance(k, str) and not k.startswith("onetrace.")}


def declared_settings(ref: Step, mine: Step, store) -> list[Item]:
    """Each declared setting either run's step records, by name: a name one lacks is not recorded."""
    import json
    a, b = _constants(ref.receipt), _constants(mine.receipt)
    shown = lambda v: v if isinstance(v, str) else json.dumps(v, sort_keys=True)  # noqa: E731
    return [compare_values(f"declared setting {k}", shown(a[k]) if k in a else None, shown(b[k]) if k in b else None)
            for k in sorted(set(a) | set(b))]


def code_fingerprint(ref: Step, mine: Step, store) -> list[Item]:
    """The fingerprint of the code that ran the step (`instrument.manifest_digest`)."""
    return [compare_values("code fingerprint", _recorded(_instrument(ref.receipt).get("manifest_digest")),
                           _recorded(_instrument(mine.receipt).get("manifest_digest")))]


def _records(step: Step) -> dict:
    """{name: the record, or `model_call.Refused` with its reason} for each of the step's outputs named
    like a model-call record, read as the step's page reads them (`model_call.read_output`)."""
    from onetrace_console import model_call
    out = {}
    for o in model_call.outputs(step.receipt):
        try:
            out[str(o["name"])] = model_call.read_output(step.file, o, step.read)
        except model_call.Refused as e:
            out[str(o["name"])] = e
    return out


def _fields(a: dict, b: dict) -> list[str]:
    """The comparator's groups, in its order: identity, then engine settings, then sampling settings."""
    from onetrace.model_call.comparator import IDENTITY
    keys = list(a) + list(b)
    return (list(IDENTITY) + sorted({k for k in keys if k.startswith("engine.settings.")})
            + sorted({k for k in keys if k.startswith("sampling.")}))


def _field(name: str, a, b) -> Item:
    """One field of two paired records. A value is recorded where its state is observed or declared
    (as the comparator reads one); otherwise the line says not recorded, with each side's state."""
    from onetrace.model_call.comparator import pair
    from onetrace.model_call.record import DECLARED, OBSERVED
    has = lambda v: isinstance(v, dict) and v.get("status") in (OBSERVED, DECLARED) and "value" in v  # noqa: E731
    shown = lambda v: str(v["value"]) if has(v) else None  # noqa: E731
    if has(a) and has(b):
        word = ITEM_SAME if pair(a, b) == "equal" else ITEM_DIFFERS
        return Item(name, word, shown(a), shown(b))
    state = lambda v: str(v.get("status")) if isinstance(v, dict) else "absent"  # noqa: E731
    return Item(name, NOT_RECORDED, shown(a) or "", shown(b) or "",
                f"reference run {state(a)}, this run {state(b)}")


def model_calls(ref: Step, mine: Step, store) -> list[Item]:
    """Each model-call record the step holds, paired by name: its identity, engine settings and sampling
    settings, as `onetrace.model_call.comparator` groups them. A record one step lacks is not recorded."""
    a, b = _records(ref), _records(mine)
    out = []
    for name in list(dict.fromkeys([*a, *b])):
        ra, rb = a.get(name), b.get(name)
        if ra is None or rb is None:
            out.append(Item(f"model-call record {name}", NOT_RECORDED, "" if ra is None else name,
                            "" if rb is None else name))
        elif isinstance(ra, Exception) or isinstance(rb, Exception):
            why = "; ".join(f"{side}: {e}" for side, e in (("reference run", ra), ("this run", rb))
                            if isinstance(e, Exception))
            out.append(Item(f"model-call record {name}", NOT_READ, note=why))
        else:
            out += [_field(f"{name} {f}", ra.get(f), rb.get(f)) for f in _fields(ra, rb)]
    return out


def _onedoor_on() -> bool:
    """Whether this render is a console's with the onedoor extension on: a console with it off never
    imports the extension (`tests/test_onedoor_ext_isolation.py`), so it holds no policy version here."""
    from onetrace_console.frame import _RENDERING
    r = _RENDERING.get()
    return bool(r is not None and r.onedoor)


def policy_version(ref: dict, store) -> str | None:
    """The policy version on the held onedoor export row a decision reference names: the row with its
    request id and its decision digest, as the Decisions cited panel joins them (`decision_refs`), and
    only where every stored copy of the row matches its delivery. None where no such row is held."""
    if not _onedoor_on() or not (store.root / "decision_exports").is_dir():
        return None
    from onetrace_console.onedoor_ext.policy_pages import all_decisions
    want, digest = ref.get("request_id"), ref.get("decision_digest")
    for d in all_decisions(store):
        if d.request_id != want:
            continue
        row = next((r for r in d.rows if r.decision_digest == digest), None)
        if row is None or d.couldnt_check(row) is not None:
            return None
        v = row.fields.get("policy_version")
        return v if isinstance(v, str) and v else None
    return None


def policies(ref: Step, mine: Step, store) -> list[Item]:
    """The policy version behind each decision the step cites, paired in call order; a line only where
    either run's step cites one. Read only where both runs' rows are held in onedoor exports."""
    from onetrace_console.onedoor_panel import decisions
    a, b = decisions(ref.receipt) or [], decisions(mine.receipt) or []
    refs = lambda ds: [d.get("ref") if isinstance(d.get("ref"), dict) else {} for d in ds]  # noqa: E731
    a, b = refs(a), refs(b)
    out = []
    for n in range(max(len(a), len(b))):
        va = policy_version(a[n], store) if n < len(a) else None
        vb = policy_version(b[n], store) if n < len(b) else None
        note = POLICY_NOT_HELD if va is None or vb is None else ""
        out.append(compare_values(f"policy version behind decision {n + 1}", va, vb, note))
    return out


#: Each compared item, in the order a step lists them.
ITEMS = (config_fingerprint, declared_settings, code_fingerprint, model_calls, policies)


def compare_step(ref: Step, mine: Step, store) -> list[Item]:
    return [item for read in ITEMS for item in read(ref, mine, store)]


def step_word(items: list[Item]) -> str:
    """"configuration differs" where any item differs; "configuration same" otherwise, with each item
    not recorded named under it, never counted as same."""
    return DIFFERS if any(i.word == ITEM_DIFFERS for i in items) else SAME


# ---- which reference run ------------------------------------------------------------------------

def reference_run(run, store, *, compute: bool):
    """(the pipeline's current reference record or None, its reference run or None). The run is the
    first of the sealed reference's `made_from.run_ids`, among the runs the console made it from."""
    from onetrace_console import verdicts
    pipeline = verdicts.pipeline_of(run, store)
    if pipeline is None:
        return None, None
    ref = verdicts.reference_record(pipeline, store, compute=compute)
    doc = (ref or {}).get("reference")
    if not isinstance(doc, dict):
        return ref, None
    made = doc.get("made_from") if isinstance(doc.get("made_from"), dict) else {}
    ids = made.get("run_ids") if isinstance(made.get("run_ids"), list) else []
    if not ids:
        return ref, None
    for key in ref.get("runs") or []:
        try:
            held = store.get_run(key)
        except StoreError:
            continue
        if held is not None and held.run_id == ids[0]:
            return ref, held
    return ref, None


def _demo_folders() -> set[str]:
    from onetrace_console.demo_store import runs
    return {spec.folder for spec in runs()}


def _demo(run) -> bool:
    return bool(run.folder) and Path(run.folder).name in _demo_folders()


# ---- drawn -------------------------------------------------------------------------------------

def _value_html(value: str) -> str:
    from onetrace_console.trace_panel import code_or_fold
    return code_or_fold(value) if value else ""


def _item_html(item: Item) -> str:
    if item.word == ITEM_DIFFERS:
        said = (f"{escape(item.name)} differs: reference run {_value_html(item.reference)}, "
                f"this run {_value_html(item.this)}")
    elif item.word == NOT_READ:
        said = f"{escape(item.name)}: {escape(NOT_READ)}"
    elif item.word == NOT_RECORDED:
        where = ("in neither run" if not item.reference and not item.this
                 else "in the reference run" if not item.reference else "in this run")
        said = f"{escape(item.name)}: {escape(NOT_RECORDED)} {escape(where)}"
    else:
        said = f"{escape(item.name)}: {escape(ITEM_SAME)}"
    note = f" ({escape(item.note)})" if item.note else ""
    return f'<li data-config-item="{escape(item.name)}" data-config-word="{escape(item.word)}">{said}{note}</li>'


def _step_html(node: str, ref: Step | None, mine: Step | None, store) -> str:
    if ref is None or mine is None:
        word = NOT_IN_REFERENCE if ref is None else NOT_IN_THIS
        return (f'<li data-config-step="{escape(node)}" data-config-word="{escape(word)}">'
                f"<code>{escape(node)}</code>: {escape(word)}</li>")
    items = compare_step(ref, mine, store)
    word = step_word(items)
    differs = [i.name for i in items if i.word == ITEM_DIFFERS]
    head = f"{escape(word)}: {escape(', '.join(differs))}" if differs else escape(word)
    return (f'<li data-config-step="{escape(node)}" data-config-word="{escape(word)}"><code>{escape(node)}</code>: '
            f'{head}<ul class="plain">{"".join(_item_html(i) for i in items)}</ul></li>')


def section(run, store, *, up: str = "../../") -> str:
    """The run page's configuration against its pipeline's reference run; "" on a public console for a
    run that is not the demo's, and where the run belongs to no pipeline."""
    from onetrace_console.viewer.page import fingerprint_html
    from onetrace_console.words import run_named
    public = _public()
    if public and not _demo(run):
        return ""
    try:
        ref, other = reference_run(run, store, compute=not public)
    except (StoreError, ValueError):
        return ""
    from onetrace_console import verdicts
    if verdicts.pipeline_of(run, store) is None:
        return ""
    out = (f'<section data-section="config-compare" class="config-compare"><h2>{escape(HEADING)}</h2>'
           f'<p data-config="within">{escape(WITHIN)}</p>')
    doc = (ref or {}).get("reference")
    if not isinstance(doc, dict):
        h, t = HOW_MADE.split("{command}")
        out += (f'<p data-config="no-reference">{escape(NO_REFERENCE)}</p>'
                f'<p data-config="how-made">{escape(h)}<code>{escape(COMMAND)}</code>{escape(t)}</p>')
        if ref is not None and (ref.get("refused") or ref.get("note")):
            out += f"<p>{escape(verdicts.NO_REFERENCE.format(why=ref.get('refused') or ref.get('note')))}</p>"
        return out + "</section>"
    seal = str(doc.get("seal", ""))
    if other is None:
        made = doc.get("made_from") if isinstance(doc.get("made_from"), dict) else {}
        first = (made.get("run_ids") or [""])[0]
        h, t = NOT_HELD.split("{seal}")
        return (out + f'<div data-config="not-held">{escape(h)}{fingerprint_html(seal)}'
                f'{escape(t.format(run_id=first))}</div></section>')
    if other.key == run.key:
        h, t = OWN_RUN.split("{seal}")
        return out + f'<div data-config="own-run">{escape(h)}{fingerprint_html(seal)}{escape(t)}</div></section>'
    if public and not _demo(other):
        return ""
    named = f'<a href="{up}runs/{escape(other.key)}/case.html" data-config-reference-run>{run_named(store, other.key)}</a>'
    head, rest = AGAINST.split("{run}")
    mid, tail = rest.split("{seal}")
    #: A seal's fold is a box of its own, never inside a paragraph (`tests/test_short_fingerprints.py`).
    out += (f'<div data-config="against">{escape(head)}{named}{escape(mid)}{fingerprint_html(seal)}{escape(tail)}</div>'
            f'<p data-config="not-compared">{escape(NOT_COMPARED)}</p>')
    try:
        pairs = paired(steps_of(other, store), steps_of(run, store))
    except (StoreError, ValueError):
        return ""
    out += f'<ul class="plain" data-config-steps>{"".join(_step_html(n, a, b, store) for n, a, b in pairs)}</ul>'
    out += f'<ul class="plain" data-config-non-claims>{"".join(f"<li>{escape(c)}</li>" for c in NON_CLAIMS)}</ul>'
    return out + "</section>"
