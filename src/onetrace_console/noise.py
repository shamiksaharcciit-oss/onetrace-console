"""Noise fields: the fields of a step's JSON output that a pipeline marks as noise (a timestamp, a request id), so that
a comparison's first difference that matters skips a difference found only there.

Marking noise changes what the console points to first, never what the record says or what a check reports: the
record's own verdict, every step's verdict and `onetrace diff`'s exit code stay as they are, and a comparison whose
first difference moves because of noise shows both, the first difference with the noise fields set aside and the first
difference in the record, each linked.

- **Where it is kept:** in the store, beside the pipeline: `noise/<the pipeline's declared stage list digest>.json`
  (`Store.noise_folder`; a team's view reads the whole console's, as a field names a step and a path, never a run),
  so a pipeline keeps its fields whatever label it has on a page. An admin sets it on the pipeline's noise page
  (`/pipelines/<label>/noise`); each change is an audit-log entry. A public console reads it from its build and
  refuses changes.
- **A path** names a field of a step's JSON output, from the top of the output: keys joined by dots, such as
  `meta.read_at`, and `*` for any index of an array, at most once (`items.*.request_id`). Nothing else is a wildcard.
  A path that matches nothing in a pipeline's kept outputs is shown as matching nothing.
- **A difference is noise only** where both runs kept the step's differing outputs as JSON, and every place they differ
  lies at or under a marked path of that step. An output that isn't kept, or isn't JSON, is never set aside.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FOLDER = "noise"
FORMAT = "onetrace-console-noise/1"
#: The most fields a pipeline may mark, and the longest path.
MOST_FIELDS = 64
LONGEST_PATH = 200
ANY_INDEX = "*"
_SEGMENT = re.compile(r"^[^.\s*]{1,100}$")


#: What marking noise never changes, word for word on the comparison, the noise page and in the CHANGELOG.
NOT_THE_RECORD = (
    "Marking noise changes what the console points to first, never what the record says or what a check reports."
)


class Refused(ValueError):
    """A field that can't be marked, and why, in the page's words."""


@dataclass(frozen=True)
class Field:
    step: str
    path: str

    def as_json(self) -> dict:
        return {"step": self.step, "path": self.path}


def path_problem(path: str) -> str | None:
    """Why `path` can't be a noise field's path, or None."""
    if not isinstance(path, str) or not path.strip():
        return "a path names a field, such as meta.read_at"
    if len(path) > LONGEST_PATH:
        return f"a path is at most {LONGEST_PATH} characters"
    if path.startswith("$") or path.startswith("/") or "[" in path or "]" in path:
        return "a path is keys joined by dots, from the top of the output, such as meta.read_at; no $, / or brackets"
    parts = path.split(".")
    if parts.count(ANY_INDEX) > 1:
        return "a path takes * (any index of an array) at most once"
    for p in parts:
        if p != ANY_INDEX and not _SEGMENT.match(p):
            return "each part of a path is a key, or * for any index of an array; no empty part, space or other *"
    return None


def _file(store, digest: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
        raise Refused("the pipeline has no stage list digest")
    return Path(store.noise_folder()) / f"{digest}.json"


def read(store, digest: str) -> list[Field]:
    """The pipeline's noise fields, in the order marked; none where none are."""
    from onetrace_console.bounded_json import load_json_bounded

    try:
        p = _file(store, digest)
    except Refused:
        return []
    if not p.is_file():
        return []
    try:
        doc = load_json_bounded(p.read_text(encoding="utf-8"), "the noise fields")
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    out = []
    for f in doc.get("fields") or [] if isinstance(doc, dict) else []:
        path = f.get("path") if isinstance(f, dict) else None
        if (
            isinstance(f, dict)
            and isinstance(f.get("step"), str)
            and isinstance(path, str)
            and path_problem(path) is None
        ):
            out.append(Field(f["step"], path))
    return out


def write(store, digest: str, label: str, fields: list[Field]) -> None:
    from onetrace_console.store import _atomic_write

    p = _file(store, digest)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {"format": FORMAT, "label": label, "fields": [f.as_json() for f in fields]}
    _atomic_write(p, (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def add(store, pipeline, step: str, path: str) -> list[Field]:
    """Mark `path` of `step`'s output as noise for `pipeline`; Refused where the step is not the pipeline's, the path
    is not one, or it is marked already."""
    path = path.strip()
    if step not in pipeline.stages:
        raise Refused("the step is not one of the pipeline's")
    why = path_problem(path)
    if why:
        raise Refused(why)
    digest = pipeline.runs[0].declared_digest
    have = read(store, digest)
    if Field(step, path) in have:
        raise Refused("that field is marked already")
    if len(have) >= MOST_FIELDS:
        raise Refused(f"a pipeline marks at most {MOST_FIELDS} fields")
    have.append(Field(step, path))
    write(store, digest, pipeline.label, have)
    return have


def remove(store, pipeline, step: str, path: str) -> list[Field]:
    digest = pipeline.runs[0].declared_digest
    have = read(store, digest)
    if Field(step, path) not in have:
        raise Refused("that field is not marked")
    have = [f for f in have if f != Field(step, path)]
    write(store, digest, pipeline.label, have)
    return have


# ------------------------------------------------------------------------------------------------- matching


def covers(noise_path: str, at: tuple) -> bool:
    """`at` (a place two outputs differ: keys and list indexes) lies at or under `noise_path`."""
    parts = noise_path.split(".")
    if len(at) < len(parts):
        return False
    for want, got in zip(parts, at):
        if want == ANY_INDEX:
            if not isinstance(got, int):
                return False
        elif isinstance(got, int):
            if want != str(got):
                return False
        elif want != got:
            return False
    return True


def differences(a, b, at: tuple = ()) -> list[tuple]:
    """Every place two JSON values differ, read all the way down: keys of objects, indexes of lists of one length;
    anything else that differs is its own place."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in dict.fromkeys([*a.keys(), *b.keys()]):
            if k not in a or k not in b:
                out.append((*at, k))
            else:
                out += differences(a[k], b[k], (*at, k))
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, (*at, i))]
    return [] if a == b and type(a) is type(b) else [at]


def only_noise(a, b, paths: list[str]) -> bool:
    """Two JSON outputs differ, and every place they differ lies under one of `paths`."""
    found = differences(a, b)
    return bool(found) and all(any(covers(p, d) for p in paths) for d in found)


def matches(value, path: str) -> bool:
    """`path` names a place in the JSON value `value`."""
    parts = path.split(".")

    def walk(v, i):
        if i == len(parts):
            return True
        want = parts[i]
        if isinstance(v, dict):
            return want in v and walk(v[want], i + 1)
        if isinstance(v, list):
            if want == ANY_INDEX:
                return any(walk(x, i + 1) for x in v)
            return want.isdigit() and int(want) < len(v) and walk(v[int(want)], i + 1)
        return False

    return walk(value, 0)


# ------------------------------------------------------------------------------------------------- a comparison


def fields_for(comparison, store) -> tuple[Any, list[Field]]:
    """(the pipeline both runs are of, its noise fields); (None, []) where the two runs are not of one pipeline."""
    from onetrace_console.verdicts import pipeline_of

    try:
        pa, pb = (pipeline_of(store.get_run(k), store) for k in (comparison.run_a, comparison.run_b))
    except Exception:  # noqa: BLE001 - a run that can't be read has no pipeline, and no noise
        return None, []
    if pa is None or pb is None or pa.label != pb.label:
        return None, []
    return pa, read(store, pa.runs[0].declared_digest)


def _noise_only(step, comparison, store, paths: list[str], settings: dict | None = None) -> bool:
    """Everything the comparison reads at `step` is the same but under `paths`: no recorded setting differs there
    (`settings`, diff's annotations at the step: its instrument, constants, corpus link, kind and agent), the outcome
    class is the same, the outputs are the same ones in the same order, and every output that differs was kept by both
    runs as JSON and differs only under `paths`."""
    from onetrace_console.compare_view import _json, _kept, _outputs

    if step.a is None or step.b is None or settings:
        return False
    ra, rb = step.a["receipt"], step.b["receipt"]
    if (ra.get("outcome") or {}).get("class") != (rb.get("outcome") or {}).get("class"):
        return False
    outs_b = {str(o.get("name")): o for o in _outputs(rb)}
    if [str(o.get("name")) for o in _outputs(ra)] != [str(o.get("name")) for o in _outputs(rb)]:
        return False
    differing = 0
    for oa in _outputs(step.a["receipt"]):
        ob = outs_b.get(str(oa.get("name")))
        if ob is None:
            return False
        if oa.get("digest") == ob.get("digest"):
            continue
        differing += 1
        ja = _json(_kept(store, comparison.run_a, oa.get("digest")))
        jb = _json(_kept(store, comparison.run_b, ob.get("digest")))
        if ja is None or jb is None or not only_noise(ja, jb, paths):
            return False
    return differing > 0


#: The verdicts of a step whose outputs differ (`compare_view.Step.verdict`).
DIFFERS = ("FIRST DIFFERENCE", "downstream")


def first_that_matters(f, comparison, store, fields: list[Field]) -> int | None:
    """The position in `f.steps` of the first difference that matters: from the record's first difference on, the
    first step that differs other than only in its fields marked noise, with nothing else the comparison reads there
    differing; None where every difference is noise. The record's first difference itself where no field is marked."""
    if f.first is None or not fields:
        return f.first
    for i in range(f.first, len(f.steps)):
        s = f.steps[i]
        if s.verdict not in DIFFERS:
            continue
        paths = [x.path for x in fields if x.step == s.stage]
        if not paths or not _noise_only(s, comparison, store, paths, f.annotations.get(s.stage)):
            return i
    return None
