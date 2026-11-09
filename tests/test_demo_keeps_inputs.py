"""Every demo pipeline keeps its inputs (console 0.7.0): each step's input from outside the run is kept beside
its digest, under the SDK's per-input opt-in, and an input read from an earlier step's output stays by
digest. P4, P7 and P8 kept theirs already and are as they were: P4 keeps its ticket, and its question,
the pipeline's own operator-authored text, stays by digest, as tests/test_demo_example_inputs.py holds a
store that is not the demo to it. P2 keeps nothing: it is the shipped reference example byte for byte
(`examples/reference-demo/demo.py`, whose committed runs tests/test_reference_demo.py pins).

Held here, on the public demo built once a session (`shared_demo`):
- every run of every pipeline but P2 keeps each outside input, its file's sha256 the input's digest, and
  no run keeps an input that is an earlier step's output;
- every kept input is the builder's own invented example data (`example_input_digests`), so a public
  console may show it;
- a run of each pipeline but P2 opens its step page with the kept text shown (the input view);
- the 15 comparisons the build stores give the verdicts and first differences they gave before
  (`tests/fixtures/demo_070/verdicts.json`, from the build at 23e8176), row for row; the 16th, beside the
  kept runs of the hosted demo, is built from those kept runs, which this change does not touch;
- `onetrace-verify` gives every run the exit it gave before (`verify.tsv`, from the same build): every
  run passes but the five the demo breaks on purpose.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "demo_070"
#: The pipeline that keeps nothing: the shipped reference example, byte for byte.
UNCHANGED = "p2"
#: The one outside input a keeping pipeline doesn't keep, as before: P4's own question.
NOT_KEPT = {("p4", "question")}
GENERATED_AT = "2026-11-07T00:00:00+00:00"


def _receipts(run: Path) -> list[tuple[str, dict]]:
    return [(p.stem, json.loads(p.read_text(encoding="utf-8"))) for p in sorted((run / "receipts").glob("*.json"))]


def outside_inputs(run: Path) -> list[dict]:
    """Each step's inputs, as the record lists them, with whether each came from outside the run (not a
    receipt, not a run link, not any earlier step's output) and whether it is kept (listed by its step,
    and its file's sha256 its digest)."""
    produced, rows = set(), []
    for stem, r in _receipts(run):
        consts = (r.get("assertions") or {}).get("constants") or {}
        listed = [n for n in (consts.get("onetrace.kept_inputs") or "").split(", ") if n]
        for i in r.get("inputs") or []:
            name, digest = i.get("name", ""), i.get("digest", "")
            if name.startswith(("receipt:", "run:")):
                continue
            f = run / "inputs" / stem / f"{name}.json"
            kept = name in listed and f.is_file() and "sha256:" + hashlib.sha256(f.read_bytes()).hexdigest() == digest
            rows.append({"step": stem, "input": name, "outside": digest not in produced, "kept": kept})
        produced |= {o.get("digest", "") for o in r.get("outputs") or []}
    return rows


@pytest.fixture(scope="module")
def runs(shared_demo) -> dict[str, Path]:
    from onetrace_console.demo_store import runs as specs
    folder = shared_demo["folder"] / "runs"
    return {s.folder: folder / s.folder for s in specs()}


@pytest.fixture(scope="module")
def pipeline_of():
    from onetrace_console.demo_store import runs as specs
    return {s.folder: s.pipeline for s in specs()}


def keep_problems(runs: dict[str, Path], pipeline_of: dict[str, str]) -> list[str]:
    out = []
    for name, run in runs.items():
        rows = outside_inputs(run)
        if pipeline_of[name] == UNCHANGED:
            out += [f"{name}: {r['step']} keeps {r['input']}" for r in rows if r["kept"]]
            continue
        if not any(r["outside"] for r in rows):
            out.append(f"{name}: no input from outside the run")
        out += [f"{name}: {r['step']} does not keep {r['input']}" for r in rows if r["outside"] and not r["kept"]
                and (pipeline_of[name], r["input"]) not in NOT_KEPT]
        out += [f"{name}: {r['step']} keeps {r['input']}, an earlier step's output" for r in rows
                if r["kept"] and not r["outside"]]
    return out


def test_every_pipeline_but_p2_keeps_each_outside_input_and_none_an_earlier_output(runs, pipeline_of, examined):
    examined(sum(len(outside_inputs(r)) for r in runs.values()), "inputs of the demo's runs")
    assert keep_problems(runs, pipeline_of) == []


def test_sabotage_a_removed_kept_file_is_named(runs, pipeline_of, tmp_path, examined):
    import shutil
    name = "p5-32-pump-baseline"
    copy = tmp_path / name
    shutil.copytree(runs[name], copy)
    for f in (copy / "inputs").rglob("*.json"):
        f.unlink()
    examined(1, "run with its kept files removed")
    assert keep_problems({name: copy}, pipeline_of) == [f"{name}: 01-readings does not keep readings.csv"]


def test_every_kept_input_is_the_builder_s_own_example_data(runs, examined):
    from onetrace_console.demo_store import example_input_digests
    kept = {"sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
            for r in runs.values() for p in (r / "inputs").glob("*/*.json")} if runs else set()
    allowed = example_input_digests()
    examined(len(kept), "kept inputs' digests")
    assert kept and kept <= allowed and allowed <= kept, (sorted(kept - allowed), sorted(allowed - kept))


def test_a_run_of_each_pipeline_but_p2_opens_its_step_page_with_the_kept_text(shared_demo, examined):
    from onetrace_console.frame import rendering
    from onetrace_console.overview import pipelines
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store
    from onetrace_console.demo_store import runs as specs
    store = Store(shared_demo["folder"] / "store" / "store")
    by_id = {s.run_id or s.folder: s.pipeline for s in specs()}
    seen, missing = [], []
    for p in pipelines(store):
        run = p.runs[0]
        if by_id[run.run_id] == UNCHANGED:
            continue
        with rendering(onedoor=False, sign_in=False, public=False):
            pages = render_execution(run, store, generated_at=GENERATED_AT).pages
        seen.append(p.label)
        if not any("<pre data-kept-text>" in h and "</pre>" in h.split("<pre data-kept-text>", 1)[1][:20000]
                   for n, h in pages.items() if n.startswith("stage-")):
            missing.append(f"{p.label} ({run.run_id})")
    examined(len(seen), "pipelines")
    assert len(seen) == 10 and missing == [], missing


def verdicts(root: Path) -> dict:
    """Each stored comparison's verdict, by its two run ids: per verb, its exit and refusal, and its
    report's envelope, exit, reason, stages identical before, first difference and cause."""
    from onetrace_console.store import Store
    st = Store(root / "store" / "store")
    ids = {r.key: r.run_id for r in st.runs()}
    out = {}
    for c in st.comparisons():
        row = {}
        for v in c.verbs:
            reps = {}
            for name, key in v.reports:
                if name in ("diff.json", "localize.json"):
                    d = json.loads(st.get(key))
                    cause = d.get("cause")
                    reps[name] = {"envelope": d.get("envelope"), "exit": d.get("exit"), "reason": d.get("reason"),
                                  "identical_before": d.get("stages_identical_before_first_difference"),
                                  "first_difference": d.get("first_difference"),
                                  "cause": cause.get("kind") if isinstance(cause, dict) else cause}
            row[v.verb] = {"exit": v.exit_status, "refused": v.refused, "reports": reps}
        out[f"{ids.get(c.run_a)} -> {ids.get(c.run_b)}"] = row
    return out


def test_the_15_comparisons_give_the_verdicts_they_gave_before_row_for_row(shared_demo, examined):
    before = json.loads((FIXTURES / "verdicts.json").read_text(encoding="utf-8"))
    now = verdicts(shared_demo["folder"])
    examined(len(now), "comparisons")
    assert sorted(now) == sorted(before) and len(now) == 15
    assert [k for k in before if now[k] != before[k]] == []


def test_onetrace_verify_gives_every_run_the_exit_it_gave_before(shared_demo, runs, examined):
    before = dict(line.split("\t") for line in (FIXTURES / "verify.tsv").read_text(encoding="utf-8").splitlines())
    from tests.console_scripts import required_script
    verify = required_script("onetrace-verify")
    trust = shared_demo["folder"] / "trust.json"
    now = {}
    for name, run in sorted(runs.items()):
        done = subprocess.run([str(verify), "--require-artifacts", "--trust", str(trust), str(run)],
                              capture_output=True, text=True, timeout=300)
        now[name] = str(done.returncode)
    examined(len(now), "runs")
    assert now == {k: v for k, v in before.items() if k in runs} and len(now) == len(runs)
    assert sorted(k for k, v in now.items() if v != "0") == [
        "p1-14-candidate-set3-byte-changed", "p1-15-candidate-set4-file-deleted", "p1-16-candidate-set5-no-artifacts",
        "p7-41-cold-chain-decision-tampered", "p8-49-invoice-paid-on-deny"]
