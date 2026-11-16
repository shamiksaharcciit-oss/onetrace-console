"""The demo's model-call records: invented example data in `model-call-record/1.0`, one self-hosted call
and one hosted call, as a step's outputs `model_call.json` and `model_call.2.json`.

Written with the installed onetrace's own `onetrace.model_call` helpers, which check each record as
they write it. No model is called and nothing is measured, so nothing is `observed`: what a call of
this kind would name (its model, engine, settings) is `declared, not observed`, with an example value;
what it would measure is `not observed`; what a call of this kind has no such thing for is `not
applicable`. Every `source` says it is example data.
"""

from __future__ import annotations

import hashlib

SOURCE = "example data, written for the demo; nothing was observed"


def _digest(what: str) -> str:
    return "sha256:" + hashlib.sha256(f"example: {what}".encode()).hexdigest()


def _sdk():
    from onetrace import model_call

    return model_call


def _declared(value):
    return _sdk().declared(value, SOURCE)


def _not(why: str) -> dict:
    return _sdk().not_observed(f"{SOURCE}; {why}")


def _na(why: str) -> dict:
    return _sdk().not_applicable(f"{SOURCE}; {why}")


MEASURED = (
    "batch.size",
    "batch.executed_size",
    "batch.position",
    "batch.members",
    "batch.fillers",
    "input.token_ids_digest",
    "output.token_ids_digest",
    "output.finish",
)


def self_hosted() -> dict:
    """A self-hosted call through vLLM: what it would name, declared; what it would measure, not observed."""
    m = _sdk()
    rec = {
        "format": m.FORMAT,
        "call.kind": "self-hosted",
        "call.api": "vllm.LLM.generate",
        "credential": "absent",
        "model.requested": _declared("example-org/example-model@0123abc"),
        "model.reported": _declared("example-org/example-model"),
        "model.files_digest": _declared(_digest("the model's files")),
        "tokenizer.digest": _declared(_digest("the tokenizer's files")),
        "provider.fingerprint": _na("self-hosted: there is no provider"),
        "engine.name": _declared("vllm"),
        "engine.version": _declared("0.0.0-example"),
        "runtime.torch": _declared("0.0.0-example"),
        "runtime.cuda": _declared("0.0-example"),
        "runtime.gpu_name": _declared("Example GPU"),
        "runtime.driver": _declared("0.0-example"),
        "runtime.compute_capability": _declared("0.0"),
        "dtype": _declared("bfloat16"),
        "attention_backend": _not("the worker's own selection is not observed"),
        "batch.padded_width": _na("vLLM pads no batch to a width"),
        "batch.batch_invariant": _declared("off"),
        "input.request_digest": _na("self-hosted: there is no request body"),
        "output.text_digest": _na("self-hosted: there is no returned text"),
        "sampling.temperature": _declared("0"),
        "fingerprints": [
            m.fingerprint("topk_exact", "first-token-logprobs", 20, "none", _not("no logprobs were taken"))
        ],
    }
    for k in MEASURED:
        rec[k] = _not("no call was made")
    return rec


def hosted() -> dict:
    """A hosted call: every internal field not observed, as a hosted API does not show it."""
    m = _sdk()
    hidden = "a hosted API does not show it"
    rec = {
        "format": m.FORMAT,
        "call.kind": "hosted",
        "call.api": "chat.completions.create",
        "credential": "present",
        "model.requested": _declared("example-hosted-model"),
        "model.reported": _not("no call was made"),
        "provider.fingerprint": _not("no call was made"),
        "input.request_digest": _not("no call was made"),
        "output.text_digest": _not("no call was made"),
        "output.finish": _not("no call was made"),
        "fingerprints": [m.fingerprint("tolerant", "provider-logprobs", 5, 3, _not("no logprobs were taken"))],
    }
    for k in (
        "model.files_digest",
        "tokenizer.digest",
        "engine.name",
        "engine.version",
        "runtime.torch",
        "runtime.cuda",
        "runtime.gpu_name",
        "runtime.driver",
        "runtime.compute_capability",
        "dtype",
        "attention_backend",
        "batch.size",
        "batch.executed_size",
        "batch.padded_width",
        "batch.position",
        "batch.members",
        "batch.fillers",
        "batch.batch_invariant",
        "input.token_ids_digest",
        "output.token_ids_digest",
    ):
        rec[k] = _not(hidden)
    return rec


def record_bytes(record: dict) -> bytes:
    """As onetrace writes one: checked, canonical JSON (`onetrace.model_call.record_bytes`)."""
    return _sdk().record_bytes(record)


#: The names the step writes its two records under, as model-call-record/1.0 names a step's records.
NAMES = ("model_call.json", "model_call.2.json")


# ---------------------------------------------------------------- the capture store's runs (model-call-record/1.1)
#: The capture runs' words: their steps file is real, written by the builder, so the record's capture members are
#: observed, as the format has them; every other field is as the 1.0 example's, declared or not observed.
CAPTURE_SOURCE = "example data, constructed for the demo; no model was called"
_IDS = ["11", "12", "13", "14", "15", "16"]
_IDS_B = _IDS[:4] + ["40", "41"]
_K = 4


def _row(n: int) -> str:
    return hashlib.sha256(f"example logits row {n}".encode()).hexdigest()


#: Each capture: its token ids, its rows' digests, and batch-invariant mode. Against the baseline, the other two's
#: logits row changes at token 2 and their chosen token at token 4; the last has batch-invariant mode off.
CAPTURES = {
    "baseline": (_IDS, [_row(i) for i in range(6)], "on"),
    "row-changed": (_IDS_B, [_row(i) for i in range(2)] + [_row(100 + i) for i in range(4)], "on"),
    "batch-off": (_IDS_B, [_row(i) for i in range(2)] + [_row(100 + i) for i in range(4)], "off"),
}


def capture_steps(variant: str) -> dict:
    """The L3 steps file: each step's chosen id, its top-k (the chosen first, then invented others) and its row's
    digest."""
    ids, rows, _mode = CAPTURES[variant]
    top = [[t] + [str(9000 + j) for j in range(1, _K)] for t in ids]
    return {
        "level": "L3",
        "method": "sha256-tree-512/v0",
        "token_ids": list(ids),
        "top_k_ids": top,
        "digests": list(rows),
    }


def capture_bytes(variant: str) -> bytes:
    """The steps file's bytes, as onetrace writes them (canonical JSON)."""
    from onetrace.model_call.canonical import cj

    return cj(capture_steps(variant))


def self_hosted_captured(variant: str, steps: dict) -> dict:
    """The self-hosted call's record in model-call-record/1.1, naming its L3 steps file (`steps`, the value object
    onetrace's `write_steps` gives)."""
    from onetrace.model_call.record import FORMAT_1_1

    m = _sdk()
    ids, _rows, mode = CAPTURES[variant]

    def observed(v):
        return m.observed(v, CAPTURE_SOURCE)

    def declared(v):
        return m.declared(v, CAPTURE_SOURCE)

    rec = dict(self_hosted())
    rec.update(
        {
            "format": FORMAT_1_1,
            "batch.batch_invariant": declared(mode),
            "steps": steps,
            "steps.level": observed("L3"),
            "steps.method": observed("sha256-tree-512/v0"),
            "steps.count": observed(str(len(ids))),
            "steps.k_requested": declared(str(_K)),
            "steps.k_returned_min": observed(str(_K)),
            "steps.k_returned_max": observed(str(_K)),
            "steps.surplus": observed("0"),
            "engine.settings.model_runner": m.declared(
                "V1", "pinned to V1 by the adapter: L3 asked for; " + CAPTURE_SOURCE
            ),
            "engine.settings.engine_core": declared("in the calling process"),
            "engine.settings.executor": declared("uni"),
            "engine.settings.executor_built": declared("uni"),
            "engine.settings.logits_processors": declared("onetrace.model_call.capture._l3_vllm.L3Digests"),
            "sampling.logprobs": declared(str(_K)),
        }
    )
    for k, v in {
        "temperature": "0.0",
        "repetition_penalty": "1.0",
        "presence_penalty": "0.0",
        "frequency_penalty": "0.0",
        "logit_bias": "none",
        "allowed_token_ids": "none",
        "bad_words": "none",
        "min_tokens": "0",
        "thinking_token_budget": "none",
        "structured_outputs": "none",
    }.items():
        rec["sampling." + k] = declared(v)
    return rec
