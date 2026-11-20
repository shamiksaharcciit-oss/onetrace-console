"""The exact run index: a derived file beside the store, and the query over it.

The index is rebuilt from the records the store holds, never a source of truth: deleting it and
rebuilding it gives the same file, byte for byte. It is written whenever the console draws its pages
(at a store's build, at start, and after each new run, comparison or benchmark mark), and a public
console reads the one its build wrote and never writes it.

What it holds, per run, each as the record states it: the run's ids, its chain head, each step's
name, outcome, instrument (its id, version and configuration digest), settings
(`assertions.constants`, by recorded name and value), inputs and outputs (name and digest); the
manifest's declarations; the verifier's verdict and the names of its
rows that read FAIL or NOT-RUN; the model-call records' fields where a step's output holds one; and
whether a person marked the run as a benchmark (`benchmarks`); and each step's store writes in format 0.5 (the store,
the key's digest or the key where the record keeps it in plain, the version and the digest), for lineage
(`store_state`); the run's origin, where its record names one (`service_link`); and each step's tokens and cost as
its model-call records hold them (`usage`). Per held comparison: the first
differing step and what differed there, from the comparison's own short answer data. No text is
indexed and no kept input is read.

The query is a list of terms, each a field the record names, every term required (`GRAMMAR`). Each
result names the fields that matched, as recorded. A query reads the index and nothing else: it runs
no check, no comparison and no model.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

from onetrace_console.bounded_json import load_json_bounded

#: 0.2 adds each step's `instrument.config_digest` (`store_read` reads runs by it); 0.3 each step's kind and own
#: agent, and the run's agent, as a format 0.5 record holds them (`step_kinds`); and each step's store writes
#: (`state_writes`), for lineage. 0.3 had not been released when it gained the writes, so it is still 0.3: an index
#: written before it did lacks `LINEAGE`, and a page that would read lineage from one says so.
FORMAT = "onetrace-console-run-index/0.3"
#: The index's own member saying it holds each step's store writes: an index without it was written before it did.
LINEAGE = "lineage"
#: The index's own member saying it holds each step's tokens and cost (`usage`): an index without it was written
#: before it did.
USAGE = "usage"
#: The index's own member saying each run holds its list entry (`LIST`): the words the runs list shows of it, which the
#: Runs page (`runs_page`) draws and the terms `agree:`, `word:`, `after:` and `before:` read. An index without it was
#: written before it did.
LIST = "list"
#: The terms that read a run's list entry.
LIST_TERMS = ("agree", "word", "after", "before")
#: "Records agree", as every page reads it (`records.state`).
AGREE_STATES = ("yes", "no", "couldnt-check", "not-checked")
#: The verifier's rows on a receipt whose writes are not indexed where they FAIL (`store_state`).
WRITE_ROWS = ("state entries", "state_writes against effect_label")
#: The derived file, beside the store's own folder under the store root.
FILE_NAME = "run_index.json"
#: The manifest's declarations the index keeps, each as written.
DECLARATIONS = (
    "optional_stages",
    "gated_stages",
    "outputs_kept",
    "traceparent",
    "parent_run",
    "parent_stage",
    "repeat_of",
)
#: The model-call record's fields the index keeps: (the index's name, the record's field).
MODEL_FIELDS = (
    ("model", "model.reported"),
    ("weights", "model.files_digest"),
    ("engine", "engine.name"),
    ("engine_version", "engine.version"),
    ("dtype", "dtype"),
    ("batch_invariant", "batch.batch_invariant"),
)
#: What can differ at a comparison's first-difference step, in the short answer's words.
KINDS = ("setting", "input", "configuration", "output")
#: The query's term for the console's own pipeline (P1, P2, ...): the index names it `pipeline_label`, as
#: the stored run's own `pipeline` field is another thing and is not read.
PIPELINE = "pipeline"
#: The row results the index keeps by name.
ROW_RESULTS = ("FAIL", "NOT-RUN")

GRAMMAR = (
    ("setting:<step>.<name>=<value>", "a step's recorded setting; * for any step"),
    ("input:<name>=<digest>", "a step's input by name and digest"),
    ("inputs:same-as:<run>", "every input of the first step equal to that run's"),
    ("first_diff:<step>", "a held comparison of the run first differs at that step"),
    ("first_diff:any:<kind>", "...and a " + ", ".join(KINDS[:-1]) + " or " + KINDS[-1] + " differs there"),
    ("diff:same-as:<run>", "first differs from the same baseline, at the same step, in the same way"),
    ("verdict:<word>", "the verifier's verdict, PASS or FAIL"),
    ('row:"<name>"=<result>', "a row of the verifier's that read FAIL or NOT-RUN"),
    ("model:<field>=<value>", "a model-call record's field: " + ", ".join(n for n, _ in MODEL_FIELDS)),
    ("engine:<name>", "a model-call record's engine"),
    ("gated:<step>", "a step the manifest declares gated"),
    ("pipeline:<id>", "the console's pipeline, P1, P2, ..."),
    ("since:<run>", "runs that arrived after that run"),
    ("benchmark:yes|no", "marked as a benchmark, or not"),
    ("kind:<kind>", "a step's recorded kind, format 0.5: a hyphen for a space, as kind:tool-call"),
    ("agent:<name>", "the run's agent, or a step's own, format 0.5"),
    ("agree:yes|no|couldnt-check|not-checked", "whether the records agree, as every page reads it"),
    ("word:<word>", "the run's verdict against its pipeline's reference, in onetrace's word"),
    ("after:<date or time>", "runs whose record starts after that time, or on or after that day"),
    ("before:<date or time>", "runs whose record starts before that time, or before that day"),
)


class QueryError(ValueError):
    """A query the index cannot answer, said in words."""


# ------------------------------------------------------------------------------- building


def _settings(receipt: dict) -> dict:
    assertions = receipt.get("assertions")
    constants = assertions.get("constants") if isinstance(assertions, dict) else None
    if not isinstance(constants, dict):
        return {}
    return {str(k): v if isinstance(v, str) else json.dumps(v, sort_keys=True) for k, v in constants.items()}


def _named(items) -> list:
    return [[str(i.get("name", "")), str(i.get("digest", ""))] for i in items or [] if isinstance(i, dict)]


def _model_calls(receipt: dict, receipt_file: str, files: dict, store) -> list:
    """Each model-call record a step's outputs hold, its fields as the record states them, where its
    stored bytes match the receipt and the record reads (`model_call.read_output`, the 1.0 reader);
    refused ones say why."""
    from onetrace_console import model_call
    from onetrace_console.stage_pages import _read

    out: list[dict[str, object]] = []
    for o in model_call.outputs(receipt):
        name = str(o["name"])
        try:
            record = model_call.read_output(receipt_file, o, lambda path: _read(files, store, path))
        except model_call.Refused as e:
            out.append({"file": name, "refused": str(e)})
            continue
        fields: dict[str, dict[str, str]] = {}
        for short, path in MODEL_FIELDS:
            #: model-call-record/1.0 names its fields with dots, flat (`engine.name`).
            v = record.get(path)
            if isinstance(v, dict) and "status" in v:
                kept = {k: str(v[k]) for k in ("value", "declared") if isinstance(v.get(k), (str, int, float))}
                if kept:
                    fields[short] = {"status": str(v["status"]), **kept}
        out.append({"file": name, "fields": fields})
    return out


def _check(run, store) -> tuple[str, dict]:
    """The verifier's verdict word and its FAIL and NOT-RUN rows by name, from the stored check."""
    from onetrace_console.info_mark import rows_of
    from onetrace_console.pages import _envelope

    try:
        envelope = _envelope(run, store, required=False)
    except Exception:  # noqa: BLE001 - a check that can't be read gives no verdict here
        return "", {}
    summary: dict = {}
    part = envelope.get("rows_json") if isinstance(envelope, dict) else None
    try:
        doc = load_json_bounded(part.get("stdout", ""), "the check's rows") if isinstance(part, dict) else None
        summary = _summary if isinstance(doc, dict) and isinstance(_summary := doc.get("summary"), dict) else {}
    except (ValueError, RecursionError):
        summary = {}
    rows: dict[str, list[str]] = {}
    for row in rows_of(envelope):
        result = str(row.get("result", ""))
        if result in ROW_RESULTS:
            rows.setdefault(result, []).append(str(row.get("name", "")))
    return str(summary.get("result", "")), rows


def _run_entry(run, order: int, label: str, store) -> dict:
    from onetrace_console.stage_pages import _files, _read, _steps

    files = _files(run, store)
    try:
        manifest = load_json_bounded(
            (_read(files, store, "MANIFEST.json") or b"{}").decode("utf-8"), "MANIFEST.json", "show"
        )
    except (ValueError, UnicodeDecodeError, RecursionError):
        manifest = {}
    manifest = manifest if isinstance(manifest, dict) else {}
    try:
        steps = _steps(run, store)
    except Exception:  # noqa: BLE001 - a record that can't be read is indexed by its ids alone
        steps = []
    verdict, rows = _check(run, store)
    failing = set(rows.get("FAIL", []))
    from onetrace_console import step_kinds, usage

    entries = []
    for s in steps:
        receipt = s["receipt"]
        stage = _stage if isinstance(_stage := receipt.get("stage"), dict) else {}
        instrument = _instrument if isinstance(_instrument := receipt.get("instrument"), dict) else {}
        outcome = _outcome if isinstance(_outcome := receipt.get("outcome"), dict) else {}
        entry: dict = {
            "name": str(stage.get("name", "")),
            "index": str(s["index"]),
            "outcome": str(outcome.get("class", "")),
            "instrument": {
                "id": str(instrument.get("id", "")),
                "version": str(instrument.get("version", "")),
                "config_digest": str(instrument.get("config_digest", "")),
            },
            "settings": _settings(receipt),
            "inputs": _named(receipt.get("inputs")),
            "outputs": _named(receipt.get("outputs")),
        }
        calls = _model_calls(receipt, s["file"], files, store)
        if calls:
            entry["model_calls"] = calls
        if step_kinds.holds_members(receipt):
            kind = (receipt.get("step") or {}).get("kind") if isinstance(receipt.get("step"), dict) else None
            if isinstance(kind, str) and not failing & {f"{s['file']}: {n}" for n in step_kinds.KIND_ROWS}:
                entry["kind"] = kind
            agent = receipt.get("agent")
            if isinstance(agent, dict) and isinstance(agent.get("name"), str) and f"{s['file']}: agent" not in failing:
                entry["agent"] = agent["name"]
            #: Each model-call record's tokens and cost, as recorded, with its model (`usage`); none where the
            #: verifier FAILs the step's `model_usage`.
            if f"{s['file']}: model_usage" not in failing:
                models = {
                    c["file"]: c["fields"]["model"]["value"]
                    for c in calls
                    if isinstance(c.get("fields"), dict)
                    and c["fields"].get("model", {}).get("status") == "observed"
                    and isinstance(c["fields"]["model"].get("value"), str)
                }
                used = [{**e, "model": models.get(e["record"])} for e in usage.entries(receipt)]
                if used:
                    entry["usage"] = used
            writes = _writes(receipt)
            if writes and not failing & {f"{s['file']}: {n}" for n in WRITE_ROWS}:
                entry["state_writes"] = writes
        entries.append(entry)
    run_agent = next(
        (
            r["receipt"]["run_agent"].get("name")
            for r in steps
            if step_kinds.holds_members(r["receipt"]) and isinstance(r["receipt"].get("run_agent"), dict)
        ),
        None,
    )
    from onetrace_console.benchmarks import mark_of

    return {
        "key": run.key,
        "run_id": run.run_id,
        "pipeline_label": label,
        "order": order,
        "chain_head": run.chain_head,
        "folder": run.folder,
        "steps": entries,
        "declared": {k: manifest[k] for k in DECLARATIONS if k in manifest},
        "verdict": verdict,
        "rows": rows,
        "benchmark": mark_of(store, run.key),
        LIST: _list_entry(run, store),
        **({"run_agent": run_agent} if isinstance(run_agent, str) and step_kinds.RUN_AGENT_ROW not in failing else {}),
        **({"origin": origin} if isinstance(origin := _origin(run, store), str) else {}),
    }


def _gated(run, store) -> int:
    from onetrace_console.authorization_list import gated_count

    return gated_count(run, store)


def _origin(run, store) -> str | None:
    """The run's origin, as its record names it (`service_link.origin_of`); None where it can't be said."""
    from onetrace_console import service_link

    try:
        return service_link.index_origin(run, store)
    except Exception:  # noqa: BLE001 - a record that can't be read names no origin
        return None


def first_difference(comparison, store) -> dict | None:
    """Where a held comparison's runs first differ and what differs there, from the stored diff report
    as its short answer reads it: {"steps": [...], "kinds": [...], "settings": [...], "inputs": [...]};
    None where the report cannot be read, and empty steps where nothing differs."""
    from onetrace_console import render, short_answer
    from onetrace_console.viewer.verbs import TwoRunDag

    got = render.read_diff(comparison, store)
    if got is None:
        return None
    report, annotations = got
    ladder = list(report.ladder)
    notes = {str(n.get("index")): n for n in annotations if isinstance(n, dict)}
    if isinstance(report, TwoRunDag):
        try:
            edges = render._union_edges(comparison, store)
        except ValueError:
            edges = None
        steps = [r.node for r in ladder if r.verdict == "FIRST DIFFERENCE"] or short_answer.begins(ladder, edges)
        #: Each start by its place in the ladder, from 1, as `render.dag_annotations` numbers them.
        places = [(s, str(next(n for n, r in enumerate(ladder, start=1) if r.node == s))) for s in steps]
    else:
        rows = [r for r in ladder if r.verdict == "FIRST DIFFERENCE"][:1]
        steps = [r.stage for r in rows]
        places = [(r.stage, str(r.index)) for r in rows]
    a = render._receipts_in_order(comparison.run_a, store)
    b = render._receipts_in_order(comparison.run_b, store)
    ins_a, ins_b = (render.own_inputs(a), render.own_inputs(b)) if a and b else ({}, {})
    settings, inputs, kinds = [], [], []
    for step, place in places:
        stage = str(step).split("#", 1)[0]
        differs = (notes.get(place) or {}).get("differs") or {}
        named, prints = short_answer._split(differs)
        x, y = ins_a.get(stage, {}), ins_b.get(stage, {})
        changed = sorted(n for n in x.keys() | y.keys() if x.get(n) != y.get(n))
        settings += [name for name, _old, _new in named]
        inputs += changed
        kinds += (
            (["setting"] if named else [])
            + (["input"] if changed else [])
            + (["configuration"] if prints and not named else [])
        )
    if steps and not kinds:
        kinds = ["output"]
    return {
        "steps": [str(s).split("#", 1)[0] for s in steps],
        "kinds": sorted(set(kinds), key=KINDS.index),
        "settings": sorted(set(settings)),
        "inputs": sorted(set(inputs)),
    }


def build(store) -> dict:
    """The index of every run and held comparison the store holds, in the console's order of runs."""
    from onetrace_console.overview import pipelines
    from onetrace_console.store import arrival_order

    with store.reading():
        label = {r.key: p.label for p in pipelines(store) for r in p.runs}
        runs = [
            _run_entry(r, i, label.get(r.key, ""), store)
            for i, r in enumerate(arrival_order(store.runs(), newest_first=False))
        ]
        _with_drift(runs, store)
        comparisons = []
        for c in sorted(store.comparisons(), key=lambda c: c.key):
            try:
                first = first_difference(c, store)
            except Exception:  # noqa: BLE001 - a report that can't be read gives no first difference
                first = None
            comparisons.append(
                {
                    "key": c.key,
                    "a": c.run_a,
                    "b": c.run_b,
                    **({"first_diff": first} if first is not None else {"unread": True}),
                }
            )
    return {
        "format": FORMAT,
        LINEAGE: "state_writes",
        USAGE: "model_usage",
        LIST: "runs_list",
        "runs": runs,
        "comparisons": comparisons,
    }


def _with_drift(runs: list[dict], store) -> None:
    """Each run's place in its pipeline's kept drift report against the first run (`drift_strip.kept`), in its list
    entry: the report made where none is kept on a local console, never on a public one, as the drift page makes it.
    A pipeline whose report can't be read or made leaves its runs with none: not compared."""
    from onetrace_console import drift, drift_strip
    from onetrace_console.frame import rendering_public
    from onetrace_console.overview import pipelines

    by_key = {r["key"]: r for r in runs}
    for p in pipelines(store):
        try:
            rec = drift.drift_record(store, p, "first", compute=not rendering_public())
            rep = drift.report_of(rec, store) if rec is not None else None
        except Exception:  # noqa: BLE001 - a report that can't be read or made leaves each run not compared
            rep = None
        if rep is None:
            continue
        for key, entry in drift_strip.kept(rep, list(p.runs)).items():
            if key in by_key:
                by_key[key][LIST]["drift"] = entry


def _list_entry(run, store) -> dict:
    """What the runs list shows of a run, by the rules it draws them by (`pages.runs_table`, `pages.verdict_pill`), as
    states and recorded values, never as a page's markup: so the Runs page draws from the index alone."""
    from onetrace_console import overview, rerun_label, verdicts
    from onetrace_console.frame import rendering_public
    from onetrace_console.pages import run_answers

    try:
        row = load_json_bounded(run.list_row, "the run's list row") if run.list_row else {}
    except ValueError:
        row = {}
    ran = row.get("case_ran") if isinstance(row, dict) else None
    #: As the runs list's pill: made where none is kept on a local console, never on a public one.
    try:
        verdicts.verdict_record(run, store, compute=not rendering_public())
    except Exception:  # noqa: BLE001 - a verdict that cannot be made is not listed; the run's page says why
        pass
    try:
        pipeline = verdicts.pipeline_of(run, store)
        unchecked = bool(
            verdicts.unchecked(run, store)
            and pipeline is not None
            and verdicts.reference_record(pipeline, store, compute=False) is not None
        )
        got = None if unchecked else verdicts.word_of(run, store)
        seal = verdicts.seal_of(run, store) if got else None
    except Exception:  # noqa: BLE001 - as above
        unchecked, got, seal = False, None, None
    declined = overview.declined(run)
    return {
        "ran": ran if isinstance(ran, str) else "",
        "received": run.received_at,
        "delivered": run.delivered_stages,
        "stages": run.stage_count,
        "retries": run.retries,
        "declined": str(declined["stage"]) if declined else "",
        "ending": run.ending,
        "kinds": run.kinds,
        #: How many gated steps the record names (`authorization_list`): the runs list's mark. An index written before
        #: this field marks none until it is built again, as a console does when it next draws its pages.
        "gated": _gated(run, store),
        "steps": _steps_kept(run),
        "rerun": rerun_label.of_run(run),
        **run_answers(run, store),
        "unchecked": unchecked,
        "word": got[0] if got else "",
        "word_at": got[1] if got else "",
        "seal": seal or "",
    }


def _steps_kept(run) -> list | None:
    """The run's kept steps (`step_marks`), or None where none are kept or they don't read."""
    try:
        got = load_json_bounded(run.steps, "the run's steps") if run.steps else None
    except ValueError:
        return None
    return got if isinstance(got, list) else None


def _writes(receipt: dict) -> list[dict]:
    """A step's store writes as the index keeps them: store, the key's digest or the key in plain, version, digest."""
    out = []
    for e in receipt.get("state_writes") or [] if isinstance(receipt.get("state_writes"), list) else []:
        if not isinstance(e, dict) or not isinstance(e.get("store"), str):
            continue
        w = {"store": e["store"]}
        for k in ("key_digest", "key", "version", "digest"):
            if isinstance(e.get(k), str):
                w[k] = e[k]
        out.append(w)
    return out


#: The index a drawing of the store's pages reads (`drawing`), so a page asks the index, never the store's records; and
#: when that index was written, so a page drawn from it says so.
_DRAWING: ContextVar[dict | None] = ContextVar("run_index_drawing", default=None)
_WRITTEN: ContextVar[str] = ContextVar("run_index_written", default="")
FROM_INDEX = "Read from the run index ({format}), written {written}."


@contextmanager
def drawing(index: dict, written: str = ""):
    """Pages drawn inside read `index` (`drawn_with`), written at `written` (`index_note`)."""
    token, wtoken = _DRAWING.set(index), _WRITTEN.set(written)
    try:
        yield index
    finally:
        _DRAWING.reset(token)
        _WRITTEN.reset(wtoken)


def drawn_with() -> dict | None:
    """The index the pages being drawn read; None outside a drawing."""
    return _DRAWING.get()


def drawn_written() -> str:
    """When the index the pages being drawn read was written; "" outside a drawing, or where it isn't known."""
    return _WRITTEN.get()


def index_note() -> str:
    """On a page drawn from the index: its format and when it was written, so a page drawn from an index written
    before the store last changed reads as such. Nothing outside a drawing."""

    index = _DRAWING.get()
    if index is None:
        return ""
    return f'<p class="note" data-section="from-index">{from_index_html(index, _WRITTEN.get())}</p>'


def from_index_html(index: dict, written: str) -> str:
    """FROM_INDEX as a page says it: the time the index was written in the page's one form, inside `<time>`."""
    from onetrace_console.words import escape, time_html

    before, after = FROM_INDEX.split("{written}")
    shown = time_html(written) if written else escape("at a time not known")
    return escape(before.format(format=str(index.get("format", "")))) + shown + escape(after)


def written_at(store_root: Path) -> str:
    """When the index beside the store was last written, from its file; "" where there is none."""
    from datetime import datetime

    try:
        stamp = (Path(store_root) / FILE_NAME).stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(stamp, UTC).isoformat(timespec="seconds")


def key_digest(key: str) -> str:
    """A key kept in plain, as its digest: onetrace's own rule, sha256 over the key's UTF-8 (`onetrace.state.key_bytes`;
    a key kept in plain is a string)."""
    import hashlib

    return "sha256:" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_match(a: dict, b: dict) -> str | None:
    """How two entries' keys match: "exact" where both are kept alike and equal; "digest" where one is kept in plain and
    the other as a digest, and the plain key's digest is the other's; None where they don't. A plain key is never
    compared with a digest as text."""
    pa, pb = a.get("key"), b.get("key")
    da, db = a.get("key_digest"), b.get("key_digest")
    if isinstance(pa, str) and isinstance(pb, str):
        return "exact" if pa == pb else None
    if isinstance(da, str) and isinstance(db, str):
        return "exact" if da == db else None
    if isinstance(pa, str) and isinstance(db, str):
        return "digest" if key_digest(pa) == db else None
    if isinstance(da, str) and isinstance(pb, str):
        return "digest" if da == key_digest(pb) else None
    return None


def wrote(index: dict, run_key: str, read: dict) -> list[tuple[dict, dict, dict, str, str]]:
    """Each (run, step, write, how) of another run in `index` whose write holds, for the read's store and key, an equal
    version (not `not observed`) or an equal digest; `how` is "version" or "digest". Lineage is that equality alone."""
    out = []
    for run in index.get("runs") or []:
        if run.get("key") == run_key:
            continue
        for step in run.get("steps") or []:
            for w in step.get("state_writes") or []:
                keyed = key_match(read, w) if w.get("store") == read.get("store") else None
                if keyed is None:
                    continue
                if (
                    isinstance(read.get("version"), str)
                    and read["version"] != "not observed"
                    and read["version"] == w.get("version")
                ):
                    out.append((run, step, w, "version", keyed))
                elif isinstance(read.get("digest"), str) and read["digest"] == w.get("digest"):
                    out.append((run, step, w, "digest", keyed))
    return out


def encode(index: dict) -> bytes:
    return (json.dumps(index, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def write(store, store_root: Path, index: dict | None = None) -> Path:
    """Write the index beside the store (`index`, where the drawing built it, or built now), replacing the last one
    whole."""
    from onetrace_console import forwarding
    from onetrace_console.store import _atomic_write

    path = Path(store_root) / FILE_NAME
    written = index if index is not None else build(store)
    #: Trace forwarding (`forwarding`): the runs this index holds that the one it replaces did not, each queued once.
    #: Read only where a destination is kept; an index there that cannot be read is taken to have held every run, so
    #: nothing is sent twice because of it.
    forwards = forwarding.wanted(store_root)
    before = _held(path, written) if forwards else None
    _atomic_write(path, encode(written))
    if forwards:
        forwarding.enqueue_new(store_root, written, before)
    return path


def _held(path: Path, written: dict) -> set[str] | None:
    """The run keys the index at `path` holds: None where there is none yet; every key of `written` where it cannot be
    read."""
    if not path.is_file():
        return None
    try:
        doc = load_json_bounded(path.read_text(encoding="utf-8"), "the run index")
        return {r["key"] for r in doc.get("runs", []) if isinstance(r, dict) and isinstance(r.get("key"), str)}
    except (OSError, ValueError, RecursionError, AttributeError):
        return {r["key"] for r in written.get("runs", [])}


def format_of(store_root: Path) -> str | None:
    """The format the store root's index states, as written; None where it holds no index that reads."""
    try:
        index = load_json_bounded((Path(store_root) / FILE_NAME).read_text(encoding="utf-8"), FILE_NAME)
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    said = index.get("format") if isinstance(index, dict) else None
    return said if isinstance(said, str) else None


def earlier(said: str) -> bool:
    """Whether `said` is this index's format at an earlier version than the one this console writes."""

    def version(f: str) -> tuple[str, tuple[int, ...]] | None:
        name, _, v = f.rpartition("/")
        try:
            return (name, tuple(int(x) for x in v.split(".")))
        except ValueError:
            return None

    mine, theirs = version(FORMAT), version(said)
    return theirs is not None and theirs[0] == mine[0] and theirs[1] < mine[1]  # type: ignore[index]  # FORMAT, this console's own, reads


def read(store_root: Path) -> dict | None:
    """The index the store root holds, or None where it holds none this version reads."""
    path = Path(store_root) / FILE_NAME
    try:
        index = load_json_bounded(path.read_text(encoding="utf-8"), FILE_NAME)
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    return index if isinstance(index, dict) and index.get("format") == FORMAT else None


# -------------------------------------------------------------------------------- the query


@dataclass(frozen=True)
class Term:
    field: str
    arg: str
    value: str = ""


@dataclass(frozen=True)
class Result:
    run: dict
    matched: tuple[str, ...]


_TOKEN = re.compile(r'(?:[^\s"]+|"[^"]*")+')


def parse(query: str) -> list[Term]:
    """The query's terms, in order; `QueryError` naming the first term the grammar does not hold."""
    terms = []
    for token in _TOKEN.findall(query or ""):
        field, sep, rest = token.partition(":")
        if not sep or not rest:
            raise QueryError(f"{token!r} is not a term: each term is a field, a colon and what to match")
        field = field.lower()
        if field in ("setting", "model"):
            arg, eq, value = rest.partition("=")
            if not eq or not arg:
                raise QueryError(f"{token!r}: {field} takes <name>=<value>")
            if field == "setting" and "." not in arg:
                raise QueryError(f"{token!r}: setting takes <step>.<name>=<value>, with * for any step")
            if field == "model" and arg not in dict(MODEL_FIELDS):
                raise QueryError(f"{token!r}: model's fields are " + ", ".join(n for n, _ in MODEL_FIELDS))
            terms.append(Term(field, arg, value.strip('"')))
        elif field == "input":
            arg, eq, value = rest.partition("=")
            if not eq or not arg:
                raise QueryError(f"{token!r}: input takes <name>=<digest>")
            terms.append(Term(field, arg.strip('"'), value))
        elif field == "row":
            m = re.fullmatch(r'"([^"]+)"=(\S+)', rest)
            if m is None:
                raise QueryError(f'{token!r}: row takes "<name>"=<result>, the name in double quotes')
            if m.group(2).upper() not in ROW_RESULTS:
                raise QueryError(f"{token!r}: the index keeps the rows that read FAIL or NOT-RUN, by name")
            terms.append(Term(field, m.group(1), m.group(2).upper()))
        elif field in ("inputs", "diff"):
            arg, _, value = rest.partition(":")
            if arg != "same-as" or not value:
                raise QueryError(f"{token!r}: {field} takes same-as:<run>")
            terms.append(Term(field, arg, value))
        elif field == "first_diff":
            if rest.startswith("any:"):
                kind = rest[4:].lower()
                if kind not in KINDS:
                    raise QueryError(f"{token!r}: first_diff:any: takes " + ", ".join(KINDS))
                terms.append(Term(field, "any", kind))
            else:
                terms.append(Term(field, rest))
        elif field == "benchmark":
            if rest.lower() not in ("yes", "no"):
                raise QueryError(f"{token!r}: benchmark takes yes or no")
            terms.append(Term(field, rest.lower()))
        elif field == "kind":
            from onetrace_console.step_kinds import STEP_KINDS

            kind = rest.strip('"').replace("-", " ").replace("_", " ").lower()
            if kind not in STEP_KINDS:
                raise QueryError(f"{token!r}: kind takes one of " + ", ".join(k.replace(" ", "-") for k in STEP_KINDS))
            terms.append(Term(field, kind))
        elif field == "agree":
            if rest.lower() not in AGREE_STATES:
                raise QueryError(f"{token!r}: agree takes " + ", ".join(AGREE_STATES[:-1]) + " or " + AGREE_STATES[-1])
            terms.append(Term(field, rest.lower()))
        elif field in ("after", "before"):
            if _instant(rest) is None:
                raise QueryError(f"{token!r}: {field} takes a date or a time, as 2026-11-12 or 2026-11-12T09:30:00Z")
            terms.append(Term(field, rest))
        elif field in ("verdict", "engine", "gated", "pipeline", "since", "agent", "word"):
            terms.append(Term(field, rest.strip('"')))
        else:
            raise QueryError(f"{token!r}: the index has no field {field!r}")
    return terms


def started(run: dict) -> str:
    """A run's recorded start, from its list entry, as written; "" where its record gives none."""
    ran = (run.get(LIST) or {}).get("ran") or ""
    return ran.split(" \u2192 ", 1)[0].strip()


_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _instant(text: str):
    """A date (its start, UTC) or a time as written (UTC where it gives no offset); None where it reads as neither."""
    from datetime import datetime

    text = text.strip()
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}([T ][0-9:.]+(Z|[+-][0-9]{2}:?[0-9]{2})?)?", text):
        return None
    try:
        at = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return at if at.tzinfo is not None else at.replace(tzinfo=UTC)


def find_run(index: dict, said: str) -> dict:
    """A run named by its run id, its key, or the first 12 or more characters of its key."""
    runs = index.get("runs") or []
    found = [r for r in runs if r["run_id"] == said] or [
        r for r in runs if len(said) >= 12 and r["key"].startswith(said)
    ]
    if not found:
        raise QueryError(f"no run is named {said!r}: give its run id or its key")
    if len(found) > 1:
        raise QueryError(f"{len(found)} runs are named {said!r}; give one's key")
    return found[0]


def first_inputs(run: dict) -> list:
    """The first step's own recorded inputs, by name and digest (`what_changed.first_inputs`)."""
    steps = run.get("steps") or []
    if not steps:
        return []
    return sorted((n, d) for n, d in steps[0]["inputs"] if not n.startswith("receipt:"))


def _differences(index: dict) -> dict[str, list[dict]]:
    """{candidate run key: [its held comparisons with a first difference]}."""
    out: dict[str, list[dict]] = {}
    for c in index.get("comparisons") or []:
        if c.get("first_diff") and c["first_diff"]["steps"]:
            out.setdefault(c["b"], []).append(c)
    return out


def _said(c: dict, runs: dict) -> str:
    f = c["first_diff"]
    what = [f"setting {s}" for s in f["settings"]] + [f"input {i}" for i in f["inputs"]] or [k for k in f["kinds"]]
    a = runs.get(c["a"], {}).get("run_id") or c["a"][:12]
    return f"first differs from {a} at {', '.join(f['steps'])}: {', '.join(what)}"


def _match(term: Term, run: dict, index: dict, runs: dict, diffs: dict) -> list[str]:
    """The fields of `run` that `term` matched, as recorded; empty where it did not match."""
    f = term.field
    if f == "setting":
        step, name = term.arg.split(".", 1)
        return [
            f"setting {s['name']}.{name} = {s['settings'][name]}"
            for s in run["steps"]
            if (step == "*" or s["name"] == step) and s["settings"].get(name) == term.value
        ]
    if f == "input":
        want = term.value if term.value.startswith("sha256:") else "sha256:" + term.value
        return [
            f"input {n} = {d} at {s['name']}"
            for s in run["steps"]
            for n, d in s["inputs"]
            if n == term.arg and d == want
        ]
    if f == "inputs":
        other = find_run(index, term.value)
        mine = first_inputs(run)
        if other["key"] == run["key"] or not mine or mine != first_inputs(other):
            return []
        return [f"the first step's inputs equal {other['run_id']}'s: " + ", ".join(f"{n} = {d}" for n, d in mine)]
    if f == "first_diff":
        out = []
        for c in diffs.get(run["key"], []):
            if term.arg == "any" and term.value in c["first_diff"]["kinds"] or term.arg in c["first_diff"]["steps"]:
                out.append(_said(c, runs))
        return out
    if f == "diff":
        other = find_run(index, term.value)
        if other["key"] == run["key"]:
            return []
        theirs = diffs.get(other["key"], [])
        out = []
        for c in diffs.get(run["key"], []):
            for t in theirs:
                if t["a"] == c["a"] and t["first_diff"] == c["first_diff"]:
                    out.append(_said(c, runs) + f", as {other['run_id']} does")
        return out
    if f == "verdict":
        return [f"verdict {run['verdict']}"] if run["verdict"] and run["verdict"].lower() == term.arg.lower() else []
    if f == "row":
        return [f'row "{term.arg}" = {term.value}'] if term.arg in run["rows"].get(term.value, []) else []
    if f in ("model", "engine"):
        name, value = (term.arg, term.value) if f == "model" else ("engine", term.arg)
        out = []
        for s in run["steps"]:
            for c in s.get("model_calls", []):
                f_ = c.get("fields", {}).get(name, {})
                for which in ("value", "declared"):
                    if f_.get(which) == value:
                        said = f"= {value}" if which == "value" else f"declared {value}"
                        out.append(f"model-call {c['file']} at {s['name']}: {name} {said} ({f_['status']})")
        return out
    if f == "gated":
        gated = run["declared"].get("gated_stages")
        return [f"gated step {term.arg}"] if isinstance(gated, list) and term.arg in gated else []
    if f == PIPELINE:
        return [f"pipeline {run['pipeline_label']}"] if run["pipeline_label"].lower() == term.arg.lower() else []
    if f == "since":
        other = find_run(index, term.arg)
        return [f"arrived after {other['run_id']}"] if run["order"] > other["order"] else []
    if f == "kind":
        return [f"kind {s['kind']} at {s['name']}" for s in run["steps"] if s.get("kind") == term.arg]
    if f == "agent":
        of_run = [f"the run's agent {term.arg}"] if run.get("run_agent") == term.arg else []
        return of_run + [f"agent {s['agent']} at {s['name']}" for s in run["steps"] if s.get("agent") == term.arg]
    if f == "agree":
        said = run[LIST]["records-agree"]
        return [f"records agree: {said}"] if said == term.arg else []
    if f == "word":
        word = run[LIST]["word"]
        return [f"verdict against the reference {word}"] if word and word.lower() == term.arg.lower() else []
    if f in ("after", "before"):
        said = started(run)
        start = _instant(said) if said else None
        at = _instant(term.arg)
        if start is None or at is None:
            return []
        day = _DAY.fullmatch(term.arg) is not None
        if f == "after" and (start >= at if day else start > at) or f == "before" and start < at:
            return [f"started {said}"]
        return []
    if f == "benchmark":
        marked = run.get("benchmark") is not None
        return (
            [("marked as a benchmark" if marked else "not marked as a benchmark")]
            if marked == (term.arg == "yes")
            else []
        )
    raise QueryError(f"the index has no field {f!r}")


def query(index: dict, text: str) -> list[Result]:
    """The runs every term matches, in the console's order of runs, each with the fields matched."""
    terms = parse(text)
    if not terms:
        return []
    if index.get(LIST) is None and any(t.field in LIST_TERMS for t in terms):
        field = next(t.field for t in terms if t.field in LIST_TERMS)
        raise QueryError(
            f"{field}: this index was written before it held each run's list words; the console writes it again when "
            "it next draws its pages"
        )
    runs = {r["key"]: r for r in index.get("runs") or []}
    diffs = _differences(index)
    out = []
    for run in index.get("runs") or []:
        matched: list[str] = []
        for term in terms:
            got = _match(term, run, index, runs, diffs)
            if not got:
                break
            matched += got
        else:
            out.append(Result(run, tuple(matched)))
    return out


def same_inputs_count(index: dict, run_key: str) -> int:
    """How many other runs' first-step inputs equal this run's: "What changed?"'s line."""
    run = next((r for r in index.get("runs") or [] if r["key"] == run_key), None)
    if run is None or not first_inputs(run):
        return 0
    mine = first_inputs(run)
    return sum(1 for r in index["runs"] if r["key"] != run_key and first_inputs(r) == mine)
