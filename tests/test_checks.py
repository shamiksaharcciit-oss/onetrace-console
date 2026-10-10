"""The check runner keeps the verifier's report exactly as produced.

The order's checks, each with a test named after it:

  - the stored report is byte-identical to running `onetrace-verify` by hand on the same
    folder;
  - a contradicting run is recorded as contradicting.

The first is deliberately not asserted by the code that produces the bytes: the test runs
the console script itself, in a separate process, and compares.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from onetrace_console import checks
from onetrace_console.checks import (CONTRADICTS, COULD_NOT_CHECK, HOLDS,
                                     TOPOLOGY_NO_EDGE_ROWS, VERIFIER_MODULES,
                                     CheckRunnerError, check, materialise,
                                     run_and_record, shipped_verifier)
from onetrace_console.ingest import MANIFEST_NAME, SUMS_NAME, accept
from tests.conftest import make_tar

pytest.importorskip("viewer", reason=None) if False else None  # see _require below

FIXED_RAN_AT = "2026-09-26T12:00:00+02:00"


REPO = Path(__file__).resolve().parent.parent


def _require_installed():
    """Refuse, with the command, rather than skip.

    The whole subject of this file is whether the console keeps a real verifier's real
    output. A skip here would report success for having examined nothing.
    """
    missing = []
    #: The verifier is asked for by the locator, not by a literal module name. The SDK
    #: moved `verify.py` inside the `onetrace_verify` package at pin `4c11f0e`, so a
    #: hardcoded `import verify` fails at the new pin -- which is what it did here, turning
    #: 30 tests into errors that said "not installed" about a verifier that was installed.
    try:
        from onetrace_console.checks import shipped_verifier
        shipped_verifier()
    except Exception:                       # noqa: BLE001 - reported, not swallowed
        missing.append("the verifier (tried " + ", ".join(VERIFIER_MODULES) + ")")
    if missing:
        pytest.fail(
            f"not importable: {missing}. The pinned distributions are not installed.\n"
            f"    python -m pip install -r requirements.lock --require-hashes\n"
            f"This refuses rather than skips (see the module docstring).")


@pytest.fixture
def stored(delivery, store):
    _require_installed()
    result = accept(delivery, store)
    assert result.run is not None
    return result.run


# ------------------------------------------------------- the verifier's own report

def test_the_verifier_is_located_by_import_and_not_by_a_path():
    """It must come from the pinned distribution, never from a copy committed here.

    "Not inside this directory" was the first formulation and it was wrong. Once a
    pinned clone under `.pins/` sat inside the working directory and was exactly what was
    supposed to provide it; now the distribution is a hash-pinned PyPI wheel
    installed into `site-packages`, outside the working directory entirely, but the
    property that matters is unchanged either way: no file git TRACKS here is the verifier
    — a copy would be committed; an install (from `site-packages` or, before, a
    materialised pin) is not.
    """
    _require_installed()
    verifier = shipped_verifier()
    assert verifier.name == "verify.py"
    assert verifier.is_file()
    assert not _is_tracked_here(verifier), (
        f"the verifier resolves to {verifier}, which is TRACKED in this repository. "
        f"Step 0 says depend on it, not copy it")


def test_a_run_that_holds_is_recorded_as_holding(stored, store):
    run = run_and_record(stored, store, ran_at=FIXED_RAN_AT)
    assert run.check_verdict == HOLDS, run.check_verdict
    assert run.check_exit == "0"
    assert run.check_report, "no report object was stored"
    envelope = json.loads(store.get(run.check_report).decode("utf-8"))
    assert envelope["format"] == "onetrace-viewer/check-report/0.1"
    assert "->  PASS" in envelope["stdout"]


def test_the_stored_report_is_byte_identical_to_running_the_command_by_hand(stored, store,
                                                                           tmp_path):
    """Step 3's check, and the comparison is made by a separate process.

    `onetrace-verify .` is also the command the page shows a reader. Asserting that the
    stored bytes equal what that command produces is what stops the shown command being a
    claim nobody checked.
    """
    run = run_and_record(stored, store, ran_at=FIXED_RAN_AT)
    stored_stdout = json.loads(store.get(run.check_report).decode("utf-8"))["stdout"]

    folder = materialise(run, store, tmp_path / "byhand")
    script = Path(sys.executable).parent / "onetrace-verify.exe"
    if script.is_file():
        argv = [str(script), "."]
    else:                                  # the same entry point, without relying on PATH
        argv = [sys.executable, "-m", "onetrace_verify.cli", "."]

    # The child runs with `cwd=folder`, so a RELATIVE PYTHONPATH entry resolves against the
    # temp folder and finds nothing there. Measured against the earlier gate, whose
    # PYTHONPATH carried `.pins/canary` and `.pins/onetrace/src`: the `-m` branch produced
    # empty stdout and `No module named onetrace_verify` on stderr, while the in-process run
    # was fine. Now `onetrace-verify` is a real pip-installed distribution and this
    # specific failure can no longer happen for IT -- but the gate's `PYTHONPATH=src` is
    # still relative, so every entry is still made absolute against the repository root for
    # the child, defensively.
    env = dict(os.environ)
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.pathsep.join(
            str((REPO / part).resolve()) if not Path(part).is_absolute() else part
            for part in env["PYTHONPATH"].split(os.pathsep) if part)
    by_hand = subprocess.run(argv, cwd=folder, capture_output=True, env=env)

    # Before comparing, refuse an empty by-hand run. Two empty strings compare equal, so
    # without this the check could report success having verified nothing -- the shape this
    # register already holds three times.
    assert by_hand.stdout.strip(), (
        f"the by-hand command produced no output at all, so there is nothing to compare "
        f"against the stored report. Ran: {' '.join(argv)} in {folder}; "
        f"exit {by_hand.returncode}; stderr: {by_hand.stderr.decode('utf-8', 'replace')[:400]}")

    #: The console reads the verifier's output with each \r\n written as
    #: \n (Windows prints \r\n to the pipe); the hand run is compared as the console reads it, by the
    #: same function, and every other byte stays strict.
    from onetrace_console.viewer.report import _lf
    assert "\r" not in stored_stdout
    assert _lf(by_hand.stdout.decode("utf-8")) == stored_stdout, (
        "the stored report is not what the command produces. Ran: "
        f"{' '.join(argv)} in {folder}")
    assert str(by_hand.returncode) == run.check_exit, (
        f"by hand exited {by_hand.returncode}, the record says {run.check_exit}")
    shutil.rmtree(folder, ignore_errors=True)


def test_running_the_check_twice_stores_one_report_object(stored, store):
    """The report is content-addressed, so an identical report is one object.

    `ran_at` is fixed here; with a live timestamp the envelopes differ and so do their
    keys, which is correct and is why the test says what it holds fixed.
    """
    first = run_and_record(stored, store, ran_at=FIXED_RAN_AT)
    second = run_and_record(stored, store, ran_at=FIXED_RAN_AT)
    assert first.check_report == second.check_report


# ---------------------------------------------- a contradicting run contradicts

def test_a_contradicting_run_is_recorded_as_contradicting(files, store):
    """A receipt whose bytes no longer match the digest the manifest recorded.

    The delivery is internally valid -- the sums are recomputed, so ingest accepts it --
    and the VERIFIER is the thing that finds the contradiction, which is the point: the
    console did not decide anything, it read a FAIL.
    """
    _require_installed()
    receipt = json.loads(files["receipts/01-zeta.json"].decode("utf-8"))
    receipt["run_id"] = receipt.get("run_id", "") + "-tampered"
    files["receipts/01-zeta.json"] = json.dumps(receipt, separators=(",", ":")).encode("utf-8")
    lines = [f"{hashlib.sha256(b).hexdigest()}  {p}"
             for p, b in files.items() if p != SUMS_NAME]
    files[SUMS_NAME] = ("\n".join(lines) + "\n").encode("utf-8")

    accepted = accept(make_tar(files), store)
    assert accepted.run is not None, getattr(accepted, "rows", accepted)

    run = run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT)
    assert run.check_verdict == CONTRADICTS, (
        f"the verifier's report was read as {run.check_verdict!r}")
    assert run.check_exit != "0"
    stdout = json.loads(store.get(run.check_report).decode("utf-8"))["stdout"]
    assert "[FAIL   ]" in stdout, stdout[:400]


def test_an_unreadable_report_is_could_not_check_and_never_contradicts(stored, store,
                                                                      monkeypatch):
    """The three-outcome rule at the runner.

    A report the console cannot read tells it nothing about the record. Calling that
    `contradicts` would be an accusation drawn from its own inability to read -- which is
    the failure direction this programme actually fears.
    """
    import onetrace_console.viewer.report as vr

    #: The check runs as the installed CLI (`capture_cli`).
    def unreadable(run_dir, *, outputs, timeout=120, **_):
        return {"format": "onetrace-viewer/check-report/0.1",
                "ran_at": FIXED_RAN_AT, "command": ["onetrace-verify", "."],
                "cwd_note": "run_folder", "exit_status": "0",
                "stdout": "this is not the verifier's row grammar at all\n", "stderr": ""}

    monkeypatch.setattr(vr, "capture_cli", unreadable)
    monkeypatch.setattr(checks, "shipped_verifier", lambda: Path("verify.py"))

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        folder = materialise(stored, store, Path(tmp) / "run")
        result = check(folder, ran_at=FIXED_RAN_AT)
    assert result.verdict == COULD_NOT_CHECK, result.verdict
    assert result.verdict != CONTRADICTS
    assert result.unreadable, "could_not_check with no reason recorded"


# ------------------------------------------------- the topology check, and its absence

def test_the_fixture_declares_edges_so_the_topology_case_is_real(files):
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    assert manifest.get("edges"), (
        "the fixture no longer declares edges, so the topology tests below prove nothing")


def test_the_runs_links_are_left_to_the_verifiers_own_edge_rows(stored, store, tmp_path):
    """The console runs no topology check of its own: since 0.2.0 the verifier checks a run's links
    (its edge rows). A run that declares links carries a one-line note only where the verifier's
    report has no edge row; never a substitute check, and never an incident.
    """
    folder = materialise(stored, store, tmp_path / "run")
    result = check(folder, ran_at=FIXED_RAN_AT)
    assert result.declares_edges is True
    assert result.topology_run is False
    has_rows = bool(checks._EDGE_ROW.search(result.output.decode("utf-8")))
    assert result.topology_note == ("" if has_rows else TOPOLOGY_NO_EDGE_ROWS)


def test_the_runner_refuses_when_the_verifier_is_not_installed(monkeypatch):
    """It does not fall back to a copy. A console that checked runs with bytes nobody
    pinned would be worth less than one that did not check them."""
    monkeypatch.setattr(checks.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(CheckRunnerError, match="the verifier is not installed"):
        shipped_verifier()


def _is_tracked_here(path: Path) -> bool:
    """Whether git tracks `path` in this repository.

    A committed copy is tracked; an install under `site-packages` (or, earlier, a clone
    under the ignored `.pins/`) is not. This is the distinction the "don't copy it" rule
    actually turns on, and `git ls-files --error-unmatch` answers it without guessing from
    path shapes.
    """
    repo = Path(__file__).resolve().parent.parent
    try:
        rel = path.resolve().relative_to(repo)
    except ValueError:
        return False                      # not under this repository at all
    r = subprocess.run(["git", "ls-files", "--error-unmatch", rel.as_posix()],
                       cwd=repo, capture_output=True, text=True)
    return r.returncode == 0
