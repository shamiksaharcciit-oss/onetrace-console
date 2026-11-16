"""No test takes the first entry a directory listing gives where the listing could hold several: a file system lists
a folder in any order, so such a test passes on one machine and fails on another (the span fixtures did, in the public
Linux job). Each listing a test takes one entry from is either the one entry it must be (`conftest.only`, which fails
where there are more), sorted, or chosen by name.

`ONETRACE_TEST_REVERSED_LISTINGS=1` (`conftest`) runs the whole suite with every listing reversed, to show it."""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LISTINGS = {"glob", "rglob", "iterdir", "listdir", "scandir"}


def _lists_unsorted(node) -> bool:
    calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
    if any(isinstance(c.func, ast.Name) and c.func.id in ("sorted", "only") for c in calls):
        return False
    return any(isinstance(c.func, ast.Attribute) and c.func.attr in LISTINGS for c in calls)


def first_of_a_listing(source: str) -> list[int]:
    """The lines where `source` takes the first entry of an unsorted listing: `next(...)` over one, or its `[0]`."""
    out = []
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "next" and n.args:
            if _lists_unsorted(n.args[0]):
                out.append(n.lineno)
        if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == 0:
            if _lists_unsorted(n.value):
                out.append(n.lineno)
    return sorted(out)


def test_no_test_or_tool_takes_the_first_entry_a_listing_gives(examined):
    found = {}
    files = sorted(p for d in ("tests", "tools") for p in (REPO / d).rglob("*.py") if "__pycache__" not in p.parts)
    for p in files:
        lines = first_of_a_listing(p.read_text(encoding="utf-8"))
        if lines:
            found[p.relative_to(REPO).as_posix()] = lines
    assert found == {}, found
    examined(len(files), "test and tool files read")


def test_the_rule_names_a_first_entry_and_passes_one_that_is_sorted_or_the_only_one(examined):
    said = "\n".join(
        [
            "a = next(p.glob('*.json'))",
            "b = list(p.iterdir())[0]",
            "c = next(iter(x for x in p.glob('*')))",
            "d = sorted(p.glob('*.json'))[0]",
            "e = only(p.glob('*.whl'))",
            "f = p / '01-call.json'",
        ]
    )
    assert first_of_a_listing(said) == [1, 2, 3]
    examined(6, "planted lines")


def test_the_span_fixtures_take_the_step_s_receipt_whatever_the_listing_order(tmp_path, monkeypatch, examined):
    from tests.conftest import _reverse_listings_on
    from tests.model_call_runs import record_run, step_receipt

    made = record_run(tmp_path / "a", "order")
    _reverse_listings_on(monkeypatch)
    listed = [p.name for p in (made / "receipts").glob("*.json")]
    assert listed[0] != "01-call.json", "reversed, the first file a listing gives is another"
    receipt = step_receipt(made)
    assert receipt.name == "01-call.json"
    assert json.loads(receipt.read_bytes())["stage"]["name"] == "call", "the step's own receipt"
    examined(1, "run recorded, read with its listing reversed")
