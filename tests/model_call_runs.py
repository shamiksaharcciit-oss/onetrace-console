"""Two recorded runs whose one step writes a model-call record in `model-call-record/1.0` and, where
asked, its steps file, written with the installed onetrace's own helpers: test data, written for these
tests; no model is called. Every field is observed with an invented value, so the SDK's comparator
compares the two records rather than stopping at a precondition.

`record_run(folder, run_id, fingerprint=..., token_ids=..., files_digest=..., with_record=...)`: the
run's folder; `with_record=False` records the same step with no model-call record.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SOURCE = "written for this test; no model was called"

_SCRIPT = r'''
import json, os, sys
import onetrace as ot
from onetrace import model_call as m
from onetrace.emit import Instrument, current_stage
from onetrace.model_call import record as r

spec = json.loads(sys.argv[2])
SOURCE = spec["source"]


def rec():
    out = {"format": m.FORMAT, "call.kind": "self-hosted", "call.api": "example.generate", "credential": "absent"}
    for k in r.REQUIRED:
        if k not in r.PLAIN and k != "fingerprints":
            out[k] = m.observed("example-" + k, SOURCE)
    for k in ("batch.size", "batch.executed_size", "batch.position", "batch.padded_width", "batch.fillers"):
        out[k] = m.observed("1", SOURCE)
    out["batch.members"] = m.observed(["sha256:" + "1" * 64], SOURCE)
    out["batch.batch_invariant"] = m.observed("off", SOURCE)
    out["engine.name"] = m.observed("transformers", SOURCE)
    out["model.files_digest"] = m.observed(spec["files_digest"], SOURCE)
    out["input.token_ids_digest"] = m.observed("sha256:" + "2" * 64, SOURCE)
    out["output.token_ids_digest"] = m.observed(spec["output"], SOURCE)
    out["fingerprints"] = [m.fingerprint("tolerant", "first-token-logprobs", 5, 3, m.observed(spec["fingerprint"], SOURCE))]
    return out


i = Instrument("example-model", "model", "1.0.0", {})


@ot.stage("call", instrument=i)
def call(x):
    if not spec["with_record"]:
        return {"answered": x}
    record = rec()
    if spec["token_ids"] is not None:
        digest, name = m.write_steps(current_stage(), "model_call.json", {"token_ids": spec["token_ids"], "level": "L1"})
        record["steps"] = m.observed(digest, name)
    current_stage().write("model_call.json", m.record_bytes(record), "application/json")
    return {"answered": x}


@ot.run(run_dir=sys.argv[1] + "/{run_id}", stages=["call"], manifest=__file__, anchor_reason="a test")
def run():
    return call("1")


run()
'''


def record_run(folder: Path, run_id: str, *, fingerprint: str = "sha256:" + "a" * 64,
               output: str = "sha256:" + "b" * 64, token_ids: list[str] | None = None,
               files_digest: str = "sha256:" + "c" * 64, with_record: bool = True) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    code = folder / "model_call_run.py"
    code.write_text(_SCRIPT, encoding="utf-8")
    spec = {"source": SOURCE, "fingerprint": fingerprint, "output": output, "token_ids": token_ids,
            "files_digest": files_digest, "with_record": with_record}
    env = {**os.environ, "ONETRACE_RUN_ID": run_id}
    subprocess.run([sys.executable, str(code), str(folder / "runs"), json.dumps(spec)], check=True,
                   capture_output=True, env=env, cwd=folder)
    return folder / "runs" / run_id
