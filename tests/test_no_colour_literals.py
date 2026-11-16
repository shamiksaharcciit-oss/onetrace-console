"""No colour literal in the console's code; every colour comes from the skin.

The skin's block (vendored by the viewer: `viewer/skin_tokens.py`'s `BLOCK`, which `viewer/tokens.py`
reads) is the one place a colour is written; that one string is allowed, and nothing else in its file.
This reads every string constant in the console's source -- its page templates are Python strings --
for a hex colour, `rgb()`/`rgba()` or `hsl()`/`hsla()`. The viewer's own code has the same test
(`viewer/tests/test_skin_tokens.py`).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
_LITERAL = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|\brgba?\(|\bhsla?\(")


#: The one string allowed to hold colours: the skin's block, in the file that holds it.
SKIN = "viewer/skin_tokens.py"


def offenders_in(files) -> list[str]:
    from onetrace_console.viewer.skin_tokens import BLOCK

    out = []
    for path in files:
        rel = path.relative_to(SRC).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if rel == SKIN and node.value == BLOCK:
                    continue
                for m in _LITERAL.finditer(node.value):
                    out.append(f"{rel}:{node.lineno}: {m.group(0)}")
    return out


def test_no_colour_literal_in_the_console_s_code(examined):
    files = sorted(SRC.rglob("*.py"))
    examined(len(files), "source files read")
    offenders = offenders_in(files)
    assert not offenders, "colour literals outside the skin's block:\n" + "\n".join(offenders)


def test_sabotage_a_colour_beside_the_block_or_the_block_elsewhere_is_named(tmp_path, monkeypatch, examined):
    import shutil

    from onetrace_console.viewer.skin_tokens import BLOCK

    root = tmp_path / "onetrace_console"
    (root / "viewer").mkdir(parents=True)
    shutil.copyfile(SRC / SKIN, root / SKIN)
    with (root / SKIN).open("a", encoding="utf-8") as f:
        f.write('EXTRA = "#123456"\n')
    (root / "other.py").write_text(f"COPY = {BLOCK!r}\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SRC", root)
    examined(2, "planted files")
    got = offenders_in([root / SKIN, root / "other.py"])
    assert f"{SKIN}:" in got[0] and "#123456" in got[0] and any(g.startswith("other.py:") for g in got)
