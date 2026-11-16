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
    "dated id": r"(?i)\bR-20\d\d-\d\d-\d\d",
    #: Two digits then two letters, never a unit ("20px", "10ms") and never part of a hex value: not after "#",
    #: "0x", a word character, ".", "-" or an ellipsis, nor before a word character, "-" or an ellipsis.
    "short id": (
        r"(?<![#…\w.-])(?<!\.\.\.)\d{2}(?!(?:px|ms|em|pt|kb|mb|gb|th|st|nd|rd|hz|ch|vw|vh|dp)\b)[a-z]{2}\b"
        r"(?![…\w-])(?!\.\.\.)"
    ),
    "work order": r"(?i)\bWO-C\d+",
    "note id": r"(?i)\bN-C0\d\d",
    "a notes folder": r"\b(?:to|from)_core\b",
    "the review party as an agent": r"\bcore(?:'s)?\s+(?:rul|said|asked|accept|decid|gave|wants|confirm|word|review)",
    "pod": r"\bpods?\b",
    "a ruling by number": r"(?i)\bruling \d+[a-z]*\b",
    "a question by number": r"(?i)\b[Qq]uestions?\s+\d+",
    #: A round of work named by its label: the word, then a letter (and a digit) or a number, as a name.
    "an iteration label": r"(?i)\brounds?[- ](?:[a-z][0-9]?|[0-9]+)\b|\bround[0-9]+\b",
    #: A review's finding named by its number.
    "a finding by number": r"(?i)\bfindings? #?[0-9]+\b",
}
PATTERNS = {name: re.compile(p) for name, p in INTERNAL.items()}
#: (file relative to src/onetrace_console/, the name assigned) -> why its strings may hold an id.
ALLOWED: dict[tuple[str, str], str] = {}


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                found.add(id(first.value))
    return found


def _allowed_ids(tree: ast.AST, rel: str) -> set[int]:
    """The string constants inside an allowed assignment of this file."""
    found = set()
    for node in ast.walk(tree):
        targets = (
            node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
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
    planted = {
        "dated id": "R-2099-01-01zz",
        "short id": "see 29zz",
        "work order": "WO-C99",
        "note id": "N-C099",
        "a notes folder": "from_" + "co" + "re",
        "the review party as an agent": "co" + "re ruled it",
        "pod": "the pod",
        "a ruling by number": "ruling 99z",
        "a question by number": "see question 99",
    }
    for name, text in planted.items():
        assert PATTERNS[name].search(text), name
    assert not PATTERNS["short id"].search("padding:28px 20px"), "a CSS length is not an id"
    assert not PATTERNS["short id"].search("within 10ms"), "a unit is not an id"
    for hexed in ("sha256 57e5f8e3…12ab", "12ab…3fb3", "color:#12ab", "0x12ab", "id 3f12ab", "b-12ab-c", "x...12ab"):
        assert not PATTERNS["short id"].search(hexed), f"{hexed}: part of a hex value is not an id"
    for text in ("(29zz)", "see 10ab.", "as 31zz said"):
        assert PATTERNS["short id"].search(text), f"{text}: an id, hex letters or not"
    assert not PATTERNS["a question by number"].search("a question of 5"), "only a question followed by its number"
    #: Written any case: each put together from two parts, so that this file's own lines hold none of them.
    assert PATTERNS["work order"].search("issuer: example-wo" + "-c9"), "a work order in lower case"
    assert PATTERNS["a ruling by number"].search("Ruling" + " 27h item 3"), "a ruling with a capital"
    assert PATTERNS["a question by number"].search("QUESTION" + " 12"), "a question in capitals"
    #: Each put together from two parts, so that this file's own lines hold none of them.
    for label in (
        "rou" + "nd g",
        "Rou" + "nd g2, part 9",
        "rou" + "nd 4",
        "the rou" + "nd-4 review",
        "rou" + "nds h and h2",
    ):
        assert PATTERNS["an iteration label"].search(label), label
    assert PATTERNS["a finding by number"].search("its find" + "ing 8") and PATTERNS["a finding by number"].search(
        "Review Find" + "ing 3"
    )
    assert not PATTERNS["a finding by number"].search("a finding that"), "a finding not named by its number"
    for words in ("rounds to 1.000", "round(took)", "around 40 minutes", "a round trip", "each round takes"):
        assert not PATTERNS["an iteration label"].search(words), words


def test_no_text_file_the_package_ships_carries_an_internal_id(examined):
    """The package's own text files (its notes, lock, licences, the demo's runs) ship in the wheel."""
    files = [
        p for p in SRC.rglob("*") if p.is_file() and p.suffix in (".md", ".txt", ".lock", ".json", ".css", ".html")
    ]
    examined(len(files), "text files the package ships")
    hits = [
        (p.relative_to(SRC).as_posix(), i, name)
        for p in files
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
        for name, pattern in PATTERNS.items()
        if pattern.search(line)
    ]
    assert not hits, hits


def test_the_project_file_carries_no_internal_id(examined):
    """pyproject.toml ships in the source distribution, comments and all."""
    lines = (SRC.parent.parent / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    examined(len(lines), "lines of pyproject.toml")
    hits = [
        (i, name, line.strip()[:80])
        for i, line in enumerate(lines, 1)
        for name, pattern in PATTERNS.items()
        if pattern.search(line)
    ]
    assert not hits, hits


#: Every file the source distribution ships (`MANIFEST.in` and the build's own rules): the package, the tests, the
#: build backend and the project's own files. Comments and docstrings count here: the sdist ships them.
SHIPPED_ROOT = SRC.parent.parent
SHIPPED = ("src", "tests", "tools/build_backend")
SHIPPED_FILES = ("LICENSE", "README.md", "PYPI_DESCRIPTION.md", "pyproject.toml", "setup.cfg", "MANIFEST.in")
SKIPPED = ("__pycache__", ".pytest-basetemp", ".egg-info")
#: (file, the exact text a hit must lie inside): a test's planted examples, or a test's own patterns. Each must
#: still hold a hit, so none outlives its reason.
PLANTED: dict[str, tuple[str, ...]] = {
    "tests/test_user_facing_strings.py": (
        #: Each put together from two parts, as below, so that these lines hold none of them.
        *(f'"{a}{b}"' for a, b in (("R-20", "99-01-01zz"), ("see 2", "9zz"), ("WO-C", "99"), ("N-C0", "99"))),
        *(f'"{a}{b}"' for a, b in (("the p", "od"), ("rul", "ing 99z"))),
        *(f'"{a}{b}"' for a, b in (("see ques", "tion 99"), ("(2", "9zz)"), ("see 1", "0ab."), ("as 3", "1zz said"))),
        '"po' + 'd": r"\\bpo' + 'ds?\\b"',
        '"po' + 'd": "the po' + 'd"',
    ),
    #: Each put together from two parts, so that this file's own lines hold none of them.
    "tests/test_export_static.py": ("R-20" + "99-01-01zz", "<span>WO-C" + "99</span>"),
    "tests/test_no_internal_ids.py": (
        '"R-20' + '26-09-28h", "(2' + '9di §2)", "WO-C' + '18 item 12"',
        '"<!-- R-20' + '26-09-28h -->"',
    ),
    "tests/test_ux_screens.py": ('"po' + 'd": re.compile(r"\\bpo' + 'd\\b")',),
}


def _shipped_hits():
    hits, used = [], set()
    paths = [SHIPPED_ROOT / f for f in SHIPPED_FILES if (SHIPPED_ROOT / f).is_file()]
    paths += [p for d in SHIPPED for p in sorted((SHIPPED_ROOT / d).rglob("*")) if p.is_file()]
    read = 0
    for path in paths:
        rel = path.relative_to(SHIPPED_ROOT).as_posix()
        if any(part in rel for part in SKIPPED):
            continue
        raw = path.read_bytes()
        if b"\0" in raw[:8192]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        read += 1
        for no, line in enumerate(text.splitlines(), 1):
            for name, pattern in PATTERNS.items():
                for m in pattern.finditer(line):
                    inside = [
                        t
                        for t in PLANTED.get(rel, ())
                        for at in [i for i in range(len(line)) if line.startswith(t, i)]
                        if at <= m.start() and m.end() <= at + len(t)
                    ]
                    if inside:
                        used |= {(rel, t) for t in inside}
                    else:
                        hits.append((rel, no, name, m.group()))
    return hits, used, read


def test_no_file_the_source_distribution_ships_carries_an_internal_id(examined):
    """The tests' and the code's comments and docstrings too, and every fixture: each ships in the sdist."""
    hits, _used, read = _shipped_hits()
    examined(read, "text files the source distribution ships")
    assert not hits, "\n".join(f"{r}:{n} {name}: {m!r}" for r, n, name, m in hits)


def test_each_planted_example_is_still_planted():
    _hits, used, _read = _shipped_hits()
    listed = {(f, t) for f, ts in PLANTED.items() for t in ts}
    assert used == listed, f"planted examples no longer found: {sorted(listed - used)}"


#: A round of work in a file's name: `test_round4_fixes.py`, `test_in_place_g2.py`.
LABELLED_NAME = re.compile(r"(?i)round[-_]?(?:[0-9]+|[a-z][0-9]?)(?=[._-])|_g[0-9]+(?=[._])")


def test_no_file_the_source_distribution_ships_is_named_by_a_round_of_work(examined):
    paths = [SHIPPED_ROOT / f for f in SHIPPED_FILES if (SHIPPED_ROOT / f).is_file()]
    paths += [p for d in SHIPPED for p in sorted((SHIPPED_ROOT / d).rglob("*")) if p.is_file()]
    names = [p.relative_to(SHIPPED_ROOT).as_posix() for p in paths]
    names = [n for n in names if not any(part in n for part in SKIPPED)]
    examined(len(names), "file names the source distribution ships")
    assert LABELLED_NAME.search("tests/test_" + "round4_fixes.py") and LABELLED_NAME.search(
        "tests/test_in_place_" + "g2.py"
    )
    assert [n for n in names if LABELLED_NAME.search(n)] == []
