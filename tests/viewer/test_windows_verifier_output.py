"""What the console's first Windows run of the 0.2.0 branch found, in two parts.

§1  The verifier's output is read with each \\r\\n written as \\n -- at capture, and on reading a report
    stored before -- so a page never carries \\r. Only \\r\\n: a lone \\r is kept.
§2  A text row is paired with its --json row by the name as the verifier escapes it: the text writes a
    backslash doubled and a control character as \\uXXXX, the --json row carries the name raw.

A stand-in verifier writes both as Windows and the real verifier do: \\r\\n line endings, and rows whose
names hold a backslash and a control character, escaped in its text and raw in its --json.
"""
from __future__ import annotations

import copy
import json

import pytest

from onetrace_console.viewer.report import capture_cli, parse, verifier_escaped

NAMES = ["--trust C:\\Users\\runner\\trust.json", "receipts/01-x\u0007.json: receipt format"]

_STANDIN = '''
import json, sys
names = %s
args = sys.argv[1:]
rows = [{"check": n, "name": n, "result": "PASS", "detail": ""} for n in names]
if "--json" in args:
    sys.stdout.buffer.write(json.dumps({"rows": rows, "summary": {"exit": 0, "result": "PASS",
        "pass": len(rows), "fail": 0, "not_run": 0}}).encode("utf-8") + b"\\r\\n")
else:
    out = "".join("[PASS   ] " + %s(n) + "\\r\\n" for n in names)
    out += "\\r\\n%%d pass, 0 fail, 0 not-run  ->  PASS\\r\\n" %% len(rows)
    sys.stdout.buffer.write(out.encode("utf-8"))
sys.exit(0)
'''


@pytest.fixture
def windows_like(tmp_path, monkeypatch):
    import inspect

    from onetrace_console.viewer import report
    pkg = tmp_path / "mods"
    pkg.mkdir()
    escaper = inspect.getsource(report._verifier_escape_char) + "\n_E = __import__('re').compile(" + \
        repr(report._VERIFIER_ESCAPED.pattern) + ")\ndef esc(t):\n    return _E.sub(lambda m: " \
        "_verifier_escape_char(m.group()), t.replace('\\\\', '\\\\\\\\'))\n"
    (pkg / "win_verify.py").write_text(escaper + _STANDIN % (json.dumps(NAMES), "esc"), encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(pkg))
    run = tmp_path / "run"
    run.mkdir()
    (run / "MANIFEST.json").write_text("{}", encoding="utf-8")
    return run


def test_the_stand_in_writes_as_windows_does(windows_like):
    """The premise: \\r\\n endings, and the names escaped in the text, raw in --json."""
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-m", "win_verify", "MANIFEST.json"], cwd=windows_like,
                         capture_output=True).stdout
    assert b"\r\n" in out and b"C:\\\\Users\\\\runner" in out and b"\\u0007" in out


def test_capture_writes_crlf_as_lf_and_the_rows_pair_by_the_verifiers_escaping(windows_like):
    env = capture_cli(windows_like, outputs=False, module="win_verify")
    assert "\r" not in env["stdout"] and "\r" not in env["rows_json"]["stdout"]
    report = parse(env)
    assert report.rows_readable and report.overall == "pass" and "\r" not in report.output
    names = [f.line for f in report.findings]
    assert names == [f"[PASS   ] {verifier_escaped(n)}" for n in NAMES], names


def test_a_report_stored_with_crlf_reads_as_one_stored_since(windows_like):
    env = capture_cli(windows_like, outputs=False, module="win_verify")
    stored = copy.deepcopy(env)
    stored["stdout"] = env["stdout"].replace("\n", "\r\n")
    stored["rows_json"]["stdout"] = env["rows_json"]["stdout"].replace("\n", "\r\n")
    then, now = parse(stored), parse(env)
    assert "\r" not in then.output and then.output == now.output
    assert then.findings == now.findings and then.overall == now.overall


def test_a_lone_cr_is_kept():
    from onetrace_console.viewer.report import _lf
    assert _lf("a\r\nb\rc\n") == "a\nb\rc\n"
