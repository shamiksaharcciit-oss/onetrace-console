"""P10, the demo store's small agent: one step that calls a sub-agent run, recorded with onetrace 0.5.

    agent_step --> (a sub-agent run: settle)

As onetrace 0.5's nesting example has it: the agent's one step, `agent_step`, starts a run of its
own inside it, the sub-agent, whose step `settle` adds an amount, a setting it records. The agent's
step records the sub-agent's run as an input named `run:<its id>`, with the sub-agent's chain head as
its digest; the sub-agent's manifest names the run and the step that called it. Each run keeps its
own folder and chain: the sub-agent's runs are runs of their own, a pipeline of their own (P11).

The demo's runs of it: a baseline, and one with the amount the sub-agent's step records changed, two
levels down. Comparing the two agent runs, onetrace descends into the sub-agent's run and names
`settle`. The agent's step also writes two model-call records (`model_call.json`, `model_call.1.json`,
the draft format `model-call-record/0.1-draft`), the same in both runs. Everything here is invented
example data; nothing is paid or settled anywhere, and no model is called.
"""
from __future__ import annotations

import os
from pathlib import Path

#: The agent's stage, and the sub-agent's.
STAGES = ["agent_step"]
INNER_STAGES = ["settle"]
EXAMPLE = "invented example data"


def main(runs_dir, run_id: str, inner_id: str, amount: str) -> None:
    """Record one agent run, `run_id`, whose step calls the sub-agent run `inner_id`; both folders in
    `runs_dir`. `amount`: the setting the sub-agent's `settle` step records."""
    import onetrace as ot
    from onetrace.emit import Instrument
    tool = Instrument("settlement-tool", "tool", "1.0.0", {"currency": "EUR"})
    planner = Instrument("agent-planner", "agent", "1.0.0", {"steps": "1"})
    runs = Path(runs_dir)

    @ot.stage("settle", instrument=tool)
    def settle(total):
        ot.constant("amount", amount)
        ot.constant("data", EXAMPLE)
        return {"settled": str(int(total) + int(amount))}

    @ot.run(run_dir=str(runs) + "/{run_id}", stages=INNER_STAGES, manifest=__file__,
            anchor_reason="a demo record; anchoring is not part of this demo")
    def sub_agent(total):
        return settle(total)

    @ot.stage("agent_step", instrument=planner)
    def agent_step(total):
        #: The planner's two model calls, as model-call records: invented example data in the
        #: draft format (`model_call_example`); no model is called.
        from onetrace.emit import current_stage
        from onetrace_console.demo_store import model_call_example as mc
        step = current_stage()
        step.write("model_call.json", mc.record_bytes(mc.self_hosted()), "application/json")
        step.write("model_call.1.json", mc.record_bytes(mc.hosted()), "application/json")
        #: The sub-agent's run id, read by its decorator as it starts.
        os.environ["ONETRACE_RUN_ID"] = inner_id
        try:
            return sub_agent(total)
        finally:
            os.environ["ONETRACE_RUN_ID"] = run_id

    @ot.run(run_dir=str(runs) + "/{run_id}", stages=STAGES, manifest=__file__,
            anchor_reason="a demo record; anchoring is not part of this demo")
    def agent():
        return agent_step("100")

    import contextlib
    import io
    before = os.environ.get("ONETRACE_RUN_ID")
    os.environ["ONETRACE_RUN_ID"] = run_id
    try:
        #: The decorators' own "run written to <folder>" lines are the SDK's, for a person running a
        #: pipeline; a demo build says what it built itself.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            agent()
    finally:
        if before is None:
            os.environ.pop("ONETRACE_RUN_ID", None)
        else:
            os.environ["ONETRACE_RUN_ID"] = before
