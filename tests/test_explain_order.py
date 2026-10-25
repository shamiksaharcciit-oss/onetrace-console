"""Explanations are listed newest press first, by the press whose command printed `recorded:`.

The command's record ids are its times, so they mostly sort as the presses do; this case is one where
they don't: the first press recorded the later id. On Windows the command writes the `recorded:` path
with backslashes, so the record is the path's last part at either separator. Without that reading
the order falls back to the record ids, and this case is listed the other way round.

Written by hand, as the command writes them: no command runs here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

KEY = "c" * 64
#: The first press recorded the later id; the second, the earlier one.
FIRST, SECOND = "2026-10-22T10-00-00.000002Z", "2026-10-22T10-00-00.000001Z"


def _press(folder: Path, n: int, recorded: str) -> None:
    d = folder / "attempts"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{n:06d}.json").write_text(json.dumps({"n": str(n), "kind": "explain", "exit": "0",
                                                 "stdout": f"recorded: {recorded}\r\n", "stderr": ""}),
                                     encoding="utf-8")


def _explanation(folder: Path, rid: str) -> None:
    d = folder / "r" / "explain"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{rid}.explanation.json").write_text(json.dumps({"record": rid, "claims": []}), encoding="utf-8")


@pytest.mark.parametrize("sep", ["/", "\\"], ids=["slashes", "backslashes, as on Windows"])
def test_explanations_are_listed_newest_press_first_whatever_their_ids(tmp_path, sep, examined):
    from onetrace_console import explain
    from onetrace_console.store import Store
    store = Store(tmp_path / "store")
    folder = explain.folder_of(store, KEY)
    for n, rid in ((1, FIRST), (2, SECOND)):
        _explanation(folder, rid)
        _press(folder, n, sep.join(["D:", "store", "x", KEY[:16], "r", "explain", rid]))
    examined(2, "explanations")
    assert sorted([FIRST, SECOND], reverse=True) == [FIRST, SECOND]     # the ids alone: FIRST first
    assert [e["record"] for e in explain.explanations(store, KEY)] == [SECOND, FIRST]


def test_sabotage_the_backslash_reading_removed_is_named(tmp_path, monkeypatch, examined):
    """`explanations` with its backslash reading taken out: the Windows path's record is not
    found, and the ids decide."""
    import inspect
    import textwrap

    from onetrace_console import explain
    from onetrace_console.store import Store
    source = textwrap.dedent(inspect.getsource(explain.explanations))
    reading = '.replace("\\\\", "/")'
    assert source.count(reading) == 1, "the backslash reading is not where this sabotage looks"
    planted = {}
    exec(compile(source.replace(reading, ""), explain.__file__, "exec"), vars(explain), planted)
    monkeypatch.setattr(explain, "explanations", planted["explanations"])
    store = Store(tmp_path / "store")
    folder = explain.folder_of(store, KEY)
    for n, rid in ((1, FIRST), (2, SECOND)):
        _explanation(folder, rid)
        _press(folder, n, "\\".join(["D:", "store", "x", KEY[:16], "r", "explain", rid]))
    examined(1, "planted reading")
    assert [e["record"] for e in explain.explanations(store, KEY)] == [FIRST, SECOND]
