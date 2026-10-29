"""Grouping, exact, first: a run's invariant signature, and the runs that share it.

The signature is the sha256 of the canonical JSON of every step's configuration as the record states
it, in the chain's order: the plan (the stages the run declares, by the digest the pipelines are
grouped by, and the manifest's optional and gated stages), and per step its name, its instrument (id,
kind, version, configuration digest, whether it is re-derivable) and its settings. A setting is what
the run index of part 1 reads as one (`run_index._settings`: `assertions.constants`, by recorded name
and value) -- the same reading, not a second index. The SDK's own constants (`onetrace.`: which inputs
a step kept, its links) are left out: they say what was kept, not how the step was configured. Inputs
and outputs are never part of it; they are what varies.

Neighbours are looked for only inside a group, so a near input on another configuration is never
offered.
"""
from __future__ import annotations

import hashlib
import json

#: The SDK's own constants, left out of the signature (`kept_inputs.KEPT`, `onetrace.links`, ...).
SDK_PREFIX = "onetrace."
#: The manifest's declarations that are part of the plan, among those the run index keeps.
PLAN = ("optional_stages", "gated_stages")
INSTRUMENT = ("id", "kind", "version", "config_digest", "rederivable")
_CACHE = "neighbours.signatures"


def parts(run, store) -> dict:
    """What the signature is taken over, for one stored run, as its record states it."""
    from onetrace_console.overview import declared_list
    from onetrace_console.run_index import _settings
    from onetrace_console.run_panels import manifest_of
    from onetrace_console.stage_pages import _stage_name, _steps
    manifest = manifest_of(run, store)
    declared = declared_list(run)
    steps = []
    for s in _steps(run, store):
        receipt = s["receipt"]
        instrument = receipt.get("instrument") if isinstance(receipt.get("instrument"), dict) else {}
        steps.append({"name": _stage_name(receipt), "index": str(s["index"]),
                      "instrument": {k: str(instrument.get(k, "")) for k in INSTRUMENT},
                      "settings": {k: v for k, v in sorted(_settings(receipt).items())
                                   if not k.startswith(SDK_PREFIX)}})
    return {"plan": {"declared": [declared[0], list(declared[1])],
                     **{k: manifest[k] for k in PLAN if k in manifest}},
            "steps": steps}


def digest(p: dict) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":"),
                                                 ensure_ascii=False).encode("utf-8")).hexdigest()


def signature(run, store) -> str:
    return digest(parts(run, store))


def signatures(store) -> dict[str, str]:
    """{run key: its invariant signature} for every run the store holds, read once per reading."""
    read = store._read()
    if read is not None and _CACHE in read:
        return read[_CACHE]
    from onetrace_console.store import arrival_order
    out = {}
    for run in arrival_order(store.runs(), newest_first=False):
        try:
            out[run.key] = signature(run, store)
        except Exception:  # noqa: BLE001 - a record that can't be read is in no group
            continue
    if read is not None:
        read[_CACHE] = out
    return out


def group_of(store, key: str) -> list[str]:
    """The other runs whose signature equals `key`'s, in the order of arrival."""
    s = signatures(store)
    mine = s.get(key)
    return [k for k, v in s.items() if v == mine and k != key] if mine else []
