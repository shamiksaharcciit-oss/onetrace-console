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
    return "sha256:" + hashlib.sha256(f"example: {what}".encode("utf-8")).hexdigest()


def _sdk():
    from onetrace import model_call
    return model_call


def _declared(value):
    return _sdk().declared(value, SOURCE)


def _not(why: str) -> dict:
    return _sdk().not_observed(f"{SOURCE}; {why}")


def _na(why: str) -> dict:
    return _sdk().not_applicable(f"{SOURCE}; {why}")


MEASURED = ("batch.size", "batch.executed_size", "batch.position", "batch.members", "batch.fillers",
            "input.token_ids_digest", "output.token_ids_digest", "output.finish")


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
        "fingerprints": [m.fingerprint("topk_exact", "first-token-logprobs", 20, "none",
                                       _not("no logprobs were taken"))],
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
    for k in ("model.files_digest", "tokenizer.digest", "engine.name", "engine.version", "runtime.torch",
              "runtime.cuda", "runtime.gpu_name", "runtime.driver", "runtime.compute_capability", "dtype",
              "attention_backend", "batch.size", "batch.executed_size", "batch.padded_width", "batch.position",
              "batch.members", "batch.fillers", "batch.batch_invariant", "input.token_ids_digest",
              "output.token_ids_digest"):
        rec[k] = _not(hidden)
    return rec


def record_bytes(record: dict) -> bytes:
    """As onetrace writes one: checked, canonical JSON (`onetrace.model_call.record_bytes`)."""
    return _sdk().record_bytes(record)


#: The names the step writes its two records under, as model-call-record/1.0 names a step's records.
NAMES = ("model_call.json", "model_call.2.json")
