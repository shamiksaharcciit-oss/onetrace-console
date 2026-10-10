"""No string the console can show a user carries an internal identifier.

Every string constant in `src/onetrace_console/` that is not a docstring is read: page words, error
messages, the `--help` text, a rule's "Source:" line. Each is checked against the export scan's
internal-id patterns (`tools/export_scan.py` on the export branch, repeated here so this test needs
nothing outside the console). Comments and docstrings are the code scrub's, not this test's.

No string is allowed an id. An allowance, if one is ever needed, is bounded to one assignment and
fails here once it no longer holds an id, so it cannot outlive its reason.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
INTERNAL = {
    "ruling id": r"\bR-20\d\d-\d\d-\d\d",
    "short ruling id": r"\b2\d(?!px)[a-z]{2}\b",
    "work order": r"\bWO-C\d+",
    "note id": r"\bN-C0\d\d",
    "to_core / from_core": r"\b(?:to|from)_core\b",
    "core as an agent": r"\bcore(?:'s)?\s+(?:rul|said|asked|accept|decid|gave|wants|confirm|word|review)",
    "pod": r"\bpods?\b",
    "a ruling by number": r"\bruling \d+[a-z]*\b",
}
PATTERNS = {name: re.compile(p) for name, p in INTERNAL.items()}
#: (file relative to src/onetrace_console/, the name assigned) -> why its strings may hold an id.
ALLOWED: dict[tuple[str, str], str] = {}


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def _allowed_ids(tree: ast.AST, rel: str) -> set[int]:
    """The string constants inside an allowed assignment of this file."""
    found = set()
    for node in ast.walk(tree):
        targets = (node.targets if isinstance(node, ast.Assign) else
                   [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and (rel, t.id) in ALLOWED for t in targets):
            found |= {id(n) for n in ast.walk(node) if isinstance(n, ast.Constant)}
    return found


def _hits():
    hits, allowed_used = [], set()
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_bytes())
        docs, allowed = _docstrings(tree), _allowed_ids(tree, rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                for name, pattern in PATTERNS.items():
                    if pattern.search(node.value):
                        if id(node) in allowed:
                            allowed_used |= {k for k in ALLOWED if k[0] == rel}
                        else:
                            hits.append((rel, node.lineno, name, node.value.strip()[:80]))
    return hits, allowed_used


def test_no_user_facing_string_carries_an_internal_id(examined):
    hits, _ = _hits()
    examined(sum(1 for _ in SRC.rglob("*.py")), "source files read")
    assert not hits, "\n".join(f"{r}:{n} {name}: {text!r}" for r, n, name, text in hits)


def test_each_allowance_still_holds_an_id():
    _, used = _hits()
    assert used == set(ALLOWED), f"allowances that no longer hold an id: {sorted(set(ALLOWED) - used)}"


def test_the_patterns_find_what_they_name():
    planted = {"ruling id": "R-2099-01-01zz", "short ruling id": "see 29zz", "work order": "WO-C99",
               "note id": "N-C099", "to_core / from_core": "from_core", "core as an agent": "core ruled it",
               "pod": "the pod", "a ruling by number": "ruling 99z"}
    for name, text in planted.items():
        assert PATTERNS[name].search(text), name
    assert not PATTERNS["short ruling id"].search("padding:28px 20px"), "a CSS length is not an id"


def test_no_text_file_the_package_ships_carries_an_internal_id(examined):
    """The package's own text files (its notes, lock, licences, the demo's runs) ship in the wheel."""
    files = [p for p in SRC.rglob("*") if p.is_file() and p.suffix in (".md", ".txt", ".lock", ".json", ".css", ".html")]
    examined(len(files), "text files the package ships")
    hits = [(p.relative_to(SRC).as_posix(), i, name) for p in files
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
            for name, pattern in PATTERNS.items() if pattern.search(line)]
    assert not hits, hits


def test_the_project_file_carries_no_internal_id(examined):
    """pyproject.toml ships in the source distribution, comments and all."""
    lines = (SRC.parent.parent / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    examined(len(lines), "lines of pyproject.toml")
    hits = [(i, name, line.strip()[:80]) for i, line in enumerate(lines, 1)
            for name, pattern in PATTERNS.items() if pattern.search(line)]
    assert not hits, hits
