"""The exact run index: a derived file beside the store, and the query over it.

The index is rebuilt from the records the store holds, never a source of truth: deleting it and
rebuilding it gives the same file, byte for byte. It is written whenever the console draws its pages
(at a store's build, at start, and after each new run, comparison or benchmark mark), and a public
console reads the one its build wrote and never writes it.

What it holds, per run, each as the record states it: the run's ids, its chain head, each step's
name, outcome, instrument, settings (`assertions.constants`, by recorded name and value), inputs and
outputs (name and digest); the manifest's declarations; the verifier's verdict and the names of its
rows that read FAIL or NOT-RUN; the model-call records' fields where a step's output holds one; and
whether a person marked the run as a benchmark (`benchmarks`). Per held comparison: the first
differing step and what differed there, from the comparison's own short answer data. No text is
indexed and no kept input is read.

The query is a list of terms, each a field the record names, every term required (`GRAMMAR`). Each
result names the fields that matched, as recorded. A query reads the index and nothing else: it runs
no check, no comparison and no model.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from onetrace_console.bounded_json import load_json_bounded

FORMAT = "onetrace-console-run-index/0.1"
#: The derived file, beside the store's own folder under the store root.
FILE_NAME = "run_index.json"
#: The manifest's declarations the index keeps, each as written.
DECLARATIONS = ("optional_stages", "gated_stages", "outputs_kept", "traceparent", "parent_run",
                "parent_stage", "repeat_of")
#: The model-call record's fields the index keeps: (the index's name, the record's field).
MODEL_FIELDS = (("model", "model.reported"), ("weights", "model.files_digest"),
                ("engine", "engine.name"), ("engine_version", "engine.version"), ("dtype", "dtype"),
                ("batch_invariant", "batch.batch_invariant"))
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
    out = []
    for o in model_call.outputs(receipt):
        name = str(o["name"])
        try:
            record = model_call.read_output(receipt_file, o, lambda path: _read(files, store, path))
        except model_call.Refused as e:
            out.append({"file": name, "refused": str(e)})
            continue
        fields = {}
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
    summary = {}
    part = envelope.get("rows_json") if isinstance(envelope, dict) else None
    try:
        doc = load_json_bounded(part.get("stdout", ""), "the check's rows") if isinstance(part, dict) else None
        summary = doc.get("summary") if isinstance(doc, dict) and isinstance(doc.get("summary"), dict) else {}
    except (ValueError, RecursionError):
        summary = {}
    rows = {}
    for row in rows_of(envelope):
        result = str(row.get("result", ""))
        if result in ROW_RESULTS:
            rows.setdefault(result, []).append(str(row.get("name", "")))
    return str(summary.get("result", "")), rows


def _run_entry(run, order: int, label: str, store) -> dict:
    from onetrace_console.stage_pages import _files, _read, _steps
    files = _files(run, store)
    try:
        manifest = load_json_bounded((_read(files, store, "MANIFEST.json") or b"{}").decode("utf-8"),
                                     "MANIFEST.json", "show")
    except (ValueError, UnicodeDecodeError, RecursionError):
        manifest = {}
    manifest = manifest if isinstance(manifest, dict) else {}
    try:
        steps = _steps(run, store)
    except Exception:  # noqa: BLE001 - a record that can't be read is indexed by its ids alone
        steps = []
    entries = []
    for s in steps:
        receipt = s["receipt"]
        stage = receipt.get("stage") if isinstance(receipt.get("stage"), dict) else {}
        instrument = receipt.get("instrument") if isinstance(receipt.get("instrument"), dict) else {}
        outcome = receipt.get("outcome") if isinstance(receipt.get("outcome"), dict) else {}
        entry = {"name": str(stage.get("name", "")), "index": str(s["index"]),
                 "outcome": str(outcome.get("class", "")),
                 "instrument": {"id": str(instrument.get("id", "")), "version": str(instrument.get("version", ""))},
                 "settings": _settings(receipt), "inputs": _named(receipt.get("inputs")),
                 "outputs": _named(receipt.get("outputs"))}
        calls = _model_calls(receipt, s["file"], files, store)
        if calls:
            entry["model_calls"] = calls
        entries.append(entry)
    verdict, rows = _check(run, store)
    from onetrace_console.benchmarks import mark_of
    return {"key": run.key, "run_id": run.run_id, "pipeline_label": label, "order": order,
            "chain_head": run.chain_head, "folder": run.folder, "steps": entries,
            "declared": {k: manifest[k] for k in DECLARATIONS if k in manifest},
            "verdict": verdict, "rows": rows, "benchmark": mark_of(store, run.key)}


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
        kinds += (["setting"] if named else []) + (["input"] if changed else []) \
            + (["configuration"] if prints and not named else [])
    if steps and not kinds:
        kinds = ["output"]
    return {"steps": [str(s).split("#", 1)[0] for s in steps], "kinds": sorted(set(kinds), key=KINDS.index),
            "settings": sorted(set(settings)), "inputs": sorted(set(inputs))}


def build(store) -> dict:
    """The index of every run and held comparison the store holds, in the console's order of runs."""
    from onetrace_console.overview import pipelines
    from onetrace_console.store import arrival_order
    with store.reading():
        label = {r.key: p.label for p in pipelines(store) for r in p.runs}
        runs = [_run_entry(r, i, label.get(r.key, ""), store)
                for i, r in enumerate(arrival_order(store.runs(), newest_first=False))]
        comparisons = []
        for c in sorted(store.comparisons(), key=lambda c: c.key):
            try:
                first = first_difference(c, store)
            except Exception:  # noqa: BLE001 - a report that can't be read gives no first difference
                first = None
            comparisons.append({"key": c.key, "a": c.run_a, "b": c.run_b,
                                **({"first_diff": first} if first is not None else {"unread": True})})
    return {"format": FORMAT, "runs": runs, "comparisons": comparisons}


def encode(index: dict) -> bytes:
    return (json.dumps(index, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def write(store, store_root: Path) -> Path:
    """Build the index and write it beside the store, replacing the last one whole."""
    from onetrace_console.store import _atomic_write
    path = Path(store_root) / FILE_NAME
    _atomic_write(path, encode(build(store)))
    return path


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
        elif field in ("verdict", "engine", "gated", "pipeline", "since"):
            terms.append(Term(field, rest.strip('"')))
        else:
            raise QueryError(f"{token!r}: the index has no field {field!r}")
    return terms


def find_run(index: dict, said: str) -> dict:
    """A run named by its run id, its key, or the first 12 or more characters of its key."""
    runs = index.get("runs") or []
    found = [r for r in runs if r["run_id"] == said] or \
        [r for r in runs if len(said) >= 12 and r["key"].startswith(said)]
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
    what = ([f"setting {s}" for s in f["settings"]] + [f"input {i}" for i in f["inputs"]]
            or [k for k in f["kinds"]])
    a = runs.get(c["a"], {}).get("run_id") or c["a"][:12]
    return f"first differs from {a} at {', '.join(f['steps'])}: {', '.join(what)}"


def _match(term: Term, run: dict, index: dict, runs: dict, diffs: dict) -> list[str]:
    """The fields of `run` that `term` matched, as recorded; empty where it did not match."""
    f = term.field
    if f == "setting":
        step, name = term.arg.split(".", 1)
        return [f"setting {s['name']}.{name} = {s['settings'][name]}" for s in run["steps"]
                if (step == "*" or s["name"] == step) and s["settings"].get(name) == term.value]
    if f == "input":
        want = term.value if term.value.startswith("sha256:") else "sha256:" + term.value
        return [f"input {n} = {d} at {s['name']}" for s in run["steps"] for n, d in s["inputs"]
                if n == term.arg and d == want]
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
    if f == "benchmark":
        marked = run.get("benchmark") is not None
        return [("marked as a benchmark" if marked else "not marked as a benchmark")] \
            if marked == (term.arg == "yes") else []
    raise QueryError(f"the index has no field {f!r}")


def query(index: dict, text: str) -> list[Result]:
    """The runs every term matches, in the console's order of runs, each with the fields matched."""
    terms = parse(text)
    if not terms:
        return []
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
