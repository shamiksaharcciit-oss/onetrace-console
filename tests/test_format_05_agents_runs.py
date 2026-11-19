"""The test runs for format 0.5's step kinds, agents, tool calls and messages (`tests/format_05_agents/`).

Two runs recorded by onetrace 0.8.0's own decorators (`tools/make_agent_runs.py`, `tools/onetrace_runs/agents.py`),
one keeping its outputs and one not, and five of onetrace 0.8.0's own reject vectors, one for each member the
console reads, copied byte for byte from its sdist. `PROVENANCE.md` names the wheels and the sdist by sha256.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent / "format_05_agents"
RECORDED = ("agents-kept", "agents-not-kept")
REJECT = {
    "R41-step-kind-outside-list": "receipts/04-decision.json: step kind",
    "R45-requested-by-not-earlier": "receipts/02-weather.json: tool_call requested_by",
    "R47-run-agent-disagrees": "run agent",
    "R74-message-digest-out-of-form": "receipts/01-s.json: messages",
    "R79-received-no-such-seq": "receipts/02-billing.json: messages_received",
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _receipts(run: Path) -> list[dict]:
    return [_json(run / e["file"]) for e in _json(run / "MANIFEST.json")["chain"]]


def _verify(run: Path) -> tuple[int, str, list[str]]:
    done = subprocess.run(
        [sys.executable, "-m", "onetrace_verify.cli", "MANIFEST.json"],
        cwd=run,
        capture_output=True,
        text=True,
        timeout=300,
    )
    counts = [ln for ln in done.stdout.splitlines() if " pass, " in ln and "->" in ln]
    fails = [ln.split("]", 1)[1].split(" -- ")[0].strip() for ln in done.stdout.splitlines() if ln.startswith("[FAIL")]
    return done.returncode, counts[-1].rsplit("->", 1)[-1].strip() if counts else "", fails


def test_every_file_is_the_one_its_provenance_names(examined):
    said = {}
    for line in (HERE / "PROVENANCE.md").read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"- `(reject/[^`]+)`: `sha256:([0-9a-f]{64})`", line.strip())
        if m:
            said[m.group(1)] = m.group(2)
    have = {
        p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (HERE / "reject").rglob("*")
        if p.is_file()
    }
    examined(len(have), "files of the reject vectors")
    assert have and have == said
    made = _json(HERE / "MADE.json")
    assert made["versions"]["onetrace"] == "0.8.0" and sorted(made["runs"]) == sorted(RECORDED)
    assert all(r["exit"] == 0 for r in made["runs"].values()), made


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


@pytest.mark.parametrize("name", RECORDED)
def test_each_recorded_run_is_format_0_5_and_verifies(name, examined):
    run = HERE / name
    examined(1, f"{name} verified")
    assert _json(run / "MANIFEST.json")["format"] == "stage-receipt-chain/0.5"
    assert _verify(run) == (0, "PASS", [])


@pytest.mark.parametrize("name", sorted(REJECT))
def test_each_reject_vector_fails_on_its_own_row_alone(name, examined):
    examined(1, f"{name} verified")
    assert _verify(HERE / "reject" / name) == (1, "FAIL", [REJECT[name]])


def test_the_recorded_runs_hold_the_members_the_pipeline_declares(examined):
    receipts = {r["stage"]["name"]: r for r in _receipts(HERE / "agents-kept")}
    examined(len(receipts), "receipts of the kept run")
    assert {n: (r.get("step") or {}).get("kind") for n, r in receipts.items() if n != "onetrace.close"} == {
        "intake": None,
        "triage": "decision",
        "research": "retrieval",
        "draft": "model call",
        "order_status": "tool call",
        "reply": None,
    }
    assert {r["run_agent"]["name"] for r in receipts.values()} == {"support-desk"}
    assert (receipts["triage"]["agent"]["name"], receipts["research"]["agent"]["name"]) == ("triage", "researcher")
    assert "agent" not in receipts["draft"]
    assert receipts["order_status"]["tool_call"]["requested_by"] == {"step": "draft", "call_id": "call-1"}
    sent = receipts["triage"]["messages"]
    assert [(m["seq"], m["from"], m["to"], m["kind"]) for m in sent] == [("1", "triage", "researcher", "task")]
    assert receipts["research"]["messages_received"] == [
        {"from_step": "triage", "seq": "1", "digest": sent[0]["digest"]}
    ]
    assert (HERE / "agents-kept" / "messages").is_dir() and not (HERE / "agents-not-kept" / "messages").exists()
