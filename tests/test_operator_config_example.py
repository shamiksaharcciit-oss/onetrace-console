"""OPERATOR_README's configuration example says it holds every key the file may hold: its `sign_in` keys are
those of the shipped `config/default.json`."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "OPERATOR_README.md"


def _example() -> dict:
    text = DOC.read_text(encoding="utf-8")
    block = re.search(r"Every key it may hold, and what it\s+means:\s+```json\n(.*?)```", text, re.S)
    assert block, "no configuration example"
    return json.loads(block.group(1))


def test_the_example_holds_every_sign_in_key_of_the_shipped_default(examined):
    shipped = json.loads((REPO / "config" / "default.json").read_text(encoding="utf-8"))["sign_in"]
    example = _example()["sign_in"]
    examined(len(shipped), "sign_in keys")
    assert set(example) == set(shipped) and example == shipped
