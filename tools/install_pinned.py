"""The one authoritative install command. Gate-verbatim: what is installed is a claim
produced by this command, not reconstructed by reading `site-packages` after the fact.

WHY THIS EXISTS, AND WHAT `--report` IS FOR
--------------------------------------------
`pip install onetrace==0.1.2` (an ordinary version-pinned requirement resolved from the
index) does **not** write `direct_url.json` into the installed distribution -- PEP 610 only
covers "direct references" (a VCS URL, a local path, an explicit URL), and an index-resolved
requirement is none of those, hash-checked or not. Measured directly: installing this exact
`requirements.lock` with `--require-hashes` alone leaves no `direct_url.json` under
`onetrace-<version>.dist-info/`, so `onetrace_console.compare.sdk_build_digest()` -- which reads
that file to learn the wheel's own sha256 -- would find nothing there and raise, wrongly
treating a correctly hash-pinned install as an unidentifiable build.

`pip install --report <path>` does the one thing `direct_url.json` does not: it writes a
`download_info.archive_info.hash` entry for **every** installed distribution, however it was
resolved -- index, direct URL, or local path alike. So this script is the standard way to
install the pins, and it always asks pip for that report, at a fixed, discoverable location
(`onetrace_console.install_report.install_report_path()`, by default
`<sys.prefix>/onetrace-console-install-report.json`). `compare.sdk_build_digest()` reads it
from there.

**A gotcha, found by re-running this script against an environment that already had two of
the three pins satisfied**: `--report` only describes packages pip actually PROCESSED in that
invocation. A requirement pip judges "already satisfied" at the right version is left out of
the report entirely -- not recorded as satisfied, simply absent -- so a report written by a
partial, incremental re-run can be missing entries a full one would have had. `--force-
reinstall` is passed for exactly this reason: it makes every requirement get processed every
time, so the report this script writes is always complete, regardless of what the environment
already had installed. A fresh container layer never hits this case at all (nothing is
"already satisfied" in an empty image), but a developer re-running this script by hand against
their own venv would, and silently, without it.

This script necessarily runs BEFORE anything it installs exists (that is the point of it), so
it never imports `onetrace_console`: it loads `src/onetrace_console/install_report.py`, a
standard-library-only module, by its path. It used to import
`onetrace_console.compare`, which came to import the vendored `viewer` -- one of the pins
this script installs -- and so failed on every fresh runner with "No module named 'viewer'".

Usage:
    python tools/install_pinned.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCK = REPO / "requirements.lock"


#: The one module this script reads, by path: standard library only (tests hold it to that).
INSTALL_REPORT_MODULE = REPO / "src" / "onetrace_console" / "install_report.py"


def report_path() -> Path:
    """Where pip's install report goes, from `install_report.py` loaded by its path, never by
    importing `onetrace_console`, whose other modules import the pins this script installs."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_onetrace_console_install_report",
                                                  INSTALL_REPORT_MODULE)
    if spec is None or spec.loader is None or not INSTALL_REPORT_MODULE.is_file():
        raise SystemExit(f"cannot find {INSTALL_REPORT_MODULE}: run from a checkout of this "
                         f"repository")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.install_report_path()


def main() -> int:
    dest = report_path()
    cmd = [sys.executable, "-m", "pip", "install", "--require-hashes", "--force-reinstall",
           "-r", str(LOCK), "--report", str(dest)]
    print("running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=REPO)
    if proc.returncode != 0:
        return proc.returncode
    if not dest.is_file():                                       # pragma: no cover
        print(f"pip exited 0 but wrote no report to {dest}", file=sys.stderr)
        return 1
    print(f"installed; build-identity report at {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
