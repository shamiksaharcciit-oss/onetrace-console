"""Each step's effect label: read, write or unknown, and its basis, as its receipt records it.

On onetrace 0.8.0's own vectors (`tests/format_04_item8/`): steps declared read and write on the stage, calls a hook
labelled by their kind, a step whose effect a framework hook could not classify, and steps a counterfactual put in.

- **Kept with each step** (`StoredRun.steps`), only where the receipt holds a label in the format and the verifier
  does not FAIL it; a step with no label gets none, never "read".
- **Drawn** on the step's page ("Effect": the value and its basis, with what a label is not), and in the Runs page's
  Steps column, each value with its steps.
- **A re-run stopped before a step labelled write** says so in its own ending, already on the Runs page's row.
"""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent / "format_04_item8" / "accept"
RAN_AT = "2026-11-13T00:00:00+00:00"
LABELLED = (
    "A05-auto-run",
    "A07-counterfactual",
    "A208-framework-graph",
    "A32-state-read-write",
    "A03-rerun-stopped-labelled",
)


def _labels(folder: Path) -> dict[str, dict]:
    """Each step's last receipt's label, by its stage name, read from the vector's own files."""
    out: dict[str, dict] = {}
    for f in sorted((folder / "receipts").glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        name = (r.get("stage") or {}).get("name")
        if name and not name.startswith("onetrace.") and isinstance(r.get("effect_label"), dict):
            out[name] = {"value": r["effect_label"]["value"], "basis": r["effect_label"]["basis"]}
    return out


@pytest.fixture(scope="module")
def held(tmp_path_factory):
    from tests.test_checks import _require_installed

    _require_installed()
    from onetrace_console import run_index
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from tests.test_format_03 import _tar

    store = Store(tmp_path_factory.mktemp("effects") / "store")
    runs = {
        n: run_and_record(accept(_tar(HERE / n), store).run, store, ran_at=RAN_AT)
        for n in (*LABELLED, "A02-closed-recorder")
    }
    return store, runs, run_index.build(store)


def test_each_step_keeps_its_label_as_recorded_and_an_unlabelled_step_none(held, examined):
    _store, runs, _index = held
    seen = 0
    for name, run in runs.items():
        want = _labels(HERE / name)
        for step in json.loads(run.steps):
            if step["mark"] == "not-reached":
                assert "effect" not in step, (name, step)
                continue
            seen += 1
            assert step.get("effect") == want.get(step["step"]), (name, step["step"])
    examined(seen, "steps")
    values = {s["effect"]["value"] for r in runs.values() for s in json.loads(r.steps) if "effect" in s}
    assert values == {"read", "write", "unknown"}, values
    assert not any("effect" in s for s in json.loads(runs["A02-closed-recorder"].steps))


def test_a_label_the_verifier_fails_is_not_drawn_and_its_row_is_shown(examined):
    from onetrace_console import effect_label

    receipt = {"effect_label": {"value": "read", "basis": "declared on the stage"}}
    rows = [{"name": "receipts/01-a.json: effect_label against effects", "result": "FAIL", "detail": "planted"}]
    examined(2, "labels")
    assert effect_label.kept(receipt, "receipts/01-a.json", rows) is None
    section = effect_label.step_section(receipt, "receipts/01-a.json", rows)
    assert 'data-check-row="fail"' in section and "data-effect=" not in section
    assert effect_label.kept({"effect_label": {"value": "maybe", "basis": "declared on the stage"}}, "x", []) is None


def test_each_labelled_step_s_page_says_its_effect_and_what_a_label_is_not(held, examined):
    from onetrace_console import effect_label
    from onetrace_console.pages import render_execution

    store, runs, _index = held
    seen = 0
    for name in ("A05-auto-run", "A07-counterfactual", "A208-framework-graph", "A03-rerun-stopped-labelled"):
        run = runs[name]
        pages = {
            k: v for k, v in render_execution(run, store, generated_at=RAN_AT).pages.items() if k.startswith("stage-")
        }
        want = _labels(HERE / name)
        for rel, page in pages.items():
            section = re.search(
                r'<section data-section="effect"[^>]*data-effect="([a-z]+)"[^>]*>(.*?)</section>', page, re.S
            )
            if section is None:
                continue
            seen += 1
            text = unescape(re.sub(r"<[^>]+>", "", section.group(2)))
            assert effect_label.NON_CLAIM in text, (name, rel)
            assert any(
                f"{v['value']}: {v['basis']}" in text and section.group(1) == v["value"] for v in want.values()
            ), (
                name,
                rel,
                text,
            )
    examined(seen, "steps' pages with an effect")
    assert seen >= 6
    plain = render_execution(runs["A02-closed-recorder"], store, generated_at=RAN_AT).pages
    assert not any('data-section="effect"' in p for p in plain.values())


def test_the_runs_page_names_each_step_by_its_label(held, examined):
    from onetrace_console import runs_page

    _store, runs, index = held
    page = runs_page.body(index, {"page": "all"}, public=False)
    examined(len(runs), "rows")
    for name, run in runs.items():
        row = re.search(rf'<tr data-run="[^"]*" data-key="{run.key}">.*?</tr>', page, re.S).group(0)
        said = unescape(re.search(r"<span class=\"note\" data-steps-said>(.*?)</span>", row, re.S).group(1))
        for s in json.loads(run.steps):
            if "effect" in s:
                assert re.search(rf"\b{s['effect']['value']}: [^;]*\b{re.escape(s['step'])}\b", said), (name, s, said)
        if name == "A02-closed-recorder":
            assert not re.search(r"\b(read|write|unknown): ", said)


def test_a_re_run_stopped_before_a_write_says_so_on_its_row(held, examined):
    from onetrace_console import runs_page

    _store, runs, index = held
    page = runs_page.body(index, {"page": "all"}, public=False)
    row = re.search(rf'<tr data-run="[^"]*" data-key="{runs["A03-rerun-stopped-labelled"].key}">.*?</tr>', page, re.S)
    examined(1, "stopped re-run")
    closed = re.search(r'<td [^>]*data-answer="closed"[^>]*>(.*?)</td>', row.group(0), re.S).group(1)
    assert "re-run stopped before b: effect write (declared on the stage)" in unescape(re.sub(r"<[^>]+>", "", closed))
