"""Where `tools/install_pinned.py` writes pip's install report, and where `compare` reads it back.

**Standard library only, on purpose.** The installer runs before anything it
installs exists, and it loads this file by its path, never through `onetrace_console`: an
installer that imports its own payload fails on a fresh machine. When the console's JSON reading
began importing the vendored `viewer`, `install_pinned.py`'s old
`from onetrace_console.compare import install_report_path` failed on both Actions runners with
"No module named 'viewer'", while the project's own machine -- whose venv already had the
viewer -- passed.
`tests/test_install_pinned_fresh.py` holds this module to the standard library and runs the
installer's lookup in a fresh venv with nothing installed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

#: Named once, here; `onetrace_console.compare` re-exports both, so its callers are unchanged.
INSTALL_REPORT_FILENAME = "onetrace-console-install-report.json"


def install_report_path() -> Path:
    """Where `python tools/install_pinned.py` writes the install report, by default.

    `$ONETRACE_CONSOLE_INSTALL_REPORT` overrides it, for a build that must put it somewhere
    else (a read-only image layer, say).
    """
    override = os.environ.get("ONETRACE_CONSOLE_INSTALL_REPORT")
    if override:
        return Path(override)
    return Path(sys.prefix) / INSTALL_REPORT_FILENAME
