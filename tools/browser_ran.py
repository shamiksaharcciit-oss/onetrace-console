"""Fail where a browser test did not run: `python tools/browser_ran.py <the run's JUnit XML>`.

The CI's browser job runs only the suite's browser tests (`pytest -m browser`), with Playwright's Chromium installed.
There a skip means the browser was not found, and a run that skipped them all would read as passed. This reads the
run's JUnit report and exits 1, naming each, where any test skipped, failed or erred, or where none ran; 0 where every
one passed. Standard library only.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def outcomes(path: str) -> dict[str, str]:
    """Each test case's name and its outcome: passed, skipped, failed."""
    out = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        name = f"{case.get('classname')}::{case.get('name')}"
        if case.find("failure") is not None or case.find("error") is not None:
            out[name] = "failed"
        elif case.find("skipped") is not None:
            out[name] = "skipped"
        else:
            out[name] = "passed"
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python tools/browser_ran.py <the run's JUnit XML>", file=sys.stderr)
        return 2
    got = outcomes(args[0])
    if not got:
        print("no browser test ran", file=sys.stderr)
        return 1
    wrong = {name: state for name, state in got.items() if state != "passed"}
    for name, state in sorted(wrong.items()):
        print(f"{state}: {name}", file=sys.stderr)
    print(f"{len(got) - len(wrong)} of {len(got)} browser tests ran and passed")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
