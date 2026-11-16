"""The code comments and docstrings of `viewer/` and `ingest.py` name no internal document: no decision's or
specification's number (three digits with a section sign or an item's number, a memo's number, a bench's record, a
requirement's id), and no "as ruled" wording. A
section of a document named in words ("the viewer's specification, §0") is not a number of that kind. They say
what the code does and why in their own words. Read by Python's tokenizer: `#` comments, and the strings that
stand as statements (docstrings), less any name in backticks (the code's own identifiers). Strings the code uses
as values are not read here.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
FILES = sorted((SRC / "viewer").glob("*.py")) + [SRC / "ingest.py"]
#: A document's number and section, a memo's, a rule's id, and the wording of a decision.
IDS = re.compile(
    r"\b(?:C?0\d\d(?:\s*§|\s+items?\s+\d|\b(?=['’]s\b))|C0\d\d\b|[XR]-C?\d+\b|REG-\d+|Bench"
    r" Record|"
    r"Response 0\d\d|29[a-z]{1,2}\b|items? \d+\b|as ruled|rul(?:ed|ings?)|already-ruled)|"
    r"(?<![\d.,:])\b0[1-6]\d\b(?![\d.,:])",
    re.I,
)


def _docstring_lines(tree) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            out |= set(range(node.lineno, node.end_lineno + 1))
    return out


def found(path: Path, text: str | None = None) -> list[str]:
    text = path.read_text(encoding="utf-8") if text is None else text
    docs = _docstring_lines(ast.parse(text))
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        is_doc = tok.type == tokenize.STRING and tok.start[0] in docs
        if tok.type == tokenize.COMMENT or is_doc:
            #: A name in backticks is the code's own identifier (`RULED`), not a citation.
            said = re.sub(r"`[^`\n]*`", "", tok.string)
            out += [f"{path.name}:{tok.start[0]}: {m.group(0)}" for m in IDS.finditer(said)]
    return out


def test_no_comment_or_docstring_names_an_internal_document(examined):
    examined(len(FILES), "source files")
    assert [hit for f in FILES for hit in found(f)] == []


@pytest.mark.parametrize(
    "planted",
    [
        #: Built from parts, so this file names none of them whole.
        "# 0" + "19 §4: the anchor rows",
        "#: as ruled in C0" + "36 item 2",
        "#: item 1's case",
        "# as 029 fixes it",
        "# as 29x said",
        '"""Bench' + ' Record 047 ruled a third field."""',
        "# (X" + "-" + "6) it raises",
    ],
)
def test_sabotage_a_planted_id_is_named(planted, examined):
    examined(1, "planted source")
    assert found(Path("planted.py"), f"x = 1\n{planted}\n")


@pytest.mark.parametrize(
    "kept",
    [
        'x = "0' + '19 §4"',
        "# the spec's own sentence",
        "# a gap of 0.3 s",
        "# runs 01 to 12",
        "# 20,000 rows",
        "#: see `RULED`",
        "# the specification, §2.1",
        "# onetrace 0.1.2",
    ],
)
def test_values_and_plain_words_are_left_alone(kept, examined):
    examined(1, "source")
    assert found(Path("kept.py"), f"y = 2\n{kept}\n") == []
