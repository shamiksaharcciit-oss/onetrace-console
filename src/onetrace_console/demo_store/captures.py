"""The capture store: P10's three capture runs, a store of its own beside the demo, built by the demo builder's
code and never into the demo's own runs (`demo_store.runs`), so the demo's tables, counts and comparisons stay as
they are.

Each run is P10's agent with its sub-agent, as the demo records them, but the agent step's self-hosted model call is
written in `model-call-record/1.1` with an L3 steps file (L2's top-k with it), through onetrace's own writer:
example data, constructed for the demo, no model called (`model_call_example.CAPTURES`). A baseline; a run whose
logits row changes before its chosen token; and one with batch-invariant mode off. The baseline is compared with
each, so a comparison shows the model's rows and choices at the first difference (`token_levels`).

The same interface as the demo builder's, for `folder_load.build_public(builder=...)`: `NAME`, `runs`, `build`,
`deliver`, `example_input_digests`.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from onetrace_console.demo_store import (
    RUNS_DIRNAME,
    TRUST_NAME,
    RunSpec,
    _record,
    app_traces,
    keys,
    traceparent_for,
    write_build_record,
    write_traces,
)

#: This builder's name in its build record: a public console serving its build reads its example data
#: (`demo_store.example_digests_for`).
NAME = "captures"


def runs() -> list[RunSpec]:
    """The capture store's runs, in recording order: each agent run, then its sub-agent's."""
    out = []
    for n, capture in ((59, "baseline"), (61, "row-changed"), (63, "batch-off")):
        agent, inner = f"pz-{n}-agent-capture-{capture}", f"pz-{n + 1}-agent-capture-{capture}-subagent"
        out.append(RunSpec(agent, "p10", {"inner": inner, "amount": "10", "capture": capture}))
        out.append(RunSpec(inner, "p11", {"of": agent}))
    return out


#: The comparisons, (baseline, candidate) by run folder: the baseline against each other capture.
COMPARISONS = [
    ("pz-59-agent-capture-baseline", "pz-61-agent-capture-row-changed"),
    ("pz-59-agent-capture-baseline", "pz-63-agent-capture-batch-off"),
]


def example_input_digests() -> frozenset:
    """The sha256 of every input this builder's runs keep and every output it names as example data (the capture
    steps files), from the pipelines' own code: "sha256:<hex>". The demo's own registry is not read."""
    from onetrace_console.demo_store import agent_settle

    return frozenset(
        "sha256:" + hashlib.sha256(data).hexdigest()
        for spec in runs()
        for data in (*agent_settle.kept_inputs(spec.args), *agent_settle.example_outputs(spec.args))
    )


def build(folder: Path) -> list[RunSpec]:
    """Record and sign every run into `folder`/runs, with each run's spans, and write the trust file and the build
    record. `folder` must be new or empty."""
    folder = Path(folder)
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise FileExistsError(f"{folder} is not a new, empty folder")
    specs = runs()
    before = os.environ.get("TRACEPARENT")
    try:
        for spec in specs:
            run_dir = folder / RUNS_DIRNAME / spec.folder
            os.environ["TRACEPARENT"] = traceparent_for(spec.folder)
            _record(spec, run_dir)
            #: Signed as every demo run is (the sub-agent's run, recorded by its agent's, too).
            keys.sign(run_dir, keys.TRUSTED_SEED)
    finally:
        if before is None:
            os.environ.pop("TRACEPARENT", None)
        else:
            os.environ["TRACEPARENT"] = before
    write_traces(folder / RUNS_DIRNAME, [s.folder for s in specs])
    app_traces.write(folder / RUNS_DIRNAME, [s.folder for s in specs])
    (folder / TRUST_NAME).write_bytes(keys.trust_file_bytes())
    write_build_record(folder, (RUNS_DIRNAME, TRUST_NAME), builder=NAME)
    return specs


def deliver(folder: Path, store, config):
    """Deliver and check every run in `folder`/runs through the console's own path, then store the comparisons.
    Returns the load, its comparison the first of them."""
    from dataclasses import replace

    from onetrace_console.folder_load import _compare, load_folder

    loaded = load_folder(Path(folder) / RUNS_DIRNAME, store, config)
    first, note = None, ""
    for i, pair in enumerate(COMPARISONS):
        comparison, why = _compare(list(loaded.runs), pair, store)
        if i == 0:
            first, note = comparison, why
    return replace(loaded, comparison=first, compare_note=note)
