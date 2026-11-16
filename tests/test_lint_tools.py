"""The lint, format and type tools: ruff and mypy, pinned by hash in the test requirements, and configured in
pyproject.toml with the byte-rewriting exclusions every tool here is given (pyproject.toml's E10 layer 2), a rule set
named rule by rule rather than a ruff release's default, and mypy over the console's package.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
#: The tools and the versions the sweep was made with.
TOOLS = {"ruff": "0.17.4", "mypy": "2.4.1"}
#: The folders no byte-rewriting tool may touch: received bundles, the stored store, and the test fixtures' runs.
NEVER_REWRITTEN = ("tests/fixtures", "store", "src/onetrace_console/_received")


def _pyproject() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def test_ruff_and_mypy_are_pinned_by_hash(examined):
    text = (REPO / "requirements-test.txt").read_text(encoding="utf-8")
    wanted = (REPO / "requirements-test.in").read_text(encoding="utf-8").split()
    examined(len(TOOLS), "tools pinned")
    for name, version in TOOLS.items():
        assert f"{name}=={version}" in wanted, name
        m = re.search(
            rf"^{re.escape(name)}=={re.escape(version)}\b[^\n]*\\\n((?:\s+--hash=sha256:[0-9a-f]{{64}}.*\n)+)",
            text,
            re.M,
        )
        assert m and m.group(1).count("--hash=sha256:") >= 1, name


def test_every_byte_rewriting_tool_is_given_the_exclusions(examined):
    cfg = _pyproject()["tool"]
    ruff = cfg["ruff"]["extend-exclude"]
    mypy = cfg["mypy"]["exclude"]
    examined(len(NEVER_REWRITTEN) * 2, "exclusions, ruff's and mypy's")
    for folder in NEVER_REWRITTEN:
        assert folder in ruff, folder
        assert any(re.search(pattern, folder + "/x.py") for pattern in mypy), folder


def test_the_rules_are_named_not_a_release_s_default(examined):
    lint = _pyproject()["tool"]["ruff"]["lint"]
    examined(1, "ruff's rule set")
    assert lint["select"], "an empty select would lint by the installed release's default set"
    assert all(re.fullmatch(r"[A-Z]+[0-9]*", r) for r in lint["select"] + lint.get("ignore", []))


def test_mypy_reads_the_console_s_package(examined):
    mypy = _pyproject()["tool"]["mypy"]
    examined(1, "mypy's files")
    assert mypy["files"] == ["src/onetrace_console"]
    assert mypy["python_version"] == "3.12"


#: Files a standing test holds byte for byte to where they came from: the viewer folder (its PROVENANCE.md), the
#: SDK's test time-stamp authority, and the reference demo's pipeline with the demo store's copy of it. No
#: rewriting tool touches them, and a type finding in them is fixed where they come from.
BYTE_FOR_BYTE = (
    "src/onetrace_console/viewer",
    "tests/rfc3161_test_tsa.py",
    "examples/reference-demo/demo.py",
    "src/onetrace_console/demo_store/reference_pipeline.py",
)


def test_the_byte_for_byte_copies_are_left_as_they_are(examined):
    cfg = _pyproject()["tool"]
    ruff = cfg["ruff"]["extend-exclude"]
    held = {m for o in cfg["mypy"].get("overrides", []) if o.get("ignore_errors") for m in o["module"]}
    examined(len(BYTE_FOR_BYTE), "byte-for-byte copies")
    for path in BYTE_FOR_BYTE:
        assert path in ruff, path
        assert (REPO / path).exists(), path
    assert {"onetrace_console.viewer.*", "onetrace_console.demo_store.reference_pipeline"} <= held


def test_the_format_only_commit_is_ignored_by_blame(examined):
    """`.git-blame-ignore-revs` lists the commit that ran `ruff format`, so `git blame` reads past it (with
    `git config blame.ignoreRevsFile .git-blame-ignore-revs`); each line a full sha, under a comment naming it. The
    public export has a history of its own and leaves the file out: there the test skips."""
    import pytest

    from tests.export_tree import is_public_export

    if is_public_export():
        pytest.skip("the public export leaves .git-blame-ignore-revs out: its history is its own")
    text = (REPO / ".git-blame-ignore-revs").read_text(encoding="utf-8")
    shas = [line for line in text.splitlines() if line and not line.startswith("#")]
    examined(len(shas), "commits ignored by blame")
    #: One commit, by its full id, which the blame tool reads; this file names it by its shape only.
    assert len(shas) == 1 and re.fullmatch(r"[0-9a-f]{40}", shas[0]), shas
    assert "ruff format" in text
