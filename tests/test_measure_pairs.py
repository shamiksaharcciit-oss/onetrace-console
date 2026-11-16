"""The measuring tool compares the six fixture pairs as six different pairs.

`tools/measure_pages.py` compares each committed token-level pair (`tests/token_level_runs_071/`) once, to time
Compare's start. Its first reading took a run's key from the first run page naming its id, and a run's page names
the other run of its pair: two pairs were given one key on both sides, and compared a run with itself. Here: the
pairs it compares, read from a store holding the twelve runs, are six, each of two different runs, each run its own
pair's, and no run in two pairs. Its sabotage plants the first reading's fault.
"""

from __future__ import annotations

import os
import sys


def pair_problems(pairs: dict[str, tuple[str, str]], ids: dict[str, str]) -> list[str]:
    """`pairs`, {pair: (key a, key b)}; `ids`, {key: run id}: what is wrong with them."""
    out = []
    if len(pairs) != 6:
        out.append(f"{len(pairs)} pairs, not six")
    for name, (a, b) in sorted(pairs.items()):
        if a == b:
            out.append(f"{name}: a run compared with itself")
        if (ids.get(a), ids.get(b)) != (f"{name}-a", f"{name}-b"):
            out.append(f"{name}: compares {ids.get(a)} and {ids.get(b)}")
    keys = [k for ab in pairs.values() for k in ab]
    if len(set(keys)) != len(keys):
        out.append("a run in two pairs")
    return out


def test_the_six_fixture_pairs_are_six_different_pairs(tmp_path, examined):
    from tests.export_tree import tool
    from tests.test_checks import _require_installed

    _require_installed()
    sys.path.insert(0, str(tool("measure_pages.py").parent))
    import measure_pages as M

    from onetrace_console.checks import run_and_record
    from onetrace_console.store import Store
    from tests.test_compare import _deliver

    store = Store(tmp_path / "store")
    for pair in sorted(p.name for p in M.FIXTURES.iterdir() if p.is_dir()):
        for side in ("a", "b"):
            run_and_record(_deliver(M.FIXTURES / pair / side, store, outputs=True), store)
    env = {**os.environ, "PYTHONPATH": str(M.REPO / "src")}
    pairs = M.fixture_pairs(tmp_path / "store", env)
    ids = {r.key: r.run_id for r in store.runs()}
    examined(len(pairs), "pairs compared")
    assert pair_problems(pairs, ids) == []


def test_sabotage_a_run_given_to_both_sides_is_named():
    ids = {"k1": "l2-ids-a", "k2": "l2-ids-b"}
    planted = {"l2-ids": ("k1", "k1"), **{f"p{i}": (f"a{i}", f"b{i}") for i in range(5)}}
    got = pair_problems(
        planted, {**ids, **{f"a{i}": f"p{i}-a" for i in range(5)}, **{f"b{i}": f"p{i}-b" for i in range(5)}}
    )
    assert got == ["l2-ids: a run compared with itself", "l2-ids: compares l2-ids-a and l2-ids-a", "a run in two pairs"]
