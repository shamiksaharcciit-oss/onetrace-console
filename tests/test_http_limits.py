"""The tests' HTTP client limits (`tests/http_limits.py`): relative to a calibration, within a floor and a ceiling.

Each rule here has its own sabotage below.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests import http_limits as hl

REPO = Path(__file__).resolve().parent.parent
#: The fixed limits the tests had, in seconds.
FIXED = (5, 10, 30, 60, 120, 300)
#: A request to a console the test started: its limit, as written.
_SITE = re.compile(r"(?:urlopen|\.open)\(.*timeout=(\{?limit\([0-9.]+\)\}?|[^),\s]+)")


@pytest.mark.parametrize("fixed", FIXED)
def test_the_limit_never_goes_below_the_floor_or_above_the_ceiling(fixed, examined):
    times = (1e-9, hl.REFERENCE_SECONDS / 2, hl.REFERENCE_SECONDS, 2 * hl.REFERENCE_SECONDS, 1e9)
    examined(len(times), "measured times")
    got = [hl.scaled(fixed, t) for t in times]
    assert all(fixed <= g <= fixed * hl.CEILING_TIMES for g in got), got
    assert got[0] == got[1] == got[2] == fixed
    assert got[3] == 2 * fixed
    assert got[4] == fixed * hl.CEILING_TIMES


@pytest.mark.parametrize("args", [(0, 1.0), (10, 0.0), (10, -1.0), (-5, 1.0)], ids=["no limit", "no time",
                                                                               "a negative time", "a negative limit"])
def test_the_helper_refuses_a_limit_or_time_not_above_zero(args, examined):
    examined(1, "refused input")
    with pytest.raises(ValueError):
        hl.scaled(*args)


def test_the_calibration_runs_none_of_the_console_s_code(examined):
    """Run in a process of its own: after it, no module of the console or the SDK is loaded."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from tests import http_limits as h; h.calibration(); "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in ('onetrace_console', 'onetrace', 'onetrace_verify')))")
    done = subprocess.run([sys.executable, "-I", "-c", code, str(REPO)], capture_output=True, text=True, timeout=600)
    examined(1, "calibration run in its own process")
    assert done.returncode == 0, done.stderr[-1500:]
    assert done.stdout.strip() == "[]", done.stdout


def test_every_request_to_a_started_console_takes_its_limit_from_the_helper(examined):
    """No request in the tests waits a fixed number of seconds: each limit is `limit(n)`."""
    sites = []
    for p in sorted(REPO.glob("tests/test_*.py")):
        if p.name == Path(__file__).name:
            continue                       # its own planted line, below
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            m = _SITE.search(line)
            if m:
                sites.append((p.name, n, m.group(1)))
    examined(len(sites), "requests with a limit")
    assert len(sites) == 33
    assert [s for s in sites if not re.fullmatch(r"\{?limit\([0-9.]+\)\}?", s[2])] == []


def test_the_summary_says_the_calibration_and_each_limit_used(monkeypatch, examined):
    monkeypatch.setattr(hl, "USED", {})
    monkeypatch.setattr(hl, "calibration", lambda: 1.5)
    hl.limit(10)
    hl.limit(30)
    lines = hl.summary_lines()
    examined(len(lines), "summary lines")
    assert lines[0].startswith("HTTP client limits: calibration 1.500 s on this machine, reference 0.5 s (3.00 times)")
    assert lines[1] == "  10 s -> 30.0 s; 30 s -> 90.0 s"


def test_sabotage_a_limit_without_its_floor_and_ceiling_is_caught(monkeypatch, examined):
    """The bare proportion, unclamped: a fast machine gives less than the floor, a stalled one more than the ceiling."""
    monkeypatch.setattr(hl, "scaled", lambda fixed, measured, reference=hl.REFERENCE_SECONDS, ceiling_times=6:
                        fixed * measured / reference)
    examined(2, "planted limits")
    assert hl.scaled(10, 1e-9) < 10 and hl.scaled(10, 1e9) > 10 * hl.CEILING_TIMES


def test_sabotage_a_fixed_limit_back_in_a_test_is_caught(examined):
    planted = '        with urllib.request.urlopen(base + path, timeout=10) as resp:'
    m = _SITE.search(planted)
    examined(1, "planted request")
    assert m and not re.fullmatch(r"\{?limit\([0-9.]+\)\}?", m.group(1))
