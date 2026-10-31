"""The tests' HTTP client limits, relative to a calibration on the same machine.

A test's request to a console it started waits at most `limit(n)` seconds, where `n` is the fixed
limit it had before. The limit is a set multiple of a calibration measured once a session on this
machine: `n` times the calibration's time over its reference time, never below `n` (the floor) and
never above `CEILING_TIMES` times `n` (the ceiling), so a hang still fails.

The calibration is a fixed workload that runs none of the console's code: SHA-256 over generated
blocks, then files written, synced, read back and removed, in a temporary folder, standard library
only. Its time is the median of `RUNS` runs. A machine slower than the reference, for any reason,
gives each request more time; a request that is slow for this machine still fails at its limit. The
run's summary prints the measured time, the reference, and each limit used.
"""
from __future__ import annotations

import hashlib
import os
import statistics
import tempfile
import time
from functools import lru_cache

#: The calibration's time on the machine the fixed limits were set on: the median of seven runs,
#: 0.482 s, measured at a load of about 96 on 16 cores, declared rounded up.
REFERENCE_SECONDS = 0.5
#: The ceiling: never more than this many times the fixed limit.
CEILING_TIMES = 6
#: The workload, and how many times it is run for the median.
BLOCK, ROUNDS, FILES, FILE_SIZE, RUNS = 1 << 20, 192, 96, 1 << 18, 3
#: Each limit asked this session: {fixed: used}.
USED: dict[float, float] = {}


def workload(folder: str) -> None:
    """The calibration's fixed work, in `folder`: CPU, then files. Standard library only."""
    data = bytes(range(256)) * (BLOCK // 256)
    digest = b""
    for _ in range(ROUNDS):
        digest = hashlib.sha256(digest + data).digest()
    for i in range(FILES):
        path = os.path.join(folder, f"calibration-{i}")
        with open(path, "wb") as f:
            f.write(data[:FILE_SIZE])
            f.flush()
            os.fsync(f.fileno())
        with open(path, "rb") as f:
            if len(f.read()) != FILE_SIZE:
                raise OSError(f"the calibration's file {path} read back short")
        os.remove(path)


@lru_cache(maxsize=None)
def calibration() -> float:
    """The workload's time on this machine, in seconds: the median of `RUNS` runs, measured once."""
    times = []
    for _ in range(RUNS):
        with tempfile.TemporaryDirectory(prefix="http-limits-") as folder:
            start = time.perf_counter()
            workload(folder)
            times.append(time.perf_counter() - start)
    return statistics.median(times)


def scaled(fixed: float, measured: float, reference: float = REFERENCE_SECONDS,
           ceiling_times: float = CEILING_TIMES) -> float:
    """`fixed` times `measured` over `reference`, never below `fixed` and never above `ceiling_times`
    times `fixed`. Refuses a limit, a time or a reference that is not above zero."""
    if not (fixed > 0 and measured > 0 and reference > 0 and ceiling_times >= 1):
        raise ValueError(f"a limit needs a fixed limit, a measured time and a reference above zero "
                         f"and a ceiling of at least 1 times: got {fixed}, {measured}, {reference}, {ceiling_times}")
    return min(fixed * ceiling_times, max(fixed, fixed * measured / reference))


def limit(fixed: float) -> float:
    """The limit, in seconds, for a request whose fixed limit was `fixed`."""
    used = scaled(fixed, calibration())
    USED[fixed] = used
    return used


def summary_lines() -> list[str]:
    """What the run's summary says of the limits it used: the calibration, and each limit."""
    if not USED:
        return []
    measured = calibration()
    return [f"HTTP client limits: calibration {measured:.3f} s on this machine, reference {REFERENCE_SECONDS} s "
            f"({measured / REFERENCE_SECONDS:.2f} times); floor each fixed limit, ceiling {CEILING_TIMES} times it",
            "  " + "; ".join(f"{fixed:g} s -> {used:.1f} s" for fixed, used in sorted(USED.items()))]
