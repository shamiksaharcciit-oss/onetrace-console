"""The tests that hold the console's reading of the verifier's CR LF output,
run under `tests.windows_crlf_pipe` in a subprocess, so a CR LF regression shows on Linux.

They are the five tests the first Windows run failed, the forged-rows test, the console's own
CR LF test, and the two more named last below.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

UNDER_CRLF = [
    "tests/test_stage_badges.py::test_yes_names_the_whole_runs_record",
    "tests/test_stage_badges.py::test_couldnt_check_gives_the_verifiers_reason_alone",
    "tests/test_signed_surfaces.py::"
    "test_a_signature_the_check_could_not_settle_is_couldnt_check_with_its_reason",
    "tests/test_step3_receipt_anchor.py::test_an_anchor_that_passes_reads_yes_existed_by_its_attested_time",
    "tests/test_step3_receipt_anchor.py::test_an_anchor_not_run_reads_couldnt_check_with_the_verifiers_reason",
    "tests/test_rows_unreadable_console.py::test_on_0_2_0_the_forged_rows_read_and_the_digest_is_quoted_escaped",
    "tests/test_run_page_marks.py::test_1_the_verifier_s_crlf_never_reaches_the_page",
    "tests/test_checks.py::test_the_stored_report_is_byte_identical_to_running_the_command_by_hand",
    "tests/test_run_page_marks.py::test_1_the_premise_the_verifier_s_output_arrives_in_crlf",
]


def test_the_crlf_tests_pass_with_the_verifiers_output_in_crlf(tmp_path, examined):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-p", "tests.windows_crlf_pipe", "-p", "no:cacheprovider",
         "-p", "no:randomly", "--basetemp", str(tmp_path / "bt"), *UNDER_CRLF],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=900)
    out = result.stdout + result.stderr
    assert "windows_crlf_pipe: the verifier's stdout arrives with CR LF line endings" in out, (
        "the aid was not loaded, so nothing ran under CR LF:\n" + out[-2000:])
    assert result.returncode == 0 and f"{len(UNDER_CRLF)} passed" in out, out[-4000:]
    examined(len(UNDER_CRLF), "tests run under the CR LF aid, in a subprocess")
