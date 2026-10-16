"""The viewer folder is what its provenance file says it is.

`src/onetrace_console/viewer/PROVENANCE.md` lists every file in the folder with its sha256 at the
commit it was copied from (or that it was added here) and its sha256 here. Each file's bytes must give the second column, and the
table must list every file: none missing, none extra.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

VIEWER = Path(__file__).resolve().parent.parent / "src" / "onetrace_console" / "viewer"
#: A file's row: its sha256 at the commit it was copied from -- or "added here" for a file this
#: repository added to the folder since -- and its sha256 here.
ROW = re.compile(r"^\| `([^`]+)` \| (?:`([0-9a-f]{64})`|added here) \| `([0-9a-f]{64})` \|$")


def _rows() -> dict[str, tuple[str, str]]:
    rows = {}
    for line in (VIEWER / "PROVENANCE.md").read_text(encoding="utf-8").splitlines():
        found = ROW.match(line)
        if found:
            rows[found.group(1)] = (found.group(2), found.group(3))
    return rows


def test_every_file_has_the_sha256_its_provenance_gives(examined):
    rows = _rows()
    examined(len(rows), "files listed")
    assert rows, "the provenance file lists no files"
    wrong = {name: (here, hashlib.sha256((VIEWER / name).read_bytes()).hexdigest())
             for name, (_at, here) in rows.items()
             if hashlib.sha256((VIEWER / name).read_bytes()).hexdigest() != here}
    assert not wrong, wrong


def test_the_provenance_lists_every_file_in_the_folder(examined):
    present = {p.relative_to(VIEWER).as_posix() for p in VIEWER.rglob("*")
               if p.is_file() and "__pycache__" not in p.parts and p.name != "PROVENANCE.md"}
    listed = set(_rows())
    examined(len(present), "files in the folder")
    assert present == listed, {"unlisted": sorted(present - listed), "missing": sorted(listed - present)}


def test_nothing_imports_the_viewer_by_its_old_top_level_name(examined):
    """The viewer is `onetrace_console.viewer` now; a top-level `viewer` import would reach for a
    package this console no longer installs."""
    import ast
    repo = VIEWER.parent.parent.parent
    files = [p for d in ("src", "tests", "tools") for p in (repo / d).rglob("*.py")]
    examined(len(files), "Python files read")
    found = []
    for path in files:
        for node in ast.walk(ast.parse(path.read_bytes())):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                     [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            found += [(path.relative_to(repo).as_posix(), node.lineno) for n in names
                      if n == "viewer" or n.startswith("viewer.")]
    assert not found, found
