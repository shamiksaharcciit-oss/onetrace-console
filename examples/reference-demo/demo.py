"""A reference demo pipeline, recorded with onetrace: a small coding agent fixes a failing
auth configuration. It is recorded as a graph, its approved plan declared (`APPROVED`):

               +--> context --+
    request ---+--> tests ×2 -+--> model --> proposal --> config applied
               +--------------+

Each link is observed: a stage that reads another stage's receipt records it. The tests stage
runs twice; its first attempt fails on purpose (`TIMEOUT_NOTE`), so the record shows a retry,
and the failed attempt is kept.

Run it twice, a day apart, and the model stage reads exactly the same data both times but
writes a different value: "production" one day, "staging" the next. Everything after it
changes too. That is the case the console's pages are built to show: where two runs first
differ, what was recorded about it, and what the record does not establish -- here, why the
model wrote what it wrote.

The model is a stand-in, not a network call: it samples one of the values its instructions
allow, with the seed its settings record. The seed is the one setting that differs between
the two runs, so the difference is visible and nothing is hidden. The model stage is declared
not re-runnable, as a real sampled model call would be.

THE CLOCK
---------
By default every time in the record is read from the clock, as onetrace reads it. To produce
two runs "a day apart" without waiting a day, `--at` sets the clock the recorder reads to a
chosen start, one second per reading after it. When it does, the first stage records the
constant `clock` saying so, in the record itself: those times were set by the demo, not read
from a clock. It is the same in both runs, so it is not a difference between them.

    python demo.py OUT_DIR RUN_ID DAY [--at 2026-09-28T10:00:00Z]

DAY is 1 or 2. Nothing here contacts a network or a policy engine.
"""
from __future__ import annotations

import datetime
import json
import random
import sys
from pathlib import Path

from onetrace.emit import Instrument, Recorder

STAGES = ["request", "context", "tests", "model", "proposal", "config applied"]

TASK = "Fix the failing auth configuration."

DOCUMENTS = [
    {"id": "doc-1", "text": "Deployments read auth_env from config/auth.json."},
    {"id": "doc-2", "text": "The test suite expects auth_env to name a real environment."},
    {"id": "doc-3", "text": "Environments: production, staging."},
]

TEST_RESULTS = {
    "failed": ["test_login_redirect", "test_token_refresh", "test_session_timeout",
               "test_sso_callback"],
    "passed": "38",
    "expected": "auth_env names a real environment",
    "configured": "(unset)",
}

#: The values the model's instructions allow it to choose between.
CHOICES = ["production", "staging"]

#: The one setting that differs between the two runs.
SEED = {1: "42", 2: "17"}

CLOCK_NOTE = "set by the demo; the times in this record were not read from a clock"

#: The approved graph, over stage names (board 2): the request feeds the context, the tests and
#: the model; the model reads all three; its proposal is applied.
APPROVED = [{"from": a, "to": b} for a, b in (
    ("request", "context"), ("request", "tests"), ("request", "model"), ("context", "model"),
    ("tests", "model"), ("model", "proposal"), ("proposal", "config applied"))]

#: The tests stage's first attempt fails on purpose, so the record shows a retry. Nothing timed
#: out: the demo raises it, and says so in the error it records.
TIMEOUT_NOTE = ("set by the demo to show a retry: the first attempt raises this instead of "
                "running; nothing timed out")


def _set_clock(start: str) -> None:
    """Make the recorder read a set clock: `start`, then one second per reading."""
    import onetrace.emit as emit

    at = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
    step = datetime.timedelta(seconds=1)
    state = {"now": at - step}

    def _now() -> str:
        state["now"] += step
        return state["now"].isoformat(timespec="milliseconds")

    emit._now = _now


def main(out_dir: str, run_id: str, day: int, at: str | None = None) -> None:
    if at is not None:
        _set_clock(at)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    docs_path = out / "documents.json"
    docs_path.write_text(json.dumps(DOCUMENTS, sort_keys=True), encoding="utf-8")
    tests_path = out / "test-results.json"
    tests_path.write_text(json.dumps(TEST_RESULTS, sort_keys=True), encoding="utf-8")

    rec = Recorder(out_dir, run_id=run_id, declared_stages=STAGES, manifest=Path(__file__),
                   policy="fail-closed", declared_edges=APPROVED,
                   anchor_reason="a demo record; anchoring is not part of this demo")

    def request(ctx):
        if at is not None:
            ctx.constant("clock", CLOCK_NOTE)
        return ctx.write_json("request.json", {"task": TASK})

    def context(ctx, asked):
        ctx.read_receipt("request")
        ctx.read_json(asked)
        docs = json.loads(ctx.read_external(docs_path, "application/json", name="documents",
                                            trust_class="operator-authored"))
        ctx.constant("top_k", "3")
        return ctx.write_json("context.json", {"documents": docs})

    def tests(ctx, asked, attempt):
        ctx.read_receipt("request")
        ctx.read_json(asked)
        ctx.constant("attempt", attempt)
        if attempt == "1":
            raise TimeoutError(TIMEOUT_NOTE)
        results = json.loads(ctx.read_external(tests_path, "application/json", name="results",
                                               trust_class="operator-authored"))
        ctx.constant("suite", "auth")
        ctx.assertion("failed", str(len(results["failed"])))
        return ctx.write_json("test-results.json", results)

    model_instrument = Instrument(
        "stand-in-model", "generator", "1.0.0",
        {"choices": ",".join(CHOICES), "seed": SEED[day], "temperature": "1.0"},
        rederivable="false",
        rederivable_note="a sampled model call: its output is recorded, not replayed")

    def model(ctx, asked, found, results):
        for upstream in ("request", "context", "tests#2"):
            ctx.read_receipt(upstream)
        task = ctx.read_json(asked)
        ctx.read_json(found)
        ctx.read_json(results)
        ctx.constant("seed", SEED[day])
        value = random.Random(int(SEED[day])).choice(CHOICES)
        return ctx.write_json("model-output.json", {
            "rationale": f"The tests fail because auth_env is unset; {task['task'].lower()}",
            "action": {"type": "modify_config", "target": "auth_service",
                       "changes": {"auth_env": value}}})

    def proposal(ctx, written):
        ctx.read_receipt("model")
        action = ctx.read_json(written)["action"]
        return ctx.write_json("proposal.json", action)

    def config_applied(ctx, proposed):
        ctx.read_receipt("proposal")
        changes = ctx.read_json(proposed)["changes"]
        return ctx.write_json("auth.json", changes)

    asked = rec.run_node("request", None, Instrument("task-intake", "reader", "1.0.0",
                                                     {"source": "operator"}), request)
    found = rec.run_node("context", None, Instrument("doc-search", "retriever", "1.0.0",
                                                     {"top_k": "3"}), context, asked)
    runner = Instrument("test-runner", "tool", "2.4.0", {"suite": "auth"})
    try:
        rec.run_node("tests", "1", runner, tests, asked, "1")
    except TimeoutError:
        pass  # recorded as an error and kept; the pipeline retries once
    results = rec.run_node("tests", "2", runner, tests, asked, "2")
    written = rec.run_node("model", None, model_instrument, model, asked, found, results)
    proposed = rec.run_node("proposal", None, Instrument("action-parser", "parser", "1.0.0",
                                                         {"schema": "v1"}), proposal, written)
    rec.run_node("config applied", None, Instrument("config-writer", "tool", "1.2.0",
                                                    {"path": "config/auth.json"}),
                 config_applied, proposed)
    rec.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    at = None
    if "--at" in args:
        i = args.index("--at")
        at = args[i + 1]
        del args[i:i + 2]
    main(args[0], args[1], int(args[2]), at)
