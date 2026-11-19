"""A passing suite keeps no temporary folders: at the end of a run in which every test passed, the `--basetemp`
folder the suite was given is removed whole, the folders fixtures make with `tmp_path_factory.mktemp` among them.
pytest's own policy (`tmp_path_retention_policy = "failed"`) removes a passing test's `tmp_path` folder, but not those.
After a run with a failure, everything is kept, to be read.

`tests/conftest.py` takes its hook from here. A folder that can't be removed is said on the terminal, with its path
and why, never left in silence. Standard library and pytest only, so a small suite can load it by its path.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

GONE = "basetemp removed: every test passed"
NOT_GONE = "basetemp not removed: {path}: {why}"


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """After pytest's own end of a run: where every test passed and a basetemp was given, remove it."""
    given = session.config.option.basetemp
    #: An xdist worker's folder is its controller's to remove, at the end of the whole run.
    if exitstatus != 0 or session.testsfailed or not given or hasattr(session.config, "workeroutput"):
        return
    path = Path(given)
    if not path.is_dir():
        return
    problems: list[str] = []
    shutil.rmtree(path, onexc=lambda _f, p, e: problems.append(f"{p}: {e}"))
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    said = NOT_GONE.format(path=path.as_posix(), why="; ".join(problems[:3])) if problems else GONE
    if reporter is not None:
        reporter.write_line(said)
