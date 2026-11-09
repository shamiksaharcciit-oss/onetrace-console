"""The test runs in `tests/onetrace_runs/`, each recorded by the onetrace its folder names, through
onetrace's own decorators and onetrace-auto, by `tools/make_onetrace_runs.py`.

- `0.7.1/`: format 0.4. `refund-closed`, `refund-raised` and `refund-killed` end each of a run's three
  ways (it returns; its step raises; its process ends inside a step); `auto-orders` and `auto-bound`
  are zero-configuration runs, the second given a store bound its second call reaches.
- `0.7.1/expect/`: `calibrate-holds` and `calibrate-fails`, whose step declares expectations
  (`tools/make_expectation_runs.py`), and `after-the-run.json`, an `onetrace-expectations/1` file
  written by `onetrace expect write`.
- `0.6.1/`: format 0.3, the same pipeline's three runs, to read beside their 0.4 twins; and in
  `members/`, `tests/test_format_03.py`'s five runs (`tools/make_format_members.py`), the format 0.3
  runs the store is held to.

Each holds what its folder says it does, read from the run's own files, and each verifies with the
installed onetrace-verify. They are kept apart from `tests/fixtures`, whose runs are read as earlier
formats (`tests/test_format_03.py`).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "tests" / "onetrace_runs"
FORMATS = {"0.7.1": "0.4", "0.6.1": "0.3"}
DECORATED = ("refund-closed", "refund-raised", "refund-killed")
SETS = {"0.7.1": DECORATED + ("auto-orders", "auto-bound"), "0.6.1": DECORATED}
MEMBERS = ("held", "nokeep", "optional", "optional-and-required", "plain")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _receipts(run: Path) -> list[dict]:
    return [_json(run / e["file"]) for e in _json(run / "MANIFEST.json")["chain"]]


def _close(run: Path) -> dict | None:
    last = _receipts(run)[-1]
    instrument = last.get("instrument") or {}
    if last.get("format") == "stage-receipt/0.4" and instrument.get("id") == "onetrace.close" \
            and instrument.get("kind") == "close":
        return last
    return None


@pytest.mark.parametrize("version", sorted(SETS))
def test_each_set_is_the_runs_its_maker_makes_by_the_onetrace_its_folder_names(version, examined):
    made = _json(RUNS / version / "MADE.json")
    examined(len(SETS[version]), f"runs made by onetrace {version}")
    assert made["versions"]["onetrace"] == version, made["versions"]
    assert sorted(made["runs"]) == sorted(SETS[version])
    folders = sorted(p.name for p in (RUNS / version).iterdir() if p.is_dir() and p.name not in ("members", "expect"))
    assert folders == sorted(SETS[version])
    for name in SETS[version]:
        run = RUNS / version / name
        assert _json(run / "MANIFEST.json")["format"] == f"stage-receipt-chain/{FORMATS[version]}", name
        assert {r["format"] for r in _receipts(run)} == {f"stage-receipt/{FORMATS[version]}"}, name


def test_the_0_7_1_runs_end_each_way_a_run_ends(examined):
    """Closed by returning, closed by the step's exception, and not closed at all: in the close
    receipt's own constants, or its absence."""
    endings = {name: (_close(RUNS / "0.7.1" / name) or {}).get("assertions", {}).get("constants", {})
               for name in DECORATED}
    examined(len(endings), "0.7.1 runs' endings")
    assert endings["refund-closed"]["onetrace.ended_by"] == "exit"
    assert endings["refund-raised"]["onetrace.ended_by"] == "unhandled exception: ValueError"
    assert endings["refund-killed"] == {}
    assert [r["stage"]["name"] for r in _receipts(RUNS / "0.7.1" / "refund-killed")] == ["intake", "retrieve"]


def test_the_0_7_1_zero_configuration_runs_hold_their_hooks_and_their_gap(examined):
    orders, bound = (_json(RUNS / "0.7.1" / n / "MANIFEST.json") for n in ("auto-orders", "auto-bound"))
    examined(2, "zero-configuration runs")
    for m in (orders, bound):
        assert {"library": "requests", "status": "hooked", "version": "2.34.2"} in m["auto"]["hooks"], m["auto"]
    assert len(orders["chain"]) == 4 and not orders.get("gaps")
    streamed = _receipts(RUNS / "0.7.1" / "auto-orders")[2]["assertions"]["constants"]
    assert streamed["onetrace.http.body"] == "not observed: streamed", streamed
    assert bound["gaps"] == [{"index": "2", "reason": "store bound reached: nothing after this point is recorded; "
                              "the call went ahead", "stage": "requests.send"}]


@pytest.mark.parametrize("version", sorted(SETS))
def test_each_run_verifies_with_the_installed_verifier(version, examined):
    from tests.test_checks import _require_installed
    _require_installed()
    said = {}
    for name in SETS[version]:
        done = subprocess.run([sys.executable, "-m", "onetrace_verify.cli", "MANIFEST.json"],
                              cwd=RUNS / version / name, capture_output=True, text=True, timeout=300)
        said[name] = (done.returncode, done.stdout.strip().splitlines()[-1].rsplit("->", 1)[-1].strip())
    examined(len(said), f"onetrace {version} runs verified")
    assert said == {name: (0, "PASS") for name in SETS[version]}, said


def test_the_0_6_1_member_runs_are_format_0_3_made_by_onetrace_0_6_1(examined):
    made = _json(RUNS / "0.6.1" / "members" / "MADE.json")
    examined(len(MEMBERS), "format 0.3 member runs")
    assert made["versions"]["onetrace"] == "0.6.1" and made["runs"] == list(MEMBERS), made
    assert sorted(p.name for p in (RUNS / "0.6.1").iterdir() if p.is_dir()) == sorted(SETS["0.6.1"] + ("members",))
    for name in MEMBERS:
        run = RUNS / "0.6.1" / "members" / name
        assert _json(run / "MANIFEST.json")["format"] == "stage-receipt-chain/0.3", name
        assert {r["format"] for r in _receipts(run)} == {"stage-receipt/0.3"}, name


def test_the_0_7_1_expectation_runs_and_file_are_onetrace_0_7_1_s_and_verify_as_their_expectations_read(examined):
    """calibrate-holds verifies PASS; calibrate-fails FAILs on its two failing expectations alone; and
    the file is onetrace's own `onetrace-expectations/1`, declared after the run."""
    from tests.test_checks import _require_installed
    _require_installed()
    expect = RUNS / "0.7.1" / "expect"
    made = _json(expect / "MADE.json")
    examined(3, "expectation runs and file")
    assert made["versions"]["onetrace"] == "0.7.1" and sorted(made["runs"]) == ["calibrate-fails", "calibrate-holds"]
    doc = _json(expect / "after-the-run.json")
    assert doc["format"] == "onetrace-expectations/1", doc.get("format")
    assert {e["declared"] for e in doc["expectations"]} == {"after the run"}
    said = {}
    for name in made["runs"]:
        done = subprocess.run([sys.executable, "-m", "onetrace_verify.cli", "MANIFEST.json"], cwd=expect / name,
                              capture_output=True, text=True, timeout=300)
        fails = sorted(ln.split("]", 1)[1].split(" -- ")[0].strip() for ln in done.stdout.splitlines()
                       if ln.startswith("[FAIL"))
        said[name] = (done.stdout.strip().splitlines()[-1].rsplit("->", 1)[-1].strip(), fails)
    assert said == {"calibrate-holds": ("PASS", []),
                    "calibrate-fails": ("FAIL", ["expect calibrate.serial", "expect calibrate.under-400"])}, said
