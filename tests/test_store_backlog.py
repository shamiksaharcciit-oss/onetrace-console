"""Backlog items found incidentally, not owned by the order that found them.

The backlog item: *"Windows MAX_PATH in the store's file naming. It predates
this order and doesn't affect the Linux container. It goes on the console
backlog as a named item: a store on Windows at a deep path fails. It will be
fixed in the order that adds a Windows install path. The report's reproduction
is kept as its test case."* This file is that test case.
"""
from __future__ import annotations

import sys

import pytest

from onetrace_console.store import Store, StoredRun


def test_backlog_windows_max_path_in_store_file_naming(tmp_path, examined):
    """Found during a cold-clone re-check: a
    fresh clone under this session's own deeply-nested scratchpad path failed
    writing `decision_exports/<64-hex>.json` with `FileNotFoundError [WinError 3]`
    -- Windows' classic 260-character path limit. Reproduced against the
    PRE-EXISTING `runs/<64-hex>.json` shape too, so this is a property of every
    content-addressed file `Store` writes, not anything the onedoor extension
    introduced.

    Not a defect of the onedoor extension and not fixed here (out of scope; it
    stays on the backlog, for the order that adds a Windows install path). This
    reproduces it directly: a `Store` rooted deep enough that a 64-hex-char
    filename pushes the full path over 260 characters.
    """
    if sys.platform != "win32":
        pytest.skip("MAX_PATH is a Windows-only limit; nothing to reproduce elsewhere")

    deep = tmp_path
    while len(str(deep)) < 240:
        deep = deep / ("d" * 50)

    examined(1, "a store write attempted at a path over 260 characters deep")
    try:
        deep.mkdir(parents=True, exist_ok=True)
        store = Store(deep / "store")
        run = StoredRun(key="a" * 64, run_id="r", chain_head="c", format="f",
                        listing=(), received_at="now")
        store.put_run(run)
    except (FileNotFoundError, OSError):
        return   # reproduced -- the known, backlogged limitation

    pytest.skip("this machine has Windows long-path support enabled (or an "
               "equivalent), so the 260-character limit did not reproduce here")
