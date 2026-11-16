"""Runs whose one step writes a model-call record in `model-call-record/1.1` with its steps file, at L2, L3 or the
hosted form, written through the installed onetrace 0.7.1's own writer (`record.record_bytes`, `write_steps`): example
data, constructed for these tests and the demo; no model is called and no GPU is used. Every value is invented, and
every source says so.

`record_run(folder, run_id, call)`: the run's folder, its one step `call` writing `model_call.json` and, where `call`
asks, `model_call.steps.json`. `call` is a dict:
- `kind`: "self-hosted" or "hosted";
- `level`: "L2", "L3" (self-hosted), "L2-hosted" (hosted), or None for no capture;
- self-hosted: `token_ids`, `top_k` (one list of ids per step), at L3 `digests` and `surplus`; `batch_invariant` ("on"
  or "off"); `k` (k requested);
- hosted: `steps` (each {"chosen": token, "candidates": [token, ...]}, a token {"text", "logprob"}), `logprobs`
  ("none" or "rounded-2"), `k`;
- `temperature` (a string; "0.0" for greedy);
- `answer`: the step's returned value (default "1"), so two runs can differ at the step while their captures agree;
- `unverifiable`: at L3, a covered sampling member off its value, so the record fails onetrace-verify's rows;
- `steps_kept`: False for a run that keeps no outputs (onetrace's `keep_outputs=False`): it holds neither its steps
  file nor its record.
The record verifies under onetrace-verify 0.7.1's rows for a 1.1 record where the call is well formed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SOURCE = "example data, constructed; no model was called"
LABEL = "example data, constructed"

_SCRIPT = r"""
import json, os, sys
import onetrace as ot
from onetrace import model_call as m
from onetrace.emit import Instrument, current_stage
from onetrace.model_call import record as r

spec = json.loads(sys.argv[2])
S = spec["source"]
call = spec["call"]
V11 = r.FORMAT_1_1
L3_SAMPLING = {"temperature": "0.0", "repetition_penalty": "1.0", "presence_penalty": "0.0",
               "frequency_penalty": "0.0", "logit_bias": "none", "allowed_token_ids": "none", "bad_words": "none",
               "min_tokens": "0", "thinking_token_budget": "none", "structured_outputs": "none"}


def self_hosted():
    out = {"format": V11, "call.kind": "self-hosted", "call.api": "example.generate", "credential": "absent"}
    for k in r.REQUIRED:
        if k not in r.PLAIN and k != "fingerprints":
            out[k] = m.observed("example-" + k, S)
    for k in ("batch.size", "batch.executed_size", "batch.position", "batch.padded_width", "batch.fillers"):
        out[k] = m.observed("1", S)
    out["batch.members"] = m.observed(["sha256:" + "1" * 64], S)
    out["batch.batch_invariant"] = m.observed(call.get("batch_invariant", "on"), S)
    out["engine.name"] = m.observed("example-engine", S)
    out["model.files_digest"] = m.observed("sha256:" + "c" * 64, S)
    out["input.token_ids_digest"] = m.observed("sha256:" + "2" * 64, S)
    out["output.token_ids_digest"] = m.observed("sha256:" + "3" * 64, S)
    out["output.finish"] = m.observed("eos", S)
    out["fingerprints"] = [m.fingerprint("tolerant", "first-token-logprobs", 5, 3, m.observed("sha256:" + "a" * 64, S))]
    out["engine.settings.model_runner"] = m.observed("V1", "pinned to V1 by the adapter: L3 asked for; " + S)
    out["engine.settings.engine_core"] = m.observed("in the calling process", S)
    out["engine.settings.executor"] = m.observed("uni", S)
    out["engine.settings.executor_built"] = m.observed("uni", S)
    out["sampling.logprobs"] = m.observed(str(call.get("k", 4)), S)
    if call["level"] == "L3":
        for k, v in L3_SAMPLING.items():
            out["sampling." + k] = m.observed(v, S)
        if call.get("unverifiable"):
            #: A covered member off its value: onetrace-verify's `L3 sampling` row reads FAIL.
            out["sampling.temperature"] = m.observed("0.7", S)
        out["engine.settings.logits_processors"] = m.observed("onetrace.model_call.capture._l3_vllm.L3Digests", S)
    else:
        out["sampling.temperature"] = m.observed(call.get("temperature", "0.0"), S)
    return out


def hosted():
    out = {"format": V11, "call.kind": "hosted", "call.api": "v1/chat/completions", "credential": "absent",
           "model.requested": m.declared("example-hosted-model", S), "model.reported": m.observed("example-hosted-model", S),
           "provider.fingerprint": m.observed("example-fingerprint", S),
           "input.request_digest": m.observed("sha256:" + "4" * 64, S), "output.finish": m.observed("stop", S),
           "output.text_digest": m.observed("sha256:" + "5" * 64, S)}
    for k in ("model.files_digest", "tokenizer.digest", "engine.name", "engine.version") + r.RUNTIME + (
            "dtype", "attention_backend", "batch.size", "batch.executed_size", "batch.padded_width", "batch.position",
            "batch.members", "batch.fillers", "batch.batch_invariant", "input.token_ids_digest", "output.token_ids_digest"):
        out[k] = m.not_observed("hosted API: not exposed by the provider")
    out["sampling.temperature"] = m.declared(call.get("temperature", "0.0"), S)
    out["fingerprints"] = [m.fingerprint("tolerant", "provider-logprobs", 16, 2, m.not_observed(S))]
    return out


def steps_members(rec, obj):
    level = call["level"]
    hosted_ = level.endswith("-hosted")
    n = len(obj["steps"]) if hosted_ else len(obj["token_ids"])
    rec["steps.level"] = m.observed(level, S)
    rec["steps.method"] = m.observed({"L2": "top-k-ids", "L3": "sha256-tree-512/v0"}.get(level, "provider-text"), S)
    rec["steps.count"] = m.observed(str(n), S)
    rec["steps.k_requested"] = m.declared(str(call.get("k", 4)), S)
    lens = [len(s["candidates"]) for s in obj["steps"]] if hosted_ else [len(x) for x in obj["top_k_ids"]]
    rec["steps.k_returned_min"] = m.observed(str(min(lens)), S)
    rec["steps.k_returned_max"] = m.observed(str(max(lens)), S)
    if hosted_:
        rec["steps.logprobs"] = m.observed(call.get("logprobs", "none"), S)
    if level == "L3":
        rec["steps.surplus"] = m.observed(str(call.get("surplus", 0)), S)


def steps_obj():
    level = call["level"]
    if level.endswith("-hosted"):
        steps = []
        for s in call["steps"]:
            def tok(t):
                return {k: v for k, v in t.items() if k in ("text", "logprob")}
            steps.append({"chosen": tok(s["chosen"]), "candidates": [tok(c) for c in s["candidates"]]})
        return {"level": level, "method": "provider-text", "steps": steps}
    obj = {"level": level, "method": {"L2": "top-k-ids", "L3": "sha256-tree-512/v0"}[level],
           "token_ids": call["token_ids"], "top_k_ids": call["top_k"]}
    if level == "L3":
        obj["digests"] = call["digests"]
    return obj


i = Instrument("example-model", "model", "1.0.0", {"data": "example data, constructed"})


@ot.stage("call", instrument=i)
def step(x):
    rec = self_hosted() if call["kind"] == "self-hosted" else hosted()
    if call.get("level"):
        obj = steps_obj()
        steps_members(rec, obj)
        digest, name = m.write_steps(current_stage(), "model_call.json", obj)
        rec["steps"] = m.observed(digest, name)
    current_stage().write("model_call.json", m.record_bytes(rec), "application/json")
    return {"answered": call.get("answer", x)}


@ot.run(run_dir=sys.argv[1] + "/{run_id}", stages=["call"], manifest=__file__, keep_outputs=call.get("steps_kept", True),
        anchor_reason="example data, constructed; anchoring is not part of it")
def run():
    return step("1")


run()
"""


def record_run(folder: Path, run_id: str, call: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    code = folder / "token_level_run.py"
    code.write_text(_SCRIPT, encoding="utf-8")
    spec = {"source": SOURCE, "call": call}
    env = {**os.environ, "ONETRACE_RUN_ID": run_id}
    done = subprocess.run(
        [sys.executable, str(code), str(folder / "runs"), json.dumps(spec)],
        capture_output=True,
        env=env,
        cwd=folder,
        text=True,
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr[-2000:])
    return folder / "runs" / run_id


def l3_call(token_ids, digests, *, batch_invariant="on", surplus=0, top_k=None, k=4) -> dict:
    """A self-hosted L3 call: each step's top-k the chosen id first, then invented others."""
    top = top_k or [[t] + [str(9000 + j) for j in range(k - 1)] for t in token_ids]
    return {
        "kind": "self-hosted",
        "level": "L3",
        "token_ids": token_ids,
        "top_k": top,
        "digests": digests,
        "surplus": surplus,
        "batch_invariant": batch_invariant,
        "k": k,
    }


def l2_call(token_ids, top_k, *, k=4, temperature="0.0") -> dict:
    return {
        "kind": "self-hosted",
        "level": "L2",
        "token_ids": token_ids,
        "top_k": top_k,
        "k": k,
        "temperature": temperature,
    }


def hosted_call(steps, *, logprobs="rounded-2", k=4, temperature="0.0", steps_kept=True) -> dict:
    return {
        "kind": "hosted",
        "level": "L2-hosted",
        "steps": steps,
        "logprobs": logprobs,
        "k": k,
        "temperature": temperature,
        "steps_kept": steps_kept,
    }


def digest(n: int) -> str:
    """An invented 64-hex digest, `n` written into it."""
    return f"{n:064x}"
