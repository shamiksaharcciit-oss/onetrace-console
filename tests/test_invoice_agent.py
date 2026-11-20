"""P12, the invoice agent, in the demo: a model call and a onedoor decision on one run, and a memory read and write.

Recorded by the demo's builder like every pipeline (example data, no network, no model called): a good run; one where
the model read 40.00 as 4,000.00, its proposal denied and its payment refused; one whose permit covers another amount;
and one whose provider fingerprint differs. The good run writes the vendor's note to memory; each later run reads that
note, by the same digest. Each run's step pages, its model-call pages and its Authorization page are its own and link
to one another.
"""

from __future__ import annotations

import json
import re

import pytest

#: In the order recorded: the run broken on purpose first, which writes the note the others read.
P12 = (
    "pzz-65-invoice-agent-permit-other-amount",
    "pzz-66-invoice-agent-good",
    "pzz-67-invoice-agent-misread",
    "pzz-68-invoice-agent-fingerprint-changed",
)
FIRST, GOOD, MISREAD, FINGERPRINT = P12


def test_the_demo_holds_p12_s_four_runs_and_its_comparisons(examined):
    from onetrace_console import demo_store

    specs = {s.folder: s for s in demo_store.runs()}
    examined(len(P12), "P12 runs")
    assert all(f in specs and specs[f].pipeline == "p12" for f in P12)
    assert demo_store.PIPELINE_NAMES["p12"] == "invoice agent"
    assert "p12" in demo_store.EXAMPLE_DATA
    assert (GOOD, MISREAD) in demo_store.COMPARISONS and (GOOD, FINGERPRINT) in demo_store.COMPARISONS
    assert GOOD in demo_store.BENCHMARKS and FIRST in demo_store.PLANTED


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    from onetrace_console import demo_store
    from onetrace_console.demo_store import onedoor_demo

    runs = tmp_path_factory.mktemp("p12") / "runs"
    runs.mkdir()
    issuer = onedoor_demo.Issuer()
    for spec in (s for s in demo_store.runs() if s.pipeline == "p12"):
        demo_store._record(spec, runs / spec.folder, issuer)
    issuer.write_beside(runs)
    return runs


def _receipt(runs, folder: str, n: int) -> dict:
    [receipt] = sorted((runs / folder / "receipts").glob(f"0{n}-*.json"))
    return json.loads(receipt.read_text(encoding="utf-8"))


def test_each_run_has_a_model_call_and_a_gated_step_citing_its_decision(recorded, examined):
    examined(len(P12), "P12 runs recorded")
    for folder in P12:
        call = _receipt(recorded, folder, 3)
        names = {o["name"] for o in call["outputs"]}
        assert {"model_call.json", "model_call.steps.json"} <= names, folder
        pay = _receipt(recorded, folder, 4)
        assert pay.get("decisions") or pay.get("decision_refs") or "decision" in json.dumps(pay), folder


def test_the_model_misread_run_proposes_4000_and_its_payment_is_refused(recorded, examined):
    examined(1, "the misread run")
    proposal = json.loads(
        (recorded / MISREAD / "artifacts" / "03-propose-payment" / "proposal.json").read_text(encoding="utf-8")
    )
    assert proposal["pay_eur"] == "4,000.00"
    assert _receipt(recorded, MISREAD, 4)["outcome"]["class"] == "refused"


def test_the_fingerprint_run_differs_only_in_its_provider_fingerprint(recorded, examined):
    def record(folder):
        return json.loads(
            (recorded / folder / "artifacts" / "03-propose-payment" / "model_call.json").read_text(encoding="utf-8")
        )

    a, b = record(GOOD), record(FINGERPRINT)
    examined(2, "model-call records")
    assert {k for k in a if a[k] != b[k]} == {"provider.fingerprint"}


def test_each_later_run_reads_the_note_the_first_run_wrote_and_keeps_it(recorded, examined):
    wrote = _receipt(recorded, FIRST, 5)["state_writes"][0]["digest"]
    examined(len(P12) - 1, "memory reads")
    assert "found" in json.dumps(_receipt(recorded, FIRST, 2)["state_reads"][0])
    for folder in P12[1:]:
        read = _receipt(recorded, folder, 2)["state_reads"][0]
        assert read["digest"] == wrote and read.get("kept") in (True, "true"), folder
        assert (recorded / folder / "state" / "02-recall-vendor" / "reads" / "1").is_file(), folder


def test_the_example_data_is_said_on_every_step(recorded, examined):
    examined(len(P12), "runs")
    for folder in P12:
        text = "".join(p.read_text(encoding="utf-8") for p in (recorded / folder / "receipts").glob("*.json"))
        assert "example data" in text, folder
        assert not re.search(r"https?://(?!payments-approver\.example)", text), folder


#: The vendor's name: plainly invented. A name widely used in sample data may be read as a real business's.
VENDOR = "Example Office Supply"


def test_the_vendor_is_a_plainly_invented_name_in_every_run_s_bytes(recorded, examined):
    from onetrace_console.demo_store import invoice_agent

    assert invoice_agent.VENDOR == VENDOR
    files = [p for folder in P12 for p in sorted((recorded / folder).rglob("*")) if p.is_file()]
    examined(len(files), "files of P12's runs")
    named = {p.relative_to(recorded).as_posix() for p in files if VENDOR.encode() in p.read_bytes()}
    assert any(n.endswith("model_call.steps.jsonl") or "steps" in n for n in named), sorted(named)[:5]
    assert all(any(n.startswith(f + "/") for n in named) for f in P12), "each run names the vendor"
    assert [p for p in files if b"Northwind" in p.read_bytes()] == []


def test_no_shipped_text_names_the_vendor_that_was_used_before(examined):
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    texts = [repo / n for n in ("README.md", "PYPI_DESCRIPTION.md", "CHANGELOG.md", "OPERATOR_README.md")]
    texts += sorted((repo / "src" / "onetrace_console").rglob("*.py"))
    examined(len(texts), "files")
    assert [p.name for p in texts if "Northwind" in p.read_text(encoding="utf-8")] == []


#: P12's record is constructed, so what it would have observed of the call is declared, as the capture store's example
#: records state theirs. What onetrace reads from the steps file it wrote stays observed: the file's digest
#: (`write_steps`), and its level, method, count and returned candidates, which `onetrace-verify` reads again.
DECLARED_NOW = (
    "model.reported",
    "provider.fingerprint",
    "input.request_digest",
    "output.finish",
    "output.text_digest",
    "steps.logprobs",
)
OBSERVED_KEPT = ("steps", "steps.level", "steps.method", "steps.count", "steps.k_returned_min", "steps.k_returned_max")


def test_the_record_declares_what_nothing_observed_and_observes_only_what_its_steps_file_holds(recorded, examined):
    from onetrace_console.demo_store import invoice_agent

    records = [p for folder in P12 for p in sorted((recorded / folder).rglob("model_call.json"))]
    examined(len(records), "model-call records")
    assert len(records) == len(P12)
    for p in records:
        doc = json.loads(p.read_text(encoding="utf-8"))
        states = {k: v for k, v in doc.items() if isinstance(v, dict) and "status" in v}
        assert sorted(k for k, v in states.items() if v["status"] == "observed") == sorted(OBSERVED_KEPT), p
        assert states["steps"]["source"].endswith("model_call.steps.jsonl") or "steps" in states["steps"]["source"]
        for k in DECLARED_NOW:
            assert states[k]["status"] == "declared, not observed", (p, k)
            assert states[k]["source"] == invoice_agent.SOURCE, (p, k)
