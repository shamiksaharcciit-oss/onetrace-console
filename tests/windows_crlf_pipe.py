"""A test aid, loaded only by name: `python -m pytest -p tests.windows_crlf_pipe ...`.

It makes the verifier's output arrive as it does on Windows, with CR LF line endings, so the
console's reading of it can be checked on Linux before a Windows run.
Every subprocess.run whose command names `onetrace_verify` has its stdout given CR LF once:
an LF already preceded by CR is left alone (never `\\r\\r\\n`).
Nothing else is changed, and nothing loads this by default.
"""
import re
import subprocess

_real_run = subprocess.run


def _windows_run(cmd, *args, **kwargs):
    done = _real_run(cmd, *args, **kwargs)
    parts = cmd if isinstance(cmd, (list, tuple)) else [cmd]
    if any("onetrace_verify" in str(part) for part in parts) and isinstance(done.stdout, bytes):
        done = subprocess.CompletedProcess(done.args, done.returncode,
                                           re.sub(rb"(?<!\r)\n", b"\r\n", done.stdout), done.stderr)
    return done


subprocess.run = _windows_run


def pytest_report_header(config):
    return "windows_crlf_pipe: the verifier's stdout arrives with CR LF line endings"
