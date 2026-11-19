"""The test runs for format 0.5's store state (`tests/format_05_state/`).

Two runs recorded by onetrace 0.8.0's own decorators (`tools/make_state_runs.py`, `tools/onetrace_runs/store_state.py`),
one keeping its outputs and store values and one keeping neither; onetrace 0.8.0's own accept vector for a cut step;
and five of its own reject vectors, one for each state row the console reads, copied byte for byte from its release
sdist. `PROVENANCE.md` names the wheels and the sdist by sha256.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from tests.test_format_05_agents_runs import _json, _receipts, _verify

HERE = Path(__file__).resolve().parent / "format_05_state"
RECORDED = ("state-kept", "state-not-kept")
ACCEPT = ("A41-state-cut",)
REJECT = {
    "R51-state-digest-out-of-form": "receipts/01-sql.json: state entries",
    "R60-state-writes-labelled-read": "receipts/02-object.json: state_writes against effect_label",
    "R61-state-kept-does-not-recompute": "receipts/01-s.json: state kept",
    "R70-state-at-open-copy-differs": "state at open",
    "R71-state-at-open-not-first": "state at open",
}


def test_every_file_is_the_one_its_provenance_names(examined):
    said = {}
    for line in (HERE / "PROVENANCE.md").read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"- `((?:accept|reject)/[^`]+)`: `sha256:([0-9a-f]{64})`", line.strip())
        if m:
            said[m.group(1)] = m.group(2)
    have = {
        p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for d in ("accept", "reject")
        for p in (HERE / d).rglob("*")
        if p.is_file()
    }
    examined(len(have), "files of onetrace's vectors")
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


@pytest.mark.parametrize("name", ACCEPT)
def test_the_cut_vector_verifies(name, examined):
    examined(1, f"{name} verified")
    assert _verify(HERE / "accept" / name) == (0, "PASS", [])


@pytest.mark.parametrize("name", sorted(REJECT))
def test_each_reject_vector_fails_on_its_own_row_alone(name, examined):
    examined(1, f"{name} verified")
    assert _verify(HERE / "reject" / name) == (1, "FAIL", [REJECT[name]])


def test_the_recorded_runs_hold_the_members_the_pipeline_declares(examined):
    receipts = {r["stage"]["name"]: r for r in _receipts(HERE / "state-kept")}
    examined(len(receipts), "receipts of the kept run")
    reads = receipts["lookup"]["state_reads"]
    assert [(e["store"], e["store_kind"], e["version"]) for e in reads] == [
        ("orders_db.orders", "postgres", "0/16B3748"),
        ("kb.articles", "document", "not observed"),
        ("replies.cache", "kv", "not observed"),
    ]
    assert reads[2] == {
        "store": "replies.cache",
        "store_kind": "kv",
        "key": "A-1001",
        "version": "not observed",
        "found": "false",
    }
    assert receipts["search"]["state_reads"][0]["digest_status"].startswith("not observed: ")
    assert [e["store"] for e in receipts["note"]["state_writes"]] == ["tickets.notes"]
    assert receipts["reply"]["state_reads"] == receipts["reply"]["state_writes"] == []
    assert not any(k.startswith("state_") for k in receipts["draft"])
    assert [s["store"] for s in receipts["intake"]["state_at_open"]] == ["orders_db.orders", "tickets.notes"]
    kept = sorted(p.relative_to(HERE / "state-kept").as_posix() for p in (HERE / "state-kept" / "state").rglob("*"))
    assert [k for k in kept if k.count("/") == 3] == [
        "state/02-lookup/reads/1",
        "state/02-lookup/reads/2",
        "state/05-note/writes/1",
    ]
    assert not (HERE / "state-not-kept" / "state").exists()
    assert _receipts(HERE / "accept" / "A41-state-cut")[0]["state_cut"] == "2"
