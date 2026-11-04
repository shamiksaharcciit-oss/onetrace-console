"""Recorded runs of one two-step pipeline, `prep` then `call`, for the configuration comparison: test
data, written for these tests with the installed onetrace; no model is called.

The pipeline's code is one script, the same for every run, so the code fingerprint is equal unless a
test asks otherwise (`code_note`). Everything else a test plants comes in through the run's spec:

- `x`: the run's input, so two runs can differ in their inputs and nothing else;
- `config`: each step's instrument configuration, by step;
- `constants`: each step's declared settings, by step;
- `skip_prep`: the run records no `prep` step;
- `records`: `call`'s model-call records, by name, each as fields over the default record (a value
  `None` leaves that field out);
- `decisions`: the decision references `call` cites.

`record_run(folder, run_id, **spec)` returns the run's folder.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SOURCE = "written for this test; no model was called"

_SCRIPT = r'''
import json, sys
import onetrace as ot
from onetrace import model_call as m
from onetrace.emit import Instrument, current_stage
from onetrace.model_call import record as r

spec = json.loads(sys.argv[2])
SOURCE = spec["source"]
#: CODE_NOTE


def rec(over):
    out = {"format": m.FORMAT, "call.kind": "self-hosted", "call.api": "example.generate", "credential": "absent"}
    for k in r.REQUIRED:
        if k not in r.PLAIN and k != "fingerprints":
            out[k] = m.observed("example-" + k, SOURCE)
    for k in ("batch.size", "batch.executed_size", "batch.position", "batch.padded_width", "batch.fillers"):
        out[k] = m.observed("1", SOURCE)
    out["batch.members"] = m.observed(["sha256:" + "1" * 64], SOURCE)
    out["batch.batch_invariant"] = m.observed("off", SOURCE)
    out["engine.name"] = m.observed("transformers", SOURCE)
    out["engine.settings.max_new_tokens"] = m.observed("64", SOURCE)
    out["sampling.temperature"] = m.observed("0", SOURCE)
    out["input.token_ids_digest"] = m.observed("sha256:" + "2" * 64, SOURCE)
    out["output.token_ids_digest"] = m.observed("sha256:" + "b" * 64, SOURCE)
    out["fingerprints"] = [m.fingerprint("tolerant", "first-token-logprobs", 5, 3, m.observed("sha256:" + "a" * 64, SOURCE))]
    for k, v in over.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = m.observed(v, SOURCE)
    return out


def constants(step):
    for k, v in (spec["constants"].get(step) or {}).items():
        current_stage().constant(k, v)


@ot.stage("prep", instrument=Instrument("example-prep", "tool", "1.0.0", spec["config"].get("prep", {})))
def prep(x):
    constants("prep")
    return {"prepared": x}


@ot.stage("call", instrument=Instrument("example-model", "model", "1.0.0", spec["config"].get("call", {})))
def call(x):
    constants("call")
    for ref in spec["decisions"]:
        current_stage().decision(ref)
    for name, over in spec["records"].items():
        current_stage().write(name, m.record_bytes(rec(over)), "application/json")
    return {"answered": str(x)}


@ot.run(run_dir=sys.argv[1] + "/{run_id}", stages=["prep", "call"], manifest=__file__, anchor_reason="a test")
def run():
    return call(spec["x"] if spec["skip_prep"] else prep(spec["x"]))


run()
'''


def record_run(folder: Path, run_id: str, *, x: str = "1", config: dict | None = None,
               constants: dict | None = None, skip_prep: bool = False, records: dict | None = None,
               decisions: list | None = None, code_note: str = "") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    code = folder / f"pipeline{'-' + code_note if code_note else ''}.py"
    code.write_text(_SCRIPT.replace("#: CODE_NOTE", f"#: {code_note}" if code_note else "#: CODE_NOTE"),
                    encoding="utf-8")
    spec = {"source": SOURCE, "x": x, "config": config or {}, "constants": constants or {},
            "skip_prep": skip_prep, "records": {"model_call.json": {}} if records is None else records,
            "decisions": decisions or []}
    env = {**os.environ, "ONETRACE_RUN_ID": run_id}
    subprocess.run([sys.executable, str(code), str(folder / "runs"), json.dumps(spec)], check=True,
                   capture_output=True, env=env, cwd=folder)
    return folder / "runs" / run_id
