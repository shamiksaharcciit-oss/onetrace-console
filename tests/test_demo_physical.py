"""The demo's four physical-world pipelines: each run reads as its builder made it.

P5 (pump maintenance), P6 (fill-level inspection), P7 (cold-chain release) and P9 (wheel-bolt
torque check) are recorded by the demo's builder over invented example data, and read by the console's own checks and comparisons --
nothing about them is set by hand. Held here, on the public demo:

1. each run's "Records agree" and whether it was declined, as the console reads it;
2. each of their comparisons' verdicts, stage by stage, from the SDK's diff the console stored, and
   the Overview's "Vs baseline" for each candidate;
3. each firmware run is the same as its baseline, with the version shown as a setting change; the
   cold-chain comparison shows the changed reading beside the changed decision, and its kept
   logger file is shown on the public demo (the demo's example-data exception);
4. every step page of theirs says its data is invented example data.

The banner's count of pipelines against those built is held in tests/test_demo_counts.py.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

#: Each run: its "Records agree" in the runs list's words, and whether a step declined it.
READINGS = {
    "p5-32-pump-baseline": ("Records agree", False),
    "p5-33-pump-offset-changed": ("Records agree", False),
    "p5-34-pump-firmware-changed": ("Records agree", False),
    "p5-35-pump-outside-window-declined": ("Records agree", True),
    "p6-36-fill-baseline": ("Records agree", False),
    "p6-37-fill-exposure-changed": ("Records agree", False),
    "p6-38-fill-below-reject-line": ("Records agree", False),
    "p7-39-cold-chain-baseline": ("Records agree", False),
    "p7-40-cold-chain-one-reading-changed": ("Records agree", False),
    "p7-41-cold-chain-decision-tampered": ("Contradicts its record", False),
    "p9-46-torque-baseline": ("Records agree", False),
    "p9-47-torque-tool-firmware-changed": ("Records agree", False),
    "p9-48-torque-one-bolt-low": ("Records agree", False),
}
#: The physical-world pipelines, by the builder's names.
PHYSICAL = ("p5", "p6", "p7", "p9")
#: Each comparison: the diff's envelope, and each stage's verdict in the SDK's words, in order.
COMPARED = {
    ("p5-32-pump-baseline", "p5-33-pump-offset-changed"): ("diverged", [
        ("readings", "same"), ("calibrate", "FIRST DIFFERENCE"), ("features", "downstream"),
        ("anomaly_check", "downstream"), ("decision", "downstream"), ("work_order", "downstream")]),
    ("p5-32-pump-baseline", "p5-34-pump-firmware-changed"): ("identical", [
        ("readings", "same"), ("calibrate", "same"), ("features", "same"), ("anomaly_check", "same"),
        ("decision", "same"), ("work_order", "same")]),
    ("p6-36-fill-baseline", "p6-37-fill-exposure-changed"): ("diverged", [
        ("measure", "FIRST DIFFERENCE"), ("classify", "reconverged"), ("reject_command", "reconverged")]),
    ("p6-36-fill-baseline", "p6-38-fill-below-reject-line"): ("diverged", [
        ("measure", "FIRST DIFFERENCE"), ("classify", "downstream"), ("reject_command", "downstream")]),
    ("p7-39-cold-chain-baseline", "p7-40-cold-chain-one-reading-changed"): ("diverged", [
        ("fill_gaps", "FIRST DIFFERENCE"), ("excursion_check", "downstream"), ("release", "downstream")]),
    ("p9-46-torque-baseline", "p9-47-torque-tool-firmware-changed"): ("identical", [
        ("read_tool_log", "same"), ("torque_check", "same"), ("station_decision", "same")]),
    ("p9-46-torque-baseline", "p9-48-torque-one-bolt-low"): ("diverged", [
        ("read_tool_log", "FIRST DIFFERENCE"), ("torque_check", "downstream"), ("station_decision", "downstream")]),
}
VS_BASELINE = {
    "p5-33-pump-offset-changed": ("changed", "First difference · stage 2 · calibrate"),
    "p5-34-pump-firmware-changed": ("same", "Same"),
    "p6-37-fill-exposure-changed": ("changed", "First difference · stage 1 · measure"),
    "p6-38-fill-below-reject-line": ("changed", "First difference · stage 1 · measure"),
    "p7-40-cold-chain-one-reading-changed": ("changed", "First difference · stage 1 · fill_gaps"),
    "p9-47-torque-tool-firmware-changed": ("same", "Same"),
    "p9-48-torque-one-bolt-low": ("changed", "First difference · stage 1 · read_tool_log"),
}
#: Each firmware run: its pair, and the setting the page shows changed (stage, setting, before, after).
FIRMWARE = {("p5-32-pump-baseline", "p5-34-pump-firmware-changed"): r"readings sensor_firmware 3\.1 3\.2",
            ("p9-46-torque-baseline", "p9-47-torque-tool-firmware-changed"): r"read_tool_log tool_firmware 4\.2 4\.3"}


def _text(page: str) -> str:
    page = re.sub(r"<style.*?</style>|<script.*?</script>", " ", page, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    return folder, store, {r.run_id: r for r in store.runs()}


def _comparison(store, runs, a, b):
    (found,) = [c for c in store.comparisons() if (c.run_a, c.run_b) == (runs[a].key, runs[b].key)]
    return found


def test_the_builder_makes_the_four_pipelines_and_their_runs(demo, examined):
    from onetrace_console.demo_store import COMPARISONS, pipeline_names, runs
    examined(1, "the builder's spec")
    assert [n for n in pipeline_names() if n in PHYSICAL] == list(PHYSICAL)
    assert {s.folder for s in runs() if s.pipeline in PHYSICAL} == set(READINGS)
    assert set(COMPARISONS) >= set(COMPARED)


@pytest.mark.parametrize("name", sorted(READINGS))
def test_each_run_reads_as_its_builder_made_it(demo, name, examined):
    from onetrace_console import records
    from onetrace_console.overview import declined
    _folder, store, runs = demo
    run = runs[name]
    examined(1, "run")
    assert (records.said(run, store), declined(run) is not None) == READINGS[name]


@pytest.mark.parametrize("pair", sorted(COMPARED), ids=lambda p: f"{p[0]}-vs-{p[1]}")
def test_each_comparison_finds_what_its_builder_changed(demo, pair, examined):
    from onetrace_console.overview import vs_baseline
    _folder, store, runs = demo
    run = _comparison(store, runs, *pair).verb("diff")
    report = json.loads(store.get(dict(run.reports)["diff.json"]))
    examined(1, "comparison")
    assert (report["envelope"], [(r["stage"], r["verdict"]) for r in report["ladder"]]) == COMPARED[pair]
    assert vs_baseline(runs[pair[1]], store) == VS_BASELINE[pair[1]]


def firmware_problems(page: str, setting: str) -> list[str]:
    """A firmware comparison's page: the two runs do not differ, and the version is a changed setting."""
    out = [] if "The two runs do not differ." in page else ["the page does not say the runs do not differ"]
    section = page[page.index("Settings that changed"):] if "Settings that changed" in page else ""
    return out + ([] if re.search(setting, section) else [f"no {setting!r} in Settings that changed"])


@pytest.mark.parametrize("pair", sorted(FIRMWARE), ids=lambda p: p[1])
def test_the_firmware_change_is_same_with_the_version_as_a_changed_setting(demo, pair, examined):
    folder, store, runs = demo
    c = _comparison(store, runs, *pair)
    page = _text((folder / "store" / "pages" / "diff" / f"{c.key}.html").read_text(encoding="utf-8"))
    examined(1, "comparison page")
    assert firmware_problems(page, FIRMWARE[pair]) == []


def test_the_cold_chain_comparison_shows_the_changed_reading_beside_the_decision(demo, examined):
    folder, store, runs = demo
    c = _comparison(store, runs, "p7-39-cold-chain-baseline", "p7-40-cold-chain-one-reading-changed")
    page = _text((folder / "store" / "pages" / "diff" / f"{c.key}-text.html").read_text(encoding="utf-8"))
    examined(1, "text diff page")
    assert '+ "temp_c": "9.4"' in page.replace("  ", " ")
    assert '- "decision": " release "' in page and '+ "decision": " quarantine "' in page
    #: The logger's kept text, the demo's own example data, is shown on the public demo.
    assert "30,9.4" in page


def test_the_cold_chain_logger_is_shown_kept_on_the_public_demo(demo, examined):
    from onetrace_console.demo_store import cold_chain
    folder, _store, runs = demo
    page = (folder / "store" / "pages" / "runs" / runs["p7-39-cold-chain-baseline"].key / "stage-1.html").read_text(
        encoding="utf-8")
    examined(1, "step page")
    assert 'data-kept="shown"' in page
    assert "invented example data for this demo" in _text(page)
    assert json.loads(cold_chain.logger_bytes(False))[:30] in html.unescape(page)


def test_every_step_page_of_theirs_says_its_data_is_invented(demo, examined):
    folder, _store, runs = demo
    pages = [p for name in READINGS for p in (folder / "store" / "pages" / "runs" / runs[name].key).glob("stage-1.html")]
    examined(len(pages), "first step pages")
    assert len(pages) == len(READINGS)
    for p in pages:
        assert "invented example data" in _text(p.read_text(encoding="utf-8")), p
