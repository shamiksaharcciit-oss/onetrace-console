"""Shipped code cites no document a reader cannot open.

Every file the package ships (`src/onetrace_console/`) says each rule in words. It names no document the public
tree does not hold, cites no section of one, and gives no review's label or name for who asked for a rule. The
documents it may name are public: the operator guide, the incident rules, `docs/store_read.md`, the fonts' notes,
onedoor's fixture provenance, onetrace's own format documents and onedoor's `docs/decision-ref.md`, named as
theirs, and the RFCs, by section.

The one file read as it is: onetrace's model-call schema, copied byte for byte from onetrace's own sdist and held
there by its digest; its words are onetrace's.

The forms looked for are built from parts, so this file names none of them whole.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.export_tree import is_public_export

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"

#: onetrace's own schema, byte for byte (its digest is held by `test_model_call.py`).
AS_RECEIVED = {"_received/model_call_record.schema.json"}

#: (what it is, the pattern). Each names a document the public tree does not hold, or a review by its label.
FORMS = [
    ("the store and console design document", "(?i)design" + r"[\s-]+" + "note"),
    ("the design gaps list", "DESIGN" + "_GAPS"),
    ("the pins document", r"\bPINS" + r"\.md"),
    ("the backlog", r"\bBACKLOG" + r"\.md"),
    ("the backlog's notes file", "backlog" + "_run_index"),
    ("the sign-in design document", "signin-" + "and-roles"),
    ("the neighbours design document", r"docs/neighbours" + r"\.md"),
    ("the viewer's and the other internal specifications", r"(?i)\bspecification"),
    ("the skin note", "(?i)skin " + "note"),
    ("the skin note's file, which left the package", "CONSOLE_" + "SKIN_v1" + r"\.md|skin" + r"\.SHA256"),
    ("a review, by name or label", r"(?i)\breview(?:s|ed|er)?\b"),
    ("a brief", r"(?i)\bbrief(?:s)?\b"),
    ("a section sign, but after an RFC's number", r"(?<!\d )" + "§"),
    ("a document's words, as specified", r"(?i)\bas specified\b|\bspecified (?:words|ones|definition|shape)\b"),
    ("the earlier shared tokens' document", r"(?i)\boneview " + "spec"),
    ("a token block's document", r"(?i)\bthe spec could not\b"),
    ("the archive of sealed sources", r"(?i)archive of sealed|archived text|sealed (?:source|note)s?\b"),
    ("the repository's private tree", r"(?i)private tree"),
]


def _shipped() -> list[tuple[str, int, str]]:
    lines = []
    for p in sorted(SRC.rglob("*")):
        rel = p.relative_to(SRC).as_posix()
        if not p.is_file() or "__pycache__" in p.parts or rel in AS_RECEIVED:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines += [(rel, n, line) for n, line in enumerate(text.splitlines(), 1)]
    return lines


SHIPPED = _shipped()


@pytest.mark.parametrize("what, pattern", FORMS, ids=[f[0] for f in FORMS])
def test_shipped_code_names_no_document_a_reader_cannot_open(what, pattern, examined):
    rx = re.compile(pattern)
    found = [f"{rel}:{n}" for rel, n, line in SHIPPED if rx.search(line)]
    assert not found, f"{what}: {found}"
    examined(len(SHIPPED), "shipped lines")


def test_a_section_sign_stands_only_after_an_rfc_s_number(examined):
    rx = re.compile(r"RFC \d+ " + "§")
    signs = [(rel, n, line) for rel, n, line in SHIPPED if "§" in line]
    assert all(rx.search(line) for _rel, _n, line in signs), [f"{r}:{n}" for r, n, line in signs if not rx.search(line)]
    examined(len(signs), "section signs, each an RFC's")


def test_the_verifier_s_install_message_says_how_in_the_guide_s_words_and_names_no_file(monkeypatch, examined):
    import importlib.util

    from onetrace_console import checks

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    with pytest.raises(checks.CheckRunnerError) as raised:
        checks.shipped_verifier()
    said = str(raised.value)
    assert "pip install --require-hashes" in said and "onetrace-verify" in said
    assert not re.search(r"\b[\w./-]+\.(?:md|lock|txt)\b", said), said
    examined(1, "the message")


def test_the_limit_sentence_s_refusal_says_what_is_refused_and_why(monkeypatch, examined):
    import onetrace_console.viewer.sentences as S
    from onetrace_console import render

    for name in ("FIXED", "TABLE", "RULED", "LABELS"):
        source = getattr(S, name, None)
        if isinstance(source, dict) and "case.limit" in source:
            monkeypatch.setitem(source, "case.limit", None)
            monkeypatch.delitem(source, "case.limit")
    with pytest.raises(RuntimeError) as raised:
        render._limit_sentence()
    said = str(raised.value)
    assert "§" not in said and "every run page" in said and "Refusing" in said
    examined(1, "the message")


def test_the_sentence_tables_header_says_what_the_entries_are(examined):
    """Each entry of the settled register carries, beside its sentence, what its words are for; the header says so,
    and says nothing of a document the entries do not name."""
    import onetrace_console.viewer.sentences as S

    header = re.sub(r"\s+", " ", S.__doc__ or "")
    assert "sealed document" not in header
    assert "Each carries, beside its sentence, what its words are for" in header
    examined(1, "the header")


#: The tests and tools the export ships hold to the same rule: each says its rule in words and names no document the
#: public tree does not hold. Read in this repository, the files the export writes, as its tool says; an export holds
#: the same files, but neither the tool nor the allowances for reads it leaves out, so there the check skips. Left out: this file, which spells the forms; the checks that plant
#: internal ids and citations to show they are refused; and recorded files kept as they came (onetrace's
#: specification addendum, as its fixture, and Entra ID's provisioning request).
SPELLS_THE_FORMS = {
    "tests/test_shipped_citations.py",
    "tests/test_no_ids_in_code_comments.py",
    "tests/test_no_internal_ids.py",
    "tests/test_user_facing_strings.py",
}
AS_RECORDED = ("tests/fixtures/spec/", "tests/scim_entra/")


def _exported_tests_and_tools() -> list[tuple[str, int, str]]:
    try:
        from tools.export_public import plan
    except ImportError:  # an export, where the check skips (is_public_export)
        pytest.skip("an export holds neither the export tool nor its read allowances")
    repo = SRC.parent.parent
    names = sorted(src for src in plan().values() if src.startswith(("tests/", "tools/")))
    lines = []
    for rel in names:
        if rel in SPELLS_THE_FORMS or rel.startswith(AS_RECORDED):
            continue
        try:
            text = (repo / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        lines += [(rel, n, line) for n, line in enumerate(text.splitlines(), 1)]
    return lines


def _without_allowed_reads(rel: str, line: str) -> str:
    """`line` less the paths of files the export leaves out that `rel` may read where they are there and skips
    without (`tests/test_export_reads.py`'s allowances): a read the export's own check must still see, so the
    path stays whole. Each such path is named once, in the line that reads it."""
    from tests.test_export_reads import ALLOWED

    for module, path in ALLOWED:
        if module == rel:
            line = line.replace(f'"{path.rsplit("/", 1)[-1]}"', '""')
    return line


@pytest.mark.skipif(is_public_export(), reason="an export holds neither the export tool nor its read allowances")
@pytest.mark.parametrize("what, pattern", FORMS, ids=[f[0] for f in FORMS])
def test_the_exported_tests_and_tools_name_no_document_a_reader_cannot_open(what, pattern, examined):
    lines = _exported_tests_and_tools()
    rx = re.compile(pattern)
    found = [f"{rel}:{n}" for rel, n, line in lines if rx.search(_without_allowed_reads(rel, line))]
    assert not found, f"{what}: {len(found)} lines: {found}"
    examined(len(lines), "lines of the exported tests and tools")
