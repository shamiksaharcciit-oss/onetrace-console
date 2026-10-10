"""No colour literal in the console's code; every colour comes from the skin.

The skin's block (vendored by the viewer, `viewer/tokens.py`) is the one place a colour is written.
This reads every string constant in the console's source -- its page templates are Python strings --
for a hex colour, `rgb()`/`rgba()` or `hsl()`/`hsla()`. The viewer's own code has the same test
(`viewer/tests/test_skin_tokens.py`).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
_LITERAL = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|\brgba?\(|\bhsla?\(")


def test_no_colour_literal_in_the_console_s_code(examined):
    files = sorted(SRC.rglob("*.py"))
    examined(len(files), "source files read")
    offenders = []
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for m in _LITERAL.finditer(node.value):
                    offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}: {m.group(0)}")
    assert not offenders, "colour literals outside the skin's block:\n" + "\n".join(offenders)
