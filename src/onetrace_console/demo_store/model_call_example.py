"""The demo's model-call records: invented example data in the draft format
`model-call-record/0.1-draft`, one self-hosted call and one hosted call, as a step's outputs.

The format's schema holds no example records, and the package that writes them is not a dependency
of the console; these are written here to the schema, each field's `source` saying it is example
data. No model is called and nothing is measured. Every digest is the sha256 of a short phrase
naming what it stands for, so none can be mistaken for a measurement.
"""
from __future__ import annotations

import hashlib
import json

FORMAT = "model-call-record/0.1-draft"
SOURCE = "example data, written for the demo; nothing was observed"


def _digest(what: str) -> str:
    return "sha256:" + hashlib.sha256(f"example: {what}".encode("utf-8")).hexdigest()


def _observed(value, declared=None) -> dict:
    out = {"status": "observed", "value": value, "source": SOURCE}
    if declared is not None:
        out["declared"] = declared
    return out


def _not(state: str, why: str) -> dict:
    return {"status": state, "source": f"{SOURCE}; {why}"}


def self_hosted() -> dict:
    """A self-hosted call through vLLM: what such a writer can observe, and what it cannot."""
    return {
        "format": FORMAT,
        "call.kind": "self-hosted",
        "call.api": "vllm.LLM.generate",
        "credential": "absent",
        "model.requested": {"status": "declared, not observed", "value": "example-org/example-model@0123abc",
                            "source": SOURCE},
        "model.reported": _observed("example-org/example-model"),
        "model.files_digest": _observed(_digest("the model's files")),
        "tokenizer.digest": _observed(_digest("the tokenizer's files")),
        "provider.fingerprint": _not("not applicable", "self-hosted: there is no provider"),
        "engine.name": _observed("vllm"),
        "engine.version": _observed("0.0.0-example"),
        "runtime.torch": _observed("0.0.0-example"),
        "runtime.cuda": _observed("0.0-example"),
        "runtime.gpu_name": _observed("Example GPU"),
        "runtime.driver": _observed("0.0-example"),
        "runtime.compute_capability": _observed("0.0"),
        "dtype": _observed("bfloat16", declared="bfloat16"),
        "attention_backend": _not("not observed", "the worker's own selection is not observed"),
        "batch.size": _observed("4"),
        "batch.executed_size": _not("not observed", "the engine does not report it"),
        "batch.padded_width": _not("not applicable", "vLLM pads no batch to a width"),
        "batch.position": _observed("2"),
        "batch.members": _observed([_digest("batch member 1"), _digest("batch member 2"), _digest("batch member 4")]),
        "batch.fillers": _observed("0"),
        "batch.batch_invariant": _observed("off", declared="off"),
        "input.token_ids_digest": _observed(_digest("the prompt's token ids")),
        "input.request_digest": _not("not applicable", "self-hosted: there is no request body"),
        "output.token_ids_digest": _observed(_digest("the generated token ids")),
        "output.text_digest": _not("not applicable", "self-hosted: there is no returned text"),
        "output.finish": _observed("stop"),
        "sampling.temperature": _observed("0", declared="0"),
        "fingerprints": [
            {"form": "topk_exact", "quantity": "first-token-logprobs", "k": "20", "decimals": "none",
             "value": _observed(_digest("the first token's top 20 logprobs"))},
            {"form": "tolerant", "quantity": "first-token-logprobs", "k": "20", "decimals": "3",
             "value": _observed(_digest("the first token's top 20 logprobs, 3 decimals"))},
        ],
    }


def hosted() -> dict:
    """A hosted call: every internal field not observed, the request digest observed."""
    hidden = "a hosted API does not show it"
    return {
        "format": FORMAT,
        "call.kind": "hosted",
        "call.api": "chat.completions.create",
        "credential": "present",
        "model.requested": {"status": "declared, not observed", "value": "example-hosted-model",
                            "source": SOURCE},
        "model.reported": _observed("example-hosted-model-2026-01-01"),
        "model.files_digest": _not("not observed", hidden),
        "tokenizer.digest": _not("not observed", hidden),
        "provider.fingerprint": _observed("fp_example"),
        "engine.name": _not("not observed", hidden),
        "engine.version": _not("not observed", hidden),
        "runtime.torch": _not("not observed", hidden),
        "runtime.cuda": _not("not observed", hidden),
        "runtime.gpu_name": _not("not observed", hidden),
        "runtime.driver": _not("not observed", hidden),
        "runtime.compute_capability": _not("not observed", hidden),
        "dtype": _not("not observed", hidden),
        "attention_backend": _not("not observed", hidden),
        "batch.size": _not("not observed", hidden),
        "batch.executed_size": _not("not observed", hidden),
        "batch.padded_width": _not("not observed", hidden),
        "batch.position": _not("not observed", hidden),
        "batch.members": _not("not observed", hidden),
        "batch.fillers": _not("not observed", hidden),
        "batch.batch_invariant": _not("not observed", hidden),
        "input.token_ids_digest": _not("not observed", hidden),
        "input.request_digest": _observed(_digest("the request body, credential and headers removed")),
        "output.token_ids_digest": _not("not observed", hidden),
        "output.text_digest": _observed(_digest("the returned text")),
        "output.finish": _observed("stop"),
        "fingerprints": [
            {"form": "tolerant", "quantity": "provider-logprobs", "k": "5", "decimals": "3",
             "value": _observed(_digest("the provider's top 5 logprobs, 3 decimals"))},
        ],
    }


def record_bytes(record: dict) -> bytes:
    """As a writer of the format writes one: canonical JSON, keys sorted, UTF-8."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
