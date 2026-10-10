"""The verdict function maps every exit status the checks can give.

`onetrace-verify` exits 0 (PASS), 1 (FAIL) or 2 (NOT VERIFIED: a receipt names a format it does
not implement, so its content was not checked). `sdk_verify` gives 4 for the same. Exit 2 and
exit 4 are never "holds" and never "contradicts": they read as the check's NOT VERIFIED, which
this console's verdicts call could_not_check.

**Not reachable end to end yet:** the console's ingest refuses every receipt format outside
`RECEIPT_FORMATS` before the check runs, and 0.1.2 exits 2 only for such a format, so no stored run
reaches exit 2 today. At the 0.2.0 re-pin, preview formats read NOT RUN (exit 2 on the bench,
exit 4 in `sdk_verify`), and it becomes reachable. Hence a test at the function level.
"""
from __future__ import annotations

import pytest

from onetrace_console.checks import COULD_NOT_CHECK, CONTRADICTS, HOLDS, verdict_for


@pytest.mark.parametrize("exit_status, overall, verdict", [
    ("0", "pass", HOLDS),
    ("1", "fail", CONTRADICTS),
    ("2", "not_verified", COULD_NOT_CHECK),
    ("4", "not_verified", COULD_NOT_CHECK),
    # Whatever the summary said, exit 2 and exit 4 never hold and never contradict.
    ("2", "pass", COULD_NOT_CHECK),
    ("2", "fail", COULD_NOT_CHECK),
    ("4", "pass", COULD_NOT_CHECK),
    # An exit status and a result that disagree are nothing to decide from.
    ("0", "fail", COULD_NOT_CHECK),
    ("1", "pass", COULD_NOT_CHECK),
    ("3", "pass", COULD_NOT_CHECK),
])
def test_each_exit_status_maps_to_one_verdict(exit_status, overall, verdict, examined):
    examined(1, f"exit {exit_status} with {overall}")
    assert verdict_for(exit_status, overall) == verdict


def test_exit_2_and_4_are_never_holds_or_contradicts(examined):
    got = {verdict_for(status, overall) for status in ("2", "4")
           for overall in ("pass", "fail", "not_verified", "")}
    examined(8, "exit 2 and 4 combinations")
    assert got == {COULD_NOT_CHECK}, got
