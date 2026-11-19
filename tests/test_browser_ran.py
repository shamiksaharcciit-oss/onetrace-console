"""`tools/browser_ran.py`: the CI's browser job fails where any browser test skipped, failed or erred, or none ran."""

from __future__ import annotations

from tools.browser_ran import main

PASSED = '<testcase classname="tests.t" name="a"/>'
SKIPPED = '<testcase classname="tests.t" name="b"><skipped message="no browser"/></testcase>'
FAILED = '<testcase classname="tests.t" name="c"><failure message="x"/></testcase>'


def _report(tmp_path, *cases: str) -> str:
    path = tmp_path / "browser.xml"
    path.write_text(f'<testsuites><testsuite name="pytest">{"".join(cases)}</testsuite></testsuites>', encoding="utf-8")
    return str(path)


def test_every_test_passed_passes(tmp_path, capsys, examined):
    examined(1, "report")
    assert main([_report(tmp_path, PASSED, PASSED.replace('"a"', '"a2"'))]) == 0
    assert "2 of 2 browser tests ran and passed" in capsys.readouterr().out


def test_a_skip_a_failure_or_no_test_at_all_fails(tmp_path, capsys, examined):
    examined(3, "reports")
    assert main([_report(tmp_path, PASSED, SKIPPED)]) == 1 and "skipped: tests.t::b" in capsys.readouterr().err
    assert main([_report(tmp_path, FAILED)]) == 1 and "failed: tests.t::c" in capsys.readouterr().err
    assert main([_report(tmp_path)]) == 1 and "no browser test ran" in capsys.readouterr().err
